"""pedald's HTTP server: ours, and deliberately small.

It is built from `socket`, `threading`, `json` and `hmac` rather than `http.server`. That is no
longer a constraint — the Core host's python3 is the full one (vip's image installs `python3`)
— it is a choice: `BaseHTTPRequestHandler` gives request parsing and none of what this API
needs, so the rules below would be written anyway, and this way they are written once and
tested (devices/common/tests/test_httpd.py) on the one component that faces the LAN. Nothing
here is on the audio path.

The rules come from "Security" and "The upload API" in that document:

* `Authorization: Bearer <token>`, compared with `hmac.compare_digest`, because the reply time
  is the one thing an attacker on the LAN can measure.
* `Content-Length` frames every body (chunked bodies are refused). A declared body over
  `max_body` is 413 and is never read for the request.
* 401 for a missing or wrong token, 404 for a path nobody registered, 405 for a registered
  path asked with the wrong method, 400 for a request that is not HTTP/1.1, 411 when a
  PUT or POST does not say how long its body is, 500 when a handler raises. Three failed
  authentications on one connection and the connection is closed.
* One thread per connection is enough for a handful of clients; a handler that raises is that
  handler's bug, and the server answers 500 and carries on.

Routes are a `dict` of path to `callable(Request) -> (status, body)`, as the frozen interface
promises. A path key alone answers every method this API uses (GET, HEAD, PUT, POST); a key
may pin its method instead (`"GET /status"`), and then the same path asked with another method
is 405 with an `Allow` header. A path nobody registered is 404 whatever the method, so 404
always wins over 405. A path ending in `/*` (`"/library/rigs/*"`) is a prefix: it answers every
path below it that no exact key claims, and the longest prefix wins. The handler reads the rest of
the path from `request.path`.

`stop()` closes the listener, shuts down every live connection and returns; a handler that never
returns is left on its daemon thread rather than holding the caller there.
"""

import hmac
import json
import socket
import sys
import threading
import time

# The request line and headers together; past this the peer is not talking to this server.
MAX_HEAD = 16 << 10
# A connection that goes quiet for this long is closed rather than held open by a thread.
READ_TIMEOUT = 30.0
# How long a closing reply waits for the peer's pending bytes before the socket is closed.
DRAIN_TIMEOUT = 0.25
# How often the accepter looks at whether it should stop.
LISTEN_TIMEOUT = 0.2
# How long stop() waits for one connection thread.
JOIN_TIMEOUT = 2.0
# Bad tokens on one connection before it is closed (Security, docs/pedal-service.md).
AUTH_FAILURES_MAX = 3
# The methods this API uses. A route registered by path alone answers these.
API_METHODS = ("GET", "HEAD", "PUT", "POST", "DELETE")
# Methods whose request is expected to carry a body, and so to frame one.
_BODY_METHODS = ("PUT", "POST", "PATCH")

_REASONS = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    411: "Length Required",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Content",
    500: "Internal Server Error",
    501: "Not Implemented",
    503: "Service Unavailable",
    507: "Insufficient Storage",
}


class Request:
    """One parsed request, and nothing else: no socket, no server, no filesystem.

    `path` is the target without its query; `query` holds the decoded parameters; `headers`
    is keyed in lower case; `body` is the framed bytes, empty when the request declared none.
    """

    def __init__(self, method, path, query, headers, body):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body


class Server:
    """The service's listener: bind, serve on a thread, stop when told to."""

    def __init__(self, host, port, token, routes, *, log=None, max_body=1 << 20):
        self._host = host
        self._requested_port = port
        self._token = token
        self._routes = dict(routes)
        self._log = log or _stderr_log
        self._max_body = max_body
        self._bound_port = port
        self._listener = None
        self._accept_thread = None
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._connections = set()
        self._threads = set()
        self._plain = {}
        self._pinned = {}
        self._pinned_methods = {}
        for key, handler in self._routes.items():
            method, path = _route_key(key)
            if method is None:
                self._plain[path] = handler
            else:
                self._pinned[(path, method)] = handler
                self._pinned_methods.setdefault(path, set()).add(method)

    @property
    def port(self):
        """The port actually bound: the useful answer when the server was built with port 0."""
        return self._bound_port

    def start(self):
        """Bind and serve on a background thread, returning as soon as it is listening."""
        if self._accept_thread is not None:
            return
        self._stopping.clear()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self._host, self._requested_port))
            listener.listen(16)
            listener.settimeout(LISTEN_TIMEOUT)
        except OSError:
            listener.close()
            raise
        self._listener = listener
        self._bound_port = listener.getsockname()[1]
        self._accept_thread = threading.Thread(
            target=self._accept_loop, args=(listener,), name="pedald-http", daemon=True
        )
        self._accept_thread.start()
        self._log(f"listening on {self._host}:{self._bound_port}")

    def stop(self):
        """Stop listening, shut every live connection down so its handler returns, and come back.

        Safe to call twice, safe before `start()`, and bounded: the joins have a timeout, so a
        handler that will not return cannot hold the caller here. The handlers close their own
        connections (see `_shutdown`), so what this owns is ending them, not freeing them.
        """
        self._stopping.set()
        listener, self._listener = self._listener, None
        if listener is not None:
            _close(listener)
        with self._lock:
            connections = list(self._connections)
            threads = list(self._threads)
        if self._accept_thread is not None:
            threads.append(self._accept_thread)
        current = threading.current_thread()
        for conn in connections:
            _shutdown(conn)
        for thread in threads:
            if thread is not current:
                thread.join(JOIN_TIMEOUT)
        self._accept_thread = None

    def _accept_loop(self, listener):
        while not self._stopping.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return                          # the listener was closed: stop()
            if self._stopping.is_set():
                _close(conn)
                return
            try:
                conn.settimeout(READ_TIMEOUT)
            except OSError:
                _close(conn)
                continue
            thread = threading.Thread(
                target=self._serve, args=(conn,), name="pedald-http-conn", daemon=True
            )
            with self._lock:
                self._connections.add(conn)
                self._threads.add(thread)
            thread.start()

    def _serve(self, conn):
        """One connection: as many requests as it keeps asking for, then one close."""
        reader = _Reader(conn)
        peer = _peer_text(conn)
        failures = 0
        try:
            while not self._stopping.is_set():
                try:
                    head = reader.read_head()
                    if head is None:
                        return
                    line, headers = head
                    method, target, version = _parse_request_line(line)
                    path, query = _split_target(target)
                    keep = _keep_alive(version, headers)
                    # A request we do not read the body of cannot be followed by another on
                    # this connection: its bytes would be parsed as the next request line.
                    reusable = keep and not _declares_body(headers)
                except _Rejected as e:
                    self._log(f"rejected request from {peer}: {e.message}")
                    self._refuse(conn, e.status, e.message, False)
                    return
                except OSError:
                    return
                if not self._authorised(headers):
                    failures += 1
                    self._log(
                        f"unauthorised {method} {path} from {peer} "
                        f"({failures} of {AUTH_FAILURES_MAX} on this connection)"
                    )
                    if failures >= AUTH_FAILURES_MAX:
                        self._refuse(conn, 401, "unauthorized", False)
                        return
                    if self._refuse(conn, 401, "unauthorized", reusable):
                        return
                    continue
                handler, allowed = self._resolve(method, path)
                if handler is None:
                    if allowed is None:
                        if self._refuse(conn, 404, "not found", reusable,
                                        head_only=method == "HEAD"):
                            return
                    else:
                        if self._refuse(conn, 405, "method not allowed", reusable,
                                        allow=allowed, head_only=method == "HEAD"):
                            return
                    continue
                try:
                    body = self._read_body(reader, method, headers)
                except _Rejected as e:
                    self._log(f"{method} {path} from {peer}: {e.message}")
                    self._refuse(conn, e.status, e.message, False)
                    return
                request = Request(method, path, query, headers, body)
                try:
                    status, reply = handler(request)
                except Exception as e:          # a handler's bug is a 500, not the server's end
                    self._log(f"{method} {path}: handler raised {e!r}")
                    status, reply = 500, {"error": "internal error"}
                self._reply(conn, status, reply, close=not keep, head_only=method == "HEAD")
                if not keep:
                    return
        finally:
            with self._lock:
                self._connections.discard(conn)
                self._threads.discard(threading.current_thread())
            _close(conn)

    def _resolve(self, method, path):
        """(handler, None) for a request to serve, or (None, allowed methods) for a 405.

        (None, None) means the path is not registered: that is a 404 whatever the method.
        """
        if path not in self._plain and path not in self._pinned_methods:
            path = self._prefix_for(path) or path
        handler = self._pinned.get((path, method))
        if handler is None and method == "HEAD":
            handler = self._pinned.get((path, "GET"))    # a GET route answers HEAD, without a body
        if handler is not None:
            return handler, None
        allowed = set(self._pinned_methods.get(path, ()))
        if path in self._plain:
            allowed.update(API_METHODS)
        if not allowed:
            return None, None
        if method in allowed or (method == "HEAD" and "GET" in allowed):
            return self._plain.get(path), None
        return None, allowed

    def _prefix_for(self, path):
        """The `/*` key that answers `path`, as that key, or None: the longest prefix wins."""
        best = None
        for key in list(self._plain) + list(self._pinned_methods):
            if key.endswith("/*") and path.startswith(key[:-1]) and len(path) > len(key) - 1:
                if best is None or len(key) > len(best):
                    best = key
        return best

    def _authorised(self, headers):
        """Whether the bearer token matches, in a time that does not depend on the guess."""
        if not self._token:
            # An empty token is a configuration mistake, not a password that matches anything.
            return False
        header = headers.get("authorization")
        if header is None:
            return False
        scheme, _, presented = header.partition(" ")
        if scheme.lower() != "bearer":
            return False
        presented = presented.strip()
        if not presented:
            return False
        # No early exit: the reply time is what an attacker on the LAN can measure.
        return hmac.compare_digest(presented, self._token)

    def _read_body(self, reader, method, headers):
        """The framed body, or _Rejected(411/400/413) before a byte of it is read."""
        if "transfer-encoding" in headers:
            raise _Rejected(400, "chunked bodies are not supported")
        declared = headers.get("content-length")
        if declared is None:
            if method in _BODY_METHODS:
                raise _Rejected(411, "Content-Length required")
            return b""
        text = declared.strip()
        # isascii() as well as isdigit(): int() accepts digits from other scripts, and this
        # header decides where one request ends and the next begins.
        if not text.isascii() or not text.isdigit():
            raise _Rejected(400, "bad Content-Length")
        length = int(text)
        if length > self._max_body:
            raise _Rejected(413, "body too large")
        body = reader.read_exactly(length)
        if body is None:
            raise _Rejected(400, "body ended early")
        return body

    def _refuse(self, conn, status, message, reusable, *, allow=None, head_only=False):
        """Write an error reply; return True when the connection must now close.

        A closing reply is followed by a short drain, so the peer's unread bytes cannot turn
        the close into a reset that discards the reply.
        """
        close = not reusable
        self._reply(conn, status, {"error": message}, close=close, allow=allow,
                    head_only=head_only)
        if close:
            self._drain(conn)
        return close

    def _reply(self, conn, status, body, *, close=False, allow=None, head_only=False):
        """Write one JSON reply. A body JSON cannot carry becomes a 500, never a lost reply."""
        try:
            payload = json.dumps(body).encode("utf-8")
        except (TypeError, ValueError) as e:
            self._log(f"reply not serialisable: {e!r}")
            status, payload = 500, json.dumps({"error": "internal error"}).encode("utf-8")
        lines = [
            f"HTTP/1.1 {status} {_REASONS.get(status, 'Status')}",
            "Content-Type: application/json",
            f"Content-Length: {len(payload)}",
            "Connection: " + ("close" if close else "keep-alive"),
        ]
        if allow:
            lines.append("Allow: " + ", ".join(sorted(allow)))
        head = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        try:
            conn.sendall(head + (b"" if head_only else payload))
        except OSError as e:
            self._log(f"reply not sent: {e}")

    def _drain(self, conn):
        """Read and discard what the peer has already sent, for a moment.

        Closing a socket with unread data queued makes the kernel send a reset. Reading first
        costs at most DRAIN_TIMEOUT and lets the reply that was just written arrive.
        """
        deadline = time.monotonic() + DRAIN_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                conn.settimeout(remaining)
                if not conn.recv(65536):
                    return
            except OSError:
                return


class _Rejected(Exception):
    """A request to answer with an error, without reading a body it may still have coming."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class _Reader:
    """A connection, plus the bytes read past the request being parsed.

    One recv can hand back the start of a body along with the header block, so what is left
    over lives here: a body is read exactly once, in order, and a Content-Length of 12 bytes
    must not consume the 4096 that arrived with it.
    """

    def __init__(self, conn):
        self._conn = conn
        self._buffer = b""

    def read_head(self):
        """(request line, headers), or None at a clean end of stream.

        Raises _Rejected(400) for a header block that is too large, malformed, or cut short.
        """
        while True:
            end = _head_end(self._buffer)
            if end is not None:
                if end > MAX_HEAD:
                    raise _Rejected(400, "header block too large")
                break
            if len(self._buffer) > MAX_HEAD:
                raise _Rejected(400, "header block too large")
            chunk = self._conn.recv(4096)
            if not chunk:
                if not self._buffer:
                    return None
                raise _Rejected(400, "connection closed before the end of the headers")
            self._buffer += chunk
        raw, self._buffer = self._buffer[:end], self._buffer[end:]
        lines = raw.decode("latin-1").replace("\r\n", "\n").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)                        # a stray CRLF between requests is not a request
        if not lines:
            raise _Rejected(400, "empty request")
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            name, separator, value = line.partition(":")
            if not separator or not name.strip() or name != name.strip():
                raise _Rejected(400, f"malformed header line {line!r}")
            # The first of a repeated header wins: two Content-Lengths are a framing fight,
            # not something to settle in the sender's favour.
            headers.setdefault(name.strip().lower(), value.strip())
        return lines[0], headers

    def read_exactly(self, length):
        """Exactly `length` body bytes, or None if the peer stopped early."""
        while len(self._buffer) < length:
            chunk = self._conn.recv(min(65536, length - len(self._buffer)))
            if not chunk:
                return None
            self._buffer += chunk
        body, self._buffer = self._buffer[:length], self._buffer[length:]
        return body


def _head_end(buffer):
    """Where the header block's blank line ends, or None while it has not arrived."""
    crlf = buffer.find(b"\r\n\r\n")
    lf = buffer.find(b"\n\n")
    ends = [offset + width for offset, width in ((crlf, 4), (lf, 2)) if offset >= 0]
    return min(ends) if ends else None


def _parse_request_line(line):
    """(method, target, version), or _Rejected(400) if the line is not one this server speaks."""
    parts = line.split()
    if len(parts) != 3:
        raise _Rejected(400, "malformed request line")
    method, target, version = parts
    if not method.isascii() or not method.isalpha() or method != method.upper():
        raise _Rejected(400, "bad method")
    if version not in ("HTTP/1.1", "HTTP/1.0"):
        raise _Rejected(400, "unsupported HTTP version")
    if not target.startswith("/"):
        # Origin-form only: this is not a proxy, so an absolute-form target is not ours.
        raise _Rejected(400, "target is not an origin-form path")
    return method, target, version


def _split_target(target):
    """(path, query): the query decoded, since urllib.parse is not on the Core host."""
    path, separator, raw = target.partition("?")
    query = {}
    if separator:
        for pair in raw.split("&"):
            if not pair:
                continue
            name, _, value = pair.partition("=")
            query[_unquote(name)] = _unquote(value)
    return path, query


def _unquote(text):
    """Percent-decoding for names and values; `+` is a space, as in a form."""
    if "%" not in text and "+" not in text:
        return text
    out = bytearray()
    i = 0
    while i < len(text):
        character = text[i]
        if character == "%" and i + 3 <= len(text):
            try:
                out.append(int(text[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend((" " if character == "+" else character).encode("utf-8"))
        i += 1
    return out.decode("utf-8", "replace")


def _keep_alive(version, headers):
    """Whether the connection may be reused: HTTP/1.1 keeps it unless asked to close."""
    connection = headers.get("connection", "").strip().lower()
    if version == "HTTP/1.0":
        return connection == "keep-alive"
    return connection != "close"


def _declares_body(headers):
    """Whether the request says a body is coming, so refusing it means closing the connection."""
    length = headers.get("content-length")
    if length is not None:
        return length.strip() not in ("", "0")
    return "transfer-encoding" in headers


def _route_key(key):
    """(method, path) for a key that pins its method, or (None, path) for a plain one."""
    method, separator, path = key.partition(" ")
    if not separator:
        return None, key
    if not path or not method.isascii() or not method.isalpha():
        raise ValueError(f"route key {key!r} is neither a path nor a method and a path")
    return method.upper(), path


def _peer_text(conn):
    """`address:port` for the log, or "?" if the peer has already gone."""
    try:
        address = conn.getpeername()
    except OSError:
        return "?"
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return str(address)


def _shutdown(conn):
    """Unblock whichever thread is reading this connection. Do not close it here.

    shutdown() makes a blocked recv() return 0, which is what wakes the handler; close() does not,
    and closing a socket another thread is inside recv() on is how a reader ends up waiting on a
    descriptor that has been closed (and possibly reused) underneath it — 2026-10-06: one handler
    thread in twenty runs of test_httpd sat in recv() for the full read timeout after stop() had
    returned. The handler closes its own connection in its `finally`, so the peer still sees EOF
    from this shutdown() and the descriptor is freed a moment later.
    """
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _close(conn):
    try:
        conn.close()
    except OSError:
        pass


def _stderr_log(message):
    print(f"pedald-http: {message}", file=sys.stderr, flush=True)

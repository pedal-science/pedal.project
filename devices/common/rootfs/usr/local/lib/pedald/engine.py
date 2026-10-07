"""engine.py — pedald's client for namchaind's control protocol, over TCP.

The service asks the engine what it is doing, loads a rig by name and asks for a library
rescan; this module is how it asks, and nothing else in pedald sees a socket.  TCP rather
than the Unix socket because a Unix-socket reply is one datagram, about 208 KiB on Linux,
and `engine.assets` or `engine.schema` is near 1 MB once the library is real
(docs/daemon.md, "Two transports"; docs/pedal-service.md).

The wire, and why this is shaped the way it is:

- Every message in either direction is a 4-byte little-endian length prefix followed by one
  JSON object; a reply may be up to 16 MiB.  Bytes arrive split or coalesced, so a message
  is reassembled from its prefix and never taken to be one `recv` (docs/daemon.md, "The
  wire, byte for byte").
- A request carries an `id`, which the daemon echoes.  This client has one request in
  flight at a time and refuses a reply that carries any other id.
- On TCP nothing but `engine.hello` is answered before the token has been presented, so a
  connection is authenticated as it is opened and a reconnect presents the token again.  A
  rig change outliving the engine's idle close is therefore a detail, not an outage.
- A refusal (`ok: false`) is the engine's answer rather than a transport failure, and is
  never retried; a connection that is missing, closed or broken is replaced once.

Standard library only, and only what `python3-minimal` has on the Core host: `socket`,
`json`, `struct`, `time`.  Nothing is imported from the rest of pedald.

The token is the caller's business.  `namchaind.json` names `/etc/namchain/token` and the
service reads it; this module opens no file and holds no default secret.

One client belongs to one thread.  The request counter and the receive buffer are shared
state, so two threads on one client would interleave a request with somebody else's reply;
give each thread its own client.  The service is single-threaded by design.
"""

import json
import socket
import struct
import time

#: The protocol this client speaks.  The daemon accepts 1..its own version and answers with
#: the version it speaks (docs/daemon.md, "The control protocol").
PROTOCOL = 2

#: The largest reply this client will reassemble, the daemon's own kMaxReplyBytes.  The
#: prefix is believed only up to this, so a corrupt one cannot make the client allocate
#: without bound; past it the stream is dropped, because a framing error cannot be
#: resynchronised.
MAX_REPLY_BYTES = 16 * 1024 * 1024

_HEADER = struct.Struct("<I")
_CHUNK = 1 << 16


class EngineError(Exception):
    """The engine refused, the reply was malformed, or the engine could not be asked.

    `code` is the daemon's own code (`unknown_method`, `rig_not_found`, `unauthorized`, …)
    when the engine answered, and `engine_unreachable` when it did not — which is the
    distinction a caller acts on.  `message` is the daemon's prose, or ours.
    """

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


class EngineClient:
    """One connection to namchaind's TCP control port, reused for as many calls as asked.

    The connection is authenticated when it is opened, as the daemon requires, and
    `hello()` returns the answer it was authenticated with rather than making a second
    request.  A later `call()` refreshes that answer if it had to replace a dead
    connection.
    """

    def __init__(self, host="127.0.0.1", port=47810, token=None, timeout=5.0):
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout
        self._sock = None
        self._buf = bytearray()
        self._hello = None
        self._next_id = 1

    # ------------------------------------------------------------------ the protocol

    def call(self, method, **params):
        """Send one request and return the reply body.

        Raises `EngineError` for a refusal, a protocol error or an unreachable engine, and
        nothing else.  `timeout` bounds the whole call: connect, write and read together.
        """
        deadline = time.monotonic() + self.timeout
        request_id, reply = self._exchange(method, params, deadline)
        return self._reply(reply, request_id)

    def hello(self):
        """The engine's account of itself: role, version, protocol, features, transport.

        This is the answer the current connection was authenticated with, so it costs no
        round trip on a client that is already connected; the first call on a fresh client
        opens the connection and asks.
        """
        if self._hello is None:
            try:
                self._connect(time.monotonic() + self.timeout)
            except OSError as exc:
                raise self._unreachable(exc)
        return self._hello

    def status(self):
        """Device state, rig and generation, block timings, health (docs/daemon.md)."""
        return self.call("engine.status")

    def rig_get(self):
        """The rig the engine is running, as the engine parsed and lowered it."""
        return self.call("rig.get")

    def rig_load(self, rig):
        """Load a rig by name, resolved under the daemon's `rigs_root`."""
        return self.call("rig.load", rig=rig)

    def rig_cost(self, rig):
        """What a rig would cost on this device, without playing or compiling it.

        The engine costs the document exactly as a publish would — the same table, the same
        headroom and the same Full→Lite trimming — on a copy it throws away, so a caller
        learns the verdict for a rig nobody has loaded. The reply is
        `{"cost": {...}, "slimmed_models": [...], "missing_assets": [...]}`, and the cost
        object's own words are the engine's (`fits`, `trimmed` or `over`); nothing here
        interprets them. This is the service's only cost model (D9): pedald never reads
        cost.json and never sums a cost itself.
        """
        return self.call("rig.cost", rig=rig)

    def assets(self, refresh=False):
        """The model and impulse-response library; `refresh` rescans the roots first."""
        return self.call("engine.assets", refresh=bool(refresh))

    def close(self):
        """Drop the connection if there is one.  The client is usable again afterwards."""
        self._disconnect()

    # ------------------------------------------------------------------ the wire

    def _request(self, method, params):
        """One request as a frame, with the id its reply will be matched by."""
        request = dict(params)
        request["method"] = method
        request["id"] = str(self._next_id)
        self._next_id += 1
        try:
            body = json.dumps(request, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            # A parameter that cannot be JSON is the caller's bug, not the engine's answer.
            raise EngineError("bad_request", "%s: %s" % (method, exc))
        return request["id"], _HEADER.pack(len(body)) + body

    def _exchange(self, method, params, deadline):
        """Put one request on a live, authenticated connection and read its reply.

        A connection that is missing, closed or broken is replaced once.  A refusal from
        the engine is not a failure and never reaches here — `_reply` raises it after the
        exchange has succeeded — so it is not retried.
        """
        try:
            return self._attempt(method, params, deadline)
        except OSError:
            self._disconnect()              # the connection died; the retry opens another
        try:
            return self._attempt(method, params, deadline)
        except OSError as exc:
            raise self._unreachable(exc)

    def _attempt(self, method, params, deadline):
        """One connect, one request, one reply.  Transport failures come out as OSError."""
        self._connect(deadline)
        request_id, frame = self._request(method, params)
        self._send(frame, deadline)
        return request_id, self._read_reply(deadline)

    def _connect(self, deadline):
        """Open and authenticate the connection if there is none.

        On TCP an unauthenticated connection may say only `engine.hello`, so this is not
        optional politeness: a reconnect that skipped it would be transparent in name only.
        The hello is built here, after the connection exists, so the ids the daemon sees
        follow the order they were sent in.
        """
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), self._left(deadline))
        # One small request per call, and the reply to it is what a knob stream waits on:
        # Nagle would hold the request for the previous reply's ack.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        try:
            params = {"protocol": PROTOCOL}
            if self.token is not None:
                params["token"] = self.token
            request_id, frame = self._request("engine.hello", params)
            self._send(frame, deadline)
            self._hello = self._reply(self._read_reply(deadline), request_id)
        except (EngineError, OSError):
            # An unauthenticated or broken connection is no use to anyone, so leave none.
            self._disconnect()
            raise

    def _send(self, frame, deadline):
        self._sock.settimeout(self._left(deadline))
        self._sock.sendall(frame)

    def _read_reply(self, deadline):
        """One framed reply, reassembled from the prefix however it was delivered."""
        while len(self._buf) < _HEADER.size:
            self._fill(deadline)
        (length,) = _HEADER.unpack_from(self._buf)
        if length > MAX_REPLY_BYTES:
            self._protocol_error("a reply of %d bytes is past the %d-byte limit"
                                 % (length, MAX_REPLY_BYTES))
        while len(self._buf) < _HEADER.size + length:
            self._fill(deadline)
        body = bytes(self._buf[_HEADER.size:_HEADER.size + length])
        del self._buf[:_HEADER.size + length]
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            self._protocol_error("the reply is not JSON: %s" % exc)

    def _fill(self, deadline):
        """More bytes into the buffer, or a transport failure if the stream has ended."""
        self._sock.settimeout(self._left(deadline))
        chunk = self._sock.recv(_CHUNK)
        if not chunk:
            # EOF: the peer closed.  A socket error rather than a protocol error, because
            # reconnecting is exactly what resolves it.
            raise ConnectionResetError("the engine closed the connection")
        self._buf += chunk

    def _reply(self, reply, request_id):
        """The body of the reply to this call, or the error it carries.

        A refusal leaves the connection alone — the daemon keeps it open, and so do we.  A
        protocol error does not: a stream that misdescribed itself is not worth the next
        request, and a fresh connection re-establishes what it should be.
        """
        if not isinstance(reply, dict):
            self._protocol_error("the reply is not a JSON object")
        if str(reply.get("id")) != request_id:
            self._protocol_error("the reply carries id %r, not %r" % (reply.get("id"), request_id))
        if reply.get("ok") is True:
            return reply
        error = reply.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            raise EngineError(error["code"], str(error.get("message", "")))
        self._protocol_error("the reply is neither ok nor an error object")

    def _protocol_error(self, message):
        """Refuse, and drop the connection the message came from.  Never returns."""
        self._disconnect()
        raise EngineError("protocol_error", message)

    def _disconnect(self):
        sock, self._sock = self._sock, None
        self._buf.clear()
        self._hello = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _unreachable(self, exc):
        """A transport failure as the error a caller can act on; drops the connection."""
        self._disconnect()
        return EngineError("engine_unreachable", _reason(exc, self.host, self.port))

    @staticmethod
    def _left(deadline):
        """What is left of this call's timeout, as the next socket timeout."""
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("the call timed out")
        return left


def _reason(exc, host, port):
    """What went wrong, and to what: the message a caller sees for an unreachable engine."""
    if isinstance(exc, TimeoutError):
        return "%s:%d did not answer in time" % (host, port)
    return "%s:%d: %s" % (host, port, exc)

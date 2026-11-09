"""Tests for pedald's HTTP server.

The server is hand-rolled (the Core host has no `http.server`, `socketserver`, `urllib` or
`hmac`), so it is tested as a real socket is tested, not by calling its internals: a Server is
started on port 0 and spoken to with `http.client` — which exists on the development machine
even though it does not exist on the Core host — and with a raw socket where the test is about
framing rather than about HTTP.

Routes here are registered by path, which is what the frozen interface promises; such a route
answers every method the API uses (GET, HEAD, PUT, POST). A path whose key pins its method
(`"GET /pinned"`) is the way a wrong method becomes the server's 405 rather than the handler's
problem, and it is tested that way.

Run with:
    python3 -m unittest discover -s devices/common/tests -t devices/common/tests \
        -p 'test_httpd.py' -v
"""

import http.client
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald.httpd import File, Server, Stream  # noqa: E402

TOKEN = "pedal-test-token"


def status_route(request):
    return 200, {
        "ok": True,
        "method": request.method,
        "path": request.path,
        "query": request.query,
        "x_test": request.headers.get("x-test"),
    }


def echo_route(request):
    return 201, {"length": len(request.body), "body": request.body.decode("utf-8", "replace")}


def pinned_route(request):
    return 200, {"pinned": True}


def boom_route(request):
    raise RuntimeError("the handler fell over")


ROUTES = {
    "/status": status_route,
    "/library/echo": echo_route,
    "/boom": boom_route,
    "GET /pinned": pinned_route,
}


class HttpdTest(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.server = self.start_server()

    def start_server(self, **kwargs):
        """A started server on port 0, stopped again when the test ends."""
        server = Server("127.0.0.1", 0, TOKEN, ROUTES, log=self.log.append, **kwargs)
        server.start()
        self.addCleanup(server.stop)
        return server

    # -- talking to it ----------------------------------------------------------------

    def request(self, method, path, body=None, token=TOKEN, headers=None, server=None):
        """One request over http.client: (status, response headers, body bytes)."""
        conn = http.client.HTTPConnection("127.0.0.1", (server or self.server).port, timeout=5)
        try:
            sent = dict(headers or {})
            if token is not None:
                sent["Authorization"] = f"Bearer {token}"
            conn.request(method, path, body=body, headers=sent)
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def raw_connection(self, server=None):
        sock = socket.create_connection(("127.0.0.1", (server or self.server).port), timeout=5)
        self.addCleanup(sock.close)
        return sock

    def raw_request(self, sock, method, path, token=TOKEN, headers=(), body=None):
        """One request written by hand: (status, headers, body) of the reply.

        With `body` the request frames it with a Content-Length; without, it sends none.
        """
        lines = [f"{method} {path} HTTP/1.1", "Host: 127.0.0.1"]
        if token is not None:
            lines.append(f"Authorization: Bearer {token}")
        for name, value in headers:
            lines.append(f"{name}: {value}")
        if body is not None:
            lines.append(f"Content-Length: {len(body)}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        if body is not None:
            request += body
        sock.sendall(request)
        return self.read_response(sock)

    def read_response(self, sock):
        """One whole response from a raw socket, as Content-Length frames it."""
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                self.fail("the server closed before it sent a response")
            buffer += chunk
        head, _, body = buffer.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status = int(lines[0].split()[1])
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(b":")
            headers[name.strip().lower().decode("latin-1")] = value.strip().decode("latin-1")
        length = int(headers.get("content-length", "0"))
        while len(body) < length:
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
        return status, headers, body[:length]

    def body_json(self, payload):
        return json.loads(payload.decode("utf-8"))

    def pedald_threads(self, server=None):
        """This server's threads, by name: another test's handlers may still be unwinding."""
        prefix = f"pedald-http-{(server or self.server).port}"
        return [t for t in threading.enumerate() if t.name.startswith(prefix)]

    # -- the answers the API promises -------------------------------------------------

    def test_a_good_token_gets_a_json_answer(self):
        status, headers, payload = self.request("GET", "/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/json")
        body = self.body_json(payload)
        self.assertTrue(body["ok"])
        self.assertEqual(body["method"], "GET")
        self.assertEqual(body["path"], "/status")

    def test_the_query_and_the_headers_reach_the_handler(self):
        status, _, payload = self.request(
            "GET", "/status?a=1&b=two%20three&empty=", headers={"X-Test": "yes"}
        )
        self.assertEqual(status, 200)
        body = self.body_json(payload)
        self.assertEqual(body["query"], {"a": "1", "b": "two three", "empty": ""})
        self.assertEqual(body["x_test"], "yes")     # the key is lower case in Request

    def test_a_framed_body_reaches_the_handler(self):
        status, _, payload = self.request("PUT", "/library/echo", body=b"hello")
        self.assertEqual(status, 201)
        body = self.body_json(payload)
        self.assertEqual(body["length"], 5)
        self.assertEqual(body["body"], "hello")

    def test_a_missing_token_is_401(self):
        status, _, payload = self.request("GET", "/status", token=None)
        self.assertEqual(status, 401)
        self.assertEqual(self.body_json(payload)["error"], "unauthorized")

    def test_a_wrong_token_is_401(self):
        status, _, _ = self.request("GET", "/status", token="not-the-token")
        self.assertEqual(status, 401)

    def test_an_unknown_path_is_404(self):
        status, _, payload = self.request("GET", "/no/such/thing")
        self.assertEqual(status, 404)
        self.assertEqual(self.body_json(payload)["error"], "not found")

    def test_a_registered_path_with_the_wrong_method_is_405(self):
        status, _, _ = self.request("GET", "/pinned")
        self.assertEqual(status, 200)
        status, headers, payload = self.request("POST", "/pinned", body=b"")
        self.assertEqual(status, 405)
        self.assertIn("GET", headers.get("Allow", ""))
        self.assertEqual(self.body_json(payload)["error"], "method not allowed")

    def test_a_method_the_api_does_not_use_is_405_on_a_known_path(self):
        status, headers, _ = self.request("PATCH", "/status")
        self.assertEqual(status, 405)
        self.assertIn("GET", headers.get("Allow", ""))

    def test_a_body_without_content_length_is_411(self):
        # Raw, because http.client will not send an unframed body at all.
        sock = self.raw_connection()
        lines = [
            "PUT /library/echo HTTP/1.1",
            "Host: 127.0.0.1",
            f"Authorization: Bearer {TOKEN}",
        ]
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + b"unframed bytes")
        status, _, payload = self.read_response(sock)
        self.assertEqual(status, 411)
        self.assertEqual(self.body_json(payload)["error"], "Content-Length required")

    def test_a_body_over_the_cap_is_413(self):
        server = self.start_server(max_body=1024)
        status, _, payload = self.request(
            "PUT", "/library/echo", body=b"x" * 1025, server=server
        )
        self.assertEqual(status, 413)
        self.assertEqual(self.body_json(payload)["error"], "body too large")
        # The refusal is the request's, not the server's: the next one is served as usual.
        status, _, _ = self.request("GET", "/status", server=server)
        self.assertEqual(status, 200)

    def test_a_handler_that_raises_gives_500_and_a_log_line(self):
        status, _, payload = self.request("GET", "/boom")
        self.assertEqual(status, 500)
        self.assertEqual(self.body_json(payload)["error"], "internal error")
        self.assertTrue(any("handler raised" in line for line in self.log), self.log)
        status, _, _ = self.request("GET", "/status")
        self.assertEqual(status, 200)

    def test_a_malformed_request_line_is_400(self):
        sock = self.raw_connection()
        sock.sendall(b"GET only-two-parts\r\nHost: 127.0.0.1\r\n\r\n")
        status, _, payload = self.read_response(sock)
        self.assertEqual(status, 400)
        self.assertEqual(self.body_json(payload)["error"], "malformed request line")

    def test_one_connection_serves_the_next_request(self):
        # Keep-alive is what makes "three failures on one connection" mean anything, and the
        # framing has to survive reuse: a body read short or long would poison the next line.
        sock = self.raw_connection()
        status, _, _ = self.raw_request(sock, "GET", "/status")
        self.assertEqual(status, 200)
        status, _, _ = self.raw_request(sock, "GET", "/no/such/thing")
        self.assertEqual(status, 404)
        status, _, payload = self.raw_request(
            sock, "PUT", "/library/echo", body=b'{"rig": "last"}'
        )
        self.assertEqual(status, 201)
        self.assertEqual(self.body_json(payload)["body"], '{"rig": "last"}')
        status, _, _ = self.raw_request(sock, "GET", "/status")
        self.assertEqual(status, 200)

    def test_an_oversized_header_block_is_400(self):
        sock = self.raw_connection()
        padding = b"x" * 20480
        sock.sendall(
            b"GET /status HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Pad: " + padding + b"\r\n\r\n"
        )
        status, _, payload = self.read_response(sock)
        self.assertEqual(status, 400)
        self.assertEqual(self.body_json(payload)["error"], "header block too large")

    def test_three_bad_tokens_on_one_connection_close_it(self):
        sock = self.raw_connection()
        for attempt in range(3):
            status, _, _ = self.raw_request(sock, "GET", "/status", token="wrong-token")
            self.assertEqual(status, 401, f"attempt {attempt + 1}")
        sock.settimeout(5)
        self.assertEqual(sock.recv(1), b"", "the connection should be closed after three")

    # -- the process's side -----------------------------------------------------------

    def test_stop_is_safe_twice_and_leaves_no_thread_running(self):
        server = Server("127.0.0.1", 0, TOKEN, ROUTES, log=self.log.append)
        server.start()
        status, _, _ = self.request("GET", "/status", server=server)
        self.assertEqual(status, 200)
        self.server.stop()          # the one setUp started; its cleanup stops it again
        server.stop()
        server.stop()
        # stop() shuts each live connection down and then joins its handler, so by the time it has
        # returned the handlers are done. The wait is only for a thread's own exit bookkeeping; the
        # 5 s that used to be here was covering a real bug — a socket closed underneath a handler
        # that was inside recv(), which could leave it waiting for its whole read timeout.
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and (self.pedald_threads() or self.pedald_threads(server)):
            time.sleep(0.01)
        self.assertEqual(self.pedald_threads(), [])
        self.assertEqual(self.pedald_threads(server), [])

    def test_stop_shuts_the_peer_down_and_stops_answering(self):
        """What a client sees when the server stops: this connection ends, and no new one starts.

        The handler owns the close — httpd._shutdown only shuts down, so that a reader is never left
        waiting on a descriptor closed underneath it — which makes this the test that the peer's
        view is still closed either way.
        """
        server = Server("127.0.0.1", 0, TOKEN, ROUTES, log=self.log.append)
        server.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/status", headers={"Authorization": f"Bearer {TOKEN}"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()             # idle keep-alive now: the handler is inside recv()
        server.stop()
        conn.sock.settimeout(2)
        self.assertEqual(conn.sock.recv(1), b"", "the peer did not see its connection end")
        conn.close()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", server.port), timeout=2)


class Limits(unittest.TestCase):
    """The rules the "Threads" section asked for: nothing a client does holds a thread for long."""

    def serve(self, routes=None, **kwargs):
        log = []
        server = Server("127.0.0.1", 0, TOKEN, routes or ROUTES, log=log.append, **kwargs)
        server.start()
        self.addCleanup(server.stop)
        return server, log

    def connect(self, server):
        sock = socket.create_connection(("127.0.0.1", server.port))
        sock.settimeout(5)
        self.addCleanup(sock.close)
        return sock

    def get_status(self, sock):
        sock.sendall(f"GET /status HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n\r\n".encode())
        return sock.recv(4096)

    def wait_for(self, check, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not check():
            time.sleep(0.005)
        return check()

    def test_past_the_connection_cap_one_is_closed_at_once(self):
        server, log = self.serve(max_connections=2)
        held = [self.connect(server), self.connect(server)]
        self.assertTrue(self.wait_for(lambda: server.stats()["connections"] == 2))
        extra = self.connect(server)
        self.assertEqual(extra.recv(1), b"")         # a close, not a claim to have understood it
        self.assertTrue(self.wait_for(lambda: server.stats()["refused"] == 1))
        self.assertTrue(any("at the cap of 2" in line for line in log))
        self.assertIn(b"200 OK", self.get_status(held[0]))     # the two it took are unharmed
        held[1].close()
        self.assertTrue(self.wait_for(lambda: server.stats()["connections"] == 1))
        self.assertIn(b"200 OK", self.get_status(self.connect(server)))

    def test_a_silent_connection_is_closed_at_the_first_byte_deadline(self):
        server, _ = self.serve(first_byte_timeout=0.1)
        sock = self.connect(server)
        started = time.monotonic()
        self.assertEqual(sock.recv(1), b"")
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(self.wait_for(lambda: server.stats()["connections"] == 0))

    def test_the_first_byte_deadline_doesnt_apply_to_a_kept_connection(self):
        server, _ = self.serve(first_byte_timeout=0.1)
        sock = self.connect(server)
        self.assertIn(b"200 OK", self.get_status(sock))
        time.sleep(0.3)
        self.assertIn(b"200 OK", self.get_status(sock))

    def test_threads_are_named_for_their_server(self):
        one, _ = self.serve()
        two, _ = self.serve()
        sock = self.connect(one)
        self.get_status(sock)
        names = {t.name for t in one.threads()}
        self.assertEqual(names, {f"pedald-http-{one.port}", f"pedald-http-{one.port}-conn"})
        self.assertEqual({t.name for t in two.threads()}, {f"pedald-http-{two.port}"})
        self.assertEqual(one.stats()["threads"], 2)

    def test_churn_leaves_one_thread(self):
        server, _ = self.serve(max_connections=8)
        for _ in range(40):
            sock = socket.create_connection(("127.0.0.1", server.port))
            self.get_status(sock)
            sock.close()
            half = socket.create_connection(("127.0.0.1", server.port))
            half.sendall(b"GET /sta")                # abandoned mid-request
            half.close()
        self.assertTrue(self.wait_for(lambda: len(server.threads()) == 1), server.threads())


class Replies(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "blob.bin")
        self.content = bytes(range(256)) * 1024      # 256 KiB, several chunks
        with open(self.path, "wb") as handle:
            handle.write(self.content)
        self.seen = []

        def lines(out):
            out.write(b"one\n")
            out.write(b"two\n")

        def upload(request):
            total, biggest = 0, 0
            while True:
                piece = request.stream.read()
                if not piece:
                    break
                total += len(piece)
                biggest = max(biggest, len(piece))
            return 201, {"total": total, "biggest": biggest}

        routes = {
            "GET /file": lambda _r: (200, File(self.path, headers={"ETag": '"abc"'})),
            "GET /gone": lambda _r: (200, File(self.path + ".nope")),
            "GET /stream": lambda _r: (200, Stream(lines, content_type="text/plain")),
            "GET /headers": lambda _r: (200, {"ok": True}, {"ETag": '"xyz"'}),
            "PUT /upload": upload,
            "PUT /buffered": lambda r: (200, {"size": len(r.body)}),
            "PUT /ignores": lambda _r: (200, {"ok": True}),
            "GET /status": lambda _r: (200, {"ok": True}),
        }
        self.server = Server("127.0.0.1", 0, TOKEN, routes, log=lambda _m: None, max_body=1 << 24,
                             max_buffered_body=1024)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        self.addCleanup(self.conn.close)

    def ask(self, method, path, body=None):
        self.conn.request(method, path, body=body, headers={"Authorization": f"Bearer {TOKEN}"})
        reply = self.conn.getresponse()
        return reply, reply.read()

    def test_a_file_arrives_whole_and_the_connection_is_kept(self):
        reply, body = self.ask("GET", "/file")
        self.assertEqual(reply.status, 200)
        self.assertEqual(body, self.content)
        self.assertEqual(reply.getheader("ETag"), '"abc"')
        self.assertEqual(reply.getheader("Content-Length"), str(len(self.content)))
        self.assertEqual(self.ask("GET", "/status")[0].status, 200)

    def test_head_of_a_file_says_its_length_and_sends_nothing(self):
        reply, body = self.ask("HEAD", "/file")
        self.assertEqual(reply.getheader("Content-Length"), str(len(self.content)))
        self.assertEqual(body, b"")

    def test_a_missing_file_is_404(self):
        self.assertEqual(self.ask("GET", "/gone")[0].status, 404)

    def test_a_stream_runs_and_then_closes_the_connection(self):
        reply, body = self.ask("GET", "/stream")
        self.assertEqual(body, b"one\ntwo\n")
        self.assertEqual(reply.getheader("Content-Type"), "text/plain")
        self.assertEqual(reply.getheader("Connection"), "close")

    def test_a_handler_may_add_headers_to_json(self):
        self.assertEqual(self.ask("GET", "/headers")[0].getheader("ETag"), '"xyz"')

    def test_a_large_body_is_read_in_pieces(self):
        reply, body = self.ask("PUT", "/upload", b"x" * (4 << 20))
        self.assertEqual(reply.status, 201)
        answer = json.loads(body)
        self.assertEqual(answer["total"], 4 << 20)
        self.assertLessEqual(answer["biggest"], 1 << 16)

    def test_a_body_too_big_to_buffer_is_413_only_where_it_would_be_buffered(self):
        self.assertEqual(self.ask("PUT", "/buffered", b"x" * 1024)[0].status, 200)
        self.assertEqual(self.ask("PUT", "/buffered", b"x" * 1025)[0].status, 413)

    def test_a_small_body_nobody_read_keeps_the_connection_usable(self):
        self.assertEqual(self.ask("PUT", "/ignores", b"y" * 100)[0].status, 200)
        self.assertEqual(self.ask("GET", "/status")[0].status, 200)

    def test_a_large_body_nobody_read_closes_the_connection(self):
        sock = socket.create_connection(("127.0.0.1", self.server.port))
        self.addCleanup(sock.close)
        sock.settimeout(5)
        sock.sendall(f"PUT /ignores HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n"
                     f"Content-Length: {1 << 20}\r\n\r\n".encode())
        reply = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            reply += chunk
        self.assertIn(b"Connection: close", reply)


if __name__ == "__main__":
    unittest.main()

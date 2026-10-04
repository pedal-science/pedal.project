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
import pathlib
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald.httpd import Server  # noqa: E402

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

    def pedald_threads(self):
        return [t for t in threading.enumerate() if t.name.startswith("pedald-http")]

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
        status, headers, _ = self.request("DELETE", "/status")
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
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.pedald_threads():
            time.sleep(0.05)
        self.assertEqual(self.pedald_threads(), [])


if __name__ == "__main__":
    unittest.main()

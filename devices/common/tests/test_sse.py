"""`GET /events`, on the real server over a real socket: the format, replay, resync, keep-alive, the
caps, and a client that stops reading (docs/pedal-service.md)."""
import json
import pathlib
import socket
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import httpd, sse  # noqa: E402
from pedald.httpd import Server, Stream  # noqa: E402

TOKEN = "t" * 32


class Client:
    def __init__(self, port, last_id=None, recv_buffer=None):
        self.sock = socket.socket()
        if recv_buffer:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, recv_buffer)
        self.sock.connect(("127.0.0.1", port))
        self.sock.settimeout(5)
        extra = f"Last-Event-ID: {last_id}\r\n" if last_id else ""
        self.sock.sendall(f"GET /events HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n{extra}\r\n".encode())
        self.buffer = b""
        self.head = self._until(b"\r\n\r\n")

    def _until(self, mark):
        while mark not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError(self.buffer)
            self.buffer += chunk
        head, _, self.buffer = self.buffer.partition(mark)
        return head.decode()

    def frame(self):
        """The next frame, as {id, event, data} or {"comment": text}."""
        out = {}
        for line in self._until(b"\n\n").split("\n"):
            if line.startswith(":"):
                out["comment"] = line[1:].strip()
            else:
                name, _, value = line.partition(": ")
                out[name] = json.loads(value) if name == "data" else value
        return out

    def close(self):
        self.sock.close()


class Base(unittest.TestCase):
    keepalive = 15.0
    max_streams = 6

    def setUp(self):
        self.hub = sse.EventHub(ring=8, run="abc")
        self.hellos = 0

        def hello():
            self.hellos += 1
            return {"pedal": {"name": "vip"}}

        def events(request):
            return 200, Stream(sse.stream(self.hub, request.headers.get("last-event-id"), hello,
                                          keepalive_s=self.keepalive, poll_s=0.02))

        self.log = []
        self.server = Server("127.0.0.1", 0, TOKEN, {"GET /events": events}, log=self.log.append,
                             max_streams=self.max_streams)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.addCleanup(self.hub.close)
        self.clients = []

    def connect(self, last_id=None, **kwargs):
        client = Client(self.server.port, last_id, **kwargs)
        self.clients.append(client)
        self.addCleanup(client.close)
        return client


class Format(Base):
    def test_a_new_client_gets_the_headers_then_hello_then_events(self):
        client = self.connect()
        self.assertIn("200 OK", client.head)
        self.assertIn("Content-Type: text/event-stream", client.head)
        self.assertIn("Cache-Control: no-cache", client.head)
        self.assertNotIn("Content-Length", client.head)
        first = client.frame()
        self.assertEqual(first["event"], "hello")
        self.assertEqual(first["data"], {"pedal": {"name": "vip"}})
        self.hub.publish("action", {"result": {"ok": True}})
        second = client.frame()
        self.assertEqual(second, {"id": "abc-1", "event": "action", "data": {"result": {"ok": True}}})

    def test_every_client_hears_each_event_once_in_order(self):
        clients = [self.connect() for _ in range(3)]
        for client in clients:
            client.frame()
        for n in range(5):
            self.hub.publish("running", {"n": n})
        for client in clients:
            self.assertEqual([client.frame()["data"]["n"] for _ in range(5)], list(range(5)))

    def test_a_token_is_still_needed(self):
        sock = socket.create_connection(("127.0.0.1", self.server.port))
        self.addCleanup(sock.close)
        sock.sendall(b"GET /events HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertIn(b"401", sock.recv(4096))


class Replay(Base):
    def test_a_known_id_continues_without_hello(self):
        for n in range(3):
            self.hub.publish("running", {"n": n})
        client = self.connect(last_id="abc-1")
        self.assertEqual([client.frame()["data"]["n"] for _ in range(2)], [1, 2])
        self.assertEqual(self.hellos, 0)

    def test_the_current_id_waits_for_the_next(self):
        self.hub.publish("running", {"n": 0})
        client = self.connect(last_id="abc-1")
        self.hub.publish("running", {"n": 1})
        self.assertEqual(client.frame()["id"], "abc-2")

    def test_an_id_the_ring_has_passed_gets_resync_then_hello(self):
        for n in range(20):
            self.hub.publish("running", {"n": n})        # the ring holds 8
        client = self.connect(last_id="abc-2")
        self.assertEqual(client.frame()["event"], "resync")
        self.assertEqual(client.frame()["event"], "hello")
        # And the id it was given is one it can come back with.
        self.hub.publish("running", {"n": 99})
        self.assertEqual(client.frame()["data"]["n"], 99)

    def test_ids_that_arent_this_runs_get_resync_then_hello(self):
        self.hub.publish("running", {"n": 0})
        for stale in ("other-1", "abc-99", "abc-x", "nonsense", "abc-٣"):
            client = self.connect(last_id=stale)
            self.assertEqual(client.frame()["event"], "resync", stale)
            self.assertEqual(client.frame()["event"], "hello", stale)

    def test_a_client_overtaken_while_connected_is_told(self):
        hub = sse.EventHub(ring=4, run="r")
        written = []

        class Out:
            def write(self, data):
                written.append(data)
                hub.publish("x", {})             # as if events kept arriving while this wrote
                for _ in range(8):
                    hub.publish("x", {})

            def closed(self):
                return len(written) >= 3

        sse.stream(hub, None, lambda: {}, keepalive_s=60, poll_s=0.01)(Out())
        self.assertIn(b"event: hello", written[0])
        self.assertIn(b"event: resync", written[1])
        self.assertIn(b"event: hello", written[1])


class KeepAlive(Base):
    keepalive = 0.05

    def test_a_quiet_stream_sends_a_comment(self):
        client = self.connect()
        client.frame()
        self.assertEqual(client.frame(), {"comment": "ka"})


class Caps(Base):
    max_streams = 2

    def test_past_the_cap_a_stream_is_503_with_retry_after(self):
        self.connect()
        self.connect()
        sock = socket.create_connection(("127.0.0.1", self.server.port))
        self.addCleanup(sock.close)
        sock.sendall(f"GET /events HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n\r\n".encode())
        reply = sock.recv(4096).decode()
        self.assertIn("503", reply)
        self.assertIn("Retry-After: 5", reply)

    def test_a_client_that_goes_gives_its_slot_back(self):
        self.connect()
        client = self.connect()
        client.frame()
        client.close()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and self.server.stats()["streams"] > 1:
            time.sleep(0.01)
        self.assertEqual(self.server.stats()["streams"], 1)
        self.connect().frame()

    def test_stop_ends_the_streams(self):
        client = self.connect()
        client.frame()
        started = time.monotonic()
        self.server.stop()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(self.server.threads(), [])


class SlowClient(Base):
    def test_a_client_that_stops_reading_doesnt_hold_up_the_publisher(self):
        original, httpd.STREAM_SEND_TIMEOUT = httpd.STREAM_SEND_TIMEOUT, 0.2
        self.addCleanup(setattr, httpd, "STREAM_SEND_TIMEOUT", original)
        slow = self.connect(recv_buffer=4096)
        slow.frame()
        fast = self.connect()
        fast.frame()
        payload = {"pad": "x" * 60000}
        started = time.monotonic()
        for _ in range(200):
            self.hub.publish("running", payload)
        self.assertLess(time.monotonic() - started, 1.0)     # publishing never waits for anyone
        # The stalled one's stream ends and gives its slot back.
        fast.sock.settimeout(0.01)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and self.server.stats()["streams"] > 1:
            self.hub.publish("running", payload)    # the kernel's buffers take a lot before it stalls
            try:
                while fast.sock.recv(1 << 20):      # keep the other one drained
                    pass
            except OSError:
                pass
        self.assertEqual(self.server.stats()["streams"], 1)


if __name__ == "__main__":
    unittest.main()

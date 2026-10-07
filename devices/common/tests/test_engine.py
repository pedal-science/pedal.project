#!/usr/bin/env python3
"""test_engine.py — pedald's engine client against a fake namchaind.

What fails for this client is not the JSON but the framing and the connection: a reply
that arrives in two pieces, two replies that arrive together, a reply to a different
request, a peer that has gone away, nothing listening at all.  So the server here is a
real socket on a port the kernel picks — never a hard-coded one, or two runs collide —
speaking the same length prefix, and each test makes it misbehave in one way.

Run from the repository root:

    python3 -m unittest discover -s devices/common/tests -t devices/common/tests \\
        -p 'test_engine.py' -v
"""

import json
import pathlib
import socket
import struct
import sys
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald.engine import EngineClient, EngineError  # noqa: E402  (after the path above)

#: The framing the daemon uses on TCP: a u32 little-endian length, then one JSON object.
HEADER = struct.Struct("<I")

#: A token of the length the daemon demands; the fake server does not check it, the wire does.
TOKEN = "0123456789abcdef"


def frame(message):
    """One message as it goes on the wire."""
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return HEADER.pack(len(body)) + body


def answer_ok(conn, request, connection, index):
    """Answer as the daemon does: this request's id, and yes."""
    conn.sendall(frame({"ok": True, "id": request.get("id"), "method": request.get("method")}))


class Reader:
    """Framed messages off a stream socket, the long way round.

    The client is the thing under test; reading the same stream slowly here is what lets a
    test tell a client that lost a message from one that never sent for it.
    """

    def __init__(self, conn, on_frame):
        self.conn = conn
        self.buf = bytearray()
        self.on_frame = on_frame

    def message(self):
        """The next message, or None if the peer closed the stream."""
        while len(self.buf) < HEADER.size:
            if not self._fill():
                return None
        (length,) = HEADER.unpack_from(self.buf)
        while len(self.buf) < HEADER.size + length:
            if not self._fill():
                return None
        header = bytes(self.buf[:HEADER.size])
        body = bytes(self.buf[HEADER.size:HEADER.size + length])
        del self.buf[:HEADER.size + length]
        self.on_frame(header, body)
        return json.loads(body)

    def _fill(self):
        chunk = self.conn.recv(65536)
        if not chunk:
            return False
        self.buf += chunk
        return True


class FakeEngine:
    """A namchaind stand-in on 127.0.0.1, on a port the kernel picks.

    `answer(conn, request, connection, index)` is called for every request except
    `engine.hello`, which the harness answers itself: authenticating the connection is the
    client's business and not what most of these tests are about, while `frames` records it
    either way.  `connection` counts from 1 and `index` counts that connection's requests.
    """

    def __init__(self, answer=None):
        self.answer = answer or answer_ok
        self.requests = []              # (connection, request), in arrival order
        self.frames = []                # (header bytes, body bytes), in arrival order
        self.connections = 0
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self.port = self._listener.getsockname()[1]
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def close(self):
        self._listener.close()

    def _accept(self):
        try:
            while True:
                conn, _ = self._listener.accept()
                self.connections += 1
                threading.Thread(target=self._serve, args=(conn, self.connections),
                                 daemon=True).start()
        except OSError:
            return                      # the listener was closed: the test is over

    def _serve(self, conn, connection):
        reader = Reader(conn, lambda header, body: self.frames.append((header, body)))
        index = 0
        try:
            while True:
                request = reader.message()
                if request is None:
                    return
                self.requests.append((connection, request))
                if request.get("method") == "engine.hello":
                    answer_ok(conn, request, connection, index)
                else:
                    self.answer(conn, request, connection, index)
                index += 1
        except OSError:
            return
        finally:
            conn.close()


class EngineClientTest(unittest.TestCase):
    def start_engine(self, answer=None):
        engine = FakeEngine(answer)
        self.addCleanup(engine.close)
        return engine

    def start_client(self, engine, token=TOKEN, timeout=2.0):
        client = EngineClient(host="127.0.0.1", port=engine.port, token=token, timeout=timeout)
        self.addCleanup(client.close)
        return client

    # ------------------------------------------------------------------ the wire

    def test_hello_frames_the_protocol_and_the_token(self):
        engine = self.start_engine()
        client = self.start_client(engine)

        reply = client.hello()

        self.assertTrue(reply["ok"])
        self.assertEqual(len(engine.frames), 1)     # one request, and the hello is it
        header, body = engine.frames[0]
        self.assertEqual(header, HEADER.pack(len(body)))
        self.assertEqual(struct.unpack("<I", header)[0], len(body))
        request = json.loads(body.decode("utf-8"))
        self.assertEqual(request["method"], "engine.hello")
        self.assertEqual(request["protocol"], 2)
        self.assertEqual(request["token"], TOKEN)
        self.assertTrue(request["id"])

    def test_a_call_returns_the_parsed_reply(self):
        engine = self.start_engine()
        client = self.start_client(engine)

        reply = client.status()

        self.assertTrue(reply["ok"])
        self.assertEqual(reply["method"], "engine.status")
        # The connection is authenticated before the method is asked for, because on TCP
        # the daemon would answer nothing else.
        asked = [request["method"] for _, request in engine.requests]
        self.assertEqual(asked, ["engine.hello", "engine.status"])

    def test_a_refusal_becomes_an_engine_error_with_the_daemons_code(self):
        def refuse(conn, request, connection, index):
            conn.sendall(frame({"ok": False, "id": request["id"],
                                "error": {"code": "rig_not_found",
                                          "message": "no rig named 'nope.json'"}}))

        engine = self.start_engine(refuse)
        client = self.start_client(engine)

        with self.assertRaises(EngineError) as caught:
            client.rig_load("nope.json")

        self.assertEqual(caught.exception.code, "rig_not_found")
        self.assertEqual(caught.exception.message, "no rig named 'nope.json'")
        self.assertEqual(engine.requests[-1][1]["rig"], "nope.json")
        self.assertEqual(engine.connections, 1)     # a refusal is an answer, not a failure

    # ------------------------------------------------------------------ rig.cost

    def test_rig_cost_asks_for_the_rig_and_returns_the_engines_verdict(self):
        def cost(conn, request, connection, index):
            conn.sendall(frame({"ok": True, "id": request["id"], "rig": "/rigs/Big Lead.json",
                                "cost": {"cost": 1.02, "full_cost": 1.02, "headroom": 0.8,
                                         "over": True, "verdict": "over", "trimmed": True,
                                         "table": "/etc/namchain/cost.json", "table_ok": True,
                                         "nodes": [{"node": "amp", "cost": 0.6, "row": "NAM.A2.full"}]},
                                "slimmed_models": [], "missing_assets": []}))

        engine = self.start_engine(cost)
        client = self.start_client(engine)

        reply = client.rig_cost("Big Lead.json")

        request = engine.requests[-1][1]
        self.assertEqual(request["method"], "rig.cost")
        self.assertEqual(request["rig"], "Big Lead.json")   # as rig.load takes it, name and all
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["cost"]["verdict"], "over")
        self.assertEqual(reply["cost"]["cost"], 1.02)
        self.assertEqual(len(reply["cost"]["nodes"]), 1)    # the engine's detail is passed through
        self.assertEqual(engine.connections, 1)

    def test_rig_cost_turns_a_refusal_into_an_engine_error(self):
        # The codes this route can answer with are the engine's: rig_not_found, bad_request,
        # asset_missing and compile_failed (namchain docs/daemon.md, "rig.cost"), and the
        # service must not read any of them as a cost.
        def refuse(conn, request, connection, index):
            conn.sendall(frame({"ok": False, "id": request["id"],
                                "error": {"code": "asset_missing",
                                          "message": "no model 'amp.nam'"}}))

        engine = self.start_engine(refuse)
        client = self.start_client(engine)

        with self.assertRaises(EngineError) as caught:
            client.rig_cost("Big Lead.json")

        self.assertEqual(caught.exception.code, "asset_missing")
        self.assertEqual(caught.exception.message, "no model 'amp.nam'")
        self.assertEqual(engine.connections, 1)     # a refusal is an answer, not a failure

    def test_rig_cost_reports_what_the_engine_could_not_find(self):
        # A missing asset is not a refusal: `ok: true` with `missing_assets` is how the engine
        # says it costed the rig against what it could resolve, and the caller decides.
        def missing(conn, request, connection, index):
            conn.sendall(frame({"ok": True, "id": request["id"],
                                "cost": {"cost": 0.4, "headroom": 0.8, "over": False,
                                         "verdict": "fits", "trimmed": False},
                                "slimmed_models": [],
                                "missing_assets": [{"node": "amp", "reference": "amp.nam"}]}))

        engine = self.start_engine(missing)
        client = self.start_client(engine)

        reply = client.rig_cost("Big Lead.json")

        self.assertEqual(reply["missing_assets"], [{"node": "amp", "reference": "amp.nam"}])

    # ------------------------------------------------------------------ arrival shapes
    def test_a_reply_in_two_pieces_is_reassembled(self):
        def split(conn, request, connection, index):
            data = frame({"ok": True, "id": request["id"], "method": request["method"]})
            conn.sendall(data[:2])              # inside the length prefix
            time.sleep(0.05)
            conn.sendall(data[2:])              # and the rest of the body

        engine = self.start_engine(split)
        client = self.start_client(engine)

        reply = client.status()

        self.assertEqual(reply["method"], "engine.status")

    def test_two_replies_in_one_write_are_both_taken(self):
        sent = []

        def coalesce(conn, request, connection, index):
            if sent:
                return                          # the next reply went out with this one
            sent.append(True)
            following = str(int(request["id"]) + 1)
            conn.sendall(frame({"ok": True, "id": request["id"], "n": 1}) +
                         frame({"ok": True, "id": following, "n": 2}))

        engine = self.start_engine(coalesce)
        client = self.start_client(engine)

        first = client.status()
        second = client.status()

        self.assertEqual(first["n"], 1)
        self.assertEqual(second["n"], 2)
        self.assertEqual(engine.connections, 1)     # the second reply came with the first

    # ------------------------------------------------------------------ bad answers

    def test_a_reply_to_another_request_is_a_protocol_error(self):
        def wrong_id(conn, request, connection, index):
            conn.sendall(frame({"ok": True, "id": "somebody-elses", "method": request["method"]}))

        engine = self.start_engine(wrong_id)
        client = self.start_client(engine)

        with self.assertRaises(EngineError) as caught:
            client.status()

        self.assertEqual(caught.exception.code, "protocol_error")
        self.assertEqual(engine.connections, 1)     # a wrong answer is not retried

    def test_a_malformed_reply_is_a_protocol_error(self):
        def malformed(conn, request, connection, index):
            body = b"{not json"
            conn.sendall(HEADER.pack(len(body)) + body)

        engine = self.start_engine(malformed)
        client = self.start_client(engine)

        with self.assertRaises(EngineError) as caught:
            client.status()

        self.assertEqual(caught.exception.code, "protocol_error")

    # ------------------------------------------------------------------ the connection

    def test_an_engine_that_is_not_listening_is_unreachable(self):
        # A bound socket with no listener refuses the connection, and holding it open for
        # the test keeps the kernel from handing the port to something else meanwhile.
        held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(held.close)
        held.bind(("127.0.0.1", 0))
        client = EngineClient(host="127.0.0.1", port=held.getsockname()[1], timeout=1.0)
        self.addCleanup(client.close)

        with self.assertRaises(EngineError) as caught:
            client.status()

        self.assertEqual(caught.exception.code, "engine_unreachable")

    def test_a_call_after_the_peer_closed_reconnects(self):
        closed = threading.Event()

        def close_after_replying(conn, request, connection, index):
            answer_ok(conn, request, connection, index)
            if connection == 1:
                conn.close()
                closed.set()

        engine = self.start_engine(close_after_replying)
        client = self.start_client(engine)

        self.assertTrue(client.status()["ok"])
        self.assertTrue(closed.wait(2.0))
        self.assertTrue(client.status()["ok"])
        self.assertEqual(engine.connections, 2)     # the first connection was replaced


if __name__ == "__main__":
    unittest.main()

"""The UART link over a pseudo-terminal: bytes both ways, and a port that is not there.

A pty stands in for the Pico: what the service writes must come out of the master, and what
the master writes must reach the session. The real port is tested on the board.
"""
import os
import pathlib
import pty
import select
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import link as link_mod  # noqa: E402
from pedald import protocol          # noqa: E402


def read_all(fd, timeout=0.5):
    out = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        out += chunk
    return out


class StubSession:
    def __init__(self):
        self.fed = b""

    def feed(self, data):
        self.fed += data


class LinkOverPty(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        self.device = os.ttyname(self.slave)
        self.logs = []
        self.link = link_mod.Link(self.device, 115200, log=self.logs.append)

    def tearDown(self):
        self.link.close()

    def test_bytes_from_the_pico_reach_the_session(self):
        session = StubSession()
        self.link.attach(session)
        self.assertTrue(self.link.open_port())
        os.write(self.master, b"\xa5\x5ahello")
        self.link.poll(0.5)
        self.assertEqual(session.fed, b"\xa5\x5ahello")

    def test_bytes_for_the_pico_come_out_of_the_port(self):
        self.assertTrue(self.link.open_port())
        self.link.send(b"\xa5\x5a\x06\x01\x42\x00\x00")
        self.assertEqual(read_all(self.master), b"\xa5\x5a\x06\x01\x42\x00\x00")

    def test_the_counters_and_timestamps_move_with_the_traffic(self):
        """What /status and pedal-diag read: a total, and when it was last true.

        A counter without a clock cannot say whether the link is alive, so both are asserted
        here rather than only in the handler's test (where the link is faked).
        """
        session = StubSession()
        self.link.attach(session)
        self.assertTrue(self.link.open_port())
        self.assertEqual((self.link.bytes_in, self.link.bytes_out, self.link.drops), (0, 0, 0))
        self.assertIsNone(self.link.last_rx_at)
        self.assertIsNotNone(self.link.opened_at)

        os.write(self.master, b"\xa5\x5aabcdef")
        self.link.poll(0.5)
        self.assertEqual(self.link.bytes_in, 8)
        self.assertIsNotNone(self.link.last_rx_at)

        self.link.send(b"\xa5\x5a\x06\x01\x42\x00\x00")
        read_all(self.master)
        self.assertEqual(self.link.bytes_out, 7)
        self.assertIsNotNone(self.link.last_tx_at)

        # A port that goes away is counted: the difference between "the Pico reset twice" and
        # "the Pico has never been heard from" is the whole diagnosis.
        self.link._drop("test")
        self.assertEqual(self.link.drops, 1)

    def test_a_session_answers_hello_through_the_link(self):
        session = protocol.Session(self.link.send)
        self.link.attach(session)
        self.assertTrue(self.link.open_port())
        os.write(self.master, protocol.frame(protocol.HELLO, bytes([1, 0, 0, 0]) + b"0.1"))
        self.link.poll(0.5)
        messages = self.link.take_messages()
        self.assertEqual([m["type"] for m in messages], [protocol.HELLO])
        self.assertEqual(messages[0]["fw"], "0.1")
        self.assertTrue(session.session_up)
        out = read_all(self.master)
        self.assertEqual(out[:2], protocol.SYNC)
        self.assertEqual(out[2], protocol.WELCOME)          # a WELCOME went out
        session.send_state(flags=protocol.STATE_AUDIO_READY, rig_index=2, bank=0,
                           bank_size=3, name="Crunch Lead")
        out = read_all(self.master)
        self.assertEqual(out[2], protocol.STATE)
        self.assertIn(b"Crunch Lead", out[4:])

    def test_a_message_that_arrives_in_pieces_is_reassembled(self):
        session = protocol.Session(self.link.send)
        self.link.attach(session)
        self.assertTrue(self.link.open_port())
        whole = protocol.frame(protocol.HELLO, bytes([1, 0, 0, 0]) + b"0.1")
        os.write(self.master, whole[:3])
        self.link.poll(0.2)
        self.assertEqual(self.link.take_messages(), [])
        os.write(self.master, whole[3:])
        self.link.poll(0.2)
        self.assertEqual([m["type"] for m in self.link.take_messages()], [protocol.HELLO])

    def test_a_missing_port_is_retried_not_fatal(self):
        missing = os.path.join(tempfile.mkdtemp(), "no-such-tty")
        self.addCleanup(shutil.rmtree, os.path.dirname(missing))
        link = link_mod.Link(missing, 115200, log=self.logs.append, retry_s=0.01)
        link.attach(StubSession())
        link.poll(0.01)
        self.assertFalse(link.open)
        self.assertTrue(any("cannot open" in line for line in self.logs))
        first = link.next_try
        link.poll(0.01)
        self.assertEqual(link.next_try, first)              # still inside the backoff
        link.next_try = 0.0
        link.poll(0.01)
        self.assertTrue(any("cannot open" in line for line in self.logs))

    def test_send_with_no_port_is_a_no_op(self):
        self.link.send(b"nothing happens")                  # must not raise


if __name__ == "__main__":
    unittest.main()

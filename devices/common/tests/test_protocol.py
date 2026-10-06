"""Tests for pedald.protocol, the Core-host end of the Pico link protocol.

The bytes asserted here are the firmware's, not the document's: draft 2 payloads carry every
string as a `str8` (one length byte, then the bytes), and `firmware/src/protocol.c` is the
other end of every claim made in this file. Nothing here needs a Pico — the Session under
test is the whole Core side, and `Link` stands in for the UART.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import protocol
from pedald.protocol import (
    ACK, CFG, ERROR, EVENT, HELLO, LOG, PING, PONG, STATE, WELCOME,
    Session, crc16, frame, str8,
)

SYNC = b"\xA5\x5A"


def unframe(data):
    """One captured frame as (type, payload). The Session writes one frame per send call."""
    assert data[:2] == SYNC, data
    length = data[3]
    assert len(data) == length + 6, data
    assert crc16(data[2:4 + length]) == data[4 + length] | (data[5 + length] << 8), data
    return data[2], data[4:4 + length]


class Link:
    """Stands in for the UART: collects what the Session writes."""

    def __init__(self):
        self.raw = []

    def __call__(self, data):
        self.raw.append(bytes(data))

    @property
    def frames(self):
        return [unframe(data) for data in self.raw]

    def types(self):
        return [msg_type for msg_type, _ in self.frames]

    def payloads(self, msg_type):
        return [payload for kind, payload in self.frames if kind == msg_type]


def hello(major=2, minor=0, caps=0x0003, fw="v1.2.3"):
    """A draft 2 HELLO: major, minor, caps u16 LE, then the firmware version as a `str8`."""
    return frame(HELLO, bytes([major, minor, caps & 0xFF, caps >> 8]) + str8(fw, 16))


def event(seq, source=1, kind=0x01, a=0, b=0):
    return frame(EVENT, bytes([seq, source, kind, a, b]))


class CrcTests(unittest.TestCase):
    def test_check_vector(self):
        self.assertEqual(crc16(b"123456789"), 0x29B1)

    def test_crc_covers_the_length(self):
        # U1: the CRC runs over type, len and payload, so the same type and payload under
        # a different length is a different CRC.
        self.assertNotEqual(crc16(bytes([ACK, 1, 0x00])), crc16(bytes([ACK, 1, 0x00, 0x00])))

    def test_crc_in_the_frame_is_the_crc_of_type_len_and_payload(self):
        data = frame(STATE, b"abc")
        body = bytes([STATE, 3]) + b"abc"
        self.assertEqual(data[2:], body + bytes([crc16(body) & 0xFF, crc16(body) >> 8]))


class FrameTests(unittest.TestCase):
    def test_frame_round_trips(self):
        data = frame(EVENT, bytes([7, 1, 0x10, 80, 127]))
        self.assertEqual(data[:2], SYNC)
        self.assertEqual(data[2], EVENT)
        self.assertEqual(data[3], 5)
        link = Link()
        session = Session(link)
        self.assertEqual(
            session.feed(data),
            [{"type": EVENT, "seq": 7, "source": 1, "kind": 0x10, "a": 80, "b": 127}],
        )

    def test_empty_payload_round_trips(self):
        link = Link()
        session = Session(link)
        self.assertEqual(session.feed(frame(PING)), [{"type": PING, "nonce": None}])

    def test_frame_refuses_a_payload_the_wire_cannot_carry(self):
        with self.assertRaises(ValueError):
            frame(EVENT, b"x" * (protocol.MAX_PAYLOAD + 1))


class DecoderTests(unittest.TestCase):
    def setUp(self):
        self.link = Link()
        self.session = Session(self.link)

    def test_frame_split_across_two_feeds(self):
        data = frame(PONG, b"\x07")
        self.assertEqual(self.session.feed(data[:3]), [])
        self.assertEqual(self.session.feed(data[3:]), [{"type": PONG, "nonce": 7}])

    def test_two_frames_coalesced_in_one_feed(self):
        data = frame(PONG, b"\x07") + frame(PONG, b"\x08")
        self.assertEqual(
            self.session.feed(data),
            [{"type": PONG, "nonce": 7}, {"type": PONG, "nonce": 8}],
        )

    def test_resync_after_leading_garbage(self):
        self.assertEqual([m["type"] for m in self.session.feed(b"\x00\xff\x5a" + hello())],
                         [HELLO])

    def test_resync_from_the_byte_after_the_first_sync_byte(self):
        # The bench's case (docs/uart-protocol.md, Framing; U3): a header whose length
        # swallows the start of a good frame must not cost the good one.
        good = frame(STATE, bytes([0x04, 1, 0, 4, 9]) + b"resync ok")
        self.assertEqual(
            [m["type"] for m in self.session.feed(SYNC + bytes([STATE, 8]) + good)],
            [STATE],
        )

    def test_bad_crc_is_dropped(self):
        data = bytearray(frame(PONG, b"\x07"))
        data[4] ^= 0xFF
        self.assertEqual(self.session.feed(bytes(data)), [])
        self.assertEqual(self.session.frames_bad, 1)

    def test_bad_crc_does_not_lose_the_frame_behind_it(self):
        bad = bytearray(frame(PONG, b"\x07"))
        bad[4] ^= 0xFF
        self.assertEqual(
            [m["type"] for m in self.session.feed(bytes(bad) + frame(PONG, b"\x09"))],
            [PONG],
        )

    def test_too_long_length_is_dropped(self):
        # Hand-built: frame() refuses to make a frame the contract forbids.
        body = bytes([EVENT, protocol.MAX_PAYLOAD + 1]) + b"x" * (protocol.MAX_PAYLOAD + 1)
        crc = crc16(body)
        self.assertEqual(self.session.feed(SYNC + body + bytes([crc & 0xFF, crc >> 8])), [])
        self.assertEqual(self.session.frames_bad, 1)

    def test_too_long_length_does_not_swallow_the_frame_behind_it(self):
        body = bytes([EVENT, 65]) + b"x" * 65
        crc = crc16(body)
        data = SYNC + body + bytes([crc & 0xFF, crc >> 8]) + frame(PONG, b"\x0b")
        self.assertEqual([m["type"] for m in self.session.feed(data)], [PONG])

    def test_unknown_type_is_ignored(self):
        self.assertEqual(self.session.feed(frame(0x7F, b"\x01\x02")), [])

    def test_malformed_input_never_raises(self):
        for data in (b"", b"\xa5", b"\xa5\x5a", b"\xa5\x5a\x01", b"\xa5\x5a\x01\xff",
                     bytes(range(256)) * 3):
            self.session.feed(data)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.link = Link()
        self.session = Session(self.link)

    def test_hello_answers_exactly_one_welcome_and_a_state(self):
        self.assertFalse(self.session.session_up)
        returned = self.session.feed(hello(caps=0x0003, fw="v1.2.3"))
        self.assertTrue(self.session.session_up)
        self.assertEqual(
            returned,
            [{"type": HELLO, "major": 2, "minor": 0, "caps": 0x0003, "fw": "v1.2.3"}],
        )
        self.assertEqual(self.link.types(), [WELCOME, STATE])
        # WELCOME is v2.0 with our heartbeat, then the service string as a `str8` (draft 2).
        self.assertEqual(self.link.payloads(WELCOME), [bytes([2, 0, 250, 0, 10]) + b"pedald 0.1"])

    def test_a_second_hello_gets_another_welcome_and_state(self):
        # A HELLO is the Pico (re)starting the handshake — at boot, or after it reset. Answering
        # only the first would leave a rebooted Pico hunting for ever, because its HELLOs are
        # themselves valid frames and keep this end's link timer alive (Session). WELCOME is
        # idempotent at the far end, so answering every one is safe.
        self.session.feed(hello())
        self.session.feed(hello())
        self.assertEqual(self.link.types().count(WELCOME), 2)
        self.assertEqual(self.link.types().count(STATE), 2)

    def test_a_hello_from_another_major_is_refused_with_error_and_no_session(self):
        returned = self.session.feed(hello(major=1, fw="0.1"))
        self.assertFalse(self.session.session_up)
        self.assertEqual(self.link.types(), [ERROR])        # no WELCOME, no STATE
        self.assertEqual(returned[0]["refused"], True)
        self.assertEqual(returned[0]["major"], 1)
        code, payload = self.link.frames[0][1][0], self.link.frames[0][1]
        self.assertEqual(code, protocol.ERR_VERSION)
        self.assertIn("2.0", payload[2:].decode())          # the str8 text names both versions
        self.assertIn("1.0", payload[2:].decode())

    def test_a_matching_hello_after_a_refusal_still_brings_the_session_up(self):
        self.session.feed(hello(major=1))
        self.session.feed(hello())
        self.assertTrue(self.session.session_up)
        self.assertIn(WELCOME, self.link.types())

    def test_a_hello_from_another_major_drops_a_session_already_held(self):
        self.session.feed(hello())
        self.assertTrue(self.session.session_up)
        self.session.feed(hello(major=3, minor=1))
        self.assertFalse(self.session.session_up)

    def test_event_is_applied_once_and_acknowledged_again_on_repeat(self):
        self.session.feed(hello())
        data = event(9, source=1, kind=0x10, a=80, b=127)
        self.assertEqual(
            self.session.feed(data),
            [{"type": EVENT, "seq": 9, "source": 1, "kind": 0x10, "a": 80, "b": 127}],
        )
        self.assertEqual(self.session.feed(data), [])
        self.assertEqual(self.link.payloads(ACK), [b"\x09", b"\x09"])

    def test_a_new_seq_after_a_repeat_is_applied(self):
        # The dedupe remembers the last seq, not every seq ever seen, so an 8-bit seq that
        # comes round again is a new event (and a set of 256 would wedge for good).
        self.session.feed(hello())
        for seq in (1, 2, 3, 1):
            self.session.feed(event(seq))
        self.assertEqual(self.link.payloads(ACK), [b"\x01", b"\x02", b"\x03", b"\x01"])

    def test_ping_is_answered_with_pong_carrying_the_nonce(self):
        self.assertEqual(self.session.feed(frame(PING, b"\x42")),
                         [{"type": PING, "nonce": 0x42}])
        self.assertEqual(self.link.payloads(PONG), [b"\x42"])

    def test_tick_pings_when_the_link_has_been_quiet(self):
        self.session.feed(hello())
        self.link.raw.clear()
        self.session.tick(250)
        self.assertEqual(self.link.types(), [PING])
        self.assertEqual(self.link.payloads(PING), [b"\x01"])
        self.session.tick(400)          # inside the heartbeat interval: nothing more
        self.assertEqual(len(self.link.raw), 1)

    def test_any_valid_frame_refreshes_the_link_timer(self):
        self.session.feed(hello())
        self.session.tick(900)
        self.session.feed(frame(PONG, b"\x01"))
        self.session.tick(1500)
        self.assertTrue(self.session.session_up)

    def test_silence_drops_the_session_and_a_later_hello_restores_it(self):
        self.session.feed(hello())
        self.session.tick(999)
        self.assertTrue(self.session.session_up)
        self.session.tick(1000)         # link_down_ms of silence
        self.assertFalse(self.session.session_up)
        self.session.feed(hello())
        self.assertTrue(self.session.session_up)
        self.assertEqual(self.link.types().count(WELCOME), 2)

    def test_a_ping_from_a_live_pico_re_establishes_a_dropped_session(self):
        # The bench's asymmetric deadlock (2026-10-04): the Pico, once up, stops sending HELLO
        # and holds its session with PINGs; a Core that dropped its half answered the PINGs
        # with PONGs (keeping the Pico up) while waiting for a HELLO that never came. Any valid
        # frame has to bring the session back, not only HELLO.
        self.session.feed(hello())
        self.session.tick(1000)
        self.assertFalse(self.session.session_up)
        self.link.raw.clear()
        self.session.feed(frame(PING, b"\x07"))
        self.assertTrue(self.session.session_up)
        self.assertEqual(self.link.types().count(WELCOME), 1)
        self.assertEqual(self.link.types().count(STATE), 1)
        self.assertEqual(self.link.payloads(PONG), [b"\x07"])

    def test_an_event_or_pong_from_a_live_pico_also_re_establishes(self):
        self.session.feed(hello())
        self.session.tick(1000)
        self.assertFalse(self.session.session_up)
        self.link.raw.clear()
        self.session.feed(frame(PONG, b"\x01"))
        self.assertTrue(self.session.session_up)
        self.assertEqual(self.link.types().count(WELCOME), 1)

    def test_state_payload_is_what_the_firmware_parses(self):
        # firmware/src/protocol.c, handle_state: flags, rig i8, bank i8, bank size, then the
        # name as a `str8`.
        self.session.send_state(flags=0x04 | 0x01, rig_index=-1, bank=-1, bank_size=0,
                                name="Ampeg VT-40 + cab")
        expected = bytes([0x05, 0xFF, 0xFF, 0x00, 17]) + b"Ampeg VT-40 + cab"
        self.assertEqual(self.link.payloads(STATE), [expected])
        self.assertEqual(self.link.raw[-1], frame(STATE, expected))

    def test_state_is_remembered_and_resent_after_a_new_session(self):
        self.session.send_state(flags=0x05, rig_index=2, bank=1, bank_size=4, name="Twin")
        self.session.feed(hello())
        self.assertEqual(self.link.payloads(STATE),
                         [bytes([0x05, 2, 1, 4, 4]) + b"Twin"] * 2)

    def test_state_name_is_cut_to_48_bytes_on_a_character_boundary(self):
        self.session.send_state(flags=0, rig_index=0, bank=0, bank_size=1,
                                name="a" * 47 + "é" + "b" * 10)
        payload = self.link.payloads(STATE)[0]
        self.assertEqual(payload[4], 47)                # é would make 49 bytes
        self.assertEqual(payload[5:], b"a" * 47)
        self.assertLessEqual(len(payload), protocol.MAX_PAYLOAD)

    def test_trailing_bytes_after_a_string_are_ignored(self):
        # U2's point: a field added after the name must not be read as part of it.
        grown = frame(STATE, bytes([0x05, 2, 0, 3, 4]) + b"Twin" + b"\xAA\xBB")
        self.assertEqual(self.session.feed(grown),
                         [{"type": STATE, "flags": 0x05, "rig_index": 2, "bank": 0,
                           "bank_size": 3, "name": "Twin"}])

    def test_a_short_state_does_not_invent_a_name(self):
        self.assertEqual(self.session.feed(frame(STATE, bytes([0x05, 0, 0, 1]))),
                         [{"type": STATE, "flags": 0x05, "rig_index": 0, "bank": 0,
                           "bank_size": 1, "name": None}])

    def test_error_text_is_decoded(self):
        self.assertEqual(
            self.session.feed(frame(ERROR, bytes([3]) + str8("version", 32))),
            [{"type": ERROR, "code": 3, "text": "version"}],
        )

    def test_battery_is_ignored_until_phase_four_speaks_it(self):
        # 0x0B is reserved for Phase 4's battery meter and neither end decodes it yet.
        self.assertEqual(self.session.feed(frame(0x0B, bytes([1, 0x2C, 0x12]))), [])

    def test_reserved_messages_decode_to_their_type(self):
        self.assertEqual(self.session.feed(frame(LOG, b"\x01")), [{"type": LOG}])
        self.assertEqual(self.session.feed(frame(CFG, b"\x02")), [{"type": CFG}])


if __name__ == "__main__":
    unittest.main()

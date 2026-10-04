"""The Core-host end of the Pico link protocol.

`docs/uart-protocol.md` is the contract, and the deployed firmware
(`firmware/src/protocol.c`) speaks **draft 1**, so that is what this implements: a string
at the end of a payload runs to the end of the frame, with no `str8` length byte. Draft 2
(the document as written today) adds that length byte and a `BATTERY` message; neither end
speaks it yet, and the wire here is the firmware's, not the document's.

A frame is

    0xA5 0x5A | type | len | payload | crc_lo | crc_hi

with CRC-16/CCITT-FALSE over `type`, `len` and `payload`, little-endian, and `len` at most
64. `Session` is the whole of the state: it decodes bytes from the link, answers `HELLO`
with `WELCOME` and `STATE`, acknowledges and dedupes `EVENT`s, answers `PING` with `PONG`,
and pings the Pico when the link has been quiet. It never raises on link input: a bad CRC
or a bad length drops the frame, and the decoder rescans from the byte after the first sync
byte so that a corrupted `len` cannot swallow the good frames behind it.

Only the standard library is used, and only what the Core host's `python3-minimal` ships:
no `termios`, no sockets, no `hmac`. The UART itself (open, `stty`, `select`) belongs to
the caller, which hands `send` one complete frame to write.
"""

# WELCOME's version. Draft 1 firmware checks the major and refuses a different one itself.
VERSION_MAJOR = 1
VERSION_MINOR = 0

# Draft 1's message types. Draft 2's BATTERY (0x0B) is deliberately absent: the deployed
# firmware does not speak it.
HELLO, WELCOME, EVENT, ACK, STATE, PING, PONG, ERROR, LOG, CFG = range(0x01, 0x0B)

SYNC = b"\xA5\x5A"
SYNC0 = SYNC[0]
MAX_PAYLOAD = 64

# The firmware copies at most this much of a STATE name (`NAME_MAX`, protocol.c); sending
# more would only be truncated at the other end.
NAME_MAX = 48

# STATE's flag bits (`PROTO_STATE_*` in the firmware; uart-protocol.md U7). Bit 1 is the
# *engine's* mute, not the relay: the relay is the Pico's, and the service only mirrors it.
STATE_AUDIO_READY = 1 << 0
STATE_ENGINE_MUTED = 1 << 1
STATE_HEALTH_MASK = 3 << 2
STATE_HEALTH_OK = 0 << 2
STATE_HEALTH_WARN = 1 << 2
STATE_HEALTH_ERROR = 2 << 2


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, not reflected, no final xor.

    Check value: b"123456789" is 0x29B1.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frame(msg_type: int, payload: bytes = b"") -> bytes:
    """One complete frame, sync pair and CRC included.

    The CRC covers `type`, `len` and `payload` (uart-protocol.md, U1). A payload the wire
    cannot carry is a caller's bug, and says so here rather than being dropped silently at
    the far end.
    """
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload of %d bytes exceeds %d" % (len(payload), MAX_PAYLOAD))
    body = bytes((msg_type, len(payload))) + payload
    crc = crc16(body)
    return SYNC + body + bytes((crc & 0xFF, crc >> 8))


def _byte_at(payload: bytes, index: int):
    """The payload's byte at `index`, or None if the frame is shorter than the field."""
    return payload[index] if index < len(payload) else None


def _int8_at(payload: bytes, index: int):
    """A signed byte: STATE's rig_index and bank are int8 and -1 means "none"."""
    value = _byte_at(payload, index)
    return None if value is None else (value - 256 if value > 127 else value)


def _truncate_utf8(text: str, limit: int) -> bytes:
    """`text` as UTF-8, at most `limit` bytes, never splitting a character."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return data
    # The cut can leave an incomplete sequence at the end; errors="ignore" drops it.
    return data[:limit].decode("utf-8", "ignore").encode("utf-8")


class Session:
    """One run of the link, from the first `HELLO` to the silence that ends it.

    `send` is called with one complete frame and must put those bytes on the UART. Time
    comes from `tick()`; `feed()` has no clock of its own and stamps what it decodes with
    the time last given to `tick()` (or to `__init__`).
    """

    def __init__(self, send, *, service_version="pedald 0.1", heartbeat_ms=250,
                 link_down_ms=1000, now_ms=0):
        self._send = send
        self._service_version = service_version
        self._heartbeat_ms = int(heartbeat_ms)
        self._link_down_ms = int(link_down_ms)
        self._now_ms = int(now_ms)
        self._last_rx_ms = self._now_ms
        self._last_tx_ms = self._now_ms
        self._up = False
        self._ping_nonce = 0
        # The seq of the last EVENT applied in this session. One EVENT is in flight at a
        # time, so a retransmit of that one is the only duplicate that can arrive; keeping
        # the last seq rather than a set stops an 8-bit seq that wraps from being mistaken
        # for a duplicate (uart-protocol.md, Reliability).
        self._last_event_seq = None
        self._rx = bytearray()
        # The current STATE, remembered for the resend that follows a re-established
        # session. The default is "nothing to say": no flags, no rig.
        self._state = (0, -1, -1, 0, "")
        # Counters, as the firmware keeps them: what the service's health line reports.
        self.frames_ok = 0
        self.frames_bad = 0

    # ------------------------------------------------------------------ state
    @property
    def session_up(self) -> bool:
        return self._up

    # ------------------------------------------------------------------ input
    def feed(self, data: bytes) -> list[dict]:
        """Decode what arrived, act on it, and report it. Never raises on link input.

        Each decoded frame yields one dict: `{"type": ..., ...}` with the frame's fields,
        e.g. `{"type": EVENT, "seq": 3, "source": 1, "kind": 0x10, "a": 80, "b": 127}` or
        `{"type": PONG, "nonce": 7}`. A repeated EVENT is acknowledged again but reported
        only once; an unknown type is ignored.
        """
        out = []
        for msg_type, payload in self._decode(bytes(data)):
            self.frames_ok += 1
            # Any valid frame is proof of life, whatever its type (Session, step 3).
            self._last_rx_ms = self._now_ms
            out.extend(self._handle(msg_type, payload))
        return out

    def _decode(self, data: bytes):
        """Frames out of the byte stream, mirroring the firmware's parser and its resync."""
        self._rx += data
        frames = []
        while True:
            start = self._rx.find(SYNC)
            if start < 0:
                # A sync byte at the very end may be the first half of a pair split across
                # feeds; anything before it can never start a frame.
                if self._rx and self._rx[-1] == SYNC0:
                    del self._rx[:-1]
                else:
                    del self._rx[:]
                break
            if start:
                del self._rx[:start]
            if len(self._rx) < 4:
                break

            length = self._rx[3]
            if length > MAX_PAYLOAD:
                # Rescan from the byte after the first sync byte, so the good frames
                # behind a corrupted length still arrive (Framing; U3).
                self.frames_bad += 1
                del self._rx[0]
                continue

            total = 4 + length + 2
            if len(self._rx) < total:
                break
            want = self._rx[4 + length] | (self._rx[5 + length] << 8)
            if crc16(self._rx[2:4 + length]) == want:
                frames.append((self._rx[2], bytes(self._rx[4:4 + length])))
                del self._rx[:total]
            else:
                self.frames_bad += 1
                del self._rx[0]
        return frames

    def _handle(self, msg_type: int, payload: bytes) -> list[dict]:
        """Act on one valid frame and decode it for the caller."""
        if msg_type == HELLO:
            # The document makes a different major a protocol error; the firmware checks
            # WELCOME's major itself, so refusing here would only lose the handshake. One
            # WELCOME per HELLO: a HELLO while the session is up is ignored.
            if not self._up:
                self._start_session()
            return [self._hello(payload)]

        if msg_type == EVENT:
            return self._event(payload)

        if msg_type == PING:
            nonce = payload[:1]
            if nonce:
                self._write(frame(PONG, nonce))
            return [{"type": PING, "nonce": nonce[0] if nonce else None}]

        if msg_type == PONG:
            return [{"type": PONG, "nonce": _byte_at(payload, 0)}]

        if msg_type == ACK:
            return [{"type": ACK, "seq": _byte_at(payload, 0)}]

        if msg_type == WELCOME:
            return [{
                "type": WELCOME,
                "major": _byte_at(payload, 0),
                "minor": _byte_at(payload, 1),
                "heartbeat_ms": (payload[2] | (payload[3] << 8)) if len(payload) >= 4 else None,
                "service": payload[4:].decode("utf-8", "replace"),
            }]

        if msg_type == STATE:
            return [{
                "type": STATE,
                "flags": _byte_at(payload, 0),
                "rig_index": _int8_at(payload, 1),
                "bank": _int8_at(payload, 2),
                "bank_size": _byte_at(payload, 3),
                "name": payload[4:].decode("utf-8", "replace"),
            }]

        if msg_type == ERROR:
            return [{
                "type": ERROR,
                "code": _byte_at(payload, 0),
                "text": payload[1:].decode("utf-8", "replace"),
            }]

        if msg_type in (LOG, CFG):
            return [{"type": msg_type}]

        # An unknown type is ignored: a newer minor may add one, and a payload may grow
        # extra bytes at its end.
        return []

    @staticmethod
    def _hello(payload: bytes) -> dict:
        return {
            "type": HELLO,
            "major": _byte_at(payload, 0),
            "minor": _byte_at(payload, 1),
            "caps": (payload[2] | (payload[3] << 8)) if len(payload) >= 4 else None,
            "fw": payload[4:].decode("utf-8", "replace"),
        }

    def _event(self, payload: bytes) -> list[dict]:
        seq = _byte_at(payload, 0)
        if seq is not None:
            # A repeat is acknowledged again: the Pico is retrying because it never saw
            # the first ACK, and saying so again is what stops the retry.
            self.send_ack(seq)
        if seq is None or seq == self._last_event_seq:
            return []
        self._last_event_seq = seq
        return [{
            "type": EVENT,
            "seq": seq,
            "source": _byte_at(payload, 1),
            "kind": _byte_at(payload, 2),
            "a": _byte_at(payload, 3),
            "b": _byte_at(payload, 4),
        }]

    # ------------------------------------------------------------------ session
    def _start_session(self):
        """WELCOME, then the current STATE, then the link is up (Session, steps 2 and 3)."""
        self._up = True
        # The dedupe belongs to the session: a Pico that reboots starts its seq again.
        self._last_event_seq = None
        self._last_tx_ms = self._now_ms
        self._write(frame(WELCOME, bytes((VERSION_MAJOR, VERSION_MINOR,
                                          self._heartbeat_ms & 0xFF, self._heartbeat_ms >> 8))
                          + _truncate_utf8(self._service_version, MAX_PAYLOAD - 4)))
        self._emit_state()

    def _drop_session(self):
        """Back to waiting for a HELLO. An EVENT still in the Pico's hand is its to drop."""
        self._up = False
        self._last_event_seq = None

    def tick(self, now_ms: int) -> None:
        """Take the time: end a silent session, and ping the Pico on a quiet link."""
        self._now_ms = int(now_ms)
        if not self._up:
            return

        # Slower than link_down_ms is a dead link. The firmware tests for strictly more
        # than it; ending a millisecond earlier costs nothing and reads as "link_down_ms
        # of silence".
        if self._now_ms - self._last_rx_ms >= self._link_down_ms:
            self._drop_session()
            return

        if self._heartbeat_ms > 0 and self._now_ms - self._last_tx_ms >= self._heartbeat_ms:
            self._ping_nonce = (self._ping_nonce + 1) & 0xFF
            self.send_ping(self._ping_nonce)

    # ------------------------------------------------------------------ output
    def send_state(self, *, flags: int, rig_index: int, bank: int, bank_size: int,
                   name: str) -> None:
        """Put the current STATE on the wire, and remember it for the next session."""
        self._state = (int(flags), int(rig_index), int(bank), int(bank_size), str(name))
        self._emit_state()

    def send_ack(self, seq: int) -> None:
        self._write(frame(ACK, bytes((int(seq) & 0xFF,))))

    def send_ping(self, nonce: int) -> None:
        self._write(frame(PING, bytes((int(nonce) & 0xFF,))))

    def _emit_state(self):
        """Draft 1 STATE: flags, rig_index i8, bank i8, bank_size, name to the end."""
        flags, rig_index, bank, bank_size, name = self._state
        payload = bytes((flags & 0xFF, rig_index & 0xFF, bank & 0xFF, bank_size & 0xFF))
        self._write(frame(STATE, payload + _truncate_utf8(name, NAME_MAX)))

    def _write(self, data: bytes):
        self._send(data)
        # The heartbeat is measured from the last frame out, as the firmware measures it:
        # a busy link needs no PING on top of it.
        self._last_tx_ms = self._now_ms

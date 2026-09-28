#!/usr/bin/env python3
"""Frame-level loopback for the Pico link protocol, through the Debug Probe.

This plays the pedal service's side of docs/uart-protocol.md against the
firmware: it answers HELLO with WELCOME, replies to PINGs and sends its own,
deliberately drops one EVENT's ACK to watch the retry, sends STATE, then goes
silent to watch the session drop and come back.

The Pico's USB console is the bench's control stand-in: the script types 'e'
there to make the firmware send an EVENT.

Usage: firmware/tools/protocol-test.py [probe-port] [pico-console-port]
"""

import glob
import os
import select
import sys
import termios
import time

BAUD = 115200
SYNC = b"\xA5\x5A"

(HELLO, WELCOME, EVENT, ACK, STATE, PING, PONG, ERROR) = range(0x01, 0x09)

EVENT_NAMES = {0x01: "rig_up", 0x02: "rig_down", 0x07: "bypass_set", 0x08: "bypass_toggle"}
SOURCE_NAMES = {0: "bench", 1: "footswitch", 2: "midi", 3: "panel", 4: "service"}


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def make_frame(mtype, payload=b""):
    body = bytes([mtype, len(payload)]) + payload
    crc = crc16(body)
    return SYNC + body + bytes([crc & 0xFF, crc >> 8])


class Decoder:
    """Mirrors the firmware's parser, including the resync rule."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        frames = []
        while True:
            start = self.buf.find(SYNC)
            if start < 0:
                if self.buf and self.buf[-1] == SYNC[0]:
                    del self.buf[:-1]
                else:
                    self.buf.clear()
                break
            if start > 0:
                del self.buf[:start]
            if len(self.buf) < 4:
                break
            mtype, length = self.buf[2], self.buf[3]
            if length > 64:
                del self.buf[0]
                continue
            if len(self.buf) < length + 6:
                break
            crc = self.buf[4 + length] | (self.buf[5 + length] << 8)
            if crc16(bytes(self.buf[2:4 + length])) == crc:
                frames.append((mtype, bytes(self.buf[4:4 + length])))
                del self.buf[:length + 6]
            else:
                del self.buf[0]
        return frames


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    speed = getattr(termios, "B%d" % BAUD, BAUD)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def read_bytes(fd, timeout):
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return b""
    try:
        return os.read(fd, 4096)
    except BlockingIOError:
        return b""


class Link:
    """The probe's UART bridge: frames in, frames out."""

    def __init__(self, path):
        self.path = path
        self.fd = open_port(path)
        self.dec = Decoder()
        self.frames = []
        self.cursor = 0

    def pump(self, timeout=0.1):
        self.frames.extend(self.dec.feed(read_bytes(self.fd, timeout)))

    def next(self, timeout, types=None):
        deadline = time.time() + timeout
        while True:
            while self.cursor < len(self.frames):
                frame = self.frames[self.cursor]
                self.cursor += 1
                if types is None or frame[0] in types:
                    return frame
            if time.time() >= deadline:
                return None
            self.pump(0.1)

    def send(self, mtype, payload=b""):
        os.write(self.fd, make_frame(mtype, payload))


class Console:
    """The Pico's USB console: text out, keystrokes in."""

    def __init__(self, path):
        self.path = path
        self.fd = open_port(path)
        self.text = ""

    def pump(self, timeout=0.1):
        self.text += read_bytes(self.fd, timeout).decode(errors="replace")

    def wait_line(self, needle, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.text:
                return True
            self.pump(0.1)
        return needle in self.text

    def write(self, data):
        os.write(self.fd, data)


class Checks:
    def __init__(self):
        self.failed = 0

    def check(self, name, ok, detail=""):
        print("%s %s%s" % ("PASS" if ok else "FAIL", name, (" -- " + detail) if detail else ""))
        if not ok:
            self.failed += 1


def find_probe(ports):
    for path in ports:
        link = Link(path)
        frame = link.next(timeout=3.0, types={HELLO})
        if frame is not None:
            return link
        os.close(link.fd)
    return None


def main():
    args = sys.argv[1:]
    if len(args) == 2:
        probe = Link(args[0])
        console = Console(args[1])
    else:
        candidates = sorted(glob.glob("/dev/cu.usbmodem*"))
        if not candidates:
            print("no /dev/cu.usbmodem* ports: is the Pico, or the probe, attached?")
            return 1
        probe = find_probe(candidates)
        if probe is None:
            print("no port is sending HELLO: is the protocol firmware running?")
            return 1
        others = [p for p in candidates if p != probe.path]
        console = None
        for path in others:
            port = Console(path)
            if port.wait_line("proto:", 2.0):
                console = port
                break
            os.close(port.fd)
        if console is None:
            print("no Pico console port: is its USB stdio attached?")
            return 1

    print("probe:   %s" % probe.path)
    print("console: %s\n" % console.path)

    checks = Checks()

    # 1. HELLO, then the session.
    frame = probe.next(timeout=2.0, types={HELLO})
    checks.check("HELLO received", frame is not None)
    if frame is None:
        return 1
    payload = frame[1]
    major, minor = payload[0], payload[1]
    caps = payload[2] | (payload[3] << 8)
    fw = payload[4:].decode(errors="replace")
    print("      v%d.%d caps=0x%04x firmware=%r" % (major, minor, caps, fw))
    checks.check("HELLO is version 1.x", major == 1, "major=%d" % major)

    probe.send(WELCOME, bytes([1, 0, 250, 0]) + b"protocol-test 0.1")
    probe.send(STATE, bytes([0x04 | 0x01, 2, 0, 4]) + b"Ampeg VT-40 + cab")
    checks.check("session up on the Pico", console.wait_line("session up", 2.0))

    # 2. PING/PONG both ways.
    frame = probe.next(timeout=2.0, types={PING})
    checks.check("Pico PING received", frame is not None)
    if frame is not None:
        probe.send(PONG, frame[1][:1])
        print("      pico ping nonce=%d, pong sent" % frame[1][0])
    probe.send(PING, bytes([0x5A]))
    frame = probe.next(timeout=2.0, types={PONG})
    checks.check("our PING answered", frame is not None and frame[1][0] == 0x5A,
                 "payload=%r" % (frame[1] if frame else None))

    # 3. STATE arrives.
    checks.check("STATE printed on the console",
                 console.wait_line("name='Ampeg VT-40 + cab'", 2.0))

    # 3b. Resync: a header whose length swallows the start of a good STATE must not cost the
    # STATE. The parser has to rescan from the byte after the bad frame's first sync byte
    # (docs/uart-protocol.md, Framing); one that carries on from the next byte loses it.
    good = make_frame(STATE, bytes([0x04 | 0x01, 1, 0, 4]) + b"resync ok")
    os.write(probe.fd, SYNC + bytes([STATE, 8]) + good)
    checks.check("a good frame behind a bad length survives (resync)",
                 console.wait_line("name='resync ok'", 2.0))

    # 4. EVENT, with the first ACK deliberately dropped.
    console.write(b"e")
    frame = probe.next(timeout=2.0, types={EVENT})
    checks.check("EVENT received after the console trigger", frame is not None)
    if frame is None:
        return 1
    seq, source, kind = frame[1][0], frame[1][1], frame[1][2]
    print("      event seq=%d source=%s kind=%s" %
          (seq, SOURCE_NAMES.get(source, source), EVENT_NAMES.get(kind, kind)))
    checks.check("EVENT is rig_up from the bench", kind == 0x01 and source == 0)

    retry = probe.next(timeout=1.0, types={EVENT})
    checks.check("unacknowledged EVENT retransmitted", retry is not None and retry[1][0] == seq,
                 "retry seq=%s" % (retry[1][0] if retry else None))
    probe.send(ACK, bytes([seq]))
    checks.check("retransmit noted on the console", console.wait_line("retransmit", 1.0))

    extra = probe.next(timeout=0.6, types={EVENT})
    checks.check("no further copies after the ACK", extra is None)

    # 5. Counters, from the console.
    console.write(b"?")
    console.wait_line("frames ok=", 2.0)
    counters = ""
    for line in console.text.splitlines():
        if "frames ok=" in line:
            counters = line
    print("      %s" % counters)
    checks.check("no events lost", "events lost=0" in counters, counters)

    # 6. Silence: the session must drop and come back.
    deadline = time.time() + 3.5
    hello = None
    while time.time() < deadline and hello is None:
        hello = probe.next(timeout=0.5, types={HELLO})
    checks.check("Pico drops the session and hunts again", hello is not None)
    checks.check("link down noted on the console", console.wait_line("link down", 1.0))
    probe.send(WELCOME, bytes([1, 0, 250, 0]) + b"protocol-test 0.1")
    checks.check("session back up", console.wait_line("session up", 2.0))

    print()
    if checks.failed:
        print("%d check(s) failed" % checks.failed)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

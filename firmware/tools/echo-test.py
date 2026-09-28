#!/usr/bin/env python3
"""Round-trip test for the Pico's link UART, through the Debug Probe.

Wiring: probe RX <- Pico GP0 (physical pin 1), probe TX -> Pico GP1 (pin 2),
GND <-> GND (pin 3).

The probe's UART bridge appears on the Mac as /dev/cu.usbmodemNNN. The script
tries every usbmodem port that is not the Pico's own console (the firmware does
not echo on USB), sends a pattern, and reports which port echoed it back.

Usage: firmware/tools/echo-test.py [device ...]
"""

import glob
import os
import select
import sys
import termios
import time

BAUD = 115200


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    speed = getattr(termios, "B%d" % BAUD, BAUD)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag: raw
    attrs[1] = 0  # oflag: raw
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag: 8N1, no modem lines
    attrs[3] = 0  # lflag: raw
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def round_trip(path, timeout=2.0):
    """Send a pattern and return what came back, or None if it never echoed."""
    pattern = ("echo-test-%d\r\n" % int(time.time())).encode()
    fd = open_port(path)
    try:
        os.write(fd, pattern)
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if chunk:
                buf += chunk
            if pattern.strip() in buf:
                return buf
        return None
    finally:
        os.close(fd)


def main():
    ports = sys.argv[1:] or sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        print("no /dev/cu.usbmodem* ports: is the Pico, or the probe, attached?")
        return 1

    found = False
    for path in ports:
        try:
            reply = round_trip(path)
        except OSError as exc:
            print("%s: %s" % (path, exc))
            continue
        if reply is None:
            print("%s: no echo" % path)
            continue
        found = True
        print("%s: echoed" % path)
        for line in reply.decode(errors="replace").splitlines():
            print("    %s" % line)

    if not found:
        print()
        print("Nothing echoed. Check that:")
        print("  - the echo firmware is running (heartbeat on the Pico's own port),")
        print("  - probe RX <- Pico GP0 (pin 1), probe TX -> Pico GP1 (pin 2),")
        print("  - GND <-> GND (pin 3).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

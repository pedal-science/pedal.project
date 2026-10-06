#!/usr/bin/env python3
"""Read a serial port for a few seconds — the bench slave's console, or any CDC device.

    console.py [device] [seconds]      default: the first /dev/cu.usbmodem*, 6 seconds

Read-only: it opens the port, sets 115200 8N1 raw, and prints whatever arrives. The Pico's USB CDC
ignores the baud rate, so the setting is for USB-TTL adapters, which do not. Nothing is written.

Why it exists: the bench slave is normally powered from the Core host's header with no USB, so its
console is unavailable exactly when it would be most useful. When it is on a USB lead instead, this
reads it without needing screen/minicom, and `--probe --console` in pedal-diag does the same thing
for the pedal's own Pico.
"""
import glob
import os
import select
import sys
import termios
import time


def main(argv):
    ports = [argv[1]] if len(argv) > 1 else sorted(glob.glob("/dev/cu.usbmodem*"))
    seconds = float(argv[2]) if len(argv) > 2 else 6.0
    if not ports:
        print("no /dev/cu.usbmodem* found", file=sys.stderr)
        return 1
    for port in ports:
        fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            a = termios.tcgetattr(fd)
            speed = getattr(termios, "B115200", 115200)
            termios.tcsetattr(fd, termios.TCSANOW,
                              [0, 0,
                               (a[2] | termios.CS8 | termios.CREAD | termios.CLOCAL)
                               & ~getattr(termios, "PARENB", 0) & ~getattr(termios, "CSTOPB", 0),
                               0, speed, speed, a[6]])
            out = b""
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                ready, _, _ = select.select([fd], [], [], 0.2)
                if ready:
                    try:
                        out += os.read(fd, 4096)
                    except OSError:
                        pass
        finally:
            os.close(fd)
        print("=== %s (%.0f s) ===" % (port, seconds))
        print(out.decode("utf-8", "replace") or "(nothing arrived)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

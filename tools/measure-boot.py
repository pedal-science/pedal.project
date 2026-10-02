#!/usr/bin/env python3
"""measure-boot.py [--seconds N] [--out DIR] [device ...] — plan 1.7: the pre-kernel half of
power-on to sound, watched from the Mac through the Debug Probe.

On a Pi 5, `BOOT_UART=1` puts the bootloader's own log on UART10 — the dedicated debug
connector — which is also where vip's console is (`console=ttyAMA10,115200`). So one passive
cable carries the bootloader's first line and the kernel log, and a capture needs only two
wires: GND, and the Pi's TXD into the probe's RX (yellow). Nothing is written back to the
getty running on that port.

The probe's UART bridge and the Pico's own console both appear as /dev/cu.usbmodemNNN, and
which is which is not advertised, so this opens every candidate and logs them all on one
clock. Timestamps are taken when a read returns, so a burst arriving in one read shares one
stamp: worth about the 10 ms select interval, well inside what a seconds-scale boot number
needs. The kernel's own `[    0.000000]` line is the handover; everything on the wire before
it is the bootloader's and the firmware's time, the part 1.7 records as unmeasured.

Power-on itself is not on the wire. The first bootloader byte arrives a small, unstated time
after power is applied, so state which anchor a number uses: see plan.md, step 7.

Usage:
    tools/measure-boot.py --seconds 600 --out bench-results/2026-10-02-boot-time-vip
    tools/measure-boot.py /dev/cu.usbmodem1302
"""

import argparse
import glob
import os
import select
import sys
import termios
import time

BAUD = 115200
READ_TIMEOUT = 0.01


def open_port(path):
    """Raw 8N1 at BAUD, non-blocking. Opened read/write as echo-test.py does, but never written."""
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


def main():
    ap = argparse.ArgumentParser(
        description="plan 1.7: capture the Pi's boot serial from the Mac, on one monotonic clock.")
    ap.add_argument("devices", nargs="*", help="serial ports; default every /dev/cu.usbmodem*")
    ap.add_argument("--seconds", type=float, default=600.0, help="how long to capture")
    ap.add_argument("--out", default=None, help="directory to write serial.log into")
    args = ap.parse_args()

    ports = args.devices or sorted(glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        print("no /dev/cu.usbmodem* ports: is the probe attached?", file=sys.stderr)
        return 1

    fds = {}
    for path in ports:
        try:
            fds[open_port(path)] = path
        except OSError as exc:
            print("%s: %s" % (path, exc), file=sys.stderr)
    if not fds:
        print("no port could be opened", file=sys.stderr)
        return 1

    start = time.monotonic()

    log = None
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        log = open(os.path.join(args.out, "serial.log"), "w", buffering=1)
        log.write("# measure-boot.py: capture on the Mac's monotonic clock\n")
        log.write("# ports: %s\n" % " ".join(sorted(fds.values())))
        log.write("# T+ is seconds since the capture started, not since power-on\n")
        # CLOCK_MONOTONIC is system-wide on macOS, so tools/measure-audio.py's own start
        # stamp lines up with this one; the header is what pairs the two logs.
        log.write("# clock start_monotonic %.6f\n" % start)
        print("start_monotonic %.6f" % start, flush=True)

    deadline = start + args.seconds
    bufs = {fd: b"" for fd in fds}
    lines = {fd: 0 for fd in fds}
    first = {fd: None for fd in fds}

    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            ready, _, _ = select.select(list(fds), [], [], READ_TIMEOUT)
            stamp = time.monotonic() - start
            for fd in ready:
                try:
                    chunk = os.read(fd, 4096)
                except (BlockingIOError, OSError):
                    continue
                if not chunk:
                    continue
                bufs[fd] += chunk
                while b"\n" in bufs[fd]:
                    line, bufs[fd] = bufs[fd].split(b"\n", 1)
                    text = line.decode(errors="replace").rstrip("\r")
                    if first[fd] is None:
                        first[fd] = (stamp, text)
                    lines[fd] += 1
                    record = "T+%9.3f  %-22s  %s" % (stamp, fds[fd], text)
                    print(record, flush=True)
                    if log:
                        log.write(record + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        for fd in fds:
            os.close(fd)
        if log:
            log.close()

    print("\ncaptured %.1f s. Per port:" % (time.monotonic() - start))
    for fd, path in sorted(fds.items(), key=lambda kv: kv[1]):
        if lines[fd]:
            print("  %-22s %5d lines, first at T+%.3f: %s"
                  % (path, lines[fd], first[fd][0], first[fd][1][:70]))
        else:
            print("  %-22s     0 lines (not the boot console, or the cable is elsewhere)" % path)
    if log:
        print("log: %s" % os.path.join(args.out, "serial.log"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

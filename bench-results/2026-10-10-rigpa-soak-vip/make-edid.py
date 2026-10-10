#!/usr/bin/env python3
"""make-edid.py OUT.bin — a minimal EDID 1.3 for a 1920x480, 60 Hz panel (the pedal's 8.8" bar), so
vc4 can be told a screen is there when none is (D14 soak, rigpa plan V2).

One detailed timing, preferred: 1920+48+32+80 = 2080 by 480+3+5+7 = 495, at 61.78 MHz, so 60.0 Hz.
Reduced blanking; not the real panel's timing (V3 reads that from its EDID), but the same pixels per
frame, which is what the scan-out costs.
"""
import struct
import sys


def dtd(clock_10khz, ha, hb, hso, hsw, va, vb, vso, vsw, wmm, hmm):
    return bytes([
        clock_10khz & 0xFF, clock_10khz >> 8,
        ha & 0xFF, hb & 0xFF, ((ha >> 8) << 4) | (hb >> 8),
        va & 0xFF, vb & 0xFF, ((va >> 8) << 4) | (vb >> 8),
        hso & 0xFF, hsw & 0xFF, ((vso & 0xF) << 4) | (vsw & 0xF),
        ((hso >> 8) << 6) | ((hsw >> 8) << 4) | ((vso >> 4) << 2) | (vsw >> 4),
        wmm & 0xFF, hmm & 0xFF, ((wmm >> 8) << 4) | (hmm >> 8),
        0, 0, 0x1E,  # no border; digital separate sync, both positive
    ])


def text(tag, s):
    return bytes([0, 0, 0, tag, 0]) + (s.encode()[:13] + b"\n").ljust(13, b" ")[:13]


maker = "RGP"
packed = sum((ord(c) - 64) << (10 - 5 * i) for i, c in enumerate(maker))
e = bytearray(b"\x00\xff\xff\xff\xff\xff\xff\x00")
e += struct.pack(">H", packed) + struct.pack("<H", 0x1920) + struct.pack("<I", 1)
e += bytes([1, 36, 1, 3])                    # week 1, 2026, EDID 1.3
e += bytes([0x80, 22, 6, 120, 0x0A])         # digital; 22 x 6 cm; gamma 2.2; preferred timing first
e += bytes([0xEE, 0x91, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])  # sRGB-ish chromaticity
e += bytes(3)                                # no established timings
e += b"\x01\x01" * 8                         # no standard timings
e += dtd(6178, 1920, 160, 48, 32, 480, 15, 3, 5, 220, 60)
e += text(0xFC, "rigpa soak")                # the name
e += bytes([0, 0, 0, 0xFD, 0, 50, 70, 25, 35, 7, 0, 10]) + b"\x20" * 6  # range limits
e += bytes([0, 0, 0, 0x10, 0]) + bytes(13)   # dummy
e += bytes([0])                              # no extensions
e += bytes([(-sum(e)) & 0xFF])
assert len(e) == 128 and sum(e) % 256 == 0
open(sys.argv[1], "wb").write(e)

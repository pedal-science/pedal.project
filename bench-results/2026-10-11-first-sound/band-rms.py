#!/usr/bin/env python3
"""band-rms.py — where a capture's noise lives, in octave bands.

    python3 band-rms.py capture.wav [--channel 0]

Prints the RMS in dBFS per octave band (31.5 Hz … 20 kHz) plus the total, from the same
Welch-averaged spectrum `scripts/codec-noise.py` uses, so the numbers agree with its
unweighted RMS. Built for the 2026-10-11 session: a broadband floor and a hum are easy to
tell apart by eye once they are split this way.
"""
import argparse
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "codec_noise", os.path.join(HERE, "..", "..", "scripts", "codec-noise.py"))
cn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cn)

BANDS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000, 20000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--channel", type=int, default=0)
    args = ap.parse_args()
    samples, rate, _ = cn.read_wav(args.wav, args.channel)
    spec = cn.power_spectrum(samples)
    n = len(spec) * 2
    bin_hz = rate / float(n)
    print("%s, channel %d (%d samples at %d Hz)" % (args.wav, args.channel, len(samples), rate))
    print("  %-16s %10s %8s" % ("band", "dBFS", "share"))
    total = sum(spec) * bin_hz
    for lo, hi in zip(BANDS, BANDS[1:]):
        k0, k1 = int(lo / bin_hz), min(int(hi / bin_hz) + 1, len(spec))
        power = sum(spec[k0:k1]) * bin_hz
        db = 10 * math.log10(power) if power > 0 else float("-inf")
        share = 100.0 * power / total if total > 0 else 0.0
        print("  %-16s %10.1f %7.1f%%" % ("%g-%g Hz" % (lo, hi), db, share))
    print("  %-16s %10.1f" % ("total 20-20k", 10 * math.log10(total) if total else float("-inf")))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""analyse-roundtrip.py — one 1 kHz line level per channel of a round-trip capture.

    python3 analyse-roundtrip.py roundtrip-line-tone.wav [--hz 1000] [--skip 4] [--secs 2]

The capture is trimmed to whole seconds so the tone lands on an exact DFT bin (a 2 s window
at 48 kHz has 1 Hz bins), which means no window and no leakage: for a sine of peak A, the
single-bin DFT magnitude is A*N/2, so rms = |X|*sqrt(2)/N. Stdlib only.

The reader is its own, not codec-noise.py's: that one's range bound drops the last frame of
every channel but the first, which is harmless for a noise floor and fatal for an exact-bin
Goertzel. (Found here, 2026-10-11; fixed there too.)
"""
import argparse
import cmath
import math
import struct
import wave


def read(path):
    """Return (list of per-channel sample lists in -1..1, rate)."""
    with wave.open(path, "rb") as w:
        channels, width = w.getnchannels(), w.getsampwidth()
        rate, frames = w.getframerate(), w.getnframes()
        raw = w.readframes(frames)
    if width == 2:
        fmt, scale = "<h", 1 << 15
    elif width == 3:
        fmt, scale = None, 1 << 23
    elif width == 4:
        fmt, scale = "<i", 1 << 31
    else:
        raise SystemExit("%s is %d bytes per sample" % (path, width))
    out = [[] for _ in range(channels)]
    for i in range(0, len(raw) - width * channels + 1, width * channels):
        for c in range(channels):
            j = i + c * width
            v = int.from_bytes(raw[j:j + 3], "little", signed=True) if width == 3 \
                else struct.unpack_from(fmt, raw, j)[0]
            out[c].append(v / scale)
    return out, rate


def goertzel_dbfs(x, rate, hz):
    n = len(x)
    k = hz * n / float(rate)
    if abs(k - round(k)) > 1e-9:
        raise SystemExit("window does not put %g Hz on a bin (n=%d)" % (hz, n))
    w = cmath.exp(-2j * math.pi * round(k) / n)
    acc = 0j
    for i, v in enumerate(x):
        acc += v * (w ** i)
    rms = abs(acc) * math.sqrt(2.0) / n
    return 20.0 * math.log10(rms) if rms else -200.0


def rms_dbfs(x):
    if not x:
        return -200.0
    r = math.sqrt(sum(v * v for v in x) / len(x))
    return 20.0 * math.log10(r) if r else -200.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--hz", type=float, default=1000.0)
    ap.add_argument("--skip", type=float, default=4.0, help="seconds to skip before the window")
    ap.add_argument("--secs", type=float, default=2.0, help="window length in whole seconds")
    args = ap.parse_args()
    chans, rate = read(args.wav)
    a, b = int(args.skip * rate), int((args.skip + args.secs) * rate)
    print("%s: %d channels at %d Hz, window %.0f-%.0f s" %
          (args.wav, len(chans), rate, args.skip, args.skip + args.secs))
    print("  ch  %9s  %10s" % ("%.0f Hz" % args.hz, "RMS"))
    for c, x in enumerate(chans):
        win = x[a:b]
        print("  %2d  %9.1f  %10.1f" % (c, goertzel_dbfs(win, rate, args.hz), rms_dbfs(win)))


if __name__ == "__main__":
    main()

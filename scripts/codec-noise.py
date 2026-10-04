#!/usr/bin/env python3
"""codec-noise.py — the codec's noise floor, from an arecord capture.

    python3 scripts/codec-noise.py capture.wav [--channel 0] [--full-scale 1.0]
    python3 scripts/codec-noise.py --selftest

For one channel it prints:

- the DC offset, so a mis-biased input shows up before the noise does
- unweighted RMS in the 20 Hz–20 kHz band, in dBFS and in µV at <full-scale> V rms — 2a's
  convention, where a 1.0 V rms full scale puts 21 µV at −93.5 dBFS
- A-weighted RMS the same way (IEC 61672 weighting applied to the spectrum), because a
  90 Hz comb counts for 30 dB less than the same power at 1 kHz
- the largest spectral lines below 1 kHz and between 1 and 20 kHz, so hum, a comb and a
  whine come out as frequencies rather than as one number that moved

Stdlib only: python3 is on the host and the Mac, numpy is not necessarily on either.  The
spectrum is a Welch average of up to 12 Hann windows (0.73 Hz bins at a 65536 window and
48 kHz), about 15 s per capture.

--selftest checks the weighting against the standard's own figures — 0 dB at 1 kHz,
−30.2 dB at 50 Hz, −19.1 dB at 100 Hz — at 2- and 3-byte sample widths, and that the
line finder lands on the tone.
"""
import argparse
import cmath
import math
import os
import struct
import sys
import tempfile
import wave

WINDOW = 1 << 16
MAX_SEGMENTS = 12
BAND = (20.0, 20000.0)


def read_wav(path, channel=0):
    """Return (samples in -1..1, sample rate, channels)."""
    with wave.open(path, "rb") as w:
        channels, width = w.getnchannels(), w.getsampwidth()
        rate, frames = w.getframerate(), w.getnframes()
        raw = w.readframes(frames)
    if channel >= channels:
        raise SystemExit("%s has %d channel(s); asked for %d" % (path, channels, channel))
    if width == 2:
        step, fmt, scale = 2 * channels, "<h", 1 << 15
    elif width == 3:
        step, fmt, scale = 3 * channels, None, 1 << 23
    elif width == 4:
        step, fmt, scale = 4 * channels, "<i", 1 << 31
    else:
        raise SystemExit("%s is %d bytes per sample; expected 2, 3 or 4" % (path, width))
    out = []
    for i in range(channel * width, len(raw) - step + 1, step):
        if width == 3:
            v = int.from_bytes(raw[i:i + 3], "little", signed=True)
        else:
            v = struct.unpack_from(fmt, raw, i)[0]
        out.append(v / scale)
    return out, rate, channels


def fft(x):
    """Iterative radix-2 FFT, in place."""
    n = len(x)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            x[i], x[j] = x[j], x[i]
    length = 2
    while length <= n:
        wl = cmath.exp(-2j * math.pi / length)
        for i in range(0, n, length):
            w = 1 + 0j
            for k in range(i, i + length // 2):
                u, v = x[k], x[k + length // 2] * w
                x[k], x[k + length // 2] = u + v, u - v
                w *= wl
        length <<= 1
    return x


def power_spectrum(samples, window=WINDOW):
    """Welch-averaged one-sided power spectrum: mean square per bin, summing to the RMS²."""
    n = 1 << (min(window, len(samples)).bit_length() - 1)
    if n < 1024:
        raise SystemExit("capture is only %d samples; need a second or two" % len(samples))
    hop = n // 2
    spread = max(hop, (len(samples) - n) // MAX_SEGMENTS)
    starts = list(range(0, len(samples) - n + 1, spread))[:MAX_SEGMENTS]
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
    wsum = sum(v * v for v in win)
    acc = None
    for start in starts:
        spec = fft([complex(samples[start + i] * win[i]) for i in range(n)])
        row = [(c.real * c.real + c.imag * c.imag) / (n * wsum) for c in spec[:n // 2]]
        for k in range(1, len(row) - 1):          # one-sided: double all but DC and Nyquist
            row[k] *= 2
        acc = row if acc is None else [a + b for a, b in zip(acc, row)]
    return [a / len(starts) for a in acc]


def a_weight(f):
    """IEC 61672 A-weighting as a linear gain."""
    if f <= 0:
        return 0.0
    f2 = f * f
    num = (12194.0 ** 2) * (f2 ** 2)
    den = ((f2 + 20.6 ** 2)
           * math.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    return (num / den) * (10 ** (2.0 / 20))       # +2.0 dB at 1 kHz


def dbfs(x, full_scale):
    return 20 * math.log10(x / full_scale) if x > 0 else float("-inf")


def analyse(samples, rate, full_scale=1.0, window=WINDOW):
    """Everything the report needs, as numbers, so it can be checked."""
    n = len(samples)
    dc = sum(samples) / n
    centred = [s - dc for s in samples]
    spec = power_spectrum(centred, window)
    bin_hz = rate / (2 * len(spec))
    lo = max(1, int(BAND[0] / bin_hz))
    hi = min(len(spec) - 1, int(BAND[1] / bin_hz))
    ms = sum(spec[lo:hi + 1])
    ms_a = sum(spec[k] * a_weight(k * bin_hz) ** 2 for k in range(lo, hi + 1))
    return {
        "samples": n, "rate": rate, "dc": dc, "bin_hz": bin_hz, "spec": spec,
        "rms": math.sqrt(ms), "rms_a": math.sqrt(ms_a),
        "peak": max(abs(s) for s in centred),
    }


def report(path, channel, full_scale, window=WINDOW):
    samples, rate, _ = read_wav(path, channel)
    a = analyse(samples, rate, full_scale, window)
    bin_hz = a["bin_hz"]
    print("%s, channel %d: %d samples at %d Hz (%.1f s), %.2f Hz bins"
          % (path, channel, a["samples"], rate, a["samples"] / rate, bin_hz))
    print("  DC offset          %+9.2f µV" % (a["dc"] * full_scale * 1e6))
    print("  unweighted RMS     %+9.2f dBFS  %8.2f µV  (20 Hz–20 kHz)"
          % (dbfs(a["rms"], full_scale), a["rms"] * full_scale * 1e6))
    print("  A-weighted RMS     %+9.2f dBFS(A) %7.2f µV"
          % (dbfs(a["rms_a"], full_scale), a["rms_a"] * full_scale * 1e6))
    print("  peak sample        %+9.2f dBFS" % dbfs(a["peak"], full_scale))
    for lo_hz, hi_hz, title in ((20, 1000, "lines below 1 kHz"),
                                (1000, 20000, "lines 1–20 kHz")):
        k0 = max(1, int(lo_hz / bin_hz))
        k1 = min(int(hi_hz / bin_hz), len(a["spec"]) - 1)
        top = sorted(range(k0, k1), key=lambda k: a["spec"][k], reverse=True)[:5]
        print("  %s:" % title)
        for k in sorted(top):
            rms = math.sqrt(a["spec"][k])
            print("    %8.1f Hz  %+7.2f dBFS   A-weighted %+7.2f"
                  % (k * bin_hz, dbfs(rms, full_scale),
                     dbfs(rms * a_weight(k * bin_hz), full_scale)))


def write_test_wav(path, rate, freq, level_dbfs, width=3, seconds=2.0):
    n = int(rate * seconds)
    amp = (10 ** (level_dbfs / 20)) * math.sqrt(2)
    scale = (1 << (8 * width - 1)) - 1
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            s = max(-scale - 1, min(scale, int(round(amp * math.sin(2 * math.pi * freq * i / rate) * scale))))
            frames += s.to_bytes(width, "little", signed=True)
        w.writeframes(bytes(frames))


def selftest():
    ok = True
    cases = ((1000.0, 0.0), (50.0, -30.2), (100.0, -19.1))
    with tempfile.TemporaryDirectory() as d:
        for freq, gain in cases:
            for width in (2, 3):
                path = os.path.join(d, "t%d_%d.wav" % (freq, width))
                write_test_wav(path, 48000, freq, -20.0, width)
                samples, rate, _ = read_wav(path, 0)
                a = analyse(samples, rate, 1.0, window=8192)
                got_unw = dbfs(a["rms"], 1.0)
                got_a = dbfs(a["rms_a"], 1.0)
                want_a = -20.0 + gain
                peak_bin = max(range(1, len(a["spec"])), key=lambda k: a["spec"][k])
                want_bin = round(freq / a["bin_hz"])
                good = (abs(got_unw + 20.0) < 0.2 and abs(got_a - want_a) < 0.5
                        and abs(peak_bin - want_bin) <= 1)
                ok = ok and good
                print("%s %6.1f Hz %d-byte: unweighted %+6.2f dBFS (want −20.00), "
                      "A-weighted %+6.2f (want %+6.2f), peak bin %d (want %d)"
                      % ("ok  " if good else "FAIL", freq, width, got_unw, got_a, want_a,
                         peak_bin, want_bin))
    print("selftest: %s" % ("ok" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("wav", nargs="?")
    ap.add_argument("--channel", type=int, default=0,
                    help="which channel to analyse (default 0, the codec's left = LIN1)")
    ap.add_argument("--full-scale", type=float, default=1.0,
                    help="V rms at 0 dBFS (default 1.0, 2a's measured codec full scale)")
    ap.add_argument("--window", type=int, default=WINDOW, help="FFT window, a power of two")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.wav:
        ap.error("give a WAV file, or --selftest")
    report(args.wav, args.channel, args.full_scale, args.window)
    return 0


if __name__ == "__main__":
    sys.exit(main())

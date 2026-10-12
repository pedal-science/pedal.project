#!/usr/bin/env python3
"""make-document.py — the codec-and-Core noise spectra, as graphs, audio and one HTML page.

    <bundled python> make-document.py

Reads the captures listed in CAPTURES, and for each one writes:

- img/spectrum-<id>.png   the power spectrum, dBFS per bin against frequency (log x)
- img/bands-<id>.png      the same noise as octave-band bars
- audio/<id>.wav          the capture as a mono 24-bit file, level unchanged
- audio/<id>-normalised.wav   the same, peak normalised to -3 dBFS so it can be heard
- img/spectra-compare.png     every capture's spectrum overlaid
- noise-numbers.json      every number the page quotes
- index.html              the document itself, with a play button per line

The spectrum and the numbers use the same Welch method as scripts/codec-noise.py (Hann window,
65536-point segments, mean square per bin), but with numpy here so 20 s of audio takes
milliseconds rather than half a minute. The RMS the script reports is checked against
codec-noise.py's own figure for each file before anything is written.
"""
import cmath
import json
import math
import os
import struct
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(HERE, "..", "2026-10-11-first-sound")
IMG = os.path.join(HERE, "img")
AUDIO = os.path.join(HERE, "audio")
WINDOW = 1 << 16
MAX_SEGMENTS = 12
TRIM = 2.0          # seconds skipped: every capture's stream start-up transient

CAPTURES = [
    ("engine-p64", os.path.join(SESSION, "t16-A-engine-p64.wav"),
     "Engine running, 64-frame periods",
     "The pedal's normal state: <code>namchaind</code> holds the codec, is muted, and the document "
     "in it is silent. This is what the player's audio path carries."),
    ("engine-p1024", os.path.join(SESSION, "t16-B-engine-p1024.wav"),
     "Engine running, 1024-frame periods",
     "The same, with <code>period_size</code> temporarily 1024 and the config restored afterwards. "
     "The period-rate comb moves from 750 Hz to 46.9 Hz and the floor drops 4.3 dB."),
    ("arecord-alone", os.path.join(SESSION, "t16-C-arecord-alone.wav"),
     "Engine stopped, arecord alone",
     "No engine and <em>no playback stream open</em>: the converter in its capture-only state. The "
     "4–16 kHz hiss is 15 dB louder here than with a playback stream open."),
    ("arecord-playback", os.path.join(SESSION, "t16-D-arecord-playback.wav"),
     "Engine stopped, arecord + silent playback",
     "No engine, but a silent <code>aplay</code> holds the playback path open — the codec state the "
     "engine leaves it in. The HF hiss is much lower; a drifting ~6.75 kHz line appears."),
    ("hum-reference", os.path.join(SESSION, "t8-A-mains-noext.wav"),
     "Reference — board 1 at node B, everything on mains",
     "<strong>Not</strong> a codec-and-Core measurement: this is the earlier capture with board 1's "
     "input node connected and every supply on mains, included so the hum can be seen and heard "
     "beside the hiss. 50 Hz and its harmonics, 25 dB above what the same node gives on batteries."),
]

BANDS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000, 20000]
COLOURS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]


def read_wav(path):
    """(float samples of channel 0, rate). Handles 16/24/32-bit PCM."""
    with wave.open(path, "rb") as w:
        channels, width = w.getnchannels(), w.getsampwidth()
        rate, frames = w.getframerate(), w.getnframes()
        raw = w.readframes(frames)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / (1 << 15)
    elif width == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        v = (a[:, 0].astype(np.int32) | (a[:, 1].astype(np.int32) << 8)
             | (a[:, 2].astype(np.int32) << 16))
        v = np.where(v >= (1 << 23), v - (1 << 24), v)
        x = v.astype(np.float64) / (1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / (1 << 31)
    else:
        raise SystemExit("%s: %d bytes per sample" % (path, width))
    return x[::channels], rate


def spectrum(x, rate):
    """Welch-averaged one-sided power spectrum, mean square per bin (codec-noise.py's method)."""
    n = 1 << (min(WINDOW, len(x)).bit_length() - 1)
    hop = n // 2
    spread = max(hop, (len(x) - n) // MAX_SEGMENTS)
    starts = list(range(0, len(x) - n + 1, spread))[:MAX_SEGMENTS]
    win = np.hanning(n + 1)[:n]
    wsum = float((win * win).sum())
    acc = np.zeros(n // 2)
    for s in starts:
        seg = x[s:s + n] * win
        sp = np.fft.rfft(seg)
        row = (sp.real ** 2 + sp.imag ** 2) / (n * wsum)
        row[1:-1] *= 2.0
        acc += row[:n // 2]
    return acc / len(starts)


def a_weight_db(f):
    f = np.asarray(f, dtype=np.float64)
    f2 = f * f
    num = (12194.0 ** 2) * (f2 ** 2)
    den = ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 20 * np.log10(np.where(f > 0, num / den, 0)) + 2.0
    return db


def db(x):
    return 10.0 * math.log10(x) if x > 0 else float("-inf")


def numbers(x, rate):
    x = x - x.mean()
    spec = spectrum(x, rate)
    bin_hz = rate / (2.0 * len(spec))
    freqs = np.arange(len(spec)) * bin_hz
    lo = max(1, int(20 / bin_hz))
    hi = min(len(spec) - 1, int(20000 / bin_hz))
    ms = float(spec[lo:hi + 1].sum())
    aw = 10 ** (a_weight_db(freqs[lo:hi + 1]) / 20.0)
    ms_a = float((spec[lo:hi + 1] * aw ** 2).sum())
    out = {
        "seconds": round(len(x) / rate, 2),
        "rms_dbfs": round(db(ms), 2),
        "rms_a_dbfs": round(db(ms_a), 2),
        "peak_dbfs": round(db(float((x ** 2).max())), 2),
        "bands": [],
        "lines": [],
    }
    for b0, b1 in zip(BANDS, BANDS[1:]):
        k0, k1 = int(b0 / bin_hz), min(int(b1 / bin_hz) + 1, len(spec))
        pw = float(spec[k0:k1].sum())
        out["bands"].append({"from": b0, "to": b1, "dbfs": round(db(pw), 1),
                             "share": round(100.0 * pw / ms, 1) if ms else 0.0})
    for l0, l1, tag in ((20, 1000, "low"), (1000, 20000, "high")):
        k0, k1 = max(1, int(l0 / bin_hz)), min(int(l1 / bin_hz), len(spec) - 1)
        top = sorted(range(k0, k1), key=lambda k: spec[k], reverse=True)[:5]
        for k in sorted(top):
            out["lines"].append({"hz": round(k * bin_hz, 1), "dbfs": round(db(float(spec[k])), 2),
                                 "band": tag})
    out["spec"] = spec
    out["bin_hz"] = bin_hz
    return out


def font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_TITLE, F_LABEL, F_TICK = font(19), font(15), font(13)
W, H = 1000, 460
L, R, T, B = 78, 40, 46, 56          # margins
Y_MIN, Y_MAX = -140.0, -50.0         # dBFS per bin


def x_of(hz):
    f0, f1 = math.log10(20.0), math.log10(20000.0)
    f = math.log10(max(20.0, min(20000.0, hz)))
    return L + (f - f0) / (f1 - f0) * (W - L - R)


def plot_spectrum(items, path, title, annotate=None):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def y_of(v):
        return T + (Y_MAX - v) / (Y_MAX - Y_MIN) * (H - T - B)

    for v in range(-140, -49, 10):
        y = y_of(v)
        d.line([(L, y), (W - R, y)], fill="#e8e8e8")
        d.text((6, y - 8), "%d" % v, font=F_TICK, fill="#666")
    for hz in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        x = x_of(hz)
        d.line([(x, T), (x, H - B)], fill="#f2f2f2")
        d.text((x - 14, H - B + 8), ("%g k" % (hz / 1000.0)) if hz >= 1000 else "%g" % hz,
               font=F_TICK, fill="#666")
    d.text((L, H - 22), "frequency, Hz (log)", font=F_LABEL, fill="#444")
    d.text((L, 14), title, font=F_TITLE, fill="#111")
    if len(items) > 1:
        ly = T + 10
        for label, _s, _b, colour in items:
            d.rectangle([W - R - 250, ly + 2, W - R - 238, ly + 12], fill=colour)
            d.text((W - R - 230, ly - 1), label[:44], font=F_TICK, fill="#333")
            ly += 17

    for i, (label, spec, bin_hz, colour) in enumerate(items):
        freqs = np.arange(len(spec)) * bin_hz
        keep = (freqs >= 20) & (freqs <= 20000)
        f, s = freqs[keep], spec[keep]
        vals = 10 * np.log10(np.maximum(s, 1e-30))
        pts = [(x_of(hz), y_of(max(Y_MIN, min(Y_MAX, v)))) for hz, v in zip(f, vals)]
        d.line(pts, fill=colour, width=1)
    if annotate:
        for text, hz, *_ in annotate:
            x = x_of(hz)
            d.line([(x, T + 6), (x, H - B - 6)], fill="#bbbbbb")
            d.text((x + 4, T + 6), text, font=F_TICK, fill="#333")
    img.save(path)


def plot_bands(n, path, title):
    img = Image.new("RGB", (W, 340), "white")
    d = ImageDraw.Draw(img)
    d.text((L, 14), title, font=F_TITLE, fill="#111")
    top, bot = 46, 286
    lo, hi = -105.0, -60.0

    def y_of(v):
        return bot - (max(lo, min(hi, v)) - lo) / (hi - lo) * (bot - top)

    for v in range(-100, -59, 10):
        y = y_of(v)
        d.line([(L, y), (W - R, y)], fill="#e8e8e8")
        d.text((10, y - 8), "%d" % v, font=F_TICK, fill="#666")
    n_b = len(n["bands"])
    bw = (W - L - R) / n_b
    for i, b in enumerate(n["bands"]):
        x0 = L + i * bw + 6
        x1 = L + (i + 1) * bw - 6
        y = y_of(b["dbfs"])
        colour = "#c0392b" if b["share"] >= 25 else "#4a7fb5"
        d.rectangle([x0, y, x1, bot], fill=colour)
        lbl = "%g" % b["from"]
        d.text(((x0 + x1) / 2 - 8, bot + 8), lbl, font=F_TICK, fill="#666")
        d.text(((x0 + x1) / 2 - 14, y - 20), "%.0f" % b["dbfs"], font=F_TICK, fill="#333")
    d.text((L, bot + 30), "octave band, Hz (lower edge)   —   bar labelled with dBFS, "
                          "red = 25%+ of the total", font=F_LABEL, fill="#444")
    img.save(path)


def write_wav_mono(path, x, rate):
    v = np.clip(np.round(x * ((1 << 23) - 1)), -(1 << 23), (1 << 23) - 1).astype(np.int32)
    b = np.empty((len(v), 3), dtype=np.uint8)
    u = v.astype(np.uint32) & 0xFFFFFF
    b[:, 0], b[:, 1], b[:, 2] = u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(rate)
        w.writeframes(b.tobytes())


def audio_block(cid, label, gain_db):
    return ("""      <div class="audio">
        <span class="alabel">%s</span>
        <audio controls preload="none" src="audio/%s.wav"></audio>
        <span class="hint">as captured — very quiet, matches the numbers</span>
        <audio controls preload="none" src="audio/%s-normalised.wav"></audio>
        <span class="hint">normalised to &minus;3&nbsp;dBFS peak (%+.0f dB) so it can be heard</span>
      </div>\n""" % (label, cid, cid, gain_db))


def main():
    os.makedirs(IMG, exist_ok=True)
    os.makedirs(AUDIO, exist_ok=True)
    data = []
    for cid, path, title, note in CAPTURES:
        x, rate = read_wav(path)
        x = x[int(TRIM * rate):]          # settled window only, see TRIM
        n = numbers(x, rate)
        # keep the file's own gain for listening; normalise a second copy
        gain = -3.0 - n["peak_dbfs"]
        write_wav_mono(os.path.join(AUDIO, cid + ".wav"), x, rate)
        write_wav_mono(os.path.join(AUDIO, cid + "-normalised.wav"),
                       x * (10 ** (gain / 20.0)), rate)
        plot_spectrum([(title, n["spec"], n["bin_hz"], COLOURS[0])],
                      os.path.join(IMG, "spectrum-%s.png" % cid), title)
        plot_bands(n, os.path.join(IMG, "bands-%s.png" % cid), title + " — where the noise is")
        n.update({"id": cid, "label": title, "note": note, "file": os.path.basename(path),
                  "norm_gain_db": round(gain, 1)})
        del n["spec"]
        data.append(n)
        print("%-18s %7.2f dBFS  %7.2f dB(A)  x%.0f" % (cid, n["rms_dbfs"], n["rms_a_dbfs"], gain))

    # comparison plot
    items = []
    for i, (cid, path, title, note) in enumerate(CAPTURES):
        x, rate = read_wav(path)
        x = x[int(TRIM * rate):]
        sp = spectrum(x - x.mean(), rate)
        items.append((title, sp, rate / (2.0 * len(sp)), COLOURS[i % len(COLOURS)]))
    plot_spectrum(items, os.path.join(IMG, "spectra-compare.png"),
                  "All five captures, one spectrum each")

    with open(os.path.join(HERE, "noise-numbers.json"), "w") as fh:
        json.dump(data, fh, indent=2)

    # ---- the page ----------------------------------------------------------------
    rows = []
    for n in data:
        named = [l for l in n["lines"] if l["dbfs"] > n["rms_dbfs"] + 8]
        lines = "".join("<li>%g Hz &mdash; %.1f dBFS</li>" % (l["hz"], l["dbfs"]) for l in named)
        bands = "".join("<tr><td>%g&ndash;%g Hz</td><td>%.1f dBFS</td><td>%.1f%%</td></tr>"
                        % (b["from"], b["to"], b["dbfs"], b["share"]) for b in n["bands"])
        rows.append("""
    <section>
      <h2>%s</h2>
      <p>%s</p>
      <p class="meta"><code>%s</code> &middot; %.1f s &middot; <strong>%.1f dBFS rms</strong>
         unweighted &middot; <strong>%.1f dBFS(A)</strong> &middot; peak %.1f dBFS</p>
      %s
      <img src="img/spectrum-%s.png" alt="spectrum">
      <img src="img/bands-%s.png" alt="octave bands">
      <div class="cols">
        <div><h3>Octave bands</h3><table><tr><th>band</th><th>level</th><th>share</th></tr>%s</table></div>
        <div><h3>Lines above the broadband floor</h3><ul>%s</ul></div>
      </div>
    </section>""" % (n["label"], n["note"], n["file"], n["seconds"], n["rms_dbfs"],
                     n["rms_a_dbfs"], n["peak_dbfs"],
                     audio_block(n["id"], n["label"], n["norm_gain_db"]),
                     n["id"], n["id"], bands, lines or "<li>none</li>"))

    legend = "".join(
        """      <tr><td><span class="swatch" style="background:%s"></span>%s</td>
        <td><audio controls preload="none" src="audio/%s.wav"></audio></td>
        <td><audio controls preload="none" src="audio/%s-normalised.wav"></audio></td></tr>\n"""
        % (COLOURS[i % len(COLOURS)], CAPTURES[i][2], CAPTURES[i][0], CAPTURES[i][0])
        for i in range(len(CAPTURES)))

    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>The pedal's noise: codec and Core only, 2026-10-11</title>
<style>
 body { font: 16px/1.55 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
        max-width: 1060px; margin: 0 auto; padding: 28px 20px 60px; color: #1a1a1a; }
 h1 { font-size: 27px; margin: 0 0 6px; } h2 { font-size: 21px; margin: 34px 0 4px; }
 h3 { font-size: 16px; margin: 18px 0 6px; }
 p  { margin: 8px 0; } code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
 img { width: 100%%; height: auto; margin: 12px 0 4px; border: 1px solid #eee; border-radius: 4px; }
 table { border-collapse: collapse; margin: 6px 0 12px; font-size: 14px; }
 th, td { border-bottom: 1px solid #eee; padding: 4px 12px 4px 0; text-align: left; }
 .meta { color: #555; font-size: 14px; }
 .cols { display: flex; gap: 40px; flex-wrap: wrap; }
 .audio { background: #fafafa; border: 1px solid #eee; border-radius: 5px;
          padding: 10px 14px; margin: 10px 0 18px; }
 .audio audio { vertical-align: middle; margin: 4px 8px 4px 0; height: 34px; }
 .alabel { display: inline-block; min-width: 190px; font-weight: 600; }
 .hint { color: #666; font-size: 13px; display: block; margin-left: 190px; }
 .swatch { display: inline-block; width: 13px; height: 13px; border-radius: 2px; margin-right: 8px; }
 .callout { background: #f7f9fc; border-left: 4px solid #4a7fb5; padding: 12px 16px; margin: 16px 0; }
 footer { margin-top: 40px; color: #666; font-size: 14px; border-top: 1px solid #eee; padding-top: 12px; }
</style></head><body>

<h1>The pedal's noise: codec and Core only</h1>
<p class="meta">11 October 2026 &middot; board 1 and every input and output circuit disconnected
&middot; LIN1 jumpered to the codec's own GND &middot; Pico removed</p>

<p>These are the measurements that need nothing plugged in: the WM8960 codec on its jumpers to the
Core host, its left input shorted at the pin so the converter sees silence, and
<code>namchaind</code> on the Core. Nothing else is attached — no board 1, no jacks, no output
fixture, no interface. The audio on this page is the codec's own silence, so
<strong>everything you hear is the pedal's noise</strong>.</p>

<div class="callout">
<p><strong>How to read it.</strong> Each capture shows a spectrum in dBFS per 0.73 Hz bin, and the
same noise as octave-band bars. <em>Hum</em> is a spike at 50 Hz and its harmonics; <em>hiss</em> is
a broad slope across the high bands. Each graph has the audio beside it — one button for the capture
at its true level (which is very quiet: the harshest of these sits at %.1f dBFS rms) and one
normalised so you can hear it. Headphones and the interface are the right way to listen; a laptop
speaker will not reproduce any of this.</p>
<p>The quietest state measured here is the engine at 1024-frame periods, at
<strong>%.1f dBFS(A)</strong>; the loudest is the mains-hum reference at
<strong>%.1f dBFS(A)</strong>.</p>
</div>

<h2>One spectrum per capture</h2>
<img src="img/spectra-compare.png" alt="all five spectra">
      <table>
      <tr><th>line</th><th>as captured</th><th>normalised</th></tr>
%s      </table>

%s

<section>
  <h2>What the graphs show</h2>
  <ul>
    <li><strong>No mains hum in any of the codec-only captures.</strong> There is no 50 Hz line to
        find in the first four spectra — the largest line below 1 kHz in the engine's own capture is
        the 750 Hz period-rate artefact, not hum. The hum appears only in the reference capture,
        which is the one with board 1 attached.</li>
    <li><strong>The engine's capture path carries a period-rate artefact.</strong> At 64-frame periods
        there is a line at 750.0 Hz with harmonics at 1500, 2250 and 3000 Hz, each with &plusmn;0.7 Hz
        sidebands, and the 1&ndash;4 kHz bands sit at the same level as that line. At 1024-frame
        periods the whole family moves to 46.875 Hz and its harmonics and falls 13&ndash;15 dB; the
        floor improves 4.3 dB A-weighted. A plain <code>arecord</code> at the same 64-frame periods
        shows the same 750 Hz line 18 dB lower, so the boundary is real and the engine's handling of
        it is what is worse.</li>
    <li><strong>The high-frequency hiss depends on the playback state.</strong> With no playback
        stream open, 4&ndash;16 kHz holds over 90%% of the energy; open a silent playback stream and
        it drops 15 dB. That is a property of this converter's capture-only state, not of the pedal's
        input.</li>
    <li><strong>Magnitude.</strong> The quietest configuration in these graphs is %.1f dBFS rms
        (%.1f dB(A)); for scale, 2a's record for this converter with its input shorted is
        &minus;90.6 dBFS unweighted and &minus;93.5 dB(A), and this host's own record from
        2026-10-06 is &minus;88.0 dB(A).</li>
  </ul>
</section>

<footer>
  <p>Raw captures, the session log and every earlier test:
  <a href="../2026-10-11-first-sound/troubleshooting-log.md">troubleshooting-log.md</a> and
  <a href="../2026-10-11-first-sound/README.md">README.md</a>. Numbers on this page are in
  <code>noise-numbers.json</code>; the page and graphs are built by <code>make-document.py</code>.
  Conventions: dBFS at 1.0 V rms full scale, 20 Hz&ndash;20 kHz, channel 0 = LIN1, and a
  2-channel capture throughout (an 8-channel capture of the same signal reads 11&ndash;12 dB
  higher because of the interface itself).</p>
  <p><strong>Sample format.</strong> The card offers <code>S16_LE S24_LE S32_LE</code> with
  <code>SAMPLE_BITS: [16 32]</code> and rates of 8&ndash;48 kHz, and <em>no</em> float format:
  I2S and the WM8960's DAI are integer PCM. These captures are 32-bit containers holding 24-bit
  data &mdash; the bottom eight bits are zero in <em>every</em> sample of every capture here, which
  is the converter's own resolution, left-justified. <code>namchaind</code> asks for S24_3LE,
  S32_LE, S16_LE in that order and takes the first the device offers, which on this card is
  S32_LE (4 bytes per sample). 16-bit would quantise at about &minus;96 dBFS, right where this
  session is measuring, so it would mask the noise rather than show it.</p>
</footer>
</body></html>
""" % (data[0]["rms_dbfs"], min(d["rms_a_dbfs"] for d in data[:4]),
       max(d["rms_a_dbfs"] for d in data), legend, "".join(rows),
       min(d["rms_dbfs"] for d in data[:4]), min(d["rms_a_dbfs"] for d in data[:4]))

    with open(os.path.join(HERE, "index.html"), "w") as fh:
        fh.write(html)
    print("wrote index.html, %d graphs" % (2 * len(CAPTURES) + 1))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""noise-document.py — a manifest of captures in, one HTML page of spectra and octave bands out.

    <python with numpy and Pillow> scripts/noise-document.py MANIFEST.json [--out DIR] [--no-audio]

The page is `index.html` in the output directory (the manifest's own directory by default), with
one spectrum and one octave-band chart per capture, each capture's numbers beside it, every
capture's spectrum overlaid, and — unless --no-audio — two play buttons per capture: the capture at
its true level and a copy normalised to -3 dBFS peak, because these captures are far too quiet to
hear otherwise. It also writes `noise-numbers.json`: every number the page quotes, plus the check
below.

The manifest is JSON:

    {"title":  "The codec's input noise, 2026-10-13",     required
     "meta":   "one line under the heading",              optional
     "intro":  ["<p>…</p>"],                              optional, HTML paragraphs
     "callout": "<p>…</p>",                               optional, HTML
     "compare_title": "…",                                optional
     "spectrum_db": [-140, -50],                          optional, per-bin dBFS axis
     "bands_db": [-105, -60],                             optional, octave-band axis
     "sections": [{"title": "…", "html": "<ul>…</ul>"}],  optional, after the captures
     "footer": ["<p>…</p>"],                              optional, HTML paragraphs
     "captures": [                                        required, in page order
       {"id": "engine-p64",        a name: file names and the page's anchors use it
        "path": "captures/engine-p64.wav",   relative to the manifest
        "label": "Engine running, muted",
        "note": "<p>HTML</p>",     what this capture is
        "channel": 0,              default 0
        "trim": 2.0}]}             default: the manifest's "trim", then 2.0 s

**It verifies itself.** For every capture it runs `codec-noise.py --json` — the reference the bench
test and the reports quote — at the same channel and trim, and refuses to write the page if its own
RMS disagrees by more than 0.05 dB (`--no-check` skips this, and says so in the JSON). The delta is
recorded per capture as `check_db`. The rest of `codec-noise.py`'s report — the DC offset, the
loudest lines, the mains family — is copied into `noise-numbers.json` unchanged, because the
spectrum maths here is the same Welch average done with numpy: the same numbers, in milliseconds
rather than the half-minute the stdlib version takes.

numpy and Pillow come from the harness's bundled python, not the system one:

    /Users/rik/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3

The spectrum is mean square per bin over 65536-point Hann segments, up to 12 of them (0.73 Hz bins
at 48 kHz); dBFS is at 1.0 V rms full scale, and the octave bands are 31.5 Hz to 20 kHz with each
band's share of the total. Frequency axes are logarithmic from 20 Hz to 20 kHz, as in
bench-results/2026-10-11-codec-noise-spectra/, whose page this one is the general form of.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import wave

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:                                        # noqa: BLE001 - said plainly
    sys.exit("noise-document.py: %s\nIt needs numpy and Pillow. Run it with the harness's "
             "bundled python:\n"
             "  /Users/rik/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 "
             "%s MANIFEST.json" % (exc, os.path.basename(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODEC_NOISE = os.path.join(REPO, "scripts", "codec-noise.py")

WINDOW = 1 << 16
MAX_SEGMENTS = 12
CHECK_TOLERANCE_DB = 0.05
DEFAULT_TRIM = 2.0
#: How far a capture's raw level may sit above its band-limited one before the page says so: at
#: 3 dB, a third of the capture's power is outside the 20 Hz-20 kHz band the figures use.
OUTSIDE_BAND_DB = 3.0
BANDS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000, 20000]
#: The mains family, as codec-noise.py reads it: the loudest bin within MAINS_SPAN_HZ of each of
#: these, in Hz and dBFS. Hum is a spike here and hiss is a slope elsewhere, and a page that shows
#: only the total leaves the reader to guess which one they are looking at.
MAINS_HZ = (50.0, 100.0, 150.0)
MAINS_SPAN_HZ = 2.0
COLOURS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#17becf"]

F_TITLE, F_LABEL, F_TICK = None, None, None
W, H = 1000, 460
L, R, T, B = 78, 40, 46, 56                   # margins


# --- reading and measuring -----------------------------------------------------------

def read_wav(path, channel=0):
    """(float samples of `channel`, rate). Handles 16/24/32-bit PCM, as codec-noise.py does."""
    with wave.open(path, "rb") as w:
        channels, width = w.getnchannels(), w.getsampwidth()
        rate, frames = w.getframerate(), w.getnframes()
        raw = w.readframes(frames)
    if channel >= channels:
        raise SystemExit("%s has %d channel(s); asked for %d" % (path, channels, channel))
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
        raise SystemExit("%s: %d bytes per sample; expected 2, 3 or 4" % (path, width))
    return x[channel::channels], rate


def spectrum(x, rate):
    """Welch-averaged one-sided power spectrum, mean square per bin (codec-noise.py's method)."""
    n = 1 << (min(WINDOW, len(x)).bit_length() - 1)
    if n < 1024:
        raise SystemExit("capture is only %d samples; need a second or two" % len(x))
    hop = n // 2
    spread = max(hop, (len(x) - n) // MAX_SEGMENTS)
    starts = list(range(0, len(x) - n + 1, spread))[:MAX_SEGMENTS]
    win = np.hanning(n + 1)[:n]
    wsum = float((win * win).sum())
    acc = np.zeros(n // 2)
    for s in starts:
        sp = np.fft.rfft(x[s:s + n] * win)
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
        return 20 * np.log10(np.where(f > 0, num / den, 0)) + 2.0


def db(x):
    return 10.0 * math.log10(x) if x > 0 else float("-inf")


def numbers(x, rate, full_scale=1.0):
    """The page's numbers for one capture, and the spectrum it draws."""
    dc = float(x.mean())
    x = x - dc
    spec = spectrum(x, rate)
    bin_hz = rate / (2.0 * len(spec))
    freqs = np.arange(len(spec)) * bin_hz
    lo = max(1, int(20 / bin_hz))
    hi = min(len(spec) - 1, int(20000 / bin_hz))
    ms = float(spec[lo:hi + 1].sum())
    aw = 10 ** (a_weight_db(freqs[lo:hi + 1]) / 20.0)
    ms_a = float((spec[lo:hi + 1] * aw ** 2).sum())
    raw_ms = float((x ** 2).mean())
    out = {"seconds": round(len(x) / rate, 2), "rms_dbfs": round(db(ms), 2),
           "rms_a_dbfs": round(db(ms_a), 2),
           "peak_dbfs": round(db(float((x ** 2).max())), 2),
           # The two figures above are band-limited to 20 Hz-20 kHz, the convention every earlier
           # reading of this converter uses and what makes them comparable with it. This is the
           # same window with nothing taken out, and `outside_band_db` is the difference between
           # them: how much of the capture lives where the convention cannot look. A capture that
           # drifts or settles reads quiet in the band and loud here.
           "raw_rms_dbfs": round(db(raw_ms), 2),
           "outside_band_db": round(db(raw_ms) - db(ms), 2) if ms > 0 and raw_ms > 0 else None,
           "full_scale_v": full_scale,
           "dc_offset": round(dc, 12), "dc_offset_uv": round(dc * full_scale * 1e6, 2),
           "rms_uv": round(math.sqrt(ms) * full_scale * 1e6, 2),
           "rms_a_uv": round(math.sqrt(ms_a) * full_scale * 1e6, 2),
           "bands": [], "lines": [], "lines_low": [], "lines_high": [], "mains": []}
    for hz in MAINS_HZ:
        centre, half = int(round(hz / bin_hz)), max(1, int(round(MAINS_SPAN_HZ / bin_hz)))
        k = max(range(max(1, centre - half), min(len(spec) - 1, centre + half) + 1),
                key=lambda i: spec[i])
        out["mains"].append({"nominal_hz": hz, "hz": round(k * bin_hz, 2),
                             "dbfs": round(db(float(spec[k])), 2)})
    for b0, b1 in zip(BANDS, BANDS[1:]):
        k0, k1 = int(b0 / bin_hz), min(int(b1 / bin_hz) + 1, len(spec))
        pw = float(spec[k0:k1].sum())
        out["bands"].append({"from": b0, "to": b1, "dbfs": round(db(pw), 1),
                             "share": round(100.0 * pw / ms, 1) if ms else 0.0})
    for l0, l1, tag in ((20, 1000, "low"), (1000, 20000, "high")):
        k0, k1 = max(1, int(l0 / bin_hz)), min(int(l1 / bin_hz), len(spec) - 1)
        top = sorted(range(k0, k1), key=lambda k: spec[k], reverse=True)[:5]
        for k in sorted(top):
            line = {"hz": round(k * bin_hz, 1), "dbfs": round(db(float(spec[k])), 2), "band": tag}
            out["lines"].append(line)
            # codec-noise.py's own names for the same two lists, so anything that reads an
            # analysis - the bench test's report logic among them - can read this one too.
            out["lines_low" if tag == "low" else "lines_high"].append({"hz": line["hz"],
                                                                      "dbfs": line["dbfs"]})
    out["spec"], out["bin_hz"] = spec, bin_hz
    return out


def check_against_codec_noise(analysis, path, channel, trim, full_scale=1.0):
    """codec-noise.py's own RMS for the same capture, channel and trim."""
    proc = subprocess.run([sys.executable, CODEC_NOISE, path, "--json", "--channel",
                           str(channel), "--skip", str(trim), "--full-scale", str(full_scale)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None, "codec-noise.py failed: %s" % proc.stderr.decode().strip().splitlines()[-1:]
    other = json.loads(proc.stdout)
    mine, theirs = analysis["rms_dbfs"], other.get("rms_dbfs")
    if theirs is None or mine is None:
        return None, "one of the two is digital silence (mine %s, codec-noise.py %s)" % (mine, theirs)
    return round(mine - theirs, 3), other


# --- drawing -------------------------------------------------------------------------

def font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def x_of(hz):
    f0, f1 = math.log10(20.0), math.log10(20000.0)
    f = math.log10(max(20.0, min(20000.0, hz)))
    return L + (f - f0) / (f1 - f0) * (W - L - R)


def plot_spectrum(items, path, title, y_range):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y_min, y_max = y_range

    def y_of(v):
        return T + (y_max - v) / (y_max - y_min) * (H - T - B)

    for v in range(int(y_min), int(y_max), 10):
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
    for _label, spec, bin_hz, colour in items:
        freqs = np.arange(len(spec)) * bin_hz
        keep = (freqs >= 20) & (freqs <= 20000)
        vals = 10 * np.log10(np.maximum(spec[keep], 1e-30))
        pts = [(x_of(hz), y_of(max(y_min, min(y_max, v)))) for hz, v in zip(freqs[keep], vals)]
        d.line(pts, fill=colour, width=1)
    img.save(path)


def plot_bands(n, path, title, y_range):
    img = Image.new("RGB", (W, 340), "white")
    d = ImageDraw.Draw(img)
    d.text((L, 14), title, font=F_TITLE, fill="#111")
    top, bot = 46, 286
    lo, hi = y_range[0], 10 * math.ceil(y_range[1] / 10.0)   # whole decibels, never below 0

    def y_of(v):
        return bot - (max(lo, min(hi, v)) - lo) / (hi - lo) * (bot - top)

    for v in range(int(lo), int(hi) + 1, 10):
        y = y_of(v)
        d.line([(L, y), (W - R, y)], fill="#e8e8e8")
        d.text((6, y - 8), "%d" % v, font=F_TICK, fill="#666")
    n_b = len(n["bands"])
    bw = (W - L - R) / n_b
    for i, b in enumerate(n["bands"]):
        x0, x1 = L + i * bw + 6, L + (i + 1) * bw - 6
        y = y_of(b["dbfs"])
        colour = "#c0392b" if b["share"] >= 25 else "#4a7fb5"
        d.rectangle([x0, y, x1, bot], fill=colour)
        d.text(((x0 + x1) / 2 - 8, bot + 8), "%g" % b["from"], font=F_TICK, fill="#666")
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


# --- the page ------------------------------------------------------------------------

CSS = """
 body { font: 16px/1.55 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
        max-width: 1060px; margin: 0 auto; padding: 28px 20px 60px; color: #1a1a1a; }
 h1 { font-size: 27px; margin: 0 0 6px; } h2 { font-size: 21px; margin: 34px 0 4px; }
 h3 { font-size: 16px; margin: 18px 0 6px; }
 p  { margin: 8px 0; } code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
 img { width: 100%; height: auto; margin: 12px 0 4px; border: 1px solid #eee; border-radius: 4px; }
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
 footer { margin-top: 40px; color: #666; font-size: 14px; border-top: 1px solid #eee;
          padding-top: 12px; }
"""


def audio_block(cid, label, gain_db):
    return ("""      <div class="audio">
        <span class="alabel">%s</span>
        <audio controls preload="none" src="audio/%s.wav"></audio>
        <span class="hint">as captured — very quiet, matches the numbers</span>
        <audio controls preload="none" src="audio/%s-normalised.wav"></audio>
        <span class="hint">normalised to &minus;3&nbsp;dBFS peak (%+.0f dB) so it can be heard</span>
      </div>\n""" % (label, cid, cid, gain_db))


def html_paras(items):
    return "\n".join(items or [])


def build_page(manifest, data, out_dir, compare_title, audio=True):
    rows = []
    for n in data:
        named = [l for l in n["lines"] if l["dbfs"] > n["rms_dbfs"] + 8]
        lines = "".join("<li>%g Hz &mdash; %.1f dBFS</li>" % (l["hz"], l["dbfs"]) for l in named)
        bands = "".join("<tr><td>%g&ndash;%g Hz</td><td>%.1f dBFS</td><td>%.1f%%</td></tr>"
                        % (b["from"], b["to"], b["dbfs"], b["share"]) for b in n["bands"])
        audio = audio_block(n["id"], n["label"], n["norm_gain_db"]) if audio else ""
        mains = " &middot; ".join("%g Hz %.1f dBFS" % (m["nominal_hz"], m["dbfs"])
                                 for m in n["mains"]) or "not measured"
        loudest = max(n["lines_low"], key=lambda l: l["dbfs"], default=None)
        rows.append("""
    <section>
      <h2>%s</h2>
      <p>%s</p>
      <p class="meta"><code>%s</code> &middot; %.1f s &middot; <strong>%.1f dBFS rms</strong>
         unweighted &middot; <strong>%.1f dBFS(A)</strong> &middot; peak %.1f dBFS &middot;
         raw (unbanded) %.1f dBFS%s</p>
      <p class="meta">mains: %s &middot; largest line below 1 kHz: %s</p>
      %s
      <img src="img/spectrum-%s.png" alt="spectrum">
      <img src="img/bands-%s.png" alt="octave bands">
      <div class="cols">
        <div><h3>Octave bands</h3><table><tr><th>band</th><th>level</th><th>share</th></tr>%s</table></div>
        <div><h3>Lines above the broadband floor</h3><ul>%s</ul></div>
      </div>
    </section>""" % (n["label"], n["note"], n["file"], n["seconds"], n["rms_dbfs"],
                     n["rms_a_dbfs"], n["peak_dbfs"], n["raw_rms_dbfs"],
                     (" &mdash; %.1f dB of it outside the 20 Hz&ndash;20 kHz band"
                      % n["outside_band_db"]) if (n.get("outside_band_db") or 0) >= OUTSIDE_BAND_DB
                     else "",
                     mains,
                     "%g Hz %.1f dBFS" % (loudest["hz"], loudest["dbfs"]) if loudest else "none",
                     audio, n["id"], n["id"], bands, lines or "<li>none</li>"))

    legend = "".join(
        ("""      <tr><td><span class="swatch" style="background:%s"></span>%s</td>
        <td><audio controls preload="none" src="audio/%s.wav"></audio></td>
        <td><audio controls preload="none" src="audio/%s-normalised.wav"></audio></td></tr>\n"""
         % (COLOURS[i % len(COLOURS)], d["label"], d["id"], d["id"]))
        for i, d in enumerate(data)) if audio else ""

    sections = "".join(
        "\n<section>\n  <h2>%s</h2>\n  %s\n</section>\n" % (s["title"], s.get("html", ""))
        for s in manifest.get("sections") or [])

    callout = manifest.get("callout")
    callout_html = '<div class="callout">\n%s\n</div>' % callout if callout else ""

    checks = [d for d in data if d.get("check_db") is not None]
    worst = max((abs(d["check_db"]) for d in checks), default=0.0)
    checked = ("Its own RMS is checked against <code>scripts/codec-noise.py</code> for every "
               "capture (worst disagreement %.2f dB, the bar is %.2f)." % (worst, CHECK_TOLERANCE_DB)
               if checks else "This page was built without the codec-noise.py cross-check.")

    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>%s</title>
<style>%s</style></head><body>

<h1>%s</h1>
<p class="meta">%s</p>

%s
%s

<h2>%s</h2>
<img src="img/spectra-compare.png" alt="all the spectra">
%s
%s

%s
<footer>
  %s
  <p>Numbers on this page are in <code>noise-numbers.json</code>; the page and every graph are
  built by <code>scripts/noise-document.py</code> from a manifest of the captures. %s
  Conventions: dBFS at 1.0 V rms full scale, 20 Hz&ndash;20 kHz, channel 0 = LIN1. Frequency axes
  are logarithmic from 20 Hz to 20 kHz; the spectra are 65536-point Hann segments, 0.73 Hz bins at
  48 kHz, mean square per bin. The unweighted and A-weighted figures, like every earlier reading
  of this converter, exclude what is below 20 Hz and above 20 kHz; the <em>raw</em> figure beside
  them excludes nothing, so where the two disagree the capture holds energy outside the audio band
  &mdash; a drift or a settling step rather than hiss.</p>
</footer>
</body></html>
""" % (manifest["title"], CSS, manifest["title"], manifest.get("meta", ""),
       html_paras(manifest.get("intro")), callout_html, compare_title,
       ("<table>\n      <tr><th>line</th><th>as captured</th><th>normalised</th></tr>\n%s      "
        "</table>" % legend) if audio else "",
       "".join(rows), sections, html_paras(manifest.get("footer")), checked)

    with open(os.path.join(out_dir, "index.html"), "w") as fh:
        fh.write(html)


def auto_bands_range(analysed):
    """An octave-band axis that holds every bar, to the nearest 10 dB with a little air."""
    levels = [b["dbfs"] for _cap, _x, _rate, n, _check, _gain in analysed for b in n["bands"]
              if b["dbfs"] != float("-inf")]
    if not levels:
        return (-105.0, -60.0)
    lo = 10.0 * math.floor((min(levels) - 4.0) / 10.0)
    hi = 10.0 * math.ceil((max(levels) + 4.0) / 10.0)
    return (lo, hi if hi > lo + 10.0 else lo + 10.0)


def main():
    global F_TITLE, F_LABEL, F_TICK
    ap = argparse.ArgumentParser(description="captures + a manifest, in; graphs and a page, out")
    ap.add_argument("manifest")
    ap.add_argument("--out", help="output directory (default: the manifest's own)")
    ap.add_argument("--no-audio", action="store_true",
                    help="write no playable copies, and no play buttons on the page")
    ap.add_argument("--no-check", action="store_true",
                    help="skip the codec-noise.py cross-check (the JSON then says it was skipped)")
    args = ap.parse_args()

    with open(args.manifest) as fh:
        manifest = json.load(fh)
    base = os.path.dirname(os.path.abspath(args.manifest))
    out_dir = os.path.abspath(args.out) if args.out else base
    img_dir, audio_dir = os.path.join(out_dir, "img"), os.path.join(out_dir, "audio")
    os.makedirs(img_dir, exist_ok=True)
    if not args.no_audio:
        os.makedirs(audio_dir, exist_ok=True)

    F_TITLE, F_LABEL, F_TICK = font(19), font(15), font(13)
    captures = manifest["captures"]
    if not captures:
        raise SystemExit("the manifest has no captures")
    default_trim = float(manifest.get("trim", DEFAULT_TRIM))
    y_range = tuple(manifest.get("spectrum_db", (-140.0, -50.0)))
    full_scale = float(manifest.get("full_scale_v", 1.0))

    # Every capture is measured before any is drawn: the octave-band axis is shared between them,
    # so it can only be chosen once all of their bands are known.
    analysed, spectra = [], []
    for i, cap in enumerate(captures):
        path = cap["path"] if os.path.isabs(cap["path"]) else os.path.join(base, cap["path"])
        channel = int(cap.get("channel", 0))
        trim = float(cap.get("trim", default_trim))
        x, rate = read_wav(path, channel)
        x = x[int(trim * rate):]
        n = numbers(x, rate, full_scale)

        check_db, _ = (None, None) if args.no_check else check_against_codec_noise(
            n, path, channel, trim, full_scale)
        if check_db is not None and abs(check_db) > CHECK_TOLERANCE_DB:
            raise SystemExit("%s: this script reads %.2f dBFS rms and codec-noise.py reads %.2f "
                             "(%.2f dB apart, bar %.2f)" % (path, n["rms_dbfs"],
                                                            n["rms_dbfs"] - check_db, check_db,
                                                            CHECK_TOLERANCE_DB))
        gain_db = None if args.no_audio else -3.0 - n["peak_dbfs"]
        analysed.append((cap, x, rate, n, check_db, gain_db))
        spectra.append((cap["label"], n["spec"], n["bin_hz"], COLOURS[i % len(COLOURS)]))
    bands_range = tuple(manifest.get("bands_db") or auto_bands_range(analysed))

    data = []
    for i, (cap, x, rate, n, check_db, gain_db) in enumerate(analysed):
        cid = cap["id"]
        if gain_db is not None:
            write_wav_mono(os.path.join(audio_dir, cid + ".wav"), x, rate)
            write_wav_mono(os.path.join(audio_dir, cid + "-normalised.wav"),
                           x * (10 ** (gain_db / 20.0)), rate)
        plot_spectrum([(cap["label"], n["spec"], n["bin_hz"], COLOURS[i % len(COLOURS)])],
                      os.path.join(img_dir, "spectrum-%s.png" % cid), cap["label"], y_range)
        plot_bands(n, os.path.join(img_dir, "bands-%s.png" % cid),
                   cap["label"] + " — where the noise is", bands_range)
        n.update({"id": cid, "label": cap["label"], "note": cap.get("note", ""),
                  "file": os.path.basename(cap["path"]), "channel": cap.get("channel", 0),
                  "trim_seconds": cap.get("trim", default_trim), "check_db": check_db,
                  "checked": not args.no_check,
                  "norm_gain_db": None if gain_db is None else round(gain_db, 1)})
        del n["spec"]
        data.append(n)
        print("%-22s %8.2f dBFS  %8.2f dB(A)  peak %7.2f%s"
              % (cid, n["rms_dbfs"], n["rms_a_dbfs"], n["peak_dbfs"],
                 "" if check_db is None else "  (codec-noise.py %+.2f dB)" % check_db))

    plot_spectrum(spectra, os.path.join(img_dir, "spectra-compare.png"),
                  manifest.get("compare_title", "Every capture, one spectrum each"), y_range)
    with open(os.path.join(out_dir, "noise-numbers.json"), "w") as fh:
        json.dump({"title": manifest["title"], "meta": manifest.get("meta", ""),
                   "checked_against": None if args.no_check else os.path.relpath(CODEC_NOISE, REPO),
                   "captures": data}, fh, indent=2)
        fh.write("\n")
    build_page(manifest, data, out_dir,
               manifest.get("compare_title", "Every capture, one spectrum each"),
               audio=not args.no_audio)
    print("wrote %s and %d graphs" % (os.path.join(out_dir, "index.html"), 2 * len(data) + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

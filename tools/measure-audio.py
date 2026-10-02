#!/usr/bin/env python3
"""measure-audio.py — plan 1.7: the jack end of "power-on to sound".

Records the pedal's output on the Mac's interface while a tone is played into the pedal's
input. Both run on the Mac's monotonic clock, and CLOCK_MONOTONIC is system-wide on macOS,
so the `# clock start_monotonic` line in tools/measure-boot.py's log pairs with this
script's stamp: the bootloader's first byte is the anchor, and the first time the tone comes
back out of the pedal is the answer (see plan.md, step 7).

The tone plays for the whole recording, so the input side is continuous — only the pedal's
own power-on can gate what comes back. A power-up transient at the pedal's output is why the
analysis reports two onsets: the first sustained energy at all, and the first sustained
energy *at the tone's frequency*, per window through a Goertzel filter, which a click cannot
fake.

    tools/measure-audio.py --list
    tools/measure-audio.py --device "SSL 2+" --seconds 180 --out bench-results/…
    tools/measure-audio.py --analyze bench-results/…/audio.wav --tone-hz 220

Capture and playback both go through sox's coreaudio driver, so the interface is named the
way CoreAudio names it (`--list` prints those, through ffmpeg). sox takes a moment to open
the device, so the log keeps the clock from before and after it is launched and the onset is
quoted with that much uncertainty. Stdlib only, like the repo's other tools.
"""

import argparse
import array
import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave

BLOCK_MS = 5.0        # energy-profile resolution
TONE_WIN_MS = 20.0    # Goertzel window
TONE_HOP_MS = 10.0


def wav_info(path):
    with wave.open(path, "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getnframes(), w.getsampwidth()


def frames(path):
    """Yield array('h') chunks of the file, about a second each."""
    with wave.open(path, "rb") as w:
        while True:
            data = w.readframes(w.getframerate())
            if not data:
                break
            yield array.array("h", data)


def mono(chunk, channels):
    if channels == 1:
        return [float(x) for x in chunk]
    return [(chunk[i] + chunk[i + 1]) * 0.5 for i in range(0, len(chunk) - 1, channels)]


def dbfs(amplitude):
    if amplitude <= 0:
        return -200.0
    return 20.0 * math.log10(min(amplitude, 32768.0) / 32768.0)


def goertzel(samples, rate, hz):
    """Amplitude of hz in a window, on the int16 scale."""
    n = len(samples)
    if n == 0:
        return 0.0
    c = 2.0 * math.cos(2.0 * math.pi * hz / rate)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + c * s1 - s2
        s2, s1 = s1, s0
    power = s2 * s2 + s1 * s1 - c * s1 * s2
    return 2.0 * math.sqrt(max(power, 0.0)) / n


def energy_profile(path, rate, channels):
    """One RMS level in dBFS per BLOCK_MS."""
    block = max(1, int(rate * BLOCK_MS / 1000.0))
    levels = []
    for chunk in frames(path):
        n = len(chunk) // channels
        for start in range(0, n - block + 1, block):
            seg = chunk[start * channels:(start + block) * channels]
            acc = 0
            for x in seg:
                acc += x * x
            levels.append(dbfs(math.sqrt(acc / len(seg))))
    return levels


def tone_profile(path, rate, channels, hz, upto_s):
    """(seconds, dBFS at hz, tonality in dB) per window, from the start until upto_s.

    Tonality is the tone's level minus the window's RMS: a pure tone sits near +3 dB, a
    broadband pop far below it, which is how a power-up click is told from the tone.
    """
    win = int(rate * TONE_WIN_MS / 1000.0)
    hop = int(rate * TONE_HOP_MS / 1000.0)
    limit = int(upto_s * rate)
    out = []
    buf = []
    base = 0       # absolute mono-sample index of buf[0]
    nxt = 0        # absolute index of the next window to measure
    for chunk in frames(path):
        buf.extend(mono(chunk, channels))
        while nxt + win <= base + len(buf) and nxt < limit:
            seg = buf[nxt - base:nxt - base + win]
            rms = math.sqrt(sum(x * x for x in seg) / len(seg))
            level = dbfs(goertzel(seg, rate, hz))
            out.append((nxt / float(rate), level, level - dbfs(rms)))
            nxt += hop
        if nxt - base > 8 * hop:          # keep only what the next window needs
            drop = nxt - base - hop
            del buf[:drop]
            base += drop
        if nxt >= limit:
            break
    return out


def first_sustained(values, ok, run):
    for i in range(0, len(values) - run + 1):
        if all(ok(v) for v in values[i:i + run]):
            return i
    return None


def analyse(path, hz, threshold_db, tonality_db=-10.0):
    rate, channels, nframes, width = wav_info(path)
    if width != 2:
        raise SystemExit("%s is %d-bit; 16-bit expected" % (path, width * 8))
    levels = energy_profile(path, rate, channels)
    peak = max(levels) if levels else -200.0
    result = {
        "file": path,
        "rate": rate,
        "channels": channels,
        "seconds": round(nframes / float(rate), 3),
        "tone_hz": hz,
        "peak_dbfs": round(peak, 1),
    }
    energy_i = first_sustained(levels, lambda v: v > threshold_db, 2)
    if energy_i is None:
        result["energy_onset_s"] = None
        result["tone_onset_s"] = None
        return result
    energy_s = energy_i * BLOCK_MS / 1000.0
    result["energy_onset_s"] = round(energy_s, 3)
    result["energy_onset_dbfs"] = round(levels[energy_i], 1)

    profile = tone_profile(path, rate, channels, hz, min(energy_s + 2.0, result["seconds"]))
    tone_i = first_sustained(profile, lambda w: w[1] > threshold_db and w[2] > tonality_db, 3)
    if tone_i is None:
        result["tone_onset_s"] = None
    else:
        result["tone_onset_s"] = round(profile[tone_i][0], 3)
        result["tone_onset_dbfs"] = round(profile[tone_i][1], 1)
        result["tone_onset_tonality_db"] = round(profile[tone_i][2], 1)
    return result


def list_devices():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg is not installed; give --device the CoreAudio name directly",
              file=sys.stderr)
        return 1
    out = subprocess.run([ffmpeg, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    section = None
    for line in out.splitlines():
        if "AVFoundation audio devices" in line:
            section = "audio"
            print("audio devices:")
        elif "AVFoundation video devices" in line:
            section = "video"
        elif section == "audio" and "] [" in line:
            print("  " + line.split("] [", 1)[1].rsplit("]", 1)[0])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="print CoreAudio device names")
    ap.add_argument("--device", help="CoreAudio device name, as --list prints it")
    ap.add_argument("--seconds", type=float, default=180.0, help="how long to record")
    ap.add_argument("--out", help="directory for audio.wav and audio.log")
    ap.add_argument("--tone-hz", type=int, default=220)
    ap.add_argument("--tone-db", type=int, default=-20, help="tone level out of the interface")
    ap.add_argument("--no-tone", action="store_true", help="record only (something else plays)")
    ap.add_argument("--threshold-db", type=float, default=-60.0)
    ap.add_argument("--analyze", help="just analyse this WAV and print the onsets")
    args = ap.parse_args()

    if args.list:
        return list_devices()
    if args.analyze:
        print(json.dumps(analyse(args.analyze, args.tone_hz, args.threshold_db), indent=2))
        return 0
    if not args.device or not args.out:
        print("need --device and --out (or --list / --analyze)", file=sys.stderr)
        return 2
    if not shutil.which("sox"):
        print("sox is not installed", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    wav = os.path.join(args.out, "audio.wav")
    log = os.path.join(args.out, "audio.log")
    header = {
        "tool": "measure-audio.py",
        "device": args.device,
        "tone_hz": None if args.no_tone else args.tone_hz,
        "tone_db": None if args.no_tone else args.tone_db,
        "record_seconds": args.seconds,
    }
    tone = None
    if not args.no_tone:
        tone = subprocess.Popen(
            ["sox", "-q", "-n", "-t", "coreaudio", args.device,
             "synth", "%.3f" % (args.seconds + 5.0), "sine", str(args.tone_hz),
             "vol", "%ddB" % args.tone_db],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    pre = time.monotonic()
    rec = subprocess.Popen(
        ["sox", "-q", "-t", "coreaudio", args.device, "-r", "48000", "-c", "2", "-b", "16",
         wav, "trim", "0", "%.3f" % args.seconds],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    post = time.monotonic()
    header["launch_pre_monotonic"] = round(pre, 6)
    header["launch_post_monotonic"] = round(post, 6)
    header["launch_latency_s"] = round(post - pre, 3)
    with open(log, "w", buffering=1) as fh:
        fh.write("# clock start_monotonic %.6f\n" % post)
        fh.write("# launch_pre_monotonic %.6f (sox had not opened the device yet)\n" % pre)
        fh.write("# recording %.1f s from %s\n" % (args.seconds, args.device))
    print("start_monotonic %.6f" % post, flush=True)

    try:
        rec.wait()
    finally:
        if tone:
            tone.terminate()
            tone.wait()

    if not os.path.exists(wav) or os.path.getsize(wav) < 1024:
        print("no recording: is %r a CoreAudio name with an input?" % args.device,
              file=sys.stderr)
        return 1

    result = analyse(wav, args.tone_hz, args.threshold_db)
    result.update(header)
    for key in ("energy_onset_s", "tone_onset_s"):
        if result.get(key) is not None:
            result[key.replace("_s", "_monotonic")] = round(post + result[key], 3)
    with open(log, "a") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""codec-input-noise.py — the noise at the codec's own input, captured, analysed and graphed.

    scripts/codec-input-noise.py [--host vip] [--seconds 20] [--state "…"] [--dir DIR]
                                 [--arms engine,playback,alone] [--device hw:wm8960]
                                 [--retry N] [--no-audio] [--dry-run]
    scripts/codec-input-noise.py --rebuild DIR          re-draw a results directory, no pedal

This is what `docs/codec-bringup-2c.md` describes in prose, as one command: the codec's input node
is wired some way \u2014 shorted at the pin for the reference row, or through the input board, or
with a jack in it \u2014 and the question is how much noise comes through it. It stops `namchaind`
for the captures that need the card to itself, starts it again afterwards, puts the mute back as it
found it, and leaves a document of graphs and numbers in
`bench-results/<date>-codec-input-noise/`.

**`--state` is required and is the record's only description of what was measured.** The script
cannot see the wiring; it measures whatever is there. Every sentence the page writes about the
setup is that line, so a wrong one is a wrong record \u2014 which is why there is no default.

Three arms, each `--seconds` long, each analysed from 2 s in:

    engine     the engine running and muted — the pedal's normal state. Captured by the engine
               itself (`namchainctl record`), which is the only path that can record while it
               holds the card, and the same one the bench test's "Guitar input noise" uses.
    playback   the engine stopped, with a silent `aplay` holding the playback path open and
               `arecord` capturing. This is the converter's quiet state: 2026-10-11 measured it
               4.4 dB better than the engine's own capture path.
    alone      the engine stopped and `arecord` on its own, with no playback stream open. Kept
               because it is the arm the earlier logs quote, and because it is known to be the
               least repeatable of the three — see bench-results/2026-10-11-first-sound/.

**Every `arecord` arm is wrapped in the kernel's log.** `arecord` dies on this platform with
`pcm_read: read error: Input/output error` when the RP1's DMA controller rejects a descriptor on the
I2S capture channel (twice on 2026-10-12; `docs/audio-dma-irq.md` is the page about it), and the
exit status alone says nothing about why. So each arm records `dmesg` before and after itself and
keeps the difference as `dmesg-<arm>.txt` in the results directory — it survives the failure,
because writing it is not the last thing the arm's script does. An arm that fails is retried
(`--retry`, default one retry) and the count is kept in `state.json` and the README: a dead capture
is no measurement, so a second go costs an arm and risks nothing.

`--arms` chooses which of the three to run; `--dry-run` prints what each one would do and touches
nothing. Everything happens under the Core host's lock (`scripts/host-lock`, rule 8: one
measurement at a time), and the engine's state before and after — mute, xruns, period size, the
recording's own counters — is written to `state.json` beside the captures. A run refuses to write
into a directory that already holds captures: `--rebuild DIR` re-analyses and re-draws those, and
`--dir` puts a new run somewhere of its own.

The analysis and the drawing are both `scripts/noise-document.py`'s, which needs numpy and Pillow
and so is run with the harness's bundled python (this script finds it). Its figures are computed
in numpy milliseconds rather than by `scripts/codec-noise.py`'s stdlib FFT, so it runs that tool
on every capture at the same channel and trim and refuses to write the page if the two disagree
by more than 0.05 dB — the bench test's numbers, which are `codec-noise.py`'s, are its numbers.
The raw captures stay in `captures/` and the playable copies in `audio/`; a `.gitignore` in the
results directory keeps both out of git, because bench-results tracks the numbers, the graphs and
the method.

Stdlib only, on the Mac's python3. The captures come from the host; nothing is measured here.
"""
import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
RESULTS = os.path.join(REPO, "bench-results")
CODEC_NOISE = os.path.join(SCRIPTS, "codec-noise.py")
NOISE_DOCUMENT = os.path.join(SCRIPTS, "noise-document.py")
HOST_LOCK = os.path.join(SCRIPTS, "host-lock")
CTL = "/opt/namchain/current/bin/namchainctl"
TMP_ON_HOST = "/run/pedal-codec-input-noise"

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
DEFAULT_SECONDS = 20
SKIP_SECONDS = 2.0
# The three arms, in the order they must run: the engine's own recording needs the engine up, and
# the two `arecord` arms need it stopped.
ARMS = ("engine", "playback", "alone")
ARM_INFO = {
    "engine": ("engine-muted", "Engine running, muted — the pedal's normal state",
               "The engine holds the codec and renders its document, muted, which is what the "
               "player's audio path carries. Captured through <code>namchainctl record</code>: the "
               "engine's own capture path, the one the bench test's \u201cGuitar input noise\u201d "
               "uses. 2026-10-11 read &minus;75.3 dBFS(A) here at 64-frame periods."),
    "playback": ("playback-open", "Engine stopped, a silent playback stream open",
                 "No engine, but a silent <code>aplay</code> holds the playback path open \u2014 "
                 "the codec state the engine leaves it in. On 2026-10-11 this converter's "
                 "capture-only state was about 15 dB louder in the 4\u201316 kHz bands and this "
                 "arm read &minus;79.9 dBFS(A), the quietest of that session's arms \u2014 not of "
                 "every session's since."),
    "alone": ("capture-only", "Engine stopped, capture only (no playback stream)",
              "The engine stopped and <code>arecord</code> on its own. The arm the earlier logs "
              "quote, and the least repeatable of the three: 2026-10-11 read &minus;75.8 dBFS(A) "
              "in the settled re-run, but 4\u201316 kHz dominated and 15 dB louder with the Pico "
              "attached earlier the same day."),
}
# What the numbers are compared against. 2026-10-11's codec-only captures
# (bench-results/2026-10-11-codec-noise-spectra/README.md) and 2a's bench record.
REFERENCE = [
    ("2026-10-11", "engine, 64-frame periods, muted", -75.72, -75.29),
    ("2026-10-11", "engine, 1024-frame periods, muted", -79.09, -79.73),
    ("2026-10-11", "arecord alone", -75.83, -75.75),
    ("2026-10-11", "arecord + silent playback", -79.74, -79.86),
    ("2026-09-27", "2a's bench record, LIN1 shorted", -90.6, -93.5),
]
# catalog.py's bar for the bench test's "Codec input on its own": -75 dBFS unweighted, +/- 3.
BENCHTEST_BAR_DBFS = -75.0
BENCHTEST_TOLERANCE_DB = 3.0
# How far a capture's raw (unbanded) level may sit above its band-limited one before the record
# says so. noise-document.py puts the same number on the page; keep the two the same.
OUTSIDE_BAND_DB = 3.0


def say(message):
    print("codec-input-noise: %s" % message, flush=True)


class Failure(Exception):
    """Something that should stop the run, with the engine put back first."""


# --- talking to the host --------------------------------------------------------------

def ssh_base(host):
    return ["ssh", *SSH_OPTS, host]


def run(args, stdin=None, check=True):
    proc = subprocess.run(args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    if check and proc.returncode != 0:
        raise Failure("%s\nexit %d\n%s" % (" ".join(shlex.quote(a) for a in args),
                                           proc.returncode, proc.stdout.strip()))
    return proc


def host_sh(host, script, check=True):
    """Run a shell script on the host as root; its output comes back as text."""
    body = "set -eu\n" + textwrap.dedent(script).strip() + "\n"
    return run(ssh_base(host) + ["sudo -n bash -s"], stdin=body, check=check)


def host_ctl(host, command, check=True):
    """namchainctl on the host, as root, parsed as JSON where the command answers with it."""
    proc = host_sh(host, "%s %s" % (CTL, command), check=check)
    text = proc.stdout.strip()
    if not check and proc.returncode != 0:
        return None
    start = text.find("{")
    if start < 0:
        return proc.stdout
    try:
        return json.loads(text[start:])
    except ValueError:
        return proc.stdout


def host_json(host, command):
    out = host_ctl(host, command)
    return out if isinstance(out, dict) else {}


def state_of(host):
    """What the engine is doing now, as much of it as is worth recording.

    The kernel is in here because vip's kernel changes: `rtpi` builds it, `vip-boot` swaps the
    slot, and a patch that touches the audio DMA would move these numbers. A record that cannot
    say which kernel it was measured on cannot be compared with the next one.
    """
    status = host_json(host, "status").get("status", {})
    active = run(ssh_base(host) + ["systemctl is-active namchaind"], check=False).stdout.strip()
    kernel = run(ssh_base(host) + ["uname -r"], check=False).stdout.strip()
    return {
        "namchaind": active,
        "kernel": kernel,
        "state": status.get("state"),
        "mute": status.get("mute"),
        "sample_rate": status.get("sample_rate"),
        "period_size": status.get("period_size"),
        "format": status.get("format"),
        "xruns": status.get("xruns"),
        "record": status.get("record"),
        "backend_diagnostics": {k: v for k, v in (status.get("backend_diagnostics") or {}).items()
                                if "xrun" in k or "overrun" in k or "mismatch" in k
                                or "floor" in k},
        "read_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


# --- the arms ------------------------------------------------------------------------

def wait_for_recording(host, name, seconds, timeout=None):
    """Poll the engine until the recording it started has finished (or failed)."""
    deadline = time.time() + (timeout or seconds * 3 + 30)
    last = None
    while time.time() < deadline:
        record = (host_json(host, "record") or {}).get("record") or {}
        last = record
        if record.get("error"):
            raise Failure("the engine's recording failed: %s" % record["error"])
        if record.get("name") == name and not record.get("active"):
            return record
        time.sleep(0.5)
    raise Failure("the recording '%s' was still running after %.0f s: %s" % (name, timeout, last))


def record_with_engine(host, name, seconds, was_muted):
    """Arm 1: the engine running and muted, recorded by the engine itself."""
    if not was_muted:
        say("muting the engine for the recording")
        host_ctl(host, "mute on")
        time.sleep(1.0)
    say("recording %d s through the engine (namchainctl record %s)" % (seconds, name))
    host_ctl(host, "record start %s --seconds %d" % (name, seconds))
    record = wait_for_recording(host, name, seconds)
    say("the engine recorded %.1f s, xruns %s, dropped %s, inserted %s"
        % (record.get("seconds", 0.0), record.get("xruns"), record.get("dropped"),
           record.get("inserted")))
    return record


def silence_script(path, seconds, channels=2, rate=48000):
    """The shell that writes a WAV of digital silence, which the playback arm plays.

    Unindented on purpose: it is embedded in the capture script below and is run on its own by
    scripts/tests, so bash has to run it exactly as written. The heredoc is quoted, so the shell
    leaves the python body alone; the terminator has to be at the start of its line.
    """
    return """python3 - {path} {seconds} {channels} {rate} <<'PY'
import sys, wave
path, seconds, channels, rate = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
with wave.open(path, "wb") as w:
    w.setnchannels(channels); w.setsampwidth(4); w.setframerate(rate)
    w.writeframes(b"\\0" * (int(seconds * rate) * channels * 4))
PY""".format(path=shlex.quote(path), seconds=seconds, channels=channels, rate=rate)


def parse_formats(dump, wanted):
    """The card's offered formats from `arecord --dump-hw-params`, best-first from `wanted`.

    Kept apart from the ssh so it can be tested against a real dump. A dump that does not list
    formats (an older arecord, a device that refused) gives `wanted` unchanged, in its own order:
    the first that works is the one that gets recorded.
    """
    line = next((l for l in dump.splitlines() if l.strip().upper().startswith("FORMAT")), "")
    offered = re.findall(r"[A-Z][A-Z0-9_]{3,}", line.split(":", 1)[-1]) if ":" in line else []
    picked = [f for f in wanted if f in offered] if offered else list(wanted)
    return picked or list(wanted), offered


def card_formats(host, device, wanted):
    """parse_formats, on the host's own dump of the card."""
    proc = host_sh(host, "arecord -D %s --dump-hw-params /dev/null 2>&1 || true"
                   % shlex.quote(device), check=False)
    return parse_formats(proc.stdout, wanted)


def arecord_script(device, fmt, seconds, path, delta_path, playback=False, tmp_dir=TMP_ON_HOST):
    """The shell that runs one `arecord` arm, with the kernel's log wrapped around it.

    **The wrap is the point.** `arecord` on this platform dies with `pcm_read: read error:
    Input/output error` when the RP1's DMA controller hits an invalid descriptor on the I2S capture
    channel — twice on 2026-10-12, both times 5 ms after the driver said the channel was non-idle.
    The `arecord` exit status alone says "I/O error" and nothing about why, so the script records
    the kernel's log before and after and keeps the difference: `delta_path` holds exactly what the
    kernel said while this arm ran, and it survives the failure because the capture is not the last
    thing the script does. `docs/audio-dma-irq.md` is the page about that error.

    The exit status is arecord's, not the wrap's: a failed arm has to fail the run (the run then
    retries it, or reports it with this log beside it).
    """
    lines = ["mkdir -p %s" % shlex.quote(tmp_dir),
             "rm -f %s %s" % (shlex.quote(path), shlex.quote(delta_path)),
             # The line count is taken with plain dmesg; the delta is taken with -T, which is the
             # same lines with readable timestamps.
             'before=$(dmesg 2>/dev/null | wc -l)']
    if playback:
        # The silence is longer than the capture so aplay is still holding the playback path open
        # when arecord stops; its pty is killed by the trap rather than left running.
        lines += [silence_script(tmp_dir + "/silence.wav", seconds + 5),
                  'aplay_pid=""',
                  'cleanup() { [ -n "$aplay_pid" ] && kill "$aplay_pid" 2>/dev/null; return 0; }',
                  "trap cleanup EXIT",
                  "aplay -q -D %s %s/silence.wav & aplay_pid=$!"
                  % (shlex.quote(device), shlex.quote(tmp_dir)),
                  "sleep 1.5"]
    lines += ['rc=0',
              "arecord -q -D %s -f %s -r 48000 -c 2 -d %d %s || rc=$?"
              % (shlex.quote(device), shlex.quote(fmt), seconds, shlex.quote(path)),
              "dmesg -T 2>/dev/null | tail -n +$((before + 1)) > %s || true"
              % shlex.quote(delta_path),
              "ls -l %s 2>/dev/null || true" % shlex.quote(path),
              'if [ "$rc" != 0 ]; then echo "arecord exited $rc"; cat %s; fi'
              % shlex.quote(delta_path),
              'exit "$rc"']
    return "\n".join(lines)


def arecord_arm(host, device, fmt, seconds, path, out_dir, arm_id, playback=False):
    """Arm 2 and 3: arecord on the host, with (or without) a silent aplay holding playback open.

    The kernel's log around the arm comes back with it and is kept beside the captures.
    """
    delta_on_host = "%s/dmesg-%s.txt" % (TMP_ON_HOST, arm_id)
    what = "arecord + a silent aplay" if playback else "arecord alone"
    say("recording %d s with %s" % (seconds, what))
    try:
        host_sh(host, arecord_script(device, fmt, seconds, path, delta_on_host, playback))
    finally:
        # Whatever happened, bring the kernel's log back: on a failure it is the evidence.
        local = os.path.join(out_dir, "dmesg-%s.txt" % arm_id)
        run(["scp", *SSH_OPTS, "%s:%s" % (host, delta_on_host), local], check=False)
        if os.path.exists(local):
            with open(local) as fh:
                kernel_lines = [l for l in fh if l.strip()]
            if kernel_lines:
                say("the kernel said %d line(s) while the %s arm ran; they are in dmesg-%s.txt"
                    % (len(kernel_lines), arm_id, arm_id))
                for line in kernel_lines[-4:]:
                    say("  %s" % line.rstrip())


def attempt_arm(arm, attempts, run_once):
    """Run one arm, retrying it if it fails; return how many attempts it took.

    A dead capture is not a bad measurement, it is no measurement: `arecord` failing with EIO
    leaves nothing to analyse, so trying again costs one arm and risks nothing. The count is kept
    because a record should say when an arm needed more than one go at it.
    """
    last = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            say("retrying the %s arm (attempt %d of %d)" % (arm, attempt, attempts))
        try:
            run_once()
            return attempt
        except Failure as exc:
            last = exc
            say("the %s arm failed on attempt %d of %d: %s"
                % (arm, attempt, attempts, str(exc).strip().splitlines()[0][:160]))
    raise Failure("the %s arm failed %d time(s); giving up.\n%s" % (arm, attempts, last))


# --- putting the two together ---------------------------------------------------------

def write_results(args, state_before, state_after, arms_done, notes, out_dir, ran_at=None,
                  attempts=None):
    """The manifest noise-document.py reads, and a README from the numbers it writes."""
    captures = []
    for arm in ARMS:
        if arm not in arms_done:
            continue
        cid, label, note = ARM_INFO[arm]
        captures.append({"id": cid, "path": "captures/%s.wav" % cid, "label": label,
                         "note": "<p>%s</p>" % note, "channel": 0, "trim": SKIP_SECONDS})
    manifest = {
        "title": "The codec's input noise — %s" % args.date,
        "meta": "%s &middot; %s" % (args.date, args.state),
        "intro": [
            "<p>Three arms, each %d s of the codec's own ADC \u2014 channel 0, LIN1 \u2014 "
            "analysed from %.0f s in, because the stream's start-up transient sits in the first "
            "seconds. What the input node is connected to decides what is in them: a pin shorted "
            "to ground measures the converter and the wiring to it, an input board measures the "
            "board, a jack measures whatever the jack is picking up.</p>"
            % (args.seconds, SKIP_SECONDS),
            "<p><strong>The state line above is the only description of the setup in this "
            "record</strong>, and it is what the owner typed when the run was started. The script "
            "cannot see the wiring and does not know what it measured; the numbers below say how "
            "quiet whatever it was, was.</p>",
        ],
        "callout": "<p><strong>How to read it.</strong> Each capture has a spectrum in dBFS per "
                   "0.73 Hz bin and the same noise as octave-band bars. <em>Hum</em> is a spike at "
                   "50 Hz and its harmonics, and the mains line beside each graph is that spike: an "
                   "A-weighted figure discounts 50 Hz by about 30 dB, which is why a hum reads far "
                   "worse unweighted than weighted. <em>Hiss</em> is a broad slope across the high "
                   "bands. <em>Drift</em> is energy below 20 Hz, which the band-limited figures do "
                   "not count and the raw one does. The three arms are the converter in its three "
                   "states \u2014 the engine running, a silent playback stream, and neither \u2014 "
                   "so where they disagree the difference is the engine or the stream, and where "
                   "they agree whatever it is sits ahead of both, in the wiring at the input "
                   "node.</p>",
        "compare_title": "Every arm, one spectrum each",
        "footer": [
            "<p>Captured by <code>scripts/codec-input-noise.py</code>, analysed and drawn by "
            "<code>scripts/codec-noise.py</code> and <code>scripts/noise-document.py</code>. "
            "The engine and host state around the run is in <code>state.json</code>.</p>",
        ],
        "trim": SKIP_SECONDS,
        "captures": captures,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out_dir, "state.json"), "w") as fh:
        json.dump({"before": state_before, "after": state_after, "arms": arms_done,
                   # How many goes each arm needed: a retried arm is a real measurement, but a
                   # record that hid the retry would be hiding that the platform hiccuped.
                   "attempts": attempts or {},
                   "notes": notes, "state_as_described": args.state,
                   "seconds_per_arm": args.seconds, "skip_seconds": SKIP_SECONDS,
                   "device": args.device, "format": args.format,
                   # Only the run's own time: a --rebuild re-derives the numbers from the same
                   # captures and must not dirty a tracked file just by being run again.
                   "ran_at": ran_at or datetime.datetime.now().astimezone().isoformat(
                       timespec="seconds")}, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(out_dir, ".gitignore"), "w") as fh:
        fh.write("# The captures and the playable copies are big and reproducible; the numbers,\n"
                 "# the graphs and the method are what the repository keeps.\ncaptures/\naudio/\n")
    return manifest


def document(args, out_dir):
    """noise-document.py needs numpy and Pillow: find a python that has them."""
    candidates = [os.environ.get("PEDAL_PYTHON"), sys.executable,
                  "/Users/rik/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3",
                  "python3"]
    for python in candidates:
        if not python:
            continue
        probe = subprocess.run([python, "-c", "import numpy, PIL"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            say("drawing the graphs with %s" % python)
            cmd = [python, NOISE_DOCUMENT, os.path.join(out_dir, "manifest.json")]
            if args.no_audio:
                cmd.append("--no-audio")
            run(cmd)
            return
    raise Failure("no python with numpy and Pillow was found; set PEDAL_PYTHON to one, or run:\n"
                  "  <bundled python> %s %s/manifest.json"
                  % (NOISE_DOCUMENT, os.path.relpath(out_dir, REPO)))


def readme(args, out_dir, state_before, state_after, arms_done, attempts=None):
    """The record: what was measured, the numbers, and what they are compared with."""
    dmesg_files = sorted(f for f in os.listdir(out_dir)
                         if f.startswith("dmesg-") and f.endswith(".txt"))
    dmesg_files = [f for f in dmesg_files
                   if os.path.getsize(os.path.join(out_dir, f)) > 0]
    numbers = {}
    path = os.path.join(out_dir, "noise-numbers.json")
    if os.path.exists(path):
        with open(path) as fh:
            numbers = {c["id"]: c for c in json.load(fh)["captures"]}
    rows = []
    for arm in ARMS:
        cid = ARM_INFO[arm][0]
        n = numbers.get(cid)
        if not n:
            continue
        fifty = next((m["dbfs"] for m in n.get("mains", []) if m["nominal_hz"] == 50.0), None)
        rows.append("| `%s` | %s | %.2f dBFS | **%.2f dBFS(A)** | %s | %.2f dBFS | %.2f | %.1f µV | %.1f µV |"
                    % (cid, n["label"], n["rms_dbfs"], n["rms_a_dbfs"],
                       "%.1f dBFS" % fifty if fifty is not None else "—", n["raw_rms_dbfs"],
                       n["peak_dbfs"], n["rms_uv"], n["rms_a_uv"]))
    unweighted = [numbers[ARM_INFO[a][0]]["rms_dbfs"] for a in ARMS if ARM_INFO[a][0] in numbers]
    present = [numbers[ARM_INFO[a][0]] for a in ARMS if ARM_INFO[a][0] in numbers]
    loudest = max(present, key=lambda n: n["raw_rms_dbfs"], default=None)
    # Where the reading sits against the bench test's bar, in the bench test's own terms: above
    # the bar its "Codec input on its own" check fails, and a failure paints the codec block.
    limit = BENCHTEST_BAR_DBFS + BENCHTEST_TOLERANCE_DB
    if unweighted:
        quietest = min(unweighted)
        if quietest <= limit:
            bar = ("The quietest arm reads **%.2f dBFS** unweighted, inside the bench test's "
                   "codec-only bar of %.0f ± %.0f dBFS." % (quietest, BENCHTEST_BAR_DBFS,
                                                            BENCHTEST_TOLERANCE_DB))
        else:
            bar = ("The quietest arm reads **%.2f dBFS** unweighted, **%.1f dB outside** the "
                   "bench test's codec-only bar of %.0f ± %.0f dBFS — its \u201cCodec input on "
                   "its own\u201d check would fail and paint the codec block for this."
                   % (quietest, quietest - limit, BENCHTEST_BAR_DBFS, BENCHTEST_TOLERANCE_DB))
    else:
        bar = "No numbers were written."
    caveat = []
    if len(present) >= 2:
        spread = max(n["rms_a_dbfs"] for n in present) - min(n["rms_a_dbfs"] for n in present)
        if spread <= 1.5:
            caveat.append(
                "**All %d arms agree to within %.1f dB A-weighted**, so none of this is the engine "
                "or the converter's stream state: whatever it is, it is common to all three and "
                "sits before the converter \u2014 the wiring at the input node." % (len(present),
                                                                                    spread))
    for n in present:
        if (n.get("outside_band_db") or 0) < OUTSIDE_BAND_DB:
            continue
        caveat.append(
            "**`%s` is not as quiet as its band-limited figure says.** Raw %+.2f dBFS against "
            "%+.2f dBFS in the 20 Hz–20 kHz band: %.1f dB, so roughly %d%% of this arm's power is "
            "outside the audio band — it drifts or settles rather than hisses, and the unweighted, "
            "A-weighted and µV columns, band-limited as every earlier reading of this converter "
            "is, cannot see it.%s"
            % (n["id"], n["raw_rms_dbfs"], n["rms_dbfs"], n["outside_band_db"],
               round(100 * (1 - 10 ** (-n["outside_band_db"] / 10.0))),
               " By the raw figure it is the loudest of the arms measured here."
               if loudest is not None and loudest["id"] == n["id"] else ""))
    retried = [a for a, n in (attempts or {}).items() if n > 1]
    kernel_note = ("none" if not dmesg_files else
                   "in " + ", ".join("`%s`" % f for f in dmesg_files))
    lines = ["# The codec's input noise — %s" % args.date, "",
             "`scripts/codec-input-noise.py` on `%s`, %d s per arm, analysed from %.0f s in. "
             "State, as the owner described it: **%s**." % (args.host, args.seconds, SKIP_SECONDS,
                                                            args.state),
             ""]
    if retried:
        lines += ["**An arm was retried.** %s needed more than one attempt: an `arecord` arm that "
                  "dies with `pcm_read: read error: Input/output error` is the RP1's DMA "
                  "controller on the I2S capture channel, and the kernel's own log from that arm "
                  "is beside this file — see [docs/audio-dma-irq.md](../docs/audio-dma-irq.md). "
                  "The numbers below are from the attempt that worked." % ", ".join(retried), ""]
    lines += ["",
              "The graphs and the audio are in [index.html](index.html); every number is in "
             "[noise-numbers.json](noise-numbers.json); the engine and host state before, during "
             "and after is in [state.json](state.json). The captures are in `captures/` and the "
             "playable copies in `audio/`, both untracked.", "",
             "| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |",
             "|---|---|---|---|---|---|---|---|---|"] + rows + ["", bar, ""] + caveat + ["",
             "## What it is compared with", "",
             "| when | state | unweighted | A-weighted |", "|---|---|---|---|"]
    lines += ["| %s | %s | %.2f dBFS | %.2f dBFS(A) |" % r for r in REFERENCE]
    lines += ["",
              "The 2026-10-11 rows are the codec-only captures in "
              "[../2026-10-11-codec-noise-spectra/README.md](../2026-10-11-codec-noise-spectra/README.md); "
              "the 2a row is that bench's own record. The bench test's \u201cCodec input on its "
              "own\u201d check reads the same measurement against a bar of %.0f dBFS ± %.0f, and "
              "paints the codec block when it fails "
              "(`devices/common/rootfs/usr/local/lib/benchtest/catalog.py`)."
              % (BENCHTEST_BAR_DBFS, BENCHTEST_TOLERANCE_DB), "",
              "## The run", "",
              "- The engine: `%s` before, `%s` after; mute `%s` \u2192 `%s`; xruns `%s` \u2192 `%s`."
              % (state_before.get("namchaind"), state_after.get("namchaind"),
                 state_before.get("mute"), state_after.get("mute"),
                 state_before.get("xruns"), state_after.get("xruns")),
              "- Card `%s`, format `%s`, %d s per arm, channel 0 = LIN1."
              % (args.device, args.format, args.seconds),
              "- Kernel `%s`%s." % (
                  state_before.get("kernel") or "not recorded",
                  "" if state_before.get("kernel") == state_after.get("kernel")
                  else " before, `%s` after" % (state_after.get("kernel") or "?")),
              "- Arms run: %s." % ", ".join(arms_done),
              "- Attempts: %s." % (", ".join("%s %d" % (a, n) for a, n in (attempts or {}).items())
                                   or "not recorded"),
              "- Kernel messages during the `arecord` arms: %s." % kernel_note,
              "",
              "## Running it again", "",
              "    scripts/codec-input-noise.py --state \"what is wired this time\"", "",
              "It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it "
              "again afterwards and puts the mute back as it found it. `--arms engine` alone needs "
              "no interruption at all: the engine records its own capture while it runs.", ""]
    with open(os.path.join(out_dir, "README.md"), "w") as fh:
        fh.write("\n".join(lines))
    return numbers


def rebuild(args):
    """--rebuild DIR: the analysis, the page and the record again, from the captures already there.

    Nothing here touches the pedal: it is for re-drawing the graphs or re-reading the numbers of a
    measurement that has already been made, and it is why the numbers and the page are not built
    inside the capture. The arm list is what the directory actually holds, and the run's own
    settings come from its state.json, so the rebuilt page says what the original did.
    """
    out_dir = os.path.abspath(args.rebuild)
    state_path = os.path.join(out_dir, "state.json")
    if not os.path.exists(state_path):
        raise SystemExit("codec-input-noise.py: %s has no state.json, so it is not a results "
                         "directory from this script" % out_dir)
    with open(state_path) as fh:
        saved = json.load(fh)
    args.state = saved.get("state_as_described", args.state)
    args.seconds = saved.get("seconds_per_arm", args.seconds)
    args.device = saved.get("device", args.device)
    args.format = saved.get("format", args.format)
    args.date = (saved.get("ran_at") or datetime.date.today().isoformat())[:10]
    arms_done = [a for a in ARMS if os.path.exists(
        os.path.join(out_dir, "captures", "%s.wav" % ARM_INFO[a][0]))]
    if not arms_done:
        raise SystemExit("codec-input-noise.py: %s/captures holds none of the three arms"
                         % out_dir)
    say("rebuilding %s from %s" % (os.path.relpath(out_dir, os.getcwd()),
                                   ", ".join(arms_done)))
    write_results(args, saved.get("before", {}), saved.get("after", {}), arms_done,
                  saved.get("notes", []), out_dir, ran_at=saved.get("ran_at"),
                  attempts=saved.get("attempts"))
    document(args, out_dir)
    numbers = readme(args, out_dir, saved.get("before", {}), saved.get("after", {}), arms_done,
                     attempts=saved.get("attempts"))
    for arm in ARMS:
        cid = ARM_INFO[arm][0]
        if cid in numbers:
            n = numbers[cid]
            print("%-14s %8.2f dBFS  %8.2f dBFS(A)  peak %7.2f dBFS  %6.1f µV"
                  % (cid, n["rms_dbfs"], n["rms_a_dbfs"], n["peak_dbfs"], n["rms_a_uv"]))
    say("results in %s" % os.path.relpath(out_dir, os.getcwd()))
    return 0


def main():
    ap = argparse.ArgumentParser(description="the noise at the codec's own input, as numbers and "
                                             "graphs")
    ap.add_argument("--host", default="vip")
    ap.add_argument("--seconds", type=int, default=DEFAULT_SECONDS,
                    help="seconds per arm (default %d)" % DEFAULT_SECONDS)
    ap.add_argument("--arms", default=",".join(ARMS),
                    help="which arms to run: %s (default all three)" % ", ".join(ARMS))
    ap.add_argument("--state", default=None,
                    help="what is wired, as one line for the page and the record: required, because "
                         "it is the only description of the setup the record will contain and this "
                         "script cannot see the wiring (--rebuild takes it from state.json)")
    ap.add_argument("--dir", help="results directory (default bench-results/<date>-codec-input-noise)")
    ap.add_argument("--device", default="hw:wm8960", help="the codec's ALSA device")
    ap.add_argument("--format", default=None,
                    help="arecord format (default: the card's best of S32_LE, S24_LE, S16_LE)")
    ap.add_argument("--retry", type=int, default=1, metavar="N",
                    help="how many times to retry an arm that fails (default 1, so an arm gets a "
                         "second go; 0 means a failure is final). A dead capture is no measurement, "
                         "so a retry costs an arm and risks nothing; the count is kept in the "
                         "record either way")
    ap.add_argument("--no-audio", action="store_true", help="no playable copies, no play buttons")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen, touch nothing")
    ap.add_argument("--rebuild", metavar="DIR",
                    help="re-analyse and re-draw the captures already in DIR; touches no pedal")
    ap.add_argument("--lock-wait", type=int, default=600,
                    help="seconds to wait for the host lock (default 600)")
    args = ap.parse_args()

    if args.rebuild:
        return rebuild(args)

    if args.retry < 0:
        ap.error("--retry takes 0 or more (0 means an arm gets one go and a failure is final)")
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in arms:
        if arm not in ARMS:
            ap.error("--arms takes %s, not '%s'" % (", ".join(ARMS), arm))
    arms = [a for a in ARMS if a in arms]                 # always in the order they must run

    args.date = datetime.date.today().isoformat()
    out_dir = os.path.abspath(args.dir) if args.dir else \
        os.path.join(RESULTS, "%s-codec-input-noise" % args.date)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    recording_name = "codec-input-noise-%s" % stamp

    if args.dry_run:
        print("would run on %s, under scripts/host-lock:" % args.host)
        print("  0. record the state line: %s" % (args.state and '"%s"' % args.state or
                                                   "MISSING — a real run needs --state, because it "
                                                   "is the record's only description of the wiring"))
        print("  1. read the engine's state, then %s" % (
            "mute it and `%s record start %s --seconds %d`, wait, and fetch "
            "capture.wav" % (CTL, recording_name, args.seconds) if "engine" in arms else
            "(skip the engine arm)"))
        if "playback" in arms or "alone" in arms:
            print("  2. `systemctl stop namchaind`")
        if "playback" in arms:
            print("  3. `arecord` %d s with a silent `aplay` holding playback open"
                  % args.seconds)
        if "alone" in arms:
            print("  4. `arecord` %d s on its own" % args.seconds)
        if "playback" in arms or "alone" in arms:
            print("  5. `systemctl start namchaind`, and the mute back as it was")
        print("  6. analyse each capture with scripts/codec-noise.py, and draw the page with "
              "scripts/noise-document.py")
        print("  results would go to %s" % os.path.relpath(out_dir, REPO))
        return 0

    # Everything that can refuse a run without the host refuses it here, before the lock is taken:
    # a run that was always going to be refused must not queue for the lock, or touch the host.
    if not args.state:
        ap.error("--state is required: it is the record's only description of what was wired, and "
                 "this script cannot see it. Say what the codec's input is connected to, e.g.\n"
                 "  --state 'LIN1 shorted to the codec's own GND, nothing else attached'")
    for tool in (CODEC_NOISE, NOISE_DOCUMENT, HOST_LOCK):
        if not os.path.exists(tool):
            raise SystemExit("codec-input-noise.py: %s is missing" % tool)
    # A run does not quietly replace an earlier one: the captures are the evidence, and the whole
    # point of the record is that it can be gone back to. Say so, and name both ways out.
    holding = os.path.join(out_dir, "captures")
    if os.path.isdir(holding) and any(f.endswith(".wav") for f in os.listdir(holding)):
        raise SystemExit(
            "codec-input-noise.py: %s already holds captures.\n"
            "  --rebuild %s   re-analyse and re-draw them, touching no pedal\n"
            "  --dir <other>  measure into a directory of its own"
            % (os.path.relpath(out_dir, os.getcwd()), os.path.relpath(out_dir, os.getcwd())))

    # Rule 8: one measurement at a time. Nested calls (PEDAL_HOST_LOCK already set) run directly.
    if os.environ.get("PEDAL_HOST_LOCK") != args.host:
        argv = [HOST_LOCK, "--host", args.host]
        if args.lock_wait:
            argv += ["--wait", str(args.lock_wait)]
        argv += ["--", sys.executable, os.path.abspath(__file__)] + sys.argv[1:]
        os.execv(HOST_LOCK, argv)

    run(ssh_base(args.host) + ["true"])                   # is the host there at all

    state_before = state_of(args.host)
    say("%s: namchaind %s, mute %s, %d-frame periods, %s, xruns %s"
        % (args.host, state_before["namchaind"], state_before["mute"],
           state_before["period_size"] or 0, state_before["format"], state_before["xruns"]))
    if state_before["namchaind"] != "active":
        raise SystemExit("codec-input-noise.py: namchaind is not running on %s, so the engine's "
                         "state cannot be recorded or put back" % args.host)
    if state_before.get("state") != "running":
        raise SystemExit("codec-input-noise.py: the engine is '%s', not running; fix that first"
                         % state_before.get("state"))

    os.makedirs(holding, exist_ok=True)
    if not args.no_audio:
        os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)

    notes = []
    arms_done = []
    attempts = {}
    engine_stopped = False
    format_used = args.format
    try:
        if "engine" in arms:
            def engine_arm():
                record_with_engine(args.host, recording_name, args.seconds, state_before["mute"])
                run(["scp", *SSH_OPTS,
                     "%s:/var/lib/namchain/recordings/%s/capture.wav"
                     % (args.host, recording_name),
                     os.path.join(out_dir, "captures", "engine-muted.wav")])
                run(["scp", *SSH_OPTS,
                     "%s:/var/lib/namchain/recordings/%s/meta.json"
                     % (args.host, recording_name),
                     os.path.join(out_dir, "captures", "engine-muted-meta.json")])
            attempts["engine"] = attempt_arm("engine", 1 + args.retry, engine_arm)
            notes.append("the engine's recording is /var/lib/namchain/recordings/%s/"
                         % recording_name)
            arms_done.append("engine")

        if "playback" in arms or "alone" in arms:
            say("stopping namchaind for the arecord arms")
            host_sh(args.host, "systemctl stop namchaind")
            engine_stopped = True
            host_sh(args.host, "mkdir -p %s && rm -f %s/*.wav" % (TMP_ON_HOST, TMP_ON_HOST))
            if not format_used:
                offered, raw = card_formats(args.host, args.device,
                                            ["S32_LE", "S24_LE", "S16_LE", "S24_3LE"])
                format_used = offered[0]
                args.format = format_used
                say("the card offers %s; recording %s" % (", ".join(offered) or raw.strip() or "?",
                                                          format_used))
            if "playback" in arms:
                def playback_arm():
                    arecord_arm(args.host, args.device, format_used, args.seconds,
                                TMP_ON_HOST + "/playback.wav", out_dir, "playback-open",
                                playback=True)
                    run(["scp", *SSH_OPTS, "%s:%s/playback.wav" % (args.host, TMP_ON_HOST),
                         os.path.join(out_dir, "captures", "playback-open.wav")])
                attempts["playback"] = attempt_arm("playback", 1 + args.retry, playback_arm)
                arms_done.append("playback")
            if "alone" in arms:
                def alone_arm():
                    arecord_arm(args.host, args.device, format_used, args.seconds,
                                TMP_ON_HOST + "/alone.wav", out_dir, "capture-only",
                                playback=False)
                    run(["scp", *SSH_OPTS, "%s:%s/alone.wav" % (args.host, TMP_ON_HOST),
                         os.path.join(out_dir, "captures", "capture-only.wav")])
                attempts["alone"] = attempt_arm("alone", 1 + args.retry, alone_arm)
                arms_done.append("alone")
    finally:
        # Whatever happened above, the engine goes back to how it was found: running, and with the
        # mute it had. A capture that dies half way through must not leave the pedal silent or dead.
        if engine_stopped:
            say("starting namchaind again")
            host_sh(args.host, "systemctl start namchaind", check=False)
            for _ in range(60):
                probe = host_json(args.host, "status").get("status", {})
                if probe.get("state") == "running":
                    break
                time.sleep(1.0)
        if state_before["mute"] is not None:
            host_ctl(args.host, "mute %s" % ("on" if state_before["mute"] else "off"), check=False)
        host_sh(args.host, "rm -rf %s" % TMP_ON_HOST, check=False)

    state_after = state_of(args.host)
    say("after: namchaind %s, mute %s, xruns %s (was %s)"
        % (state_after["namchaind"], state_after["mute"], state_after["xruns"],
           state_before["xruns"]))

    write_results(args, state_before, state_after, arms_done, notes, out_dir, attempts=attempts)
    document(args, out_dir)
    numbers = readme(args, out_dir, state_before, state_after, arms_done, attempts=attempts)

    print()
    for arm in ARMS:
        cid = ARM_INFO[arm][0]
        if cid in numbers:
            n = numbers[cid]
            print("%-14s %8.2f dBFS  %8.2f dBFS(A)  peak %7.2f dBFS  %6.1f µV"
                  % (cid, n["rms_dbfs"], n["rms_a_dbfs"], n["peak_dbfs"], n["rms_a_uv"]))
    say("results in %s" % os.path.relpath(out_dir, os.getcwd()))
    say("open %s" % os.path.join(os.path.relpath(out_dir, os.getcwd()), "index.html"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as exc:
        sys.exit("codec-input-noise: %s" % exc)
    except KeyboardInterrupt:
        sys.exit("codec-input-noise: interrupted; the engine's state is in the results directory")

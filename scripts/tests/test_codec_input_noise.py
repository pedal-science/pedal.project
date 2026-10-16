"""scripts/codec-input-noise.py and scripts/noise-document.py, without a pedal, an ssh or a card.

    python3 -m unittest discover -s scripts/tests

The capture itself cannot be tested here — it is ssh, `arecord` and the codec — so what is tested
is everything around it: the card's format dump read back, the silence file the playback arm
holds the card open with, the arm order, `--dry-run` touching nothing, and `--rebuild` over a
synthetic results directory, which is where the numbers, the caveat and the record are made. The
document builder is tested only when numpy and Pillow are importable (they come from the harness's
bundled python, not the system one): without them the tests say they were skipped, as the browser
test does without uv.

Nothing here opens an audio device, ssh, or the browser. Every run of the driver goes through
`run_driver`, whose PATH puts an `ssh` and an `scp` first that refuse and say so: a run that would
have reached for the Core host (its lock, or the host itself) fails its test instead.
"""
import atexit
import importlib.machinery
import importlib.util
import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent

DRIVER = SCRIPTS / "codec-input-noise.py"
DOCUMENT = SCRIPTS / "noise-document.py"
BUNDLED_PYTHON = ("/Users/rik/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


driver = load("codec_input_noise", DRIVER)


# `ssh` and `scp` for the driver's runs: they refuse, and say so, so no test can reach a host.
NO_HOST = "a test reached for the Core host"
NO_HOST_BIN = tempfile.mkdtemp(prefix="codec-input-noise-no-host-")
atexit.register(shutil.rmtree, NO_HOST_BIN, True)
for _tool in ("ssh", "scp"):
    with open(os.path.join(NO_HOST_BIN, _tool), "w") as _fh:
        _fh.write("#!/bin/sh\necho \"%s: %s $*\" >&2\nexit 97\n" % (NO_HOST, _tool))
    os.chmod(os.path.join(NO_HOST_BIN, _tool), 0o755)


def run_driver(*argv, check=False):
    """Run codec-input-noise.py with ssh and scp refusing; a run that tried either fails here."""
    env = dict(os.environ)
    env["PATH"] = NO_HOST_BIN + os.pathsep + env.get("PATH", "")
    env.pop("PEDAL_HOST_LOCK", None)
    proc = subprocess.run([sys.executable, str(DRIVER), *argv], env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    if NO_HOST in proc.stdout:
        raise AssertionError("codec-input-noise.py %s tried to reach a host:\n%s"
                             % (" ".join(argv), proc.stdout))
    if check and proc.returncode != 0:
        raise AssertionError("codec-input-noise.py %s exited %d:\n%s"
                             % (" ".join(argv), proc.returncode, proc.stdout))
    return proc


def document_python():
    """A python that can import numpy and Pillow, or None."""
    for python in (os.environ.get("PEDAL_PYTHON"), BUNDLED_PYTHON, sys.executable):
        if not python:
            continue
        probe = subprocess.run([python, "-c", "import numpy, PIL"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            return python
    return None


DOC_PYTHON = document_python()


def write_wav(path, seconds=3.0, rate=48000, channels=2, width=4, tone_hz=0.0,
              level_dbfs=-90.0, drift=False, mains_hz=0.0, mains_dbfs=None):
    """A stereo capture: everything on channel 0, silence on channel 1.

    `drift` adds a very low frequency wander (0.5 Hz) far below the 20 Hz-20 kHz band every figure
    is quoted in, which is what the capture-only arm of a real run shows.
    """
    peak = (1 << (8 * width - 1)) - 1
    scale = (10 ** (level_dbfs / 20)) * math.sqrt(2) * peak
    frames = bytearray()
    for i in range(int(rate * seconds)):
        t = i / rate
        v = scale * math.sin(2 * math.pi * tone_hz * t) if tone_hz else 0.0
        if mains_hz and mains_dbfs is not None:
            v += (10 ** (mains_dbfs / 20)) * math.sqrt(2) * peak * math.sin(2 * math.pi * mains_hz * t)
        if drift:
            v += 0.3 * peak * math.sin(2 * math.pi * 0.5 * t)
        s = max(-peak - 1, min(peak, int(round(v))))
        frames += s.to_bytes(width, "little", signed=True) + (0).to_bytes(width, "little",
                                                                         signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def make_results_dir(root, arms=("engine", "playback", "alone"), drift=("alone",),
                     ran_at="2026-10-12T18:44:03+01:00", level_dbfs=-90.0, mains_hz=0.0,
                     mains_dbfs=None):
    """A results directory shaped like a real run's, with synthetic captures."""
    out = pathlib.Path(root)
    (out / "captures").mkdir(parents=True, exist_ok=True)
    for arm in arms:
        cid = driver.ARM_INFO[arm][0]
        # A tone inside the band, so the band-limited figure is a real one; the drift arm gets the
        # sub-audio wander on top of it, as the real capture-only arm has.
        write_wav(out / "captures" / ("%s.wav" % cid), seconds=3.0, tone_hz=1000.0,
                  level_dbfs=level_dbfs, drift=arm in drift, mains_hz=mains_hz,
                  mains_dbfs=mains_dbfs)
    (out / "state.json").write_text(json.dumps({
        "before": {"namchaind": "active", "mute": False, "xruns": 2, "period_size": 64},
        "after": {"namchaind": "active", "mute": False, "xruns": 0, "period_size": 64},
        "arms": list(arms), "notes": [], "state_as_described": "a synthetic bench",
        "seconds_per_arm": 20, "skip_seconds": 2.0, "device": "hw:wm8960", "format": "S32_LE",
        "ran_at": ran_at, "rebuilt_at": None}, indent=2))
    return out


class Formats(unittest.TestCase):
    """The card's own word on what it can record, and what is asked for when it has none."""

    DUMP = """Warning: rate is not accurate (requested = 48000Hz, got = 48000Hz)
HW Params of device "hw:wm8960":
--------------------
ACCESS:  MMAP_INTERLEAVED RW_INTERLEAVED
FORMAT:  S16_LE S24_LE S32_LE
SUBFORMAT:  STD
SAMPLE_BITS: [16 32]
RATE: [8000 48000]
--------------------
arecord: set_params:1407: Unable to install hw params
"""

    def test_reads_the_formats_out_of_a_real_dump(self):
        wanted = ["S32_LE", "S24_LE", "S16_LE", "S24_3LE"]
        picked, offered = driver.parse_formats(self.DUMP, wanted)
        self.assertEqual(offered, ["S16_LE", "S24_LE", "S32_LE"])
        # Best-first from what was asked for, and S24_3LE is not offered so it is not picked.
        self.assertEqual(picked, ["S32_LE", "S24_LE", "S16_LE"])

    def test_a_dump_with_no_format_line_keeps_the_preference_order(self):
        wanted = ["S32_LE", "S16_LE"]
        picked, offered = driver.parse_formats("arecord: main:831: audio open error", wanted)
        self.assertEqual(offered, [])
        self.assertEqual(picked, wanted)

    def test_the_first_pick_is_what_gets_recorded(self):
        # The engine records S32_LE on this card; the arms must not silently differ from it.
        picked, _ = driver.parse_formats(self.DUMP, ["S32_LE", "S24_LE", "S16_LE"])
        self.assertEqual(picked[0], "S32_LE")


class SilenceFile(unittest.TestCase):
    """The file the playback arm holds the card open with: digital silence, real WAV."""

    def test_it_writes_a_silent_wav_of_the_length_asked_for(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "silence.wav")
            script = driver.silence_script(path, 2.0)
            subprocess.run(["bash", "-c", script], check=True, stdout=subprocess.PIPE)
            with wave.open(path, "rb") as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()),
                                 (2, 4, 48000))
                self.assertEqual(w.getnframes(), 96000)
                self.assertEqual(set(w.readframes(w.getnframes())), {0})
        self.assertIn("<<'PY'", script)          # quoted heredoc: the shell leaves the body alone


class TheArecordWrapper(unittest.TestCase):
    """The shell that runs one arecord arm, with the kernel's log wrapped around it.

    Run for real, with stub `dmesg` and `arecord` on PATH: what matters is that the wrap records
    what the kernel said while the arm ran, and that it cannot swallow arecord's exit status --
    the run's retry logic depends on that status arriving.
    """

    def stub_bin(self, d, arecord_rc=0, new_dmesg=()):
        bindir = os.path.join(d, "bin")
        os.makedirs(bindir, exist_ok=True)

        def write(name, body):
            path = os.path.join(bindir, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)

        # dmesg: the first call is the baseline count, the second is the delta after the arm.
        # A file in the directory tells the stub which call it is on.
        write("dmesg", """#!/bin/bash
count=%s
if [ -f %s ]; then
  # the second call: the baseline plus whatever the arm added
  cat %s
  cat %s/*.dmesg-new 2>/dev/null || true
else
  touch %s
  cat %s/old.txt
fi
""" % (os.path.join(d, "count"), os.path.join(d, "seen"), os.path.join(d, "old.txt"),
       d, os.path.join(d, "seen"), d))
        with open(os.path.join(d, "old.txt"), "w") as fh:
            fh.write("old line one\nold line two\n")
        with open(os.path.join(d, "count"), "w") as fh:
            fh.write("2\n")
        if new_dmesg:
            with open(os.path.join(d, "new.dmesg-new"), "w") as fh:
                fh.write("".join(l + "\n" for l in new_dmesg))
        write("arecord", "#!/bin/bash\nfor a in \"$@\"; do :; done\necho 'arecord ran'\nexit %d\n"
              % arecord_rc)
        write("aplay", "#!/bin/bash\nsleep 0.1\n")
        return bindir

    def run_script(self, d, script, bindir):
        env = dict(os.environ)
        env["PATH"] = bindir + os.pathsep + env["PATH"]
        return subprocess.run(["bash", "-c", script], cwd=d, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)

    def test_the_kernel_log_around_the_arm_survives_and_is_only_the_difference(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = self.stub_bin(d, new_dmesg=["dma dma2chan3: Bad descriptor submitted"])
            capture = os.path.join(d, "alone.wav")
            delta = os.path.join(d, "dmesg-capture-only.txt")
            script = driver.arecord_script("hw:wm8960", "S32_LE", 20, capture, delta,
                                           playback=False, tmp_dir=d)
            proc = self.run_script(d, script, bindir)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            with open(delta) as fh:
                got = fh.read()
            self.assertIn("Bad descriptor", got)
            self.assertNotIn("old line one", got)     # the baseline is not the delta

    def test_arecords_exit_status_is_what_the_script_returns(self):
        for rc, expect in ((0, 0), (1, 1), (5, 5)):
            with tempfile.TemporaryDirectory() as d:
                bindir = self.stub_bin(d, arecord_rc=rc,
                                       new_dmesg=["dma dma2chan3: dma2chan3 is non-idle!"])
                script = driver.arecord_script("hw:wm8960", "S32_LE", 20,
                                               os.path.join(d, "alone.wav"),
                                               os.path.join(d, "dmesg-capture-only.txt"),
                                               playback=False, tmp_dir=d)
                proc = self.run_script(d, script, bindir)
                self.assertEqual(proc.returncode, expect, proc.stdout)
                if rc:
                    # a failed arm brings its evidence out with it
                    self.assertIn("non-idle", proc.stdout)

    def test_the_playback_arm_still_holds_the_card_open_and_kills_its_aplay(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = self.stub_bin(d)
            script = driver.arecord_script("hw:wm8960", "S32_LE", 1, os.path.join(d, "playback.wav"),
                                           os.path.join(d, "dmesg-playback-open.txt"),
                                           playback=True, tmp_dir=d)
            proc = self.run_script(d, script, bindir)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("aplay -q -D hw:wm8960", script)
            self.assertIn("trap cleanup EXIT", script)
            self.assertTrue(os.path.exists(os.path.join(d, "silence.wav")))
            # nothing of the arm's aplay is left behind
            self.assertNotIn("aplay", subprocess.run(["pgrep", "-a", "aplay"], stdout=subprocess.PIPE,
                                                     text=True).stdout)

    def test_the_script_is_valid_shell(self):
        for playback in (False, True):
            script = driver.arecord_script("hw:wm8960", "S32_LE", 20, "/tmp/x.wav", "/tmp/x.txt",
                                           playback=playback)
            proc = subprocess.run(["bash", "-n"], input=script, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(proc.returncode, 0, proc.stdout)


class Retries(unittest.TestCase):
    """An arm that fails is tried again, and the record says how many goes it took."""

    def test_an_arm_that_fails_once_is_retried_and_the_count_is_kept(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise driver.Failure("arecord: pcm_read:2285: read error: Input/output error")

        self.assertEqual(driver.attempt_arm("playback", 2, flaky), 2)
        self.assertEqual(len(calls), 2)

    def test_the_option_means_retries_so_zero_is_one_go_and_the_default_is_two(self):
        # The bug this pins: --retry was wired straight into the attempt count, so the default of
        # 1 bought no retry at all and --retry 0 bought no arm at all ("failed 0 time(s)").
        def run_with(retries, fail_first):
            calls = []

            def arm():
                calls.append(1)
                if fail_first and len(calls) < 2:
                    raise driver.Failure("arecord: pcm_read:2285: read error: Input/output error")
            try:
                took = driver.attempt_arm("x", 1 + retries, arm)
                return took, len(calls), None
            except driver.Failure as exc:
                return None, len(calls), str(exc)
        self.assertEqual(run_with(0, True)[:2], (None, 1))       # --retry 0: one go, then final
        self.assertEqual(run_with(1, True)[:2], (2, 2))          # default: a second go
        self.assertEqual(run_with(0, False)[:2], (1, 1))
        self.assertNotIn("0 time(s)", run_with(0, True)[2])

    def test_a_negative_retry_is_refused(self):
        proc = run_driver("--dry-run", "--state", "x", "--retry", "-1")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--retry takes 0 or more", proc.stdout)

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_the_record_names_the_kernel_it_was_measured_on(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine",), drift=())
            state = json.loads((out / "state.json").read_text())
            state["before"]["kernel"] = "7.0.0-1017-raspi-realtime-numaemu3-trimmed"
            state["after"]["kernel"] = "7.0.0-1017-raspi-realtime-numaemu3-trimmed"
            (out / "state.json").write_text(json.dumps(state))
            run_driver("--rebuild", str(out), check=True)
            readme = (out / "README.md").read_text()
            self.assertIn("Kernel `7.0.0-1017-raspi-realtime-numaemu3-trimmed`", readme)

    def test_an_arm_that_works_takes_one_attempt(self):
        self.assertEqual(driver.attempt_arm("alone", 3, lambda: None), 1)

    def test_an_arm_that_keeps_failing_stops_at_the_limit_and_says_so(self):
        calls = []

        def broken():
            calls.append(1)
            raise driver.Failure("arecord: pcm_read:2285: read error: Input/output error")

        with self.assertRaises(driver.Failure) as caught:
            driver.attempt_arm("alone", 3, broken)
        self.assertEqual(len(calls), 3)
        self.assertIn("failed 3 time(s)", str(caught.exception))
        self.assertIn("Input/output error", str(caught.exception))

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_a_retried_arm_says_so_in_the_record(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine", "alone"), drift=())
            state = json.loads((out / "state.json").read_text())
            state["attempts"] = {"engine": 1, "alone": 2}
            (out / "state.json").write_text(json.dumps(state))
            (out / "dmesg-capture-only.txt").write_text(
                "[Mon Oct 12 20:25:02 2026] dma dma2chan3: Bad descriptor submitted for "
                "dma2chan3, cookie: 54, irq: 0x00002000\n")
            run_driver("--rebuild", str(out), check=True)
            readme = (out / "README.md").read_text()
            self.assertIn("Attempts: engine 1, alone 2", readme)
            self.assertIn("An arm was retried", readme)
            self.assertIn("dmesg-capture-only.txt", readme)
            state = json.loads((out / "state.json").read_text())
            self.assertEqual(state["attempts"], {"engine": 1, "alone": 2})


class ArmsAndDryRun(unittest.TestCase):
    """The arm list, its order, and that --dry-run is not a measurement."""

    def test_the_arms_run_in_the_order_they_must(self):
        # The engine's own recording needs it up; the arecord arms need it stopped. Whatever order
        # the user names them in, the driver runs them in the only order that works.
        args = driver.ARMS
        self.assertEqual(args, ("engine", "playback", "alone"))
        named = [a for a in driver.ARMS if a in ["alone", "engine"]]
        self.assertEqual(named, ["engine", "alone"])

    def test_an_unknown_arm_is_refused(self):
        proc = run_driver("--arms", "engine,sideways")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("sideways", proc.stdout)

    def test_dry_run_says_what_it_would_do_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "results")
            proc = run_driver("--dry-run", "--dir", out, "--arms", "playback")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("systemctl stop namchaind", proc.stdout)
            self.assertIn("arecord", proc.stdout)
            self.assertIn("would go to", proc.stdout)
            self.assertNotIn("stop namchaind", proc.stdout.split("would run")[0])
            self.assertFalse(os.path.exists(out))

    def test_every_arm_has_a_label_and_a_note_for_the_page(self):
        for arm in driver.ARMS:
            cid, label, note = driver.ARM_INFO[arm]
            self.assertTrue(cid and label and note)
            self.assertNotEqual(cid, arm)         # the ids are the results' names, not the flags


class Rebuild(unittest.TestCase):
    """--rebuild: the numbers, the caveat and the record, from captures already on disk."""

    def run_rebuild(self, out, expect=0):
        proc = run_driver("--rebuild", str(out))
        self.assertEqual(proc.returncode, expect, proc.stdout)
        return proc.stdout

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_it_writes_the_numbers_the_page_and_the_record(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d)
            self.run_rebuild(out)
            for name in ("manifest.json", "state.json", "noise-numbers.json", "index.html",
                         "README.md", ".gitignore"):
                self.assertTrue((out / name).exists(), name)
            numbers = json.loads((out / "noise-numbers.json").read_text())
            self.assertEqual([c["id"] for c in numbers["captures"]],
                             ["engine-muted", "playback-open", "capture-only"])
            for c in numbers["captures"]:
                self.assertAlmostEqual(c["check_db"], 0.0, delta=0.05)
                self.assertIn("raw_rms_dbfs", c)
            # The page and every graph it points at.
            page = (out / "index.html").read_text()
            self.assertIn("The codec's input noise", page)
            for c in numbers["captures"]:
                self.assertIn("img/spectrum-%s.png" % c["id"], page)
                self.assertIn("img/bands-%s.png" % c["id"], page)
            self.assertTrue((out / "img" / "spectra-compare.png").exists())

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_the_record_calls_out_a_capture_that_is_mostly_outside_the_band(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, drift=("alone",))
            self.run_rebuild(out)
            readme = (out / "README.md").read_text()
            numbers = {c["id"]: c for c in json.loads(
                (out / "noise-numbers.json").read_text())["captures"]}
            drift = numbers["capture-only"]
            self.assertGreater(drift["outside_band_db"], driver.OUTSIDE_BAND_DB)
            self.assertIn("`capture-only` is not as quiet as its band-limited figure says.", readme)
            # ... and the two arms that do not drift are not accused of it.
            for cid in ("engine-muted", "playback-open"):
                self.assertLess(numbers[cid]["outside_band_db"], driver.OUTSIDE_BAND_DB)
                self.assertNotIn("`%s` is not as quiet" % cid, readme)

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_the_record_keeps_the_runs_own_date_and_settings(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine",), drift=(), ran_at="2026-10-11T09:00:00+01:00")
            self.run_rebuild(out)
            state = json.loads((out / "state.json").read_text())
            self.assertEqual(state["ran_at"], "2026-10-11T09:00:00+01:00")
            self.assertNotIn("rebuilt_at", state)     # a rebuild does not dirty a tracked file
            readme = (out / "README.md").read_text()
            self.assertIn("2026-10-11", readme)
            self.assertIn("a synthetic bench", readme)
            self.assertIn("`engine-muted`", readme)
            self.assertNotIn("`playback-open`", readme)     # an arm that was not run
            self.assertIn("format `S32_LE`", readme)

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_it_ignores_captures_that_are_not_there(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine", "playback", "alone"))
            os.remove(out / "captures" / "playback-open.wav")
            self.run_rebuild(out)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual([c["id"] for c in manifest["captures"]],
                             ["engine-muted", "capture-only"])

    def test_a_run_does_not_quietly_replace_an_earlier_one(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d)
            proc = run_driver("--dir", str(out), "--arms", "engine", "--state", "a synthetic bench")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("already holds captures", proc.stdout)
            self.assertIn("--rebuild", proc.stdout)
            # ... and what it refused to overwrite is still there.
            self.assertTrue((out / "captures" / "engine-muted.wav").exists())

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_the_bar_claim_follows_the_number_it_is_about(self):
        # A run far above the bench test's bar must not be described as inside it. -63.7 dBFS is
        # 11 dB outside, and the record said "inside" until this was fixed.
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine",), drift=(), level_dbfs=-63.7)
            self.run_rebuild(out)
            readme = (out / "README.md").read_text()
            self.assertIn("outside", readme)
            self.assertIn("paint the codec block", readme)
            self.assertNotIn("unweighted, inside the bench test", readme)
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine",), drift=(), level_dbfs=-89.0)
            self.run_rebuild(out)
            readme = (out / "README.md").read_text()
            self.assertIn("unweighted, inside the bench test", readme)
            self.assertNotIn("outside", readme)

    @unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
    def test_the_record_names_the_mains_line_and_what_agreement_means(self):
        with tempfile.TemporaryDirectory() as d:
            out = make_results_dir(d, arms=("engine", "playback", "alone"), drift=("alone",),
                                   mains_hz=50.0, mains_dbfs=-68.0)
            self.run_rebuild(out)
            readme = (out / "README.md").read_text()
            numbers = {c["id"]: c for c in json.loads(
                (out / "noise-numbers.json").read_text())["captures"]}
            for c in numbers.values():
                fifty = [m for m in c["mains"] if m["nominal_hz"] == 50.0]
                self.assertEqual(len(fifty), 1)
                # A tone is not bin-centred (0.73 Hz bins), so the Hann-windowed peak bin reads
                # about 2 dB under the tone's own level -- codec-noise.py's figure does the same,
                # which is why the two agree exactly on a real capture.
                self.assertAlmostEqual(fifty[0]["dbfs"], -68.0, delta=3.0)
                self.assertLess(abs(fifty[0]["hz"] - 50.0), 2.0)
            self.assertIn("| 50 Hz |", readme)
            self.assertIn("All 3 arms agree", readme)

    def test_a_real_run_will_not_start_without_a_state_line(self):
        # The state line is the record's only description of the wiring, and the script cannot see
        # it: a run with no --state would write a record that says nothing about what it measured.
        proc = run_driver("--dir", "/tmp/never-used", "--arms", "engine")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--state is required", proc.stdout)
        # ... but a rehearsal writes no record, so it may go without one, and it says so.
        proc = run_driver("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("MISSING", proc.stdout)

    def test_a_run_that_would_reach_the_host_fails_its_test(self):
        # The guard every test above relies on: a run with nothing to refuse goes for the host's
        # lock, and the ssh it reaches for is the stub, which fails the test rather than connect.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(AssertionError) as caught:
                run_driver("--dir", d, "--arms", "engine", "--state", "a synthetic bench",
                           "--lock-wait", "0")
            self.assertIn("tried to reach a host", str(caught.exception))
            self.assertFalse(os.path.exists(os.path.join(d, "captures")))

    def test_a_directory_that_is_not_a_run_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            proc = run_driver("--rebuild", d)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("state.json", proc.stdout)


@unittest.skipUnless(DOC_PYTHON, "no python with numpy and Pillow (the harness's bundled one)")
class DocumentBuilder(unittest.TestCase):
    """noise-document.py's own numbers, against scripts/codec-noise.py's."""

    def build(self, d, captures, extra=None):
        manifest = {"title": "a synthetic page", "meta": "no pedal", "trim": 0.0,
                    "captures": captures}
        manifest.update(extra or {})
        path = os.path.join(d, "manifest.json")
        with open(path, "w") as fh:
            json.dump(manifest, fh)
        proc = subprocess.run([DOC_PYTHON, str(DOCUMENT), path], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        with open(os.path.join(d, "noise-numbers.json")) as fh:
            return json.load(fh), proc.stdout

    def test_rms_matches_codec_noise_py_on_a_tone_and_the_dc_and_uv_come_with_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tone.wav")
            write_wav(path, seconds=2.0, tone_hz=1000.0, level_dbfs=-40.0)
            numbers, _ = self.build(d, [{"id": "tone", "path": path, "label": "a 1 kHz tone",
                                         "note": "", "trim": 0.0}])
            c = numbers["captures"][0]
            self.assertAlmostEqual(c["rms_dbfs"], -40.0, delta=0.2)
            self.assertAlmostEqual(c["check_db"], 0.0, delta=0.05)
            self.assertAlmostEqual(c["rms_uv"], 10 ** (-40.0 / 20) * 1e6, delta=1e4)
            self.assertLess(abs(c["dc_offset_uv"]), 5.0)

    def test_the_raw_figure_separates_hiss_from_drift(self):
        with tempfile.TemporaryDirectory() as d:
            hiss = os.path.join(d, "hiss.wav")
            drift = os.path.join(d, "drift.wav")
            write_wav(hiss, seconds=2.0, tone_hz=1000.0, level_dbfs=-90.0)
            write_wav(drift, seconds=2.0, tone_hz=1000.0, level_dbfs=-90.0, drift=True)
            numbers, _ = self.build(d, [
                {"id": "hiss", "path": hiss, "label": "hiss", "note": "", "trim": 0.0},
                {"id": "drift", "path": drift, "label": "drift", "note": "", "trim": 0.0}])
            by_id = {c["id"]: c for c in numbers["captures"]}
            # The 1 kHz tone is in the band for both; only the drifting one has energy outside it.
            self.assertLess(by_id["hiss"]["outside_band_db"], 1.0)
            self.assertGreater(by_id["drift"]["outside_band_db"], 5.0)
            self.assertGreater(by_id["drift"]["raw_rms_dbfs"], by_id["drift"]["rms_dbfs"])

    def test_the_band_axis_is_chosen_to_hold_every_bar(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "quiet.wav")
            write_wav(path, seconds=2.0, tone_hz=1000.0, level_dbfs=-80.0)
            numbers, _out = self.build(d, [{"id": "quiet", "path": path, "label": "quiet",
                                            "note": "", "trim": 0.0}])
            self.assertIn("index.html", os.listdir(d))
            self.assertTrue(os.path.exists(os.path.join(d, "img", "bands-quiet.png")))

    def test_a_manifest_with_no_captures_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manifest.json")
            with open(path, "w") as fh:
                json.dump({"title": "empty", "captures": []}, fh)
            proc = subprocess.run([DOC_PYTHON, str(DOCUMENT), path], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("no captures", proc.stdout)


if __name__ == "__main__":
    unittest.main()

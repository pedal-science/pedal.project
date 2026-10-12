"""Tests for pedal.benchtest's runner, its fakes, and the real bench with stand-ins behind it.

The runner is driven through FakeBench, the same fakes `--fake` serves: an outcome queued for a
benchtest is what its next run reports, and an empty queue passes. The real bench is given a
stand-in pedal-diag (a script that prints a report and exits 1, as the real one does on a fail),
a stub engine client, and a helper thread that answers jobs, so no pedal is touched.

Run with:
    devices/common/test-pedald -v test_benchtest_runner
"""

import json
import os
import pathlib
import stat
import sys
import tempfile
import threading
import time
import unittest

ROOTFS = pathlib.Path(__file__).resolve().parents[1] / "rootfs"
sys.path.insert(0, str(ROOTFS / "usr/local/lib"))

from benchtest import catalog, real  # noqa: E402
from benchtest.fakes import FakeBench  # noqa: E402
from benchtest.helper import HelperQueue  # noqa: E402
from benchtest.lamps import History  # noqa: E402
from benchtest.runner import Busy, Runner  # noqa: E402

INTERFACE = real.load_interface(str(ROOTFS / "etc/pedal/pedal-interface.json"))
QUIET = {"dc_offset": 0.0, "rms_dbfs": -99.4, "rms_dbfs_a": -100.4, "peak_dbfs": -88.0,
         "lines_low": [{"hz": 750.0, "dbfs": -115.0}], "lines_high": [], "seconds": 18.0,
         "sample_rate": 48000}


class Rig:
    """A runner, its history and its helper queue, in a temporary state directory."""

    def __init__(self, test, bench=None):
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.bench = bench or FakeBench()
        self.history = History(os.path.join(self.dir.name, "history.json"))
        self.helper = HelperQueue()
        self.runner = Runner(self.bench, self.history, self.helper, threading.RLock())
        test.addCleanup(self.stop)

    def stop(self):
        self.runner.cancel()
        self.helper.close()
        self.runner.join(5)

    def start(self, tests, origin=None):
        return self.runner.start(tests, origin or {"kind": "tests"})

    def wait(self, predicate, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self.runner.snapshot()
            if snap and predicate(snap):
                return snap
            time.sleep(0.02)
        raise AssertionError("timed out; run is %r" % self.runner.snapshot())

    def finish(self, timeout=10.0):
        return self.wait(lambda s: s["status"] in ("done", "stopped") and not self.runner.active(),
                         timeout)

    def answer_setups(self, snap_predicate=None, timeout=10.0):
        """Say "done" to every setup prompt until the run ends."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self.runner.snapshot()
            if snap["status"] == "waiting_setup":
                self.runner.decide(snap["id"], False)
            elif snap["status"] in ("done", "stopped") and not self.runner.active():
                return snap
            time.sleep(0.02)
        raise AssertionError("timed out; run is %r" % self.runner.snapshot())


def statuses(snap):
    return {t["test"]: t["status"] for t in snap["tests"]}


class RunnerWithFakes(unittest.TestCase):
    def test_tests_run_in_catalog_order_and_empty_queues_pass(self):
        rig = Rig(self)
        rig.start(["core", "codec", "link"])
        snap = rig.finish()
        self.assertEqual([t["test"] for t in snap["tests"]], ["codec", "link", "core"])
        self.assertEqual(set(statuses(snap).values()), {"pass"})
        self.assertEqual([r["test"] for r in rig.bench.snapshot()["ran"]], ["codec", "link", "core"])

    def test_a_queued_outcome_is_used_once(self):
        rig = Rig(self)
        rig.bench.push("link", {"ok": False, "component": "uart_wires", "check": "pin 8"})
        rig.start(["link"])
        first = rig.finish()["tests"][0]["result"]
        self.assertEqual(first["status"], "fail")
        self.assertEqual({c["component"]: c["ok"] for c in first["checks"]},
                         {"uart_wires": False, "pico": True, "core": True})
        rig.start(["link"])
        self.assertEqual(rig.finish()["tests"][0]["status"], "pass")
        lamp = rig.history.lamps(["uart_wires"], ["link"])
        self.assertEqual(lamp["components"]["uart_wires"], {"current": "pass", "previous": "fail"})

    def test_one_run_at_a_time(self):
        rig = Rig(self)
        rig.start(["noise_left"])
        rig.wait(lambda s: s["status"] == "waiting_setup")
        with self.assertRaises(Busy):
            rig.start(["codec"])

    def test_setup_is_asked_once_per_change_and_remembered(self):
        rig = Rig(self)
        rig.start(["noise_left"])
        snap = rig.wait(lambda s: s["status"] == "waiting_setup")
        self.assertEqual(snap["waiting"]["test"], "noise_left")
        self.assertIn("left output", snap["waiting"]["steps"][0])
        self.assertTrue(rig.runner.decide(snap["id"], False))
        self.assertEqual(rig.finish()["tests"][0]["status"], "pass")
        rig.start(["noise_left"])
        self.assertEqual(rig.finish()["tests"][0]["status"], "pass")
        self.assertEqual(rig.runner.setup, {"lead": "left_output", "codec_input": "board"})

    def test_skip_and_stop_while_waiting_for_setup(self):
        rig = Rig(self)
        rig.start(["codec", "noise_left", "noise_right"])
        snap = rig.wait(lambda s: s["status"] == "waiting_setup")
        rig.runner.decide(snap["id"], True)
        rig.wait(lambda s: s["status"] == "waiting_setup" and s["waiting"]["test"] == "noise_right")
        rig.runner.cancel()
        snap = rig.finish()
        self.assertEqual(statuses(snap), {"codec": "pass", "noise_left": "skipped",
                                          "noise_right": "stopped"})
        self.assertEqual(snap["status"], "stopped")

    def test_codec_absent_blocks_the_noise_tests_in_the_same_run(self):
        rig = Rig(self)
        rig.bench.push("codec", {"ok": False, "codec_present": False})
        rig.start(["codec", "noise_left"])
        snap = rig.finish()
        self.assertEqual(statuses(snap), {"codec": "fail", "noise_left": "not_run"})
        self.assertEqual(snap["tests"][1]["result"]["summary"], catalog.CODEC_FIRST)
        self.assertEqual(rig.history.lamps(["output_left"], [])["components"]["output_left"]["current"], None)

    def test_a_named_failure_paints_only_the_named_block(self):
        rig = Rig(self)
        rig.bench.push("codec", {"component": "codec_wires", "check": "SDA on header pin 3"})
        rig.start(["codec"])
        result = rig.finish()["tests"][0]["result"]
        self.assertEqual({c["component"]: c["ok"] for c in result["checks"]},
                         {"codec_wires": False, "codec": True})
        self.assertTrue(result["facts"]["codec_present"])

    def test_hum_offers_the_battery_test_and_the_battery_test_uses_its_reading(self):
        rig = Rig(self)
        rig.bench.push("noise_input", {"hum": True})
        rig.start(["noise_input"])
        snap = rig.answer_setups()
        self.assertEqual(snap["tests"][0]["result"]["facts"]["line50_dbfs"], -58.3)
        self.assertTrue(rig.history.bench_facts()["hum"])
        rig.start(["noise_battery"])
        snap = rig.answer_setups()
        result = snap["tests"][0]["result"]
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["reference_line50_dbfs"], -58.3)

    def test_not_run_paints_nothing(self):
        rig = Rig(self)
        rig.bench.push("core", "not_run")
        rig.start(["core"])
        rig.finish()
        self.assertEqual(rig.history.data["runs"], [])

    def test_a_benchtest_that_raises_is_not_run(self):
        class Broken(FakeBench):
            def run(self, test_id, ctx):
                raise RuntimeError("boom")
        rig = Rig(self, Broken())
        rig.start(["core"])
        result = rig.finish()["tests"][0]["result"]
        self.assertEqual(result["status"], "not_run")
        self.assertIn("boom", result["summary"])


class HelperGate(unittest.TestCase):
    def test_without_a_helper_the_helper_tests_say_so(self):
        bench = FakeBench()
        bench.needs_helper = True
        rig = Rig(self, bench)
        rig.runner.setup = {"lead": "left_output"}
        rig.start(["probe", "noise_left"])
        snap = rig.finish()
        self.assertEqual(statuses(snap), {"probe": "not_run", "noise_left": "not_run"})
        for t in snap["tests"]:
            self.assertIn("scripts/benchtest", t["result"]["summary"])

    def test_a_polling_helper_counts_as_present_for_a_minute(self):
        clock = [100.0]
        queue = HelperQueue(clock=lambda: clock[0])
        self.assertFalse(queue.present())
        self.assertIsNone(queue.next(0))
        self.assertTrue(queue.present())
        clock[0] += 59
        self.assertTrue(queue.present())
        clock[0] += 2
        self.assertFalse(queue.present())

    def test_jobs_round_trip(self):
        queue = HelperQueue()
        job_id = queue.submit("capture", {"seconds": 20})
        job = queue.next(1)
        self.assertEqual((job["id"], job["kind"], job["seconds"]), (job_id, "capture", 20))
        self.assertTrue(queue.post(job_id, True, None, {"rms_dbfs": -99.0}))
        self.assertEqual(queue.wait(job_id, 1), {"ok": True, "error": None, "result": {"rms_dbfs": -99.0}})
        self.assertFalse(queue.post(job_id, True, None, {}))


class HelperThread:
    """Answers the helper's jobs the way scripts/benchtest would."""

    def __init__(self, queue, analysis=QUIET, probe=None):
        self.queue = queue
        self.analysis = analysis
        self.probe = probe or {"present": True, "serial": "E661", "port": "/dev/cu.usbmodem1"}
        self.jobs = []
        self.fetched = []
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 2
        while not queue.present() and time.monotonic() < deadline:
            time.sleep(0.01)

    def _loop(self):
        while not self._stop.is_set():
            job = self.queue.next(0.2)
            if job is None:
                continue
            self.jobs.append(job)
            if job["kind"] == "probe_usb":
                self.queue.post(job["id"], True, None, self.probe)
            elif job["kind"] == "analyse_recording":
                path = self.queue.recording(job["url"].rsplit("/", 1)[-1])
                self.fetched.append(path)
                self.queue.post(job["id"], path is not None, None if path else "no recording",
                                self.analysis)
            else:
                self.queue.post(job["id"], True, None, self.analysis)

    def stop(self):
        self._stop.set()
        self.thread.join(2)


class StubEngine:
    """The calls RealBench makes on namchaind, answered from memory."""

    def __init__(self, record_dir, mute=False):
        self.record_dir = record_dir
        self.mute = mute
        self.calls = []
        self.recording = None

    def status(self):
        self.calls.append(("engine.status", {}))
        return {"status": {"mute": self.mute}}

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "engine.mute":
            self.mute = params["mute"]
            return {"mute": self.mute}
        if method == "engine.record":
            if params.get("action") == "start":
                path = os.path.join(self.record_dir, params["name"])
                os.makedirs(path)
                with open(os.path.join(path, "capture.wav"), "wb") as f:
                    f.write(b"RIFF....WAVE")
                self.recording = {"active": True, "name": params["name"], "path": path}
                return {"record": dict(self.recording)}
            if self.recording:
                self.recording["active"] = False
            return {"record": dict(self.recording or {"active": False})}
        raise AssertionError("unexpected call %s" % method)

    def close(self):
        pass


def fake_diag(directory, report, exit_code=1):
    path = os.path.join(directory, "pedal-diag")
    with open(path, "w") as f:
        f.write("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\nexit %d\n" % (json.dumps(report), exit_code))
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class RealBenchWithStandIns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._settle = real.MUTE_SETTLE_S
        real.MUTE_SETTLE_S = 0.0
        self.addCleanup(setattr, real, "MUTE_SETTLE_S", self._settle)

    def bench(self, report, exit_code=1):
        return real.RealBench(diag=fake_diag(self.tmp.name, report, exit_code), interface=INTERFACE)

    def test_one_diag_report_judges_every_health_test(self):
        report = {"findings": [
            {"severity": "fail", "key": "codec.i2c_absent", "what": "nothing answers at 0x1a",
             "evidence": "i2cget: NACK", "likely": ["the lead in pin 1"], "check": "x"},
            {"severity": "ok", "key": "host.thermal", "what": "cool", "evidence": "48 C"},
        ], "sample": {}}
        bench = self.bench(report)
        calls = []
        original = bench._diag_once
        bench._diag_once = lambda: calls.append(1) or original()
        rig = Rig(self, bench)
        rig.start(["codec", "core", "noise_left"])
        snap = rig.finish()
        self.assertEqual(len(calls), 1)
        self.assertEqual(statuses(snap), {"codec": "fail", "core": "pass", "noise_left": "not_run"})
        codec = snap["tests"][0]["result"]
        self.assertIn("header pin 1", codec["next"])
        self.assertEqual(snap["tests"][2]["result"]["summary"], catalog.CODEC_FIRST)

    def test_an_unreadable_diag_is_not_run(self):
        path = os.path.join(self.tmp.name, "missing-pedal-diag")
        rig = Rig(self, real.RealBench(diag=path, interface=INTERFACE))
        rig.start(["codec"])
        self.assertEqual(rig.finish()["tests"][0]["status"], "not_run")

    def test_probe_asks_the_helper(self):
        rig = Rig(self, self.bench({"findings": []}))
        helper = HelperThread(rig.helper)
        self.addCleanup(helper.stop)
        rig.start(["probe"])
        result = rig.finish()["tests"][0]["result"]
        self.assertEqual(result["status"], "pass")
        self.assertIn("E661", result["summary"])

    def test_output_noise_mutes_captures_and_puts_the_mute_back(self):
        bench = self.bench({"findings": [{"severity": "ok", "key": "codec.answers", "what": "ok"}]})
        engine = StubEngine(self.tmp.name, mute=False)
        bench.engine = lambda: engine
        rig = Rig(self, bench)
        helper = HelperThread(rig.helper)
        self.addCleanup(helper.stop)
        rig.runner.setup = {"lead": "left_output"}
        rig.start(["noise_left"])
        result = rig.finish()["tests"][0]["result"]
        self.assertEqual(result["status"], "pass")
        mutes = [p["mute"] for m, p in engine.calls if m == "engine.mute"]
        self.assertEqual(mutes, [True, False])
        job = helper.jobs[0]
        self.assertEqual((job["kind"], job["seconds"], job["skip_seconds"], job["channel"]),
                         ("capture", 20, 2, 0))

    def test_input_noise_records_on_the_engine_and_the_helper_fetches_it(self):
        bench = self.bench({"findings": [{"severity": "ok", "key": "codec.answers", "what": "ok"}]})
        engine = StubEngine(self.tmp.name, mute=True)
        bench.engine = lambda: engine
        rig = Rig(self, bench)
        hum = dict(QUIET, rms_dbfs=-52.8, lines_low=[{"hz": 49.8, "dbfs": -58.3}])
        helper = HelperThread(rig.helper, analysis=hum)
        self.addCleanup(helper.stop)
        rig.runner.setup = {"lead": "guitar_input"}
        rig.start(["noise_input"])
        result = rig.finish()["tests"][0]["result"]
        self.assertEqual({c["component"]: c["ok"] for c in result["checks"]},
                         {"mains": False, "guitar_input": True})
        starts = [p for m, p in engine.calls if m == "engine.record" and p.get("action") == "start"]
        self.assertEqual(starts[0]["seconds"], 20)
        self.assertTrue(starts[0]["name"].startswith("benchtest-"))
        self.assertEqual(helper.jobs[0]["kind"], "analyse_recording")
        self.assertTrue(helper.fetched[0].endswith("capture.wav"))
        self.assertEqual([p["mute"] for m, p in engine.calls if m == "engine.mute"], [True, True])


if __name__ == "__main__":
    unittest.main()

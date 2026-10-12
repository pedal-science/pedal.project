"""The two halves of pedal.benchtest against each other: the app's job queue and the workstation
helper's job loop, over the real HTTP API.

The app is the real one (`server.serve`, `RealBench`'s probe, capture and recording paths, the
runner's helper gate) with only what lives on the pedal stood in for: pedal-diag's report and the
engine's mute and `engine.record`. The helper is `scripts/benchtest-helper.py`'s own `Session`,
`serve` loop and `Jobs`, with the sox capture, the spectrum and the USB look injected. So a job the
app issues must be one the helper parses, the helper's result must be one the app accepts, and the
engine's recording must come down `/api/helper/recording/<id>` byte for byte.

Run with:
    devices/common/test-pedald -v test_benchtest_contract
"""

import datetime
import importlib.machinery
import importlib.util
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

DEVICE = pathlib.Path(__file__).resolve().parents[1]
REPO = DEVICE.parents[1]
sys.path.insert(0, str(DEVICE / "rootfs/usr/local/lib"))

from benchtest import real  # noqa: E402
from test_benchtest_server import Service  # noqa: E402


def load_helper():
    path = REPO / "scripts" / "benchtest-helper.py"
    loader = importlib.machinery.SourceFileLoader("benchtest_helper_contract", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = load_helper()

DIAG_REPORT = {"findings": [{"severity": "ok", "key": "codec.answers",
                             "what": "the codec answers on I2C"}]}
WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt the engine's recording, as the helper must fetch it"


def analysis(rms, lines=()):
    return {"dc_offset": 0.0, "rms_dbfs": rms, "rms_dbfs_a": rms - 1.0, "peak_dbfs": rms + 11.0,
            "lines_low": [{"hz": hz, "dbfs": level} for hz, level in lines],
            "lines_high": [], "seconds": 18.0, "sample_rate": 48000}


class FakeEngine:
    """namchaind's mute and engine.record, as RealBench uses them."""

    def __init__(self, directory):
        self.directory = directory
        self.mute = False
        self.mutes = []
        self.recording = None

    def status(self):
        return {"status": {"mute": self.mute}}

    def call(self, method, **params):
        if method == "engine.mute":
            self.mute = bool(params["mute"])
            self.mutes.append(self.mute)
            return {"mute": self.mute}
        if method == "engine.record" and params.get("action") == "start":
            path = os.path.join(self.directory, params["name"])
            os.makedirs(path)
            with open(os.path.join(path, "capture.wav"), "wb") as f:
                f.write(WAV_BYTES)
            self.recording = {"active": True, "name": params["name"], "path": path}
            return {"record": dict(self.recording)}
        if method == "engine.record":
            self.recording["active"] = False
            return {"record": dict(self.recording)}
        raise AssertionError("unexpected engine call %s" % method)

    def close(self):
        pass


class StandInBench(real.RealBench):
    """RealBench with pedal-diag's report and the engine stood in for; everything else is real."""

    def __init__(self, engine):
        super().__init__(diag="/nonexistent/pedal-diag")
        self.fake_engine = engine

    def _diag_once(self):
        return DIAG_REPORT, None

    def engine(self):
        return self.fake_engine


class StubDevice:
    def get(self):
        return "SSL 2+ Mk II"


class HelperAgainstTheApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        saved = real.MUTE_SETTLE_S
        real.MUTE_SETTLE_S = 0.0
        self.addCleanup(setattr, real, "MUTE_SETTLE_S", saved)
        self.engine = FakeEngine(os.path.join(self.tmp.name, "engine"))
        os.makedirs(self.engine.directory)
        self.svc = Service(self, bench=StandInBench(self.engine))
        self.recorded, self.analysed, self.said = [], [], []

    def record(self, device, path, seconds):
        self.recorded.append((device, seconds))
        with open(path, "wb") as f:
            f.write(b"RIFF sox's capture")

    def analyse(self, path, channel, skip_seconds):
        with open(path, "rb") as f:
            data = f.read()
        self.analysed.append((os.path.basename(path), data, channel, skip_seconds))
        if data == WAV_BYTES:
            return analysis(-68.4, ((750.0, -80.0),))
        return analysis(-99.4, ((750.0, -115.0),))

    def start_helper(self):
        jobs = helper.Jobs(device=StubDevice(), record=self.record, analyse=self.analyse,
                           probe_usb=lambda: {"present": True, "serial": "E6633861A3555B38",
                                              "port": "/dev/cu.usbmodem1102", "machine": "desk"},
                           results=os.path.join(self.tmp.name, "results"),
                           now=lambda: datetime.datetime(2026, 10, 12, 13, 45, 7),
                           out=self.said.append)
        session = helper.Session(self.svc.url)
        self.assertEqual(session.token, self.svc.token)
        outcome = []
        thread = threading.Thread(
            target=lambda: outcome.append(helper.serve(session, jobs, wait=1, gone_after=2,
                                                       sleep=lambda s: time.sleep(min(s, 0.05)),
                                                       out=self.said.append)),
            daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not self.svc.app.helper.present():
            self.assertLess(time.monotonic(), deadline, "the helper never polled")
            time.sleep(0.02)
        return thread, outcome

    def test_every_job_kind_round_trips_through_the_real_api(self):
        thread, outcome = self.start_helper()
        status, _, _ = self.svc.request("POST", "/api/run",
                                        {"tests": ["probe", "noise_left", "noise_input"]})
        self.assertEqual(status, 202)
        state = self.svc.wait_run(timeout=30)
        results = {slot["test"]: slot["result"] for slot in state["run"]["tests"]}

        probe = results["probe"]
        self.assertEqual(probe["status"], "pass", probe["summary"])
        self.assertIn("E6633861A3555B38", probe["evidence"])

        left = results["noise_left"]
        self.assertEqual(left["status"], "pass", left["summary"])
        self.assertEqual(left["facts"]["rms_dbfs"], -99.4)
        self.assertEqual(self.recorded, [("SSL 2+ Mk II", 20.0)])

        guitar = results["noise_input"]
        self.assertEqual(guitar["status"], "pass", guitar["summary"])
        self.assertEqual(guitar["facts"]["rms_dbfs"], -68.4)

        # What the helper analysed: sox's capture, then the engine's WAV fetched over the API,
        # each from channel 0 with the first 2 s dropped.
        self.assertEqual([(data, channel, skip) for _, data, channel, skip in self.analysed],
                         [(b"RIFF sox's capture", 0, 2.0), (WAV_BYTES, 0, 2.0)])
        self.assertTrue(self.analysed[0][0].startswith("134507-capture-left-output-noise"),
                        self.analysed[0][0])
        self.assertTrue(self.analysed[1][0].startswith("134507-core-"), self.analysed[1][0])

        # Muted for each measurement and put back each time.
        self.assertEqual(self.engine.mutes, [True, False, True, False])
        self.assertFalse(any("failed" in line or "could not post" in line for line in self.said),
                         self.said)

        self.svc.app.request_stop("test over")
        thread.join(15)
        self.assertFalse(thread.is_alive(), "the helper did not notice the service had gone")
        self.assertEqual(outcome, ["gone"])

    def test_a_helper_failure_is_the_pages_sentence(self):
        def record(device, path, seconds):
            raise helper.JobError("sox is not installed on this computer")
        self.record = record
        thread, _ = self.start_helper()
        self.svc.request("POST", "/api/run", {"tests": ["noise_left"]})
        state = self.svc.wait_run(timeout=30)
        result = state["run"]["tests"][0]["result"]
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(result["evidence"], "sox is not installed on this computer")
        self.assertEqual(self.engine.mutes, [True, False])


if __name__ == "__main__":
    unittest.main()

"""scripts/benchtest-helper.py: the workstation's job handling, without an interface or a pedal.

    python3 -m unittest discover -s scripts/tests

A fake service on loopback hands out one job of each kind and an unknown one, and the posted
results are checked; the recording is a WAV written by a stand-in for sox, analysed by the real
scripts/codec-noise.py --json. Nothing here opens an audio device, ssh, or the browser.
"""
import datetime
import http.server
import importlib.machinery
import importlib.util
import json
import math
import os
import pathlib
import queue
import signal
import tempfile
import threading
import types
import unittest
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = load("benchtest_helper", SCRIPTS / "benchtest-helper.py")

TOKEN = "t0k3n"


def write_stereo(path, seconds=3.0, rate=48000, freq=1000.0, level_dbfs=-40.0):
    """2 channels, 24-bit: a tone on channel 0 (input 1), silence on channel 1."""
    amp = (10 ** (level_dbfs / 20)) * math.sqrt(2) * ((1 << 23) - 1)
    frames = bytearray()
    for i in range(int(rate * seconds)):
        s = int(round(amp * math.sin(2 * math.pi * freq * i / rate)))
        frames += s.to_bytes(3, "little", signed=True) + (0).to_bytes(3, "little", signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


class FakeService:
    """The helper half of pedal.benchtest's API, on 127.0.0.1, with a bearer token."""

    def __init__(self, jobs, recording):
        self.jobs = queue.Queue()
        for job in jobs:
            self.jobs.put(job)
        self.expected = len(jobs)
        self.results = []
        self.requests = []
        self.recording = recording
        self.lock = threading.Lock()
        self.stopping = False
        service = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=None):
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def authorised(self):
                with service.lock:
                    service.requests.append((self.command, self.path, dict(self.headers)))
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    self.reply(401, {"error": "token"})
                    return False
                return True

            def do_GET(self):
                if not self.authorised():
                    return
                if self.path == "/api/health":
                    self.reply(200, {"ok": True})
                elif self.path.startswith("/api/helper/next"):
                    try:
                        self.reply(200, {"job": service.jobs.get_nowait()})
                    except queue.Empty:
                        self.reply(204)
                        with service.lock:
                            done = len(service.results) >= service.expected
                        if done:
                            service.stop()
                elif self.path == "/api/recordings/t2-adc.wav":
                    with open(service.recording, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.reply(404, {"error": "no such path"})

            def do_POST(self):
                if not self.authorised():
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/helper/result":
                    with service.lock:
                        service.results.append(body)
                    self.reply(200, {"ok": True})
                else:
                    self.reply(404, {"error": "no such path"})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = "http://127.0.0.1:%d/#%s" % (self.port, TOKEN)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        """Go away the way the real service does when it exits: connections are refused."""
        if self.stopping:
            return
        self.stopping = True

        def down():
            self.server.shutdown()
            self.server.server_close()
        threading.Thread(target=down, daemon=True).start()


class StubDevice:
    def __init__(self, name="SSL 2+ Mk II"):
        self.name = name

    def get(self):
        return self.name


class ServeAgainstFakeService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.core_wav = self.dir / "core.wav"
        write_stereo(self.core_wav, level_dbfs=-60.0)
        self.recorded = []

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, device, path, seconds):
        self.recorded.append((device, path, seconds))
        write_stereo(path, seconds=seconds, level_dbfs=-40.0)

    def test_one_job_of_each_kind(self):
        jobs = [
            {"id": "j1", "kind": "capture",
             "params": {"seconds": 3, "skip_seconds": 1, "channel": 0, "note": "Left output"}},
            {"id": "j2", "kind": "analyse_recording",
             "params": {"url": "/api/recordings/t2-adc.wav", "channel": 0, "skip_seconds": 1}},
            {"id": "j3", "kind": "probe_usb", "params": {}},
            {"id": "j4", "kind": "make_tea", "params": {}},
        ]
        service = FakeService(jobs, self.core_wav)
        said = []
        station = helper.Jobs(
            device=StubDevice(), record=self.record,
            probe_usb=lambda: {"present": True, "serial": "E6633861A3555B38",
                               "port": "/dev/cu.usbmodem1102"},
            results=str(self.dir / "results"),
            now=lambda: datetime.datetime(2026, 10, 12, 13, 45, 7), out=said.append)
        session = helper.Session(service.url)
        how = helper.serve(session, station, wait=1, gone_after=2, sleep=lambda s: None,
                           out=said.append)
        self.assertEqual(how, "gone")
        by_id = {r["id"]: r for r in service.results}
        self.assertEqual(sorted(by_id), ["j1", "j2", "j3", "j4"])
        for r in service.results:
            self.assertEqual(set(r), {"id", "ok", "error", "result"})

        capture = by_id["j1"]
        self.assertTrue(capture["ok"], capture["error"])
        self.assertIsNone(capture["error"])
        self.assertEqual(self.recorded[0][0], "SSL 2+ Mk II")
        self.assertEqual(self.recorded[0][2], 3.0)
        result = capture["result"]
        for key in ("dc_offset", "rms_dbfs", "rms_dbfs_a", "peak_dbfs", "lines_low",
                    "lines_high", "seconds", "sample_rate"):
            self.assertIn(key, result)
        self.assertAlmostEqual(result["rms_dbfs"], -40.0, delta=0.3)
        self.assertAlmostEqual(result["seconds"], 2.0, places=2)
        self.assertEqual(result["sample_rate"], 48000)
        self.assertEqual(result["device"], "SSL 2+ Mk II")
        self.assertTrue(any(abs(l["hz"] - 1000) < 1 for l in result["lines_high"]))
        wav = self.dir / "results" / "2026-10-12" / "134507-capture-left-output.wav"
        self.assertTrue(wav.exists())
        self.assertEqual(result["file"], str(wav))
        sidecar = json.loads(wav.with_suffix(".json").read_text())
        self.assertEqual(sidecar["job"]["id"], "j1")
        self.assertEqual(sidecar["result"]["rms_dbfs"], result["rms_dbfs"])

        recording = by_id["j2"]
        self.assertTrue(recording["ok"], recording["error"])
        self.assertAlmostEqual(recording["result"]["rms_dbfs"], -60.0, delta=0.3)
        fetched = self.dir / "results" / "2026-10-12" / "134507-core-t2-adc.wav"
        self.assertEqual(fetched.read_bytes(), self.core_wav.read_bytes())

        probe = by_id["j3"]
        self.assertTrue(probe["ok"])
        self.assertEqual(probe["result"], {"present": True, "serial": "E6633861A3555B38",
                                           "port": "/dev/cu.usbmodem1102"})

        unknown = by_id["j4"]
        self.assertFalse(unknown["ok"])
        self.assertIsNone(unknown["result"])
        self.assertIn("make_tea", unknown["error"])

        for method, path, headers in service.requests:
            self.assertEqual(headers.get("Authorization"), "Bearer " + TOKEN, path)
            self.assertNotEqual(headers.get("X-Benchtest-Client", "").lower(), "browser", path)
        self.assertTrue(any(p.startswith("/api/helper/next?wait=1") for _, p, _ in service.requests))

    def test_wait_for_service_reads_the_url_again_until_the_token_answers(self):
        service = FakeService([], self.core_wav)
        try:
            urls = iter([None, "http://127.0.0.1:%d/#stale" % service.port, service.url])
            said = []
            session = helper.wait_for_service(lambda: next(urls), timeout=30,
                                              sleep=lambda s: None, out=said.append)
            self.assertEqual(session.token, TOKEN)
            self.assertEqual(said, ["waiting for the service (no URL yet)",
                                    "waiting for the service (GET /api/health answered 401)"])
        finally:
            service.stop()

    def test_wait_for_service_gives_up_with_the_reason(self):
        ticks = iter(range(0, 1000, 10))
        with self.assertRaises(SystemExit) as caught:
            helper.wait_for_service(lambda: None, timeout=30, sleep=lambda s: None,
                                    clock=lambda: next(ticks), out=lambda m: None)
        self.assertIn("did not answer within 30 s (no URL yet)", str(caught.exception))

    def test_wait_for_service_stops_when_the_unit_failed(self):
        with self.assertRaises(SystemExit) as caught:
            helper.wait_for_service(lambda: None, alive=lambda: "pedal.benchtest on vip is failed",
                                    sleep=lambda s: None, out=lambda m: None)
        self.assertIn("is failed", str(caught.exception))


STANDIN_APP = '''\
import argparse, http.server, json, os, sys, threading, time
ap = argparse.ArgumentParser()
ap.add_argument("--fake", action="store_true")
ap.add_argument("--bind")
ap.add_argument("--port", type=int)
ap.add_argument("--state-dir")
ap.add_argument("--run-dir")
args = ap.parse_args()
with open(os.environ["STANDIN_LOG"], "w") as f:
    json.dump({"argv": sys.argv[1:], "state_dir_exists": os.path.isdir(args.state_dir)}, f)

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        ok = self.headers.get("Authorization") == "Bearer fk"
        self.send_response(200 if ok and self.path == "/api/health" else 204 if ok else 401)
        self.send_header("Content-Length", "0")
        self.end_headers()

server = http.server.ThreadingHTTPServer((args.bind, args.port), H)
with open(os.path.join(args.run_dir, "url"), "w") as f:
    f.write("http://%s:%d/#fk\\n" % (args.bind, server.server_address[1]))
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(1.5)
'''


class FakeMode(unittest.TestCase):
    def test_fake_starts_the_app_locally_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            app = os.path.join(d, "pedal-benchtest")
            log = os.path.join(d, "log.json")
            with open(app, "w") as f:
                f.write(STANDIN_APP)
            os.environ["STANDIN_LOG"] = log
            saved = helper.APP
            helper.APP = app
            try:
                self.assertEqual(helper.main(["--fake", "--no-browser", "--timeout", "10"]), 0)
            finally:
                helper.APP = saved
                del os.environ["STANDIN_LOG"]
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                signal.signal(signal.SIGHUP, signal.SIG_DFL)
            with open(log) as f:
                seen = json.load(f)
        argv = seen["argv"]
        self.assertEqual(argv[:5], ["--fake", "--bind", "127.0.0.1", "--port", "0"])
        state = argv[argv.index("--state-dir") + 1]
        self.assertTrue(seen["state_dir_exists"])
        self.assertFalse(os.path.exists(os.path.dirname(state)), "the scratch directory is removed")


class RecordingSession:
    def __init__(self):
        self.posted = []

    def post_result(self, job_id, ok, error=None, result=None, timeout=10.0):
        self.posted.append({"id": job_id, "ok": ok, "error": error, "result": result})


class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_sox_is_a_plain_failure(self):
        def record(device, path, seconds):
            helper.record_with_sox(device, path, seconds, which=lambda name: None)
        station = helper.Jobs(device=StubDevice(), record=record, results=str(self.dir),
                              out=lambda m: None)
        session = RecordingSession()
        helper.do_job({"id": "c", "kind": "capture", "params": {"seconds": 20}}, station, session,
                      out=lambda m: None)
        self.assertEqual(len(session.posted), 1)
        self.assertFalse(session.posted[0]["ok"])
        self.assertIn("brew install sox", session.posted[0]["error"])

    @unittest.skipUnless(helper.sys.platform == "darwin", "the capture is CoreAudio's")
    def test_sox_records_two_channels_24_bit_48k_from_the_named_device(self):
        seen = []

        def run(argv, **kwargs):
            seen.append(argv)
            write_stereo(argv[argv.index("-b") + 2], seconds=1.0)
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        path = str(self.dir / "c.wav")
        helper.record_with_sox("SSL 2+ Mk II", path, 1.0, run=run, which=lambda name: "/bin/sox")
        argv = seen[0]
        self.assertEqual(argv[:5], ["sox", "-q", "-t", "coreaudio", "SSL 2+ Mk II"])
        self.assertEqual(argv[argv.index("-c") + 1], "2")
        self.assertEqual(argv[argv.index("-b") + 1], "24")
        self.assertEqual(argv[argv.index("-r") + 1], "48000")
        self.assertEqual(argv[-3:], ["trim", "0", "1"])

    def test_a_crashing_handler_still_posts_a_result(self):
        def record(device, path, seconds):
            raise RuntimeError("boom")
        station = helper.Jobs(device=StubDevice(), record=record, results=str(self.dir),
                              out=lambda m: None)
        session = RecordingSession()
        helper.do_job({"id": "c", "kind": "capture", "params": {}}, station, session,
                      out=lambda m: None)
        self.assertFalse(session.posted[0]["ok"])
        self.assertIn("RuntimeError: boom", session.posted[0]["error"])

    def test_ctrl_c_during_a_job_posts_a_failure_and_stops(self):
        def record(device, path, seconds):
            raise KeyboardInterrupt
        station = helper.Jobs(device=StubDevice(), record=record, results=str(self.dir),
                              out=lambda m: None)
        session = RecordingSession()
        with self.assertRaises(KeyboardInterrupt):
            helper.do_job({"id": "c", "kind": "capture", "params": {}}, station, session)
        self.assertFalse(session.posted[0]["ok"])
        self.assertIn("Ctrl-C", session.posted[0]["error"])

    def test_bad_numbers_are_refused(self):
        station = helper.Jobs(device=StubDevice(), record=None, results=str(self.dir),
                              out=lambda m: None)
        session = RecordingSession()
        for params in ({"seconds": "lots"}, {"seconds": 5, "skip_seconds": 6}):
            helper.do_job({"id": "c", "kind": "capture", "params": params}, station, session,
                          out=lambda m: None)
        self.assertEqual([p["ok"] for p in session.posted], [False, False])
        self.assertNotIn("the helper failed", session.posted[0]["error"])


class DeviceChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmp.name, "pedal-benchtest", "station.json")
        self.devices = ["MacBook Air Microphone", "SSL 2+ Mk II"]

    def tearDown(self):
        self.tmp.cleanup()

    def choice(self, answers=(), **kwargs):
        answers = list(answers)
        return helper.DeviceChoice(config=self.config, lister=lambda: list(self.devices),
                                   ask=lambda prompt: answers.pop(0), interactive=True,
                                   show=lambda line: None, **kwargs)

    def test_asks_once_then_remembers(self):
        self.assertEqual(self.choice(["9", "2"]).get(), "SSL 2+ Mk II")
        with open(self.config) as f:
            self.assertEqual(json.load(f), {"device": "SSL 2+ Mk II"})
        self.assertEqual(self.choice([]).get(), "SSL 2+ Mk II")

    def test_device_option_wins(self):
        self.assertEqual(self.choice([], override="Other").get(), "Other")

    def test_remembered_but_unplugged_says_so(self):
        self.choice(["2"]).get()
        self.devices = ["MacBook Air Microphone"]
        with self.assertRaises(helper.JobError) as caught:
            self.choice([]).get()
        self.assertIn("not plugged in", str(caught.exception))

    def test_no_terminal_names_the_option(self):
        choice = helper.DeviceChoice(config=self.config, lister=lambda: self.devices,
                                     interactive=False)
        with self.assertRaises(helper.JobError) as caught:
            choice.get()
        self.assertIn("--device", str(caught.exception))
        self.assertIn("SSL 2+ Mk II", str(caught.exception))


IOREG = """\
+-o Root  <class IORegistryEntry, id 0x100000100, retain 30>
  +-o Debug Probe (CMSIS-DAP)@01100000  <class IOUSBHostDevice, id 0x100000abc, registered>
    | {
    |   "idProduct" = 12
    |   "idVendor" = 11914
    |   "USB Serial Number" = "E6633861A3555B38"
    |   "USB Product Name" = "Debug Probe (CMSIS-DAP)"
    |   "locationID" = 17825792
    | }
"""


class ProbeUsb(unittest.TestCase):
    def test_uses_pedal_diags_view_of_this_computer(self):
        diag = helper.load_pedal_diag()
        side = {"hostname": "desk", "usb": diag.parse_ioreg_usb(IOREG),
                "serial": [{"device": "/dev/cu.usbmodem1102", "name": "cu.usbmodem1102"}]}
        fake = types.SimpleNamespace(local_machine_aids=lambda: side,
                                     DEBUG_PROBE=diag.DEBUG_PROBE,
                                     serial_ports_for=diag.serial_ports_for)
        self.assertEqual(helper.probe_usb_local(fake),
                         {"present": True, "serial": "E6633861A3555B38",
                          "port": "/dev/cu.usbmodem1102", "machine": "desk"})
        side["usb"] = []
        self.assertEqual(helper.probe_usb_local(fake)["present"], False)

    def test_runs_on_this_computer(self):
        result = helper.probe_usb_local()
        self.assertIsInstance(result["present"], bool)
        self.assertTrue({"present", "serial", "port"} <= set(result))


class Parsing(unittest.TestCase):
    def test_token_is_the_fragment(self):
        self.assertEqual(helper.parse_url("http://vip:47820/#abc\n"), ("http://vip:47820/", "abc"))
        self.assertEqual(helper.parse_url("http://vip:47820/#token=abc"),
                         ("http://vip:47820/", "abc"))

    def test_loopback_url_is_reached_through_the_host(self):
        self.assertEqual(helper.reachable_url("http://0.0.0.0:47820/#a", "vip"),
                         "http://vip:47820/#a")
        self.assertEqual(helper.reachable_url("http://vip.local:47820/#a", "vip"),
                         "http://vip.local:47820/#a")

    def test_job_shapes(self):
        self.assertIsNone(helper.parse_job(b""))
        self.assertIsNone(helper.parse_job(b'{"job": null}'))
        self.assertEqual(helper.parse_job(b'{"job": {"id": 1, "kind": "probe_usb", "params": {}}}'),
                         {"id": 1, "kind": "probe_usb", "params": {}})
        self.assertEqual(helper.parse_job(b'{"id": 2, "kind": "capture", "seconds": 15}'),
                         {"id": 2, "kind": "capture", "params": {"seconds": 15}})

    def test_download_keeps_the_token_on_the_service(self):
        session = helper.Session("http://127.0.0.1:9/#abc")
        with self.assertRaises(helper.JobError):
            session.download("http://elsewhere.example/x.wav", os.devnull)


if __name__ == "__main__":
    unittest.main()

"""Tests for pedal.benchtest's HTTP service: the token, the API, the helper's routes, the idle
timer and shutdown.

Each test starts the real server (`server.serve`, as `pedal-benchtest` runs it) on port 0 with
fake benchtests and a temporary state and run directory, finds its address in the URL file, and
speaks to it with `http.client`. `serve` returning is the process exiting 0.

Run with:
    devices/common/test-pedald -v test_benchtest_server
"""

import http.client
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

DEVICE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEVICE / "rootfs/usr/local/lib"))

from benchtest import server  # noqa: E402
from benchtest.fakes import FakeBench  # noqa: E402


class Service:
    def __init__(self, test, idle_seconds=300.0, bench=None):
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.state_dir = os.path.join(self.dir.name, "state")
        self.run_dir = os.path.join(self.dir.name, "run")
        os.makedirs(self.state_dir)
        self.app = server.App(bench or FakeBench(), self.state_dir, idle_seconds=idle_seconds,
                              log=lambda message: None)
        self.out = io.StringIO()
        self.code = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        url_file = os.path.join(self.run_dir, "url")
        deadline = time.monotonic() + 5
        while not os.path.exists(url_file):
            if time.monotonic() > deadline:
                raise AssertionError("no URL file")
            time.sleep(0.01)
        with open(url_file) as f:
            self.url = f.read().strip()
        self.url_file = url_file
        self.port = urlsplit(self.url).port
        self.token = self.app.token
        test.addCleanup(self.stop)

    def _serve(self):
        self.code = server.serve(self.app, "127.0.0.1", 0, self.run_dir, out=self.out)

    def stop(self):
        self.app.request_stop("test over")
        self.thread.join(20)

    def exited(self, timeout=20):
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def request(self, method, path, body=None, token=True, browser=True, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if token:
            h["Authorization"] = "Bearer " + (self.token if token is True else token)
        if browser:
            h["X-Benchtest-Client"] = "browser"
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=h)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return response.status, payload, response

    def wait_run(self, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, state, _ = self.request("GET", "/api/state")
            run = state["run"]
            if run and run["status"] == "waiting_setup":
                self.request("POST", "/api/run/continue", {"run": run["id"], "skip": False})
            elif run and run["status"] in ("done", "stopped"):
                return state
            time.sleep(0.05)
        raise AssertionError("run did not finish")


class Basics(unittest.TestCase):
    def test_url_file_and_stdout(self):
        svc = Service(self)
        self.assertRegex(svc.url, r"^http://127\.0\.0\.1:\d+/#token=[A-Za-z0-9_-]+$")
        self.assertNotEqual(svc.port, 0)
        self.assertEqual(stat.S_IMODE(os.stat(svc.url_file).st_mode), 0o600)
        self.assertEqual(svc.out.getvalue().strip(), svc.url)
        self.assertTrue(svc.url.endswith("#token=" + svc.token))

    def test_page_and_assets_need_no_token(self):
        svc = Service(self)
        for path in ("/", "/stopped", "/static/app.js", "/static/app.css", "/static/stopped.js"):
            status, body, response = svc.request("GET", path, token=False, browser=False)
            self.assertEqual(status, 200, path)
            self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertEqual(svc.request("GET", "/static/../server.py", token=False)[0], 404)
        self.assertEqual(svc.request("GET", "/static/missing.js", token=False)[0], 404)

    def test_api_needs_the_token(self):
        svc = Service(self)
        self.assertEqual(svc.request("GET", "/api/health", token=False)[0], 401)
        self.assertEqual(svc.request("GET", "/api/health", token="wrong")[0], 401)
        self.assertEqual(svc.request("GET", "/api/health?token=" + svc.token, token=False)[0], 401)
        status, body, _ = svc.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["fake"], True)
        self.assertIn("version", body)

    def test_state_lists_blocks_tests_and_lamps(self):
        svc = Service(self)
        status, state, _ = svc.request("GET", "/api/state")
        self.assertEqual(status, 200)
        ids = [c["id"] for c in state["components"]]
        self.assertIn("codec_wires", ids)
        codec = next(t for t in state["tests"] if t["id"] == "codec")
        self.assertTrue(codec["default"])
        self.assertEqual(state["lamps"]["components"]["codec"], {"current": None, "previous": None})
        self.assertIsNone(state["run"])
        self.assertIn("queues", state["fake_bench"])


class Runs(unittest.TestCase):
    def test_a_fake_failure_then_a_pass_shows_two_lamps(self):
        svc = Service(self)
        status, _, _ = svc.request("POST", "/api/fake/next",
                                   {"test": "codec", "ok": False, "component": "codec_wires",
                                    "check": "SDA on header pin 3"})
        self.assertEqual(status, 200)
        status, body, _ = svc.request("POST", "/api/run", {"tests": ["codec"]})
        self.assertEqual(status, 202)
        self.assertEqual(body["run"]["tests"][0]["test"], "codec")
        state = svc.wait_run()
        self.assertEqual(state["lamps"]["components"]["codec_wires"]["current"], "fail")
        self.assertEqual(state["failures"]["codec_wires"][0]["check"], "SDA on header pin 3")
        svc.request("POST", "/api/run", {"component": "codec_wires"})
        state = svc.wait_run()
        self.assertEqual(state["lamps"]["components"]["codec_wires"], {"current": "pass", "previous": "fail"})
        ran = svc.request("GET", "/api/fake")[1]["ran"]
        self.assertEqual([r["status"] for r in ran], ["fail", "pass"])

    def test_forget(self):
        svc = Service(self)
        svc.request("POST", "/api/run", {"tests": ["core"]})
        svc.wait_run()
        self.assertEqual(svc.request("POST", "/api/history/forget", {})[0], 200)
        state = svc.request("GET", "/api/state")[1]
        self.assertEqual(state["results"], {})
        self.assertEqual(state["lamps"]["components"]["core"]["current"], None)

    def test_bad_requests(self):
        svc = Service(self)
        self.assertEqual(svc.request("POST", "/api/run", {"tests": ["nope"]})[0], 400)
        self.assertEqual(svc.request("POST", "/api/run", {"tests": ["noise_battery"]})[0], 400)
        self.assertEqual(svc.request("POST", "/api/run", {"component": "nope"})[0], 400)
        self.assertEqual(svc.request("POST", "/api/run", b"not json")[0], 400)
        self.assertEqual(svc.request("POST", "/api/fake/next", {"test": "codec", "component": "x"})[0], 400)
        self.assertEqual(svc.request("POST", "/api/run/continue", {"run": "x"})[0], 409)

    def test_a_second_run_while_one_waits_is_refused(self):
        svc = Service(self)
        svc.request("POST", "/api/run", {"tests": ["noise_left"]})
        deadline = time.monotonic() + 5
        while svc.request("GET", "/api/state")[1]["run"]["status"] != "waiting_setup":
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        self.assertEqual(svc.request("POST", "/api/run", {"tests": ["codec"]})[0], 409)
        self.assertEqual(svc.request("POST", "/api/run/cancel", {})[0], 200)
        self.assertEqual(svc.wait_run()["run"]["status"], "stopped")

    def test_fake_routes_exist_only_in_fake_mode(self):
        class NotFake(FakeBench):
            fake = False
        svc = Service(self, bench=NotFake())
        self.assertEqual(svc.request("GET", "/api/fake")[0], 404)
        self.assertNotIn("fake_bench", svc.request("GET", "/api/state")[1])


class Helper(unittest.TestCase):
    def test_long_poll_job_and_result(self):
        svc = Service(self)
        status, body, _ = svc.request("GET", "/api/helper/next?wait=0.1", browser=False)
        self.assertEqual((status, body), (200, {"job": None}))
        job_id = svc.app.helper.submit("probe_usb", {})
        status, body, _ = svc.request("GET", "/api/helper/next?wait=1", browser=False)
        self.assertEqual(body["job"], {"id": job_id, "kind": "probe_usb"})
        status, _, _ = svc.request("POST", "/api/helper/result", {
            "id": job_id, "ok": True, "error": None,
            "result": {"present": True, "serial": "E661", "port": "/dev/cu.usbmodem1"}}, browser=False)
        self.assertEqual(status, 200)
        self.assertEqual(svc.app.helper.wait(job_id, 1)["result"]["serial"], "E661")
        self.assertEqual(svc.request("POST", "/api/helper/result", {"id": job_id, "ok": True},
                                     browser=False)[0], 404)
        self.assertTrue(svc.request("GET", "/api/state")[1]["helper"]["present"])

    def test_recording_download(self):
        svc = Service(self)
        wav = os.path.join(svc.dir.name, "capture.wav")
        with open(wav, "wb") as f:
            f.write(b"RIFF\x00\x00\x00\x00WAVEdata")
        job_id = svc.app.helper.new_id()
        svc.app.helper.attach_recording(job_id, wav)
        status, body, response = svc.request("GET", "/api/helper/recording/" + job_id, browser=False)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"RIFF\x00\x00\x00\x00WAVEdata")
        self.assertEqual(response.getheader("Content-Type"), "audio/wav")
        self.assertEqual(svc.request("GET", "/api/helper/recording/nope", browser=False)[0], 404)
        self.assertEqual(svc.request("GET", "/api/helper/recording/" + job_id, token=False)[0], 401)


class Stopping(unittest.TestCase):
    def test_shutdown_answers_then_exits_zero_and_removes_the_url_file(self):
        svc = Service(self)
        status, body, _ = svc.request("POST", "/api/shutdown")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(svc.exited())
        self.assertEqual(svc.code, 0)
        self.assertFalse(os.path.exists(svc.url_file))

    def test_shutdown_takes_the_token_as_a_query_for_send_beacon(self):
        svc = Service(self)
        self.assertEqual(svc.request("POST", "/api/shutdown?token=nope", token=False)[0], 401)
        self.assertEqual(svc.request("POST", "/api/shutdown?token=" + svc.token, token=False,
                                     browser=False)[0], 200)
        self.assertTrue(svc.exited())
        self.assertEqual(svc.code, 0)

    def test_idle_without_a_browser_exits_zero(self):
        svc = Service(self, idle_seconds=0.5)
        self.assertTrue(svc.exited(5))
        self.assertEqual(svc.code, 0)
        self.assertIn("no browser", svc.app.stop_reason)

    def test_browser_requests_keep_it_alive_and_helper_requests_do_not(self):
        svc = Service(self, idle_seconds=0.8)
        for _ in range(8):
            svc.request("GET", "/api/health")
            time.sleep(0.2)
        self.assertTrue(svc.thread.is_alive())
        deadline = time.monotonic() + 5
        while svc.thread.is_alive() and time.monotonic() < deadline:
            # The helper's long-poll carries no browser mark, and the helper's routes never
            # count even if they did.
            try:
                svc.request("GET", "/api/helper/next?wait=0.1", browser=True)
            except OSError:
                break                            # the service closed while it was asked
        self.assertTrue(svc.exited(5))
        self.assertEqual(svc.code, 0)

    def test_health_without_the_browser_mark_does_not_keep_it_alive(self):
        svc = Service(self, idle_seconds=0.6)
        deadline = time.monotonic() + 5
        while svc.thread.is_alive() and time.monotonic() < deadline:
            try:
                svc.request("GET", "/api/health", browser=False)
            except OSError:
                break                            # the service closed while it was asked
            time.sleep(0.05)
        self.assertTrue(svc.exited(5))

    def test_a_running_benchtest_defers_the_idle_exit(self):
        gate = threading.Event()

        class Slow(FakeBench):
            def run(self, test_id, ctx):
                gate.wait(5)
                return super().run(test_id, ctx)

        svc = Service(self, idle_seconds=0.4, bench=Slow())
        svc.request("POST", "/api/run", {"tests": ["core"]})
        time.sleep(1.2)
        self.assertTrue(svc.thread.is_alive())
        gate.set()
        self.assertTrue(svc.exited(5))
        self.assertEqual(svc.code, 0)


class Launcher(unittest.TestCase):
    def test_the_launcher_starts_in_fake_mode_on_port_0_and_stops_on_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = os.path.join(tmp, "run")
            proc = subprocess.Popen(
                [sys.executable, str(DEVICE / "rootfs/usr/local/sbin/pedal-benchtest"), "--fake",
                 "--bind", "127.0.0.1", "--port", "0", "--state-dir", os.path.join(tmp, "state"),
                 "--run-dir", run_dir, "--idle-seconds", "30"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                url = proc.stdout.readline().strip()
                self.assertRegex(url, r"^http://127\.0\.0\.1:\d+/#token=")
                with open(os.path.join(run_dir, "url")) as f:
                    self.assertEqual(f.read().strip(), url)
                parts = urlsplit(url)
                token = parts.fragment.split("=", 1)[1]
                conn = http.client.HTTPConnection("127.0.0.1", parts.port, timeout=5)
                conn.request("POST", "/api/shutdown", headers={"Authorization": "Bearer " + token})
                self.assertEqual(conn.getresponse().status, 200)
                conn.close()
                self.assertEqual(proc.wait(20), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.stdout.close()
                proc.stderr.close()


class Port(unittest.TestCase):
    def test_the_default_port_is_none_the_core_host_already_listens_on(self):
        # pedald listens on its http_port for good; the unit's bind would fail with EADDRINUSE.
        from benchtest import main
        from pedald import config
        taken = {config.DEFAULT_HTTP_PORT: "pedald's default"}
        pedald = sorted(DEVICE.parent.glob("*/rootfs/etc/pedal/pedald.json"))
        engine = sorted(DEVICE.parent.glob("*/rootfs/etc/namchain/namchaind.json"))
        self.assertTrue(pedald and engine)
        for path in pedald:
            taken[json.loads(path.read_text())["http_port"]] = str(path)
        for path in engine:
            taken[json.loads(path.read_text())["tcp_port"]] = str(path)
        self.assertNotIn(main.PORT, taken, "pedal.benchtest's port is taken by %s" % taken.get(main.PORT))


if __name__ == "__main__":
    unittest.main()

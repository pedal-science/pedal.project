"""pedal.benchtest's page in Chromium, against the app started with --fake (the plan's "Checks
before this is done").

    uv run --no-project --with playwright python devices/common/tests/browser/test_benchtest_browser.py [-v]

`devices/common/test-pedald` runs it after the stdlib suites. It lives under `browser/`, which has
no `__init__.py`, so the stdlib discovery never imports Playwright and that suite stays on system
python3. Chromium is Playwright's own (`uv run --with playwright playwright install chromium`).

Each test starts `pedal-benchtest --fake` on a free port with its state in a temporary directory,
drives the page, and stops the process afterwards. Lamps are read twice: from the data attributes
the page sets, and from the lamp elements' computed colour against the page's own lamp colour
variables. A screenshot of each checked state is kept in BENCHTEST_SCREENSHOTS, by default the
checkout's gitignored scratch/benchtest-browser/<time>/, and a failing check saves one there too.
"""

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

DEVICE = pathlib.Path(__file__).resolve().parents[2]
REPO = DEVICE.parents[1]
APP = DEVICE / "rootfs/usr/local/sbin/pedal-benchtest"
sys.path.insert(0, str(DEVICE / "rootfs/usr/local/lib"))

from benchtest import catalog  # noqa: E402

SHOTS = pathlib.Path(os.environ.get("BENCHTEST_SCREENSHOTS")
                     or REPO / "scratch" / "benchtest-browser" / time.strftime("%Y%m%d-%H%M%S"))
TIMEOUT_MS = 10000

#: The check the codec walk fails on: a benchtest that lists the codec, failing on how it
#: exercises the codec rather than on its usual block.
FAILING_TEST = "audio"
FAILING_CHECK = "the engine streams 48 kHz from the codec's sound device"


class FakeApp:
    """`pedal-benchtest --fake` on 127.0.0.1, a free port, and a temporary state directory."""

    def __init__(self):
        self.dir = tempfile.TemporaryDirectory(prefix="benchtest-browser-")
        state, run = os.path.join(self.dir.name, "state"), os.path.join(self.dir.name, "run")
        self.log_path = os.path.join(self.dir.name, "app.log")
        self.log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, str(APP), "--fake", "--bind", "127.0.0.1", "--port", "0",
             "--state-dir", state, "--run-dir", run, "--idle-seconds", "300"],
            stdout=self.log, stderr=subprocess.STDOUT)
        url_file = os.path.join(run, "url")
        deadline = time.monotonic() + 15
        while not os.path.exists(url_file):
            if self.proc.poll() is not None or time.monotonic() > deadline:
                self.close()
                raise AssertionError("the fake app did not start:\n" + self.output())
            time.sleep(0.05)
        with open(url_file) as f:
            self.url = f.read().strip()
        parts = urlsplit(self.url)
        self.origin = "%s://%s" % (parts.scheme, parts.netloc)
        self.token = parts.fragment.split("=", 1)[1]

    def api(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.origin + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())

    def output(self):
        self.log.flush()
        with open(self.log_path) as f:
            return f.read()

    def wait_exit(self, timeout=20):
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            if self.wait_exit(10) is None:
                self.proc.kill()
                self.proc.wait()
        self.log.close()
        self.dir.cleanup()


def hex_to_rgb(value):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return "rgb(%d, %d, %d)" % tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


class BrowserTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()
        SHOTS.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.app = FakeApp()
        self.addCleanup(self.app.close)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 1000},
                                                color_scheme="light")
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(TIMEOUT_MS)
        self.visited = []
        self.page.on("framenavigated",
                     lambda frame: frame == self.page.main_frame and self.visited.append(frame.url))
        self.page.goto(self.app.url)
        self.page.wait_for_selector("#module-codec")
        self.page.wait_for_selector("#test-codec")
        self.colours = {name: hex_to_rgb(self.page.evaluate(
            "(n) => getComputedStyle(document.documentElement).getPropertyValue(n)", "--" + name))
            for name in ("lamp-pass", "lamp-fail", "lamp-pass-muted", "lamp-fail-muted")}
        self.assertEqual(len(set(self.colours.values())), 4, self.colours)

    # -- evidence -------------------------------------------------------------------------------

    def shot(self, name):
        path = SHOTS / ("%s-%s.png" % (self.id().rsplit(".", 1)[-1], name))
        self.page.screenshot(path=str(path))
        return path

    @contextlib.contextmanager
    def state(self, name):
        """A checked state: a screenshot when it holds, and one beside the failure when not."""
        try:
            yield
        except Exception as exc:
            path = SHOTS / ("FAILED-%s-%s.png" % (self.id().rsplit(".", 1)[-1], name))
            try:
                self.page.screenshot(path=str(path))
            except Exception as shot_error:            # the page may be gone; say so, keep the cause
                path = "no screenshot (%s)" % shot_error
            raise AssertionError("%s: %s\nscreenshot: %s\napp output:\n%s"
                                 % (name, exc, path, self.app.output())) from exc
        self.shot(name)

    # -- driving the page -----------------------------------------------------------------------

    def run_id(self):
        return self.page.evaluate("document.body.dataset.runId || ''")

    def wait_for_run_after(self, previous):
        """Wait until the page shows a finished run that is not `previous`; its id."""
        self.page.wait_for_function(
            "(prev) => { const b = document.body.dataset;"
            " return b.runId && b.runId !== prev && b.runStatus === 'done'; }", arg=previous)
        return self.run_id()

    def click_block(self, component):
        previous = self.run_id()
        self.page.click("#module-%s" % component)
        return self.wait_for_run_after(previous)

    def press_test(self, tests):
        # Some boxes are out of sight (collapsed under "Go further", or not offered yet), where a
        # click cannot reach them; the Test button reads `checked` either way.
        self.page.eval_on_selector_all(
            "input.test-pick", "(boxes, wanted) => boxes.forEach((b) => {"
            " b.checked = wanted.includes(b.dataset.test); })", list(tests))
        previous = self.run_id()
        self.page.click("#test-button")
        return self.wait_for_run_after(previous)

    def set_fake_fail_from_the_page(self, test_id):
        """The fake control the page shows in --fake mode: this benchtest's next run fails."""
        self.page.select_option('select[data-fake-test="%s"]' % test_id, "fail")
        self.page.click('button[data-fake-set="%s"]' % test_id)
        self.page.wait_for_function(
            "(t) => (document.querySelector('[data-fake-queue=\"' + t + '\"]') || {}).textContent"
            " === 'next: fail'", arg=test_id)

    # -- reading the lamps ----------------------------------------------------------------------

    def lamps(self, selector):
        """The element's lamp attributes, and each lamp as (role, state, tone, computed colour)."""
        return self.page.evaluate(
            """(sel) => {
                const node = document.querySelector(sel);
                const lamps = [...node.querySelectorAll('.lamp')].map((l) => {
                  const cs = getComputedStyle(l);
                  return {role: l.dataset.lampRole, state: l.dataset.state,
                          tone: l.classList.contains('lamp-muted') ? 'muted'
                              : l.classList.contains('lamp-bright') ? 'bright' : '?',
                          colour: l instanceof SVGElement ? cs.fill : cs.backgroundColor};
                });
                return {lamp: node.dataset.lamp, prev: node.dataset.prev,
                        transition: node.dataset.transition, lamps};
            }""", selector)

    def assert_lamps(self, selector, *expected):
        """`expected` is the lamps left to right, as "muted-fail", "bright-pass" and so on."""
        got = self.lamps(selector)
        want = []
        for item in expected:
            tone, state = item.split("-")
            role = "previous" if tone == "muted" else "current"
            colour = self.colours["lamp-%s%s" % (state, "-muted" if tone == "muted" else "")]
            want.append({"role": role, "state": state, "tone": tone, "colour": colour})
        self.assertEqual(got["lamps"], want, "%s lamps" % selector)
        current = expected[-1].split("-")[1]
        previous = expected[0].split("-")[1] if len(expected) == 2 else ""
        self.assertEqual(got["lamp"], current, "%s data-lamp" % selector)
        self.assertEqual(got["prev"], previous, "%s data-prev" % selector)
        self.assertEqual(got["transition"],
                         "%s-to-%s" % (previous, current) if previous else "none",
                         "%s data-transition" % selector)


class CodecBlock(BrowserTest):
    def test_the_codec_walk(self):
        block = "#module-codec"
        expected_run = catalog.tests_for_component("codec", {})
        self.assertEqual(expected_run, [t["id"] for t in catalog.TESTS
                                        if "codec" in t["components"] and t["auto"]])
        self.assertIn(FAILING_TEST, expected_run)

        with self.state("1-fail-then-pass-muted-red-bright-green"):
            self.assertEqual(self.lamps(block)["lamps"], [])
            self.assertEqual(self.lamps(block)["lamp"], "none")
            self.set_fake_fail_from_the_page("codec")
            self.press_test(["codec"])
            self.assert_lamps(block, "bright-fail")
            self.press_test(["codec"])
            self.assert_lamps(block, "muted-fail", "bright-pass")

        with self.state("2-click-runs-the-codecs-benchtests"):
            self.app.api("POST", "/api/fake/reset", {"ran": True, "queues": True})
            run = self.click_block("codec")
            self.assertEqual(self.page.get_attribute(block, "data-selected"), "true")
            self.assertEqual(self.page.get_attribute("#detail", "data-component"), "codec")
            ran = self.app.api("GET", "/api/fake")["ran"]
            self.assertEqual([r["test"] for r in ran], expected_run)
            self.assertEqual({r["run"] for r in ran}, {run})
            listed = self.page.eval_on_selector_all(
                '#detail-tests li[data-runs-on-click="true"]', "els => els.map(e => e.dataset.test)")
            self.assertEqual(listed, expected_run)
            for test_id in catalog.TEST_IDS:
                status = self.page.get_attribute("#test-%s" % test_id, "data-status")
                self.assertEqual(status, "pass" if test_id in expected_run else "", test_id)

        with self.state("3-pass-then-fail-muted-green-bright-red"):
            self.app.api("POST", "/api/fake/outcome", {"test": FAILING_TEST, "ok": False,
                                                       "component": "codec",
                                                       "check": FAILING_CHECK})
            self.click_block("codec")
            self.assertEqual(self.page.get_attribute("#test-%s" % FAILING_TEST, "data-status"),
                             "fail")
            failures = self.page.eval_on_selector_all(
                "#detail[data-component=codec] #detail-failures li.detail-failure",
                "els => els.map(e => [e.dataset.test, e.dataset.check, e.textContent])")
            self.assertEqual(len(failures), 1, failures)
            test_id, check, text = failures[0]
            self.assertEqual((test_id, check), (FAILING_TEST, FAILING_CHECK))
            self.assertIn(catalog.test(FAILING_TEST)["name"], text)
            self.assertIn(FAILING_CHECK, text)
            self.assert_lamps(block, "muted-pass", "bright-fail")
            self.assert_lamps("#test-%s" % FAILING_TEST, "muted-pass", "bright-fail")

        with self.state("4-fail-again-single-red"):
            self.app.api("POST", "/api/fake/outcome", {"test": FAILING_TEST, "ok": False,
                                                       "component": "codec",
                                                       "check": FAILING_CHECK})
            self.click_block("codec")
            self.assert_lamps(block, "bright-fail")
            self.assert_lamps("#test-%s" % FAILING_TEST, "bright-fail")

        with self.state("5-pass-again-muted-red-bright-green"):
            self.click_block("codec")
            self.assert_lamps(block, "muted-fail", "bright-pass")
            self.assertEqual(self.page.query_selector_all("#detail-failures li"), [])
            self.assertEqual(self.page.text_content("#detail .detail-pass"),
                             "Passed in the last run that exercised it.")

    def test_green_stays_green(self):
        block = "#module-pico"
        with self.state("green-stays-green"):
            self.click_block("pico")
            self.assert_lamps(block, "bright-pass")
            self.click_block("pico")
            self.assert_lamps(block, "bright-pass")
            self.assert_lamps("#test-link", "bright-pass")
            ran = self.app.api("GET", "/api/fake")["ran"]
            self.assertEqual([r["test"] for r in ran], ["link", "link"])


class Leaving(BrowserTest):
    def test_stop_goes_to_the_stopped_page_and_the_process_exits_zero(self):
        with self.state("stopped-page"):
            self.page.click("#stop-button")
            self.page.wait_for_function("document.body.dataset.stopped === 'true'")
            self.assertEqual(urlsplit(self.page.url).path, "/stopped")
            self.assertNotIn("token", self.page.url, "the stopped page drops the key from the address")
            self.assertIn("run scripts/benchtest", self.page.text_content("body"))
            self.assertEqual(self.app.wait_exit(), 0, self.app.output())

    def test_leaving_asks_and_leave_and_stop_stops_without_the_stopped_page(self):
        dialog = "#leave-dialog"
        with self.state("leave-dialog"):
            self.page.evaluate("history.back()")              # an in-app navigation: the back button
            self.page.wait_for_selector(dialog, state="visible")
            self.assertTrue(self.page.evaluate("document.getElementById('leave-dialog').open"))
        self.page.click("#leave-stay")
        self.page.wait_for_selector(dialog, state="hidden")
        self.assertIsNone(self.app.proc.poll(), "Stay must leave the service running")

        self.page.evaluate("history.back()")
        self.page.wait_for_selector(dialog, state="visible")
        self.page.click("#leave-stop")
        self.assertEqual(self.app.wait_exit(), 0, self.app.output())
        self.assertFalse([u for u in self.visited if urlsplit(u).path == "/stopped"], self.visited)
        self.assertNotEqual(urlsplit(self.page.url).path, "/stopped")


if __name__ == "__main__":
    unittest.main()

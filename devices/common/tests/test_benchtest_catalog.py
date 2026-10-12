"""Tests for pedal.benchtest's catalog and lamps: the one table, the pass bars, the lamp rule.

The catalog is data plus pure functions, so these call it directly: a pedal-diag report or a
codec-noise.py analysis goes in, a result in the page's shape comes out. The noise figures are
the 2026-10-11 bench session's (troubleshooting-log.md), so a bar that drifts from what was
measured fails here.

Run with:
    devices/common/test-pedald -v test_benchtest_catalog
"""

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOTFS = pathlib.Path(__file__).resolve().parents[1] / "rootfs"
sys.path.insert(0, str(ROOTFS / "usr/local/lib"))

from benchtest import catalog, lamps  # noqa: E402

INTERFACE = json.loads((ROOTFS / "etc/pedal/pedal-interface.json").read_text())


def analysis(rms, lines=(), seconds=18.0):
    return {"dc_offset": 0.0, "rms_dbfs": rms, "rms_dbfs_a": rms - 1.0, "peak_dbfs": rms + 10.0,
            "lines_low": [{"hz": hz, "dbfs": level} for hz, level in lines],
            "lines_high": [], "seconds": seconds, "sample_rate": 48000}


def report(*findings, sample=None):
    return {"format": 1, "tool": "pedal-diag", "findings": [
        {"severity": sev, "key": key, "what": what, "evidence": "evidence of " + key,
         "likely": ["a likely cause"], "check": "the diag's own check"}
        for sev, key, what in findings], "sample": sample or {}}


def painted(result):
    return {c["component"]: c["ok"] for c in result["checks"]}


class CatalogTable(unittest.TestCase):
    def test_every_test_names_real_blocks_and_says_how_it_exercises_each(self):
        for t in catalog.TESTS:
            with self.subTest(test=t["id"]):
                self.assertTrue(t["components"])
                for c in t["components"]:
                    self.assertIn(c, catalog.COMPONENT_IDS)
                self.assertEqual(set(t["exercises"]), set(t["components"]))
                if t["setup"]:
                    for fact, value in t["setup"].items():
                        self.assertIn((fact, value), catalog.SETUP_STEPS)

    def test_every_block_on_the_page_is_exercised_by_something(self):
        exercised = {c for t in catalog.TESTS for c in t["components"]}
        self.assertEqual(exercised, set(catalog.COMPONENT_IDS))

    def test_diag_rows_only_paint_blocks_their_test_exercises(self):
        for row in catalog.DIAG_ROWS:
            with self.subTest(key=row["key"], test=row["test"]):
                self.assertLessEqual(set(row["components"]), set(catalog.test(row["test"])["components"]))

    def test_every_signal_a_row_names_is_in_pedal_interface_json(self):
        for row in catalog.DIAG_ROWS:
            for ref in row.get("signals") or []:
                with self.subTest(ref=ref):
                    self.assertTrue(catalog.interface_checks(INTERFACE, [ref]))

    def test_order_is_the_catalogs_whatever_was_ticked(self):
        self.assertEqual(catalog.ordered(["noise_left", "codec", "core", "codec"]),
                         ["codec", "core", "noise_left"])

    def test_battery_is_offered_only_after_hum(self):
        battery = catalog.test("noise_battery")
        self.assertFalse(catalog.offered(battery, {}))
        self.assertTrue(catalog.offered(battery, {"hum": True}))
        self.assertNotIn("noise_battery", catalog.tests_for_component("mains", {}))
        self.assertIn("noise_battery", catalog.tests_for_component("mains", {"hum": True}))

    def test_a_click_never_chooses_codec_input_on_its_own(self):
        self.assertNotIn("noise_codec", catalog.tests_for_component("guitar_input", {"hum": True}))
        self.assertEqual(catalog.tests_for_component("codec", {}), ["codec", "audio"])


class SetupSteps(unittest.TestCase):
    def test_a_health_test_needs_no_cables(self):
        self.assertEqual(catalog.setup_steps({}, catalog.test("codec")["setup"]), [])

    def test_steps_are_said_only_when_the_setup_changes(self):
        needed = catalog.test("noise_left")["setup"]
        first = catalog.setup_steps({}, needed)
        self.assertEqual(len(first), 1)
        self.assertIn("left output", first[0])
        self.assertEqual(catalog.setup_steps(dict(needed), needed), [])
        right = catalog.setup_steps(dict(needed), catalog.test("noise_right")["setup"])
        self.assertEqual(len(right), 1)
        self.assertIn("right output", right[0])

    def test_board_and_mains_are_assumed_until_said_otherwise(self):
        steps = catalog.setup_steps({"lead": "guitar_input"}, catalog.test("noise_input")["setup"])
        self.assertEqual(steps, [])
        steps = catalog.setup_steps({"lead": "guitar_input"}, catalog.test("noise_battery")["setup"])
        self.assertEqual(steps, [catalog.SETUP_STEPS[("core_power", "battery")]])


class OutputNoise(unittest.TestCase):
    def test_the_benchs_baseline_passes(self):
        result = catalog.classify_output("noise_left", analysis(-99.4, ((750.0, -115.0),)))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(painted(result), {"output_left": True, "interface": True})

    def test_noise_above_the_bar_fails_that_output_only(self):
        result = catalog.classify_output("noise_right", analysis(-84.0))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(painted(result), {"output_right": False, "interface": True})
        self.assertIn("-84.0 dBFS", result["summary"])
        self.assertIn("right output", result["next"])

    def test_a_mains_comb_fails_a_quiet_output(self):
        result = catalog.classify_output("noise_left", analysis(-95.0, ((50.1, -104.0),)))
        self.assertEqual(result["status"], "fail")
        self.assertIn("50 Hz", result["summary"])

    def test_a_missing_analysis_is_not_a_pass(self):
        self.assertEqual(catalog.classify_output("noise_left", {})["status"], "fail")


class InputNoise(unittest.TestCase):
    # 2026-10-11: on the mains adapter the floor was near -50 with 50 Hz at about -55; on
    # batteries the same input read -65.5 with 50 Hz at -84; a shorted codec input read -74.

    def test_the_known_mains_hum_paints_mains_not_the_guitar_input(self):
        result = catalog.classify_input(analysis(-52.8, ((49.8, -58.3), (100.3, -59.8))))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(painted(result), {"mains": False, "guitar_input": True})
        self.assertTrue(result["facts"]["hum"])
        self.assertEqual(result["facts"]["line50_dbfs"], -58.3)
        self.assertIn("battery", result["summary"])

    def test_hum_louder_than_the_mains_case_paints_both(self):
        result = catalog.classify_input(analysis(-40.0, ((50.0, -44.0),)))
        self.assertEqual(painted(result), {"mains": False, "guitar_input": False})

    def test_quiet_input_passes(self):
        result = catalog.classify_input(analysis(-68.4, ((750.0, -80.0),)))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(painted(result), {"mains": True, "guitar_input": True})
        self.assertFalse(result["facts"]["hum"])

    def test_hiss_without_hum_fails_the_guitar_input(self):
        result = catalog.classify_input(analysis(-55.0, ((750.0, -70.0),)))
        self.assertEqual(painted(result), {"mains": True, "guitar_input": False})
        self.assertIn("Codec input on its own", result["next"])

    def test_digital_silence_is_a_dead_input(self):
        result = catalog.classify_input(analysis(float("-inf")))
        self.assertEqual(painted(result), {"guitar_input": False})
        self.assertIn("header pin 38", result["next"])


class Battery(unittest.TestCase):
    def test_hum_that_falls_by_the_bar_passes(self):
        result = catalog.classify_battery(analysis(-65.5, ((50.0, -84.0),)), -58.3)
        self.assertEqual(result["status"], "pass")
        self.assertAlmostEqual(result["facts"]["drop_db"], 25.7)

    def test_hum_that_stays_fails_mains(self):
        result = catalog.classify_battery(analysis(-55.0, ((50.0, -62.0),)), -58.3)
        self.assertEqual(painted(result), {"mains": False})

    def test_a_line_gone_from_the_list_counts_as_below_the_quietest_listed(self):
        result = catalog.classify_battery(analysis(-65.5, ((750.0, -90.0),)), -58.3)
        self.assertEqual(result["status"], "pass")
        self.assertIn("not among the loudest", result["evidence"])

    def test_no_reference_is_not_run(self):
        self.assertEqual(catalog.classify_battery(analysis(-65.0), None)["status"], "not_run")


class CodecOnly(unittest.TestCase):
    def test_the_codec_floor_passes_and_clears_the_input(self):
        result = catalog.classify_codec_only(analysis(-74.0), -71.0)
        self.assertEqual(painted(result), {"guitar_input": True, "codec": True})

    def test_a_big_drop_blames_the_guitar_input(self):
        result = catalog.classify_codec_only(analysis(-74.0), -60.0)
        self.assertEqual(painted(result), {"guitar_input": False, "codec": True})

    def test_a_noisy_codec_fails_the_codec(self):
        result = catalog.classify_codec_only(analysis(-62.0), -62.0)
        self.assertEqual(painted(result)["codec"], False)
        self.assertIn("VIN", result["next"])


class Diag(unittest.TestCase):
    def test_codec_absent_fails_both_codec_blocks_with_the_header_pins(self):
        result = catalog.evaluate_diag("codec", report(
            ("fail", "codec.i2c_absent", "nothing answers at 0x1a on i2c-1")), INTERFACE)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(painted(result), {"codec": False, "codec_wires": False})
        self.assertFalse(result["facts"]["codec_present"])
        self.assertIn("header pin 1", result["next"])
        self.assertIn("header pin 3", result["next"])
        self.assertIn("Nothing answers at 0x1a", result["summary"])

    def test_a_healthy_codec_passes(self):
        result = catalog.evaluate_diag("codec", report(
            ("ok", "codec.answers", "the codec answers at 0x1a"),
            ("ok", "audio.streaming", "capture and playback are running")), INTERFACE)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(painted(result), {"codec": True, "codec_wires": True})
        self.assertTrue(result["facts"]["codec_present"])

    def test_a_link_without_a_session_fails_the_wires_and_says_pin_8(self):
        result = catalog.evaluate_diag("link", report(
            ("fail", "link.no_session", "HELLO arrives but the session never comes up")), INTERFACE)
        self.assertEqual(painted(result), {"uart_wires": False})
        self.assertIn("pin 8", result["next"])

    def test_undervoltage_paints_mains_and_its_absence_passes_it(self):
        bad = catalog.evaluate_diag("core", report(
            ("ok", "host.thermal", "cool"), ("fail", "host.undervoltage", "the supply sagged")),
            INTERFACE)
        self.assertEqual(painted(bad), {"core": True, "mains": False})
        good = catalog.evaluate_diag("core", report(("ok", "host.thermal", "cool")), INTERFACE)
        self.assertEqual(painted(good), {"core": True, "mains": True})

    def test_xruns_in_the_engine_sample_fail_the_audio_test(self):
        sample = {"engine": {"status": {"xruns": 12, "issues": [
            {"code": "render.xrun", "message": "12 xruns"}]}}}
        result = catalog.evaluate_diag("audio", report(
            ("ok", "audio.streaming", "streaming"), sample=sample), INTERFACE)
        self.assertEqual(painted(result), {"core": False, "codec": True})

    def test_a_warning_fails_only_where_the_row_says_so(self):
        result = catalog.evaluate_diag("audio", report(
            ("ok", "audio.streaming", "streaming"),
            ("warn", "audio.hw_params", "the period is 128 frames")), INTERFACE)
        self.assertEqual(painted(result)["core"], False)

    def test_a_report_that_says_nothing_is_not_run(self):
        self.assertEqual(catalog.evaluate_diag("link", report(), INTERFACE)["status"], "not_run")


def load_pedal_diag():
    path = str(ROOTFS / "usr/local/sbin/pedal-diag")
    loader = importlib.machinery.SourceFileLoader("pedal_diag_for_benchtest", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class DiagFromPedalDiag(unittest.TestCase):
    """The real tool's `--json` output for the real healthy sample, and for faults made from it
    the way test_diag.py makes them."""

    @classmethod
    def setUpClass(cls):
        cls.pd = load_pedal_diag()
        with open(pathlib.Path(__file__).resolve().parent / "fixtures/diag/healthy-vip.json") as f:
            cls.healthy = json.load(f)

    def judge(self, sample):
        iface, path = self.pd.load_interface()
        report = json.loads(self.pd.render_json(self.pd.build_report(sample, iface, path), sample))
        return {t: catalog.evaluate_diag(t, report, INTERFACE) for t in ("codec", "audio", "link", "core")}

    def sample(self):
        return json.loads(json.dumps(self.healthy))

    def test_the_healthy_pedal_passes_every_health_benchtest(self):
        for test_id, result in self.judge(self.sample()).items():
            with self.subTest(test=test_id):
                self.assertEqual(result["status"], "pass", result["summary"])

    def test_an_absent_codec_fails_the_codec_and_names_its_pins(self):
        s = self.sample()
        s["i2c"]["devices"] = ["i2c-1"]
        s["codec"] = {"regmap_present": False, "name": None, "range": None, "registers": None,
                      "registers_readable": False}
        s["alsa"]["cards"] = ""
        codec = self.judge(s)["codec"]
        self.assertEqual(codec["status"], "fail")
        self.assertFalse(codec["facts"]["codec_present"])
        self.assertFalse(painted(codec)["codec_wires"])
        self.assertIn("header pin 1", codec["next"])

    def test_frames_with_no_session_fail_the_link_wires(self):
        s = self.sample()
        s["service"]["link"]["session"] = False
        s["service"]["link"]["frames_ok"] = 500
        link = self.judge(s)["link"]
        self.assertEqual(painted(link)["uart_wires"], False)
        self.assertIn("pin 8", link["next"])

    def test_undervoltage_fails_mains(self):
        s = self.sample()
        s["hwmon"]["rpi_volt"]["in0_lcrit_alarm"] = "1"
        core = self.judge(s)["core"]
        self.assertEqual(painted(core)["mains"], False)


class LampRule(unittest.TestCase):
    def test_the_rule(self):
        self.assertEqual(lamps.lamp([]), {"current": None, "previous": None})
        self.assertEqual(lamps.lamp([True]), {"current": "pass", "previous": None})
        self.assertEqual(lamps.lamp([False]), {"current": "fail", "previous": None})
        self.assertEqual(lamps.lamp([False, True]), {"current": "pass", "previous": "fail"})
        self.assertEqual(lamps.lamp([True, False]), {"current": "fail", "previous": "pass"})
        self.assertEqual(lamps.lamp([True, False, False]), {"current": "fail", "previous": None})
        self.assertEqual(lamps.lamp([False, True, True]), {"current": "pass", "previous": None})


class HistoryFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "history.json")
        self.addCleanup(self.dir.cleanup)

    def run_once(self, history, run_id, *results):
        history.begin_run(run_id, {"kind": "tests"})
        for r in results:
            history.record(run_id, r)
        history.end_run(run_id)

    def codec(self, ok, component="codec_wires"):
        checks = [catalog.check("codec", True, "c", "fine"),
                  catalog.check(component, ok, "SDA on header pin 3", "said")]
        return catalog.make_result("codec", checks, "s")

    def test_lamps_follow_runs_that_exercised_the_block(self):
        h = lamps.History(self.path)
        self.run_once(h, "r1", self.codec(False))
        self.run_once(h, "r2", catalog.make_result("link", [catalog.check("uart_wires", True, "c", "s")], "s"))
        self.run_once(h, "r3", self.codec(True))
        state = h.lamps(catalog.COMPONENT_IDS, catalog.TEST_IDS)
        self.assertEqual(state["components"]["codec_wires"], {"current": "pass", "previous": "fail"})
        self.assertEqual(state["components"]["codec"], {"current": "pass", "previous": None})
        self.assertEqual(state["components"]["pico"], {"current": None, "previous": None})
        self.assertEqual(state["tests"]["codec"], {"current": "pass", "previous": "fail"})

    def test_failures_name_the_benchtest_and_the_check(self):
        h = lamps.History(self.path)
        self.run_once(h, "r1", self.codec(False))
        self.assertEqual(h.failures(["codec_wires"])["codec_wires"][0]["test"], "codec")
        self.assertEqual(h.failures(["codec_wires"])["codec_wires"][0]["check"], "SDA on header pin 3")
        self.assertEqual(h.failures(["codec"])["codec"], [])

    def test_not_run_leaves_no_trace(self):
        h = lamps.History(self.path)
        self.run_once(h, "r1", catalog.not_run("noise_left", "no helper"))
        self.assertEqual(h.data["runs"], [])
        self.assertEqual(h.last_results(), {})

    def test_it_persists_and_forgets(self):
        h = lamps.History(self.path)
        self.run_once(h, "r1", self.codec(False))
        self.run_once(h, "r2", self.codec(True))
        again = lamps.History(self.path)
        self.assertEqual(again.lamps(["codec_wires"], [])["components"]["codec_wires"]["previous"], "fail")
        again.forget()
        self.assertEqual(lamps.History(self.path).lamps(["codec_wires"], [])["components"]["codec_wires"],
                         {"current": None, "previous": None})

    def test_a_broken_file_is_kept_aside_and_started_again(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        h = lamps.History(self.path, clock=lambda: 1234)
        self.assertEqual(h.data["runs"], [])
        self.assertTrue(os.path.exists(self.path + ".broken-1234"))

    def test_bench_facts_come_from_the_guitar_input_test(self):
        h = lamps.History(self.path)
        hum = catalog.classify_input(analysis(-52.8, ((49.8, -58.3),)))
        self.run_once(h, "r1", hum)
        self.assertEqual(h.bench_facts(), {"hum": True, "input_rms_dbfs": -52.8, "input_line50_dbfs": -58.3})


if __name__ == "__main__":
    unittest.main()

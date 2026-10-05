"""pedal-diag: the tool's pure half, from fixtures rather than from a board.

`pedal-diag` is one file with two halves: a gatherer that reads the host (tested on the host,
where the files are) and a report that turns a sample into findings (tested here, where the
fixtures are). This is the second half, and it is where the interesting logic lives — "which
wire", "why did the device not open" — so it is worth testing without a pedal attached.

`fixtures/diag/healthy-vip.json` is a real sample taken from vip on 2026-10-05, and the fault
cases are mutations of it: unplug a lead, stop a service, overheat the board, and the report must
name the thing that was unplugged. That is the acceptance criterion in miniature: a fixture per
fault, and a finding per fixture.

Why the import whitelist: the tool must run on the Core host, whose python3 is
`python3-minimal`. `test-pedald` already holds pedald to that standard by listing what vip lacks;
this holds pedal-diag to it the same way, and it is the assertion that keeps the tool deployable
rather than merely present in the repo.
"""
import importlib.machinery
import importlib.util
import json
import pathlib
import sys
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TOOL_PATH = HERE.parent / "rootfs/usr/local/sbin/pedal-diag"
FIXTURES = HERE / "fixtures/diag"

# What `python3-minimal` on vip has. Anything outside this list is a package the image does not
# install, and the import would fail on the host rather than here (which is the point of the test).
ALLOWED_IMPORTS = {
    "argparse", "errno", "glob", "io", "json", "math", "os", "re", "select", "socket",
    "struct", "subprocess", "sys", "termios", "time", "types", "unittest",
    # Inside functions: the gatherer's own ioctl attempt, deliberately absent today.
    "array", "fcntl",
}
# The gatherer runs on the host under this tool's own ssh path; `secure` and `amixer` are called
# as subprocesses instead, precisely because the modules are not there.
ALLOWED_GATHERER_IMPORTS = {"errno", "glob", "json", "os", "re", "subprocess", "sys", "time",
                            "array", "fcntl", "termios", "socket", "struct"}


def load_tool():
    """The tool as a module, by path: it is `/usr/local/sbin/pedal-diag`, with no `.py`, because
    that is what the host installs."""
    loader = importlib.machinery.SourceFileLoader("pedal_diag", str(TOOL_PATH))
    spec = importlib.util.spec_from_loader("pedal_diag", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


pd = load_tool()


def sample(name="healthy-vip.json"):
    with open(FIXTURES / name) as f:
        return json.load(f)


def report_for(sample_dict):
    interface, path = pd.load_interface()
    return pd.build_report(sample_dict, interface, path)


def finding(findings, key):
    for f in findings:
        if f["key"] == key:
            return f
    return None


class TheHealthyPedal(unittest.TestCase):
    """A fixture of the real thing: the report must say nothing is wrong."""

    def setUp(self):
        self.findings = report_for(sample()).findings
        self.severity = {f["key"]: f["severity"] for f in self.findings}

    def test_nothing_fails_on_a_working_pedal(self):
        fails = [f for f in self.findings if f["severity"] == "fail"]
        self.assertEqual([f["key"] for f in fails], [], "a healthy fixture produced a fail")

    def test_the_codec_the_link_and_the_stream_are_reported_healthy(self):
        for key in ("codec.answers", "audio.streaming", "link.session", "host.tuning",
                    "host.rt", "wire.pico_usb"):
            self.assertEqual(self.severity.get(key), "ok", "%s: %s" % (key, self.severity.get(key)))

    def test_the_missing_debug_probe_is_information_not_a_fault(self):
        self.assertEqual(self.severity.get("wire.probe_absent"), "info")
        self.assertEqual(self.severity.get("wire.probe"), None)

    def test_the_unbuilt_levels_are_reported_rather_than_faked(self):
        """The engine has no levels yet, and the tool must say so instead of printing zeros:
        a report of -200 dBFS everywhere would look exactly like a broken input."""
        self.assertEqual(self.severity.get("levels.unavailable"), "info")
        self.assertIsNone(sample()["engine"].get("levels"))


class UnpluggedLeads(unittest.TestCase):
    """Each historical fault, as the report sees it: the finding must name the wire.

    The mutations are the ones that were measured on the bench (bench-results/2026-10-04-*.md,
    2026-10-05-*.md), so each test is a claim about a real fault rather than an invented one.
    """

    def test_the_codec_absent_from_the_bus_names_the_power_and_the_bus_leads(self):
        s = sample()
        s["i2c"]["devices"] = ["i2c-1"]
        s["codec"] = {"regmap_present": False, "name": None, "range": None, "registers": None,
                      "registers_readable": False}
        s["alsa"]["cards"] = ""
        f = finding(report_for(s).findings, "codec.i2c_absent")
        self.assertIsNotNone(f, "an absent codec produced no finding")
        self.assertEqual(f["severity"], "fail")
        joined = " ".join(f["likely"])
        self.assertIn("pin 1", joined)
        self.assertIn("SDA or SCL", joined)
        self.assertEqual(f["seed"], "i2c-nack-vs-timeout")

    def test_a_card_that_never_appears_names_the_clocks(self):
        s = sample()
        s["alsa"]["cards"] = ""
        f = finding(report_for(s).findings, "codec.no_card")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")
        self.assertIn("CLK", " ".join(f["likely"]))

    def test_no_frames_ever_names_the_pico_tx_lead(self):
        s = sample()
        s["service"]["link"]["frames_ok"] = 0
        s["service"]["link"]["session"] = False
        f = finding(report_for(s).findings, "link.silent")
        self.assertIsNotNone(f)
        self.assertIn("pin 10", f["check"])

    def test_frames_arriving_with_no_session_names_the_pico_rx_lead(self):
        s = sample()
        s["service"]["link"]["session"] = False
        s["service"]["link"]["frames_ok"] = 500
        f = finding(report_for(s).findings, "link.no_session")
        self.assertIsNotNone(f)
        self.assertIn("pin 8", " ".join(f["likely"]))

    def test_a_link_that_is_up_and_silent_is_a_failure_not_an_absence(self):
        s = sample()
        s["service"]["link"]["last_rx_s_ago"] = 42.0
        f = finding(report_for(s).findings, "link.silent_now")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")

    def test_a_link_that_keeps_dropping_points_at_the_picos_power(self):
        s = sample()
        s["service"]["link"]["drops"] = 3
        f = finding(report_for(s).findings, "link.drops")
        self.assertIsNotNone(f)
        self.assertIn("uptime", f["check"])

    def test_a_dead_engine_reports_its_own_issues(self):
        s = sample()
        s["engine"]["status"]["state"] = "lost"
        s["engine"]["status"]["issues"] = [
            {"code": "device_lost", "severity": "error", "message": "card wm8960 did not appear"}]
        f = finding(report_for(s).findings, "audio.engine_down")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")
        self.assertTrue(any("wm8960" in l for l in f["likely"]), f["likely"])


class Levels(unittest.TestCase):
    """The levels section, once the engine publishes them.

    The fixture predates `engine.levels` (namchain a69d315), so the mutations here add the object a
    live engine returns rather than replacing fields in one. The values are from the pedal with a
    guitar plugged in and nothing played: about -60 dBFS on the input, which is signal, and -200 on
    the output's second channel, which is a channel nothing is routed to.
    """

    def levels(self, **overrides):
        base = {
            "state": "running", "blocks": 2039, "sample_rate": 48000, "period_size": 64,
            "truncated": False,
            "input": {"peak": [-61.5, -75.3], "rms": [-72.0, -84.0], "clipped": [0, 0]},
            "output": {"peak": [-49.5, -200.0], "rms": [-60.0, -200.0], "clipped": [0, 0]},
            "chains": [{"id": "main", "name": "Guitar", "output_channel": 0, "muted": False,
                        "out": {"peak": -49.5, "rms": -60.0, "frames": 4224, "clipped": 0},
                        "nodes": [
                            {"node": "in", "element": "E1", "role": "", "peak": -61.5,
                             "rms": -72.0, "frames": 4224},
                            {"node": "g", "element": "E2", "role": "level", "peak": -55.0,
                             "rms": -68.0, "frames": 4224},
                        ]}],
        }
        base.update(overrides)
        return base

    def report(self, levels):
        s = sample()
        s["engine"]["features"] = (s["engine"].get("features") or []) + ["levels"]
        s["engine"]["levels"] = levels
        return report_for(s).findings

    def test_a_quiet_input_is_measured_not_called_silent(self):
        """The trap this finding exists for: -60 dBFS is signal. Reporting it as silence would be
        the tool inventing a fault out of a quiet guitar."""
        findings = self.report(self.levels())
        self.assertIsNone(finding(findings, "levels.silent_input"))
        present = finding(findings, "levels.present")
        self.assertIsNotNone(present)
        self.assertEqual(present["severity"], "ok")
        self.assertIn("-61.5", present["what"])

    def test_a_hot_channel_names_the_gain_stages(self):
        levels = self.levels()
        levels["input"]["peak"] = [-0.4, -0.4]
        f = finding(self.report(levels), "levels.hot")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")
        self.assertIn("Inst/Line", f["check"])

    def test_an_input_at_the_floor_names_the_historical_wire(self):
        levels = self.levels()
        levels["input"]["peak"] = [-200.0, -200.0]
        f = finding(self.report(levels), "levels.silent_input")
        self.assertIsNotNone(f)
        self.assertIn("pin 38", f["check"])

    def test_the_engine_without_levels_says_so_rather_than_printing_zeros(self):
        findings = self.report(None) if False else report_for(sample()).findings
        f = finding(findings, "levels.unavailable")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "info")
        self.assertIsNone(finding(findings, "levels.present"))

    def test_a_window_with_no_frames_is_not_a_level(self):
        """``frames: 0`` means the window measured nothing -- the read landed between two blocks.
        The engine's answer is still valid, and the tool must not turn it into a level."""
        self.assertFalse(pd.levels_have_frames({"input": {"rms": [-200.0]}}))
        self.assertFalse(pd.levels_have_frames({"chains": [{"nodes": [{"frames": 0}]}]}))
        self.assertTrue(pd.levels_have_frames({"input": {"rms": [-61.0]}}))
        self.assertTrue(pd.levels_have_frames({"chains": [{"out": {"frames": 64}}]}))
        self.assertTrue(pd.levels_have_frames({"chains": [{"nodes": [{"frames": 64}]}]}))
        self.assertFalse(pd.levels_have_frames(None))


class HeatAndPressure(unittest.TestCase):
    def test_a_normal_pi5_temperature_is_not_a_finding(self):
        s = sample()
        s["thermal"]["thermal_zone0"]["temp_mc"] = 56000
        self.assertEqual(finding(report_for(s).findings, "host.thermal")["severity"], "ok")

    def test_heat_near_the_first_cooling_step_is_a_warning(self):
        s = sample()
        s["thermal"]["thermal_zone0"]["temp_mc"] = 66000
        self.assertEqual(finding(report_for(s).findings, "host.thermal")["severity"], "warn")

    def test_heat_at_the_clock_pull_back_is_a_failure(self):
        s = sample()
        s["thermal"]["thermal_zone0"]["temp_mc"] = 76000
        self.assertEqual(finding(report_for(s).findings, "host.thermal")["severity"], "fail")

    def test_an_undervoltage_alarm_is_a_failure(self):
        s = sample()
        s["hwmon"]["rpi_volt"]["in0_lcrit_alarm"] = "1"
        self.assertEqual(finding(report_for(s).findings, "host.undervoltage")["severity"], "fail")

    def test_a_render_thread_off_its_isolated_core_is_a_warning(self):
        s = sample()
        for t in s["processes"]["namchaind"]["threads"]:
            if t["policy"] != 0:
                t["affinity"] = "0-1"
        f = finding(report_for(s).findings, "host.rt_affinity")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")

    def test_an_audio_irq_on_the_wrong_core_is_a_warning(self):
        s = sample()
        s["audio_irq"]["affinity_mask"] = "1"      # cpu 0, and the design says cpu 2
        f = finding(report_for(s).findings, "host.irq_affinity")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")
        self.assertEqual(f["severity"], "warn")

    def test_the_irq_mask_is_hex_not_binary(self):
        """`4` means cpu 2. Reading it as a binary string is the trap this covers."""
        self.assertEqual(pd.expand_hex_mask("4"), {2})
        self.assertEqual(pd.expand_hex_mask("c"), {2, 3})
        self.assertEqual(pd.expand_hex_mask("00000001,00000000"), {32})


class TheInterfaceModelIsEnoughToNameWires(unittest.TestCase):
    def test_every_codec_signal_names_a_physical_place_and_a_fault(self):
        interface, _ = pd.load_interface()
        signals = interface["codec"]["signals"]
        self.assertGreaterEqual(len(signals), 8)
        for signal in signals:
            self.assertTrue(signal.get("signal"), signal)
            self.assertTrue(signal.get("fault_symptom"), signal)
            self.assertTrue(signal.get("check"), signal)

    def test_the_id_in_the_model_is_the_wm8960s(self):
        interface, _ = pd.load_interface()
        self.assertEqual(interface["codec"]["id_value_hex"], "0x8960")
        self.assertEqual(interface["codec"]["id_value"], 0x8960)
        self.assertEqual(interface["codec"]["i2c_address_hex"], "0x1a")

    def test_a_missing_model_says_so_rather_than_guessing(self):
        report = pd.build_report(sample(), None, None)
        f = finding(report.findings, "interface.missing")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")


class TheInvariants(unittest.TestCase):
    """The things that keep this tool from becoming part of the problem."""

    def test_only_the_modules_python3_minimal_has(self):
        source = TOOL_PATH.read_text()
        imported = set()
        for line in source.splitlines():
            line = line.strip()
            if line.startswith("import "):
                line = line.split("#")[0]
                for name in line[len("import "):].split(","):
                    imported.add(name.strip().split(" as ")[0].split(".")[0])
            elif line.startswith("from ") and " import " in line:
                imported.add(line.split()[1].split(".")[0])
        unknown = imported - ALLOWED_IMPORTS
        self.assertEqual(unknown, set(), "%s import(s) the Core host may not have" % sorted(unknown))

    def test_the_gatherer_is_even_lighter_than_the_tool(self):
        """The half that runs on the host, checked separately: it is the half that must survive
        python3-minimal, and it is embedded text, so a careless import would not be caught by
        running the tool on the Mac."""
        imported = set()
        for line in pd.GATHER_SOURCE.splitlines():
            line = line.strip()
            if line.startswith("import "):
                line = line.split("#")[0]
                for name in line[len("import "):].split(","):
                    imported.add(name.strip().split(" as ")[0].split(".")[0])
        unknown = imported - ALLOWED_GATHERER_IMPORTS
        self.assertEqual(unknown, set(), "%s in the gatherer" % sorted(unknown))

    def test_the_gatherer_never_opens_a_sound_device_or_writes_to_the_bus(self):
        """Read-only is the tool's whole licence to run while the pedal is playing.

        Listing /dev/snd is fine (it says whether the PCM nodes exist); OPENING one is not, and
        the difference is the whole point of the test.
        """
        source = pd.GATHER_SOURCE
        self.assertNotIn("os.open(\"/dev/snd", source)
        self.assertNotIn("os.open('/dev/snd", source)
        self.assertNotIn("arecord", source)
        self.assertNotIn("i2cset", source)
        self.assertNotIn("O_CREAT", source)
        self.assertNotIn("subprocess.Popen", source)
        # And the only writes are the ones the kernel's own interfaces need.
        for line in source.splitlines():
            if "os.write(" in line or ".write(" in line:
                self.assertIn("stderr", line, line)
                self.assertIn("stdout", line, line)

    def test_the_wire_frame_is_the_length_prefix_the_engine_uses(self):
        body = b'{"ok":true}'
        frame = pd.struct.pack("<I", len(body)) + body
        self.assertEqual(pd.struct.unpack("<I", frame[:4])[0], len(body))

    def test_every_finding_carries_a_way_to_close_it(self):
        s = sample()
        s["service"]["link"]["drops"] = 2
        s["hwmon"]["rpi_volt"]["in0_lcrit_alarm"] = "1"
        for f in report_for(s).findings:
            self.assertTrue(f.get("what"), f)
            self.assertTrue(f.get("evidence") is not None, f)
            if f["severity"] in ("fail", "warn"):
                self.assertTrue(f.get("check"), "no check for %s" % f["key"])
                self.assertTrue(f.get("likely"), "no cause for %s" % f["key"])


class TheRendering(unittest.TestCase):
    def test_the_text_report_says_the_verdict_and_the_interface_it_used(self):
        interface, path = pd.load_interface()
        s = sample()
        report = pd.build_report(s, interface, path)
        text = pd.render_text(report, s)
        self.assertIn("verdict", text)
        self.assertIn("interface model: %s" % path, text)
        self.assertIn("things software cannot see", text)

    def test_json_round_trips_and_keeps_the_findings(self):
        interface, path = pd.load_interface()
        s = sample()
        report = pd.build_report(s, interface, path)
        out = json.loads(pd.render_json(report, s))
        self.assertEqual(out["tool"], "pedal-diag")
        self.assertEqual(out["format"], pd.FORMAT)
        self.assertEqual(len(out["findings"]), len(report.findings))

    def test_the_worst_severity_drives_the_exit_code(self):
        self.assertEqual(pd.worst([{"severity": "ok"}, {"severity": "info"}]), "ok")
        self.assertEqual(pd.worst([{"severity": "ok"}, {"severity": "warn"}]), "warn")
        self.assertEqual(pd.worst([{"severity": "warn"}, {"severity": "fail"}]), "fail")

    def test_the_parsers_read_the_real_files_they_were_written_for(self):
        """The exact text of the pedal's own procfs files, so the parsers are tested against the
        thing rather than against a paraphrase."""
        status = textwrap.dedent("""\
            state: RUNNING
            owner_pid   : 2128
            delay       : 24
            avail       : 24
            -----
            hw_ptr      : 81551000
            appl_ptr    : 81550976
            """)
        parsed = pd.parse_pcm_status(status)
        self.assertEqual(parsed["state"], "RUNNING")
        self.assertEqual(parsed["owner_pid"], "2128")
        self.assertEqual(parsed["hw_ptr"], 81551000)

        hw = pd.parse_hw_params("access: RW_INTERLEAVED\nformat: S32_LE\nchannels: 2\n"
                                "rate: 48000 (48000/1)\nperiod_size: 64\nbuffer_size: 384\n")
        self.assertEqual(hw, {"rate": 48000, "period_size": 64, "buffer_size": 384, "channels": 2})

        registers = pd.parse_registers("00: 0117\n04: 0005\n04: 0005\n")
        self.assertEqual(registers[0x00], 0x0117)
        self.assertEqual(registers[0x04], 0x0005)

    def test_the_register_decoder_names_the_registers_that_matter(self):
        decoded = pd.decode_codec_registers({0x00: 0x0117, 0x04: 0x0005, 0x06: 0x0000})
        self.assertTrue(any("clocking" in k for k in decoded), decoded)
        self.assertTrue(any("audio interface" in k for k in decoded), decoded)


class TheWatchLog(unittest.TestCase):
    def test_two_samples_describe_a_rate(self):
        import copy
        first = sample()
        second = copy.deepcopy(first)
        second["at"] = first["at"] + 2.0
        second["service"]["link"]["frames_ok"] = first["service"]["link"]["frames_ok"] + 48
        second["service"]["link"]["frames_bad"] = first["service"]["link"]["frames_bad"] + 2
        second["engine"]["status"]["xruns"] = first["engine"]["status"]["xruns"] + 1
        d = pd.delta(first, second)
        self.assertAlmostEqual(d["elapsed_s"], 2.0, places=3)
        self.assertEqual(d["service.link.frames_ok"], 48)
        self.assertAlmostEqual(d["service.link.frames_ok_per_s"], 24.0, places=2)
        self.assertEqual(d["service.link.frames_bad"], 2)
        self.assertEqual(d["engine.xruns"], 1)

    def test_a_sample_line_stays_small_and_carries_the_numbers_a_person_wants(self):
        import argparse
        args = argparse.Namespace()
        s = sample()
        s["deep_skipped"] = {"every": 10, "sample": 3, "why": "test"}
        report = pd.build_report(s, *pd.load_interface())
        line, evidence = pd.watch_line(args, s, None, report)
        self.assertIsNone(evidence, "a non-deep sample must not carry the whole sample")
        self.assertEqual(line["kind"], "sample")
        self.assertFalse(line["deep"])
        self.assertIn("render_worst_percent", line["readings"])
        self.assertIn("frames_ok", line["readings"])
        self.assertLess(len(json.dumps(line)), 8000)

    def test_percent_available_is_a_percentage(self):
        s = sample()
        value = pd.percent_available(s)
        self.assertIsNotNone(value)
        self.assertGreater(value, 0)
        self.assertLessEqual(value, 100)


if __name__ == "__main__":
    unittest.main()

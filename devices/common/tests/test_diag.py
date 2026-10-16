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
import ast
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
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
        """A fixture cannot see the operator's machine, so "no probe anywhere" is the honest
        answer for it — and it is an info, never a fault."""
        probe = finding(self.findings, "probe.none")
        self.assertIsNotNone(probe)
        self.assertEqual(probe["severity"], "info")
        self.assertEqual(probe["what"], "No debug probes connected via USB to any device")
        self.assertEqual(self.severity.get("probe.on_core"), None)
        self.assertEqual(self.severity.get("probe.on_local"), None)

    def test_the_unbuilt_levels_are_reported_rather_than_faked(self):
        """An engine with no levels must be reported as such rather than as -200 dBFS everywhere,
        which would look exactly like a broken input. The fixture is a *working* pedal and does have
        levels, so the no-levels case is made here instead of borrowed from it (the fixture was
        captured with the engine down until 2026-10-09, and the test quietly depended on that)."""
        bare = sample()
        bare["engine"].pop("levels", None)
        severity = {f["key"]: f["severity"] for f in report_for(bare).findings}
        self.assertEqual(severity.get("levels.unavailable"), "info")
        self.assertIsNone(severity.get("levels.present"))
        # And the fixture itself is the other case: levels that are there are reported.
        self.assertIsNotNone(sample()["engine"].get("levels"))
        self.assertEqual(self.severity.get("levels.unavailable"), None)


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

    def test_a_protocol_version_mismatch_is_named_first(self):
        # Both ends refuse a different major (uart-protocol.md, Session), so a half-swapped pair
        # shows as frames with no session. Say which two versions, rather than listing wires.
        s = sample()
        s["service"]["link"]["session"] = False
        s["service"]["link"]["frames_ok"] = 500
        s["service"]["link"]["protocol"] = "2.0"
        s["service"]["link"]["pico"] = {"fw": "0.1", "major": 1, "minor": 0, "caps": 0x0003}
        f = finding(report_for(s).findings, "link.no_session")
        self.assertIsNotNone(f)
        self.assertIn("version mismatch", f["likely"][0])
        self.assertIn("1.0", f["likely"][0])
        self.assertIn("2.0", f["likely"][0])

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

    def test_a_hot_channel_names_the_gain_stages_and_how_many_were_clamped(self):
        levels = self.levels()
        levels["input"]["peak"] = [-0.4, -0.4]
        f = finding(self.report(levels), "levels.hot")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")
        self.assertIn("inst/line", " ".join(f["likely"]).lower())
        # A peak over a window is not a clamp, and saying which it is is the difference between a
        # player reaching for their guitar's volume and reaching for their gain knob.
        self.assertIn("clip count", " ".join(f["likely"]))

    def test_a_long_silent_window_names_the_historical_wire(self):
        """A second of every input channel at the engine's floor: that is a fault, and the check
        names the lead that has caused it before."""
        levels = self.levels()
        levels["input"]["peak"] = [-200.0, -200.0]
        for chain in levels["chains"]:
            chain["out"]["frames"] = 48000
            for node in chain["nodes"]:
                node["frames"] = 48000
        f = finding(self.report(levels), "levels.silent_input")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")
        self.assertIn("pin 38", f["check"])

    def test_a_short_silent_window_is_not_a_fault(self):
        """Sixty-four frames of silence is a decay between two notes, not a dead input. The engine
        reads and resets, so a window can be one period long, and calling that silent would fire
        the finding between every pair of notes -- the tool inventing a fault out of its own
        timing, which is the mistake this whole section exists to avoid."""
        levels = self.levels()
        levels["input"]["peak"] = [-200.0, -200.0]
        for chain in levels["chains"]:
            chain["out"]["frames"] = 64
            for node in chain["nodes"]:
                node["frames"] = 64
        self.assertIsNone(finding(self.report(levels), "levels.silent_input"))

    def test_a_window_with_no_samples_is_never_silence(self):
        """No frames means nothing was measured, whatever the peak says."""
        levels = self.levels()
        levels["input"]["peak"] = [-200.0, -200.0]
        for chain in levels["chains"]:
            chain["out"]["frames"] = 0
            for node in chain["nodes"]:
                node["frames"] = 0
        self.assertIsNone(finding(self.report(levels), "levels.silent_input"))

    def test_the_engine_without_levels_says_so_rather_than_printing_zeros(self):
        """No levels object at all -- the engine down, or too old to publish them."""
        s = sample()
        s["engine"].pop("levels", None)
        findings = report_for(s).findings
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
        """D5 (2026-10-09): the IRQ belongs on a render core that is *not* the active one, and the
        report must notice any other core. The mutation has to be derived, not remembered:
        `affinity_mask` is hex, and the design has moved the IRQ twice (core 2 -> 0 in P7, 0 -> 1
        when the core rules changed), so a hardcoded "wrong" value goes stale the moment the design
        does. Both wrong kinds are checked: the active render core, which is the one D5 exists to
        protect, and the housekeeping core."""
        interface, _ = pd.load_interface()
        cpu = interface["host"]["cpu"]
        want = cpu["audio_irq_cpu"]
        active = cpu["render_cpu"]
        housekeeping = cpu["housekeeping"].split("-")[0].split(",")[0]
        for wrong in (active, housekeeping):
            if str(wrong) == want:
                continue        # a device whose active core IS the IRQ core has no such case
            with self.subTest(wrong=wrong):
                s = sample()
                s["audio_irq"]["affinity_mask"] = "%x" % (1 << int(wrong))
                f = finding(report_for(s).findings, "host.irq_affinity")
                self.assertIsNotNone(f)
                self.assertEqual(f["severity"], "warn")
                self.assertIn("cores %s" % wrong, f["evidence"])
                self.assertIn("design says core %s" % want, f["evidence"])

    def test_the_irq_mask_is_hex_not_binary(self):
        """`4` means cpu 2. Reading it as a binary string is the trap this covers."""
        self.assertEqual(pd.expand_hex_mask("4"), {2})
        self.assertEqual(pd.expand_hex_mask("c"), {2, 3})
        self.assertEqual(pd.expand_hex_mask("00000001,00000000"), {32})

    def test_the_gatherer_s_output_parses_with_the_cost_line_after_it(self):
        """The gatherer prints one line of JSON and then `COST <seconds>`; the local path used to
        json.loads the whole buffer, which crashed the moment the cost line was there -- that is, on
        every non-deep sample of `pedal-diag --json` on the pedal itself (Extra data: line 2 column
        1). Both paths parse through one function now, so they cannot drift."""
        sample = pd.sample_from_gather_output('{"a": 1}\nCOST 0.2500\n')
        self.assertEqual(sample["a"], 1)
        self.assertEqual(sample["cost_cpu_s"], 0.25)
        # A sudo warning ahead of them, and no cost line at all: both are normal.
        self.assertEqual(pd.sample_from_gather_output('sudo: a warning\n{"a": 2}\n')["a"], 2)
        self.assertIsNone(pd.sample_from_gather_output('{"a": 3}\nCOST nonsense\n').get("cost_cpu_s"))
        with self.assertRaises(SystemExit):
            pd.sample_from_gather_output("COST 0.5\n")


def gatherer_function(name):
    """One function out of the gatherer's source, on its own: the gatherer as a whole reads the
    host at import, so it cannot be run here, but its pure parts can."""
    tree = ast.parse(pd.GATHER_SOURCE)
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in (name, "read")]
    namespace = {"os": os}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<gatherer>", "exec"), namespace)
    return namespace[name]


def fake_asound(root, cards):
    """A /proc/asound of numbered card directories, each with its id file and the kernel's
    id -> cardN symlink beside it."""
    for index, card_id in enumerate(cards):
        os.makedirs(os.path.join(root, "card%d" % index, "pcm0p", "sub0"))
        with open(os.path.join(root, "card%d" % index, "id"), "w") as f:
            f.write(card_id + "\n")
        os.symlink("card%d" % index, os.path.join(root, card_id))
    return root


class TheEngineCardIsFoundByIdNotNumber(unittest.TestCase):
    """The PCM state is the engine's card's, whatever number the kernel gave it.

    The gatherer read /proc/asound/card0 until 2026-10-16. Since the screen (D14) vip probes two
    vc4 HDMI cards first, so card 0 is vc4hdmi0 and the codec is card 2, and the report's PCM
    status, hw_params and sw_params were the HDMI port's, or empty. `cards-vip-with-screen.txt` is
    that card list, in the kernel's format with the ids vip showed on 2026-10-16.
    """

    VIP = ["vc4hdmi0", "vc4hdmi1", "wm8960"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.asound = fake_asound(os.path.join(self.tmp.name, "asound"), self.VIP)

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, device, asound):
        return gatherer_function("_alsa_card")(device, asound=asound)

    def test_the_gatherer_never_reads_a_card_by_number(self):
        self.assertNotIn("/proc/asound/card0", pd.GATHER_SOURCE)
        self.assertNotIn("asound/card%", pd.GATHER_SOURCE)

    def test_the_codec_behind_two_hdmi_cards_is_card_2(self):
        card = self.resolve("hw:CARD=wm8960,DEV=0", asound=self.asound)
        self.assertTrue(card["present"])
        self.assertEqual(card["index"], 2)
        self.assertEqual(card["id"], "wm8960")
        self.assertEqual(os.path.basename(card["dir"]), "card2")
        self.assertEqual(card["pcm_device"], 0)

    def test_every_spelling_of_the_device_finds_the_same_card(self):
        for device in ("hw:CARD=wm8960,DEV=0", "hw:wm8960,0", "hw:wm8960", "plughw:CARD=wm8960",
                       "hw:2,0", "hw:2"):
            card = self.resolve(device, asound=self.asound)
            self.assertEqual((card["present"], card["index"]), (True, 2), device)

    def test_the_device_number_is_kept(self):
        self.assertEqual(self.resolve("hw:CARD=wm8960,DEV=1", asound=self.asound)["pcm_device"], 1)

    def test_a_card_that_is_not_there_is_absent_rather_than_card_0(self):
        card = self.resolve("hw:CARD=II,DEV=0", asound=self.asound)
        self.assertFalse(card["present"])
        self.assertIsNone(card["dir"])
        self.assertIsNone(card["index"])

    def three_cards(self):
        """The healthy fixture as vip is now: the same streams, read from card 2."""
        s = sample()
        s["alsa"]["cards"] = (FIXTURES / "cards-vip-with-screen.txt").read_text().strip()
        s["alsa"]["card"].update({"dir": "/proc/asound/card2", "index": 2})
        for side, letter in (("capture", "c"), ("playback", "p")):
            s["alsa"]["pcm"][side]["node"] = "/proc/asound/card2/pcm0%s/sub0" % letter
        return s

    def test_the_card_list_is_read_by_id(self):
        cards = pd.parse_cards(self.three_cards()["alsa"]["cards"])
        self.assertEqual([(c["index"], c["id"]) for c in cards],
                         [(0, "vc4hdmi0"), (1, "vc4hdmi1"), (2, "wm8960")])
        self.assertEqual(cards[2]["name"], "simple-card - wm8960")

    def test_the_codec_as_card_2_is_a_healthy_pedal(self):
        findings = report_for(self.three_cards()).findings
        severity = {f["key"]: f["severity"] for f in findings}
        self.assertEqual([f["key"] for f in findings if f["severity"] == "fail"], [])
        self.assertIsNone(severity.get("codec.no_card"))
        self.assertIsNone(severity.get("audio.card_absent"))
        self.assertEqual(severity.get("audio.streaming"), "ok")
        self.assertEqual(severity.get("audio.hw_params"), "ok")

    def test_an_hdmi_card_alone_is_no_codec(self):
        s = self.three_cards()
        s["alsa"]["cards"] = "\n".join(s["alsa"]["cards"].splitlines()[:4])
        f = finding(report_for(s).findings, "codec.no_card")
        self.assertIsNotNone(f)
        self.assertIn("vc4hdmi0", f["evidence"])

    def test_a_closed_engine_names_its_own_card_not_the_first(self):
        s = self.three_cards()
        s["engine"]["status"]["state"] = "closed"
        f = finding(report_for(s).findings, "audio.closed_with_codec")
        self.assertIsNotNone(f)
        self.assertIn("card 2 wm8960", f["evidence"])
        self.assertNotIn("vc4hdmi", f["evidence"])

    def test_the_advice_names_the_card_by_id(self):
        s = self.three_cards()
        s["engine"]["status"].pop("format", None)
        f = finding(report_for(s).findings, "audio.format_unpublished")
        self.assertIsNotNone(f)
        self.assertIn("/proc/asound/wm8960/pcm0p/sub0/hw_params", f["check"])
        self.assertNotIn("card0", f["check"])

    def test_an_engine_card_that_is_absent_says_nothing_was_read(self):
        """piv's engine opens the SSL 2+ (hw:CARD=II): unplugged, its PCM state is not empty
        files to judge but a card that is not there."""
        s = self.three_cards()
        s["alsa"]["card"] = {"card": "II", "device": "hw:CARD=II,DEV=0", "pcm_device": 0,
                             "present": False, "dir": None, "index": None, "id": None,
                             "device_source": "/etc/namchain/namchaind.json"}
        for side in ("capture", "playback"):
            s["alsa"]["pcm"][side].update({"status": None, "hw_params": None, "sw_params": None})
        f = finding(report_for(s).findings, "audio.card_absent")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")
        self.assertIn("hw:CARD=II", f["evidence"])
        self.assertIn("2 wm8960", f["evidence"])

    def test_a_sample_from_before_the_card_entry_still_reports(self):
        """A watch log written by the old gatherer has no alsa.card; its card comes from the
        interface model and the card list."""
        s = self.three_cards()
        del s["alsa"]["card"]
        s["engine"]["status"]["state"] = "closed"
        f = finding(report_for(s).findings, "audio.closed_with_codec")
        self.assertIn("card 2 wm8960", f["evidence"])

    def test_the_interface_model_names_no_card_by_number(self):
        audio = pd.load_interface()[0]["host"]["audio"]
        for key in ("capture_node", "playback_node"):
            self.assertIn("/proc/asound/%s/" % audio["card_id"], audio[key])
        self.assertNotIn("card0", json.dumps(audio))


class TheInterfaceModelIsEnoughToNameWires(unittest.TestCase):
    def test_the_interface_model_lives_where_the_rootfs_installs_it(self):
        """It has to reach /etc/pedal/pedal-interface.json, and the only thing that installs
        anything is the rootfs tree: apply stages rootfs_files() and the image build copies
        rootfs/. Until 2026-10-09 the model sat at devices/common/pedal-interface.json, which looks
        installed and is not — neither path carried it, the pedal-diag service's
        ConditionPathExists never matched, and the tool never ran on the pedal at all."""
        inside = TOOL_PATH.parents[3] / "etc/pedal/pedal-interface.json"   # devices/common/rootfs
        self.assertTrue(inside.exists(), f"{inside} must exist: that is what installs it")
        self.assertTrue(any(pathlib.Path(p).name == "pedal-interface.json" and "rootfs" in pathlib.Path(p).parts
                            for p in pd.INTERFACE_PATHS),
                        f"a checkout must find the model inside the rootfs: {pd.INTERFACE_PATHS}")

    def test_every_codec_signal_names_a_physical_place_and_a_fault(self):
        interface, _ = pd.load_interface()
        signals = interface["codec"]["signals"]
        self.assertGreaterEqual(len(signals), 8)
        for signal in signals:
            self.assertTrue(signal.get("signal"), signal)
            self.assertTrue(signal.get("fault_symptom"), signal)
            self.assertTrue(signal.get("check"), signal)

    def test_the_model_does_not_invent_a_device_id_register(self):
        """The WM8960 has no ID register: R0 is LINVOL, and a real read returns a volume. The model
        claimed 0x8960 at register 0 until 2026-10-06, which would have made any real read look
        like the wrong chip (sound/soc/codecs/wm8960.h)."""
        interface, _ = pd.load_interface()
        codec = interface["codec"]
        self.assertEqual(codec["i2c_address_hex"], "0x1a")
        self.assertIs(codec["has_id_register"], False)
        self.assertNotIn("id_value", codec)
        self.assertTrue(codec.get("why_no_id"), "the model must say why there is no id to read")

    def test_the_register_map_names_the_registers_the_driver_names(self):
        """The table used to be one register out from R5 on, which labelled the audio interface as
        a clocking register. R7 is IFACE1, and it is where the codec's I2S master bit lives."""
        regs = {0x00: 0x0117, 0x02: 0x0173, 0x05: 0x0000, 0x06: 0x0000, 0x07: 0x004E,
                0x08: 0x01C4, 0x0F: 0x0000}
        names = pd.decode_codec_registers(regs)
        labels = {int(k.split()[0], 16): k for k in names}
        self.assertIn("left input volume", labels[0x00])
        self.assertIn("headphone", labels[0x02])
        self.assertIn("DAC control 1", labels[0x05])
        self.assertIn("DAC control 2", labels[0x06])
        self.assertIn("audio interface", labels[0x07])
        self.assertIn("master/slave", labels[0x07])
        self.assertIn("clocking (2)", labels[0x08])
        self.assertIn("software reset", labels[0x0F])

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


class TheChipsOwnRegisters(unittest.TestCase):
    """--probe asks the codec for its registers, and what comes back is a finding either way.

    On this pedal the read does not complete (2026-10-06: every register aborts with lost
    arbitration and SDA stuck at low, while writes are clean), so the failure itself is what the
    report has to carry — with the controller's own words, and without pretending the driver's
    cache is the chip.
    """

    def probe(self, s, **kw):
        s["i2c_probe"] = dict({"requested": True, "attempted": True, "tool": "/usr/sbin/i2cget",
                               "client": "1-001a", "bus": "1", "address": "0x1a",
                               "aborts_before": 0, "aborts_after": 0, "abort_lines": []}, **kw)
        return s

    def test_a_successful_read_is_reported_as_the_chips_own_words(self):
        s = self.probe(sample(), reads={"0x00": {"value": 0x0117, "raw": "0x0117"},
                                        "0x07": {"value": 0x004E, "raw": "0x004e"}})
        f = finding(report_for(s).findings, "codec.read")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "ok")
        self.assertIn("audio interface", f["evidence"])
        self.assertIn("0x004e", f["evidence"])

    def test_a_read_that_disagrees_with_the_cache_is_a_warning(self):
        s = sample()
        s["codec"]["registers"] = "00: 0117\n07: 004e\n"      # the driver's cache
        s = self.probe(s, reads={"0x00": {"value": 0x0117, "raw": "0x0117"},
                                 "0x07": {"value": 0x0000, "raw": "0x0000"}})
        findings = report_for(s).findings
        self.assertIsNotNone(finding(findings, "codec.read"))
        differs = finding(findings, "codec.cache_differs")
        self.assertIsNotNone(differs)
        self.assertEqual(differs["severity"], "warn")
        self.assertIn("0x07", differs["evidence"])
        # and no "everything agrees" line while something does not
        self.assertIsNone(finding(findings, "codec.read_agrees"))

    def test_a_read_that_the_controller_aborts_carries_the_abort_reason(self):
        s = self.probe(sample(), reads={"0x00": {"error": "Error: Read failed"},
                                        "0x07": {"error": "Error: Read failed"}},
                       aborts_before=22, aborts_after=26,
                       abort_lines=["i2c_designware 1f00074000.i2c: i2c_dw_handle_tx_abort: lost arbitration",
                                    "i2c_designware 1f00074000.i2c: i2c_dw_handle_tx_abort: SDA stuck at low"])
        f = finding(report_for(s).findings, "codec.read_failed")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "warn")
        self.assertIn("lost arbitration", f["evidence"])
        self.assertIn("SDA stuck at low", f["evidence"])
        self.assertIn("4 controller abort(s)", f["evidence"])
        self.assertIn("i2cget", f["evidence"])
        # and it must not blame the SDA hold time, which was tried and changed nothing
        self.assertIn("SDA hold time", " ".join(f["likely"]))

    def test_a_probe_that_could_not_ask_says_why_rather_than_guessing(self):
        s = sample()
        s["i2c_probe"] = {"requested": True, "attempted": False,
                          "why": "i2cget is not installed on this host"}
        f = finding(report_for(s).findings, "codec.read_unavailable")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "info")
        self.assertIn("i2cget", f["evidence"])

    def test_an_ordinary_sample_asks_nothing_and_says_nothing(self):
        findings = report_for(sample()).findings
        for key in ("codec.read", "codec.read_failed", "codec.read_unavailable"):
            self.assertIsNone(finding(findings, key), key)

    def test_a_card_that_failed_to_probe_is_not_blamed_on_the_i2s_leads_first(self):
        """What actually happened on 2026-10-06: the driver could not issue its reset write over a
        wedged I2C bus, and the report was naming ADCLRC and BCLK."""
        s = sample()
        s["alsa"]["cards"] = ""
        s["kmsg_lines"] = ["[  123.456] wm8960 1-001a: Failed to issue reset",
                           "[  123.456] i2c_designware 1f00074000.i2c: controller timed out"]
        f = finding(report_for(s).findings, "codec.no_card")
        self.assertIsNotNone(f)
        self.assertIn("Failed to issue reset", f["likely"][0])
        self.assertIn("I2C bus", f["likely"][1])
        self.assertIn("Failed to issue reset", f["evidence"])
        self.assertIn("dmesg for 'wm8960 1-001a' first", f["check"])

    def test_with_nothing_in_dmesg_the_leads_are_still_the_place_to_look(self):
        s = sample()
        s["alsa"]["cards"] = ""
        s["kmsg_lines"] = []
        s["kmsg_interesting"] = []
        f = finding(report_for(s).findings, "codec.no_card")
        self.assertIn("ADCLRC", f["likely"][0])


class ProbesAndTheLink(unittest.TestCase):
    """Where the probes are, and whether the link that should exist does.

    The probe question cost a session (2026-10-05): the Debug Probe's USB was on the Mac, the
    report was gathered on vip, and "no Debug Probe is attached to this host" read as a fault on
    the pedal. A probe's USB goes to the machine running the tooling and only its UART or SWD lead
    goes to the pedal, so the report now says which machine it looked at and which machine has it.
    """

    PROBE_ON_CORE = {"path": "3-2", "vid": "2e8a", "pid": "000c",
                     "product": "Debug Probe (CMSIS-DAP)", "serial": "E664A836A3366B37"}

    def probe_on_local(self, s, ports=("/dev/cu.usbmodem1102",)):
        s["local"] = {"hostname": "M2", "platform": "darwin", "gathered_with": "ioreg",
                      "usb": [{"vid": "2e8a", "pid": "000c", "product": "Debug Probe _CMSIS_DAP_",
                               "serial": "E664A836A3366B37", "path": "Debug Probe@01100000"}],
                      "serial": [{"device": p, "name": os.path.basename(p), "holders": []}
                                 for p in ports]}
        return s

    def test_a_probe_on_the_core_is_reported_with_the_machine_it_is_on(self):
        s = sample()
        s["usb"].append(self.PROBE_ON_CORE)
        f = finding(report_for(s).findings, "probe.on_core")
        self.assertIsNotNone(f)
        self.assertIn("vip", f["what"])
        self.assertIn("2e8a:000c", f["evidence"])
        self.assertIn("not visible to software", f["connected_to"])

    def test_a_probe_on_the_operators_own_machine_is_reported_as_being_there(self):
        """The Mac's own USB, read by the tool itself: this is the case that was misread."""
        s = self.probe_on_local(sample())
        findings = report_for(s).findings
        self.assertIsNone(finding(findings, "probe.none"))
        f = finding(findings, "probe.on_local")
        self.assertIsNotNone(f)
        self.assertIn("M2", f["what"])
        self.assertIn("machine running this tool", f["what"])
        self.assertIn("/dev/cu.usbmodem1102", f["evidence"])

    def test_the_two_machines_are_reported_separately(self):
        s = self.probe_on_local(sample())
        s["usb"].append(self.PROBE_ON_CORE)
        findings = report_for(s).findings
        self.assertIsNotNone(finding(findings, "probe.on_local"))
        self.assertIsNotNone(finding(findings, "probe.on_core"))
        self.assertIsNone(finding(findings, "probe.none"))

    def test_a_held_port_names_the_process_that_holds_it(self):
        s = self.probe_on_local(sample())
        s["local"]["serial"][0]["holders"] = ["measure-boot.py (4312)"]
        f = finding(report_for(s).findings, "probe.on_local")
        self.assertIn("measure-boot.py", f["connected_to"])

    def test_a_probe_sniffed_on_the_pico_is_said_to_be_on_the_pico(self):
        s = self.probe_on_local(sample())
        s["probe_uart"] = {"device": "/dev/cu.usbmodem1102", "target": "the Pico's link UART",
                           "because": "protocol frames (a5 5a) are on it"}
        f = finding(report_for(s).findings, "probe.on_local")
        self.assertIn("the Pico's link UART", f["connected_to"])

    def test_no_probe_anywhere_says_so_in_one_sentence(self):
        f = finding(report_for(sample()).findings, "probe.none")
        self.assertEqual(f["what"], "No debug probes connected via USB to any device")
        self.assertIn("vip", f["evidence"])

    def test_another_usb_serial_lead_is_reported_as_an_aid(self):
        s = sample()
        s["usb"].append({"path": "3-3", "vid": "0403", "pid": "6001", "product": "FT232R",
                         "serial": "A50285BI"})
        f = finding(report_for(s).findings, "probe.other.core")
        self.assertIsNotNone(f)
        self.assertIn("FTDI", f["what"])

    def test_the_link_that_should_exist_is_reported_as_up_in_one_line(self):
        f = finding(report_for(sample()).findings, "link.session")
        self.assertEqual(f["severity"], "ok")
        self.assertIn("Core→Pico UART link is up", f["what"])

    def test_a_registered_uart_with_no_device_node_is_not_blamed_on_the_overlay(self):
        """The state measured on vip on 2026-10-05: the tty was registered (204:64) and /dev had
        no node for it. That is a node problem, and the fix is udev, not the device tree."""
        s = sample()
        del s["tty"]["ttyAMA0"]
        s["link_device"] = {"name": "ttyAMA0", "node": "/dev/ttyAMA0", "node_exists": False,
                            "class_entry": True, "major_minor": "204:64", "holders": [],
                            "path": "/sys/devices/platform/1f00030000.serial/1f00030000.serial:0"}
        s["overlays"] = {"2_uart0-enable": "applied"}
        f = finding(report_for(s).findings, "link.no_node")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")
        self.assertIn("204:64", f["evidence"])
        self.assertIn("udevadm", f["check"])
        self.assertIsNone(finding(report_for(s).findings, "link.no_device"))

    def test_an_absent_uart_names_the_service_that_enables_it(self):
        s = sample()
        del s["tty"]["ttyAMA0"]
        s["link_device"] = {"name": "ttyAMA0", "node": "/dev/ttyAMA0", "node_exists": False,
                            "class_entry": False, "major_minor": None, "holders": []}
        s["overlays"] = {}
        s["units"] = {"pedal-uart.service": {"ActiveState": "failed"}}
        f = finding(report_for(s).findings, "link.no_device")
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "fail")
        self.assertIn("pedal-uart.service", f["evidence"])
        self.assertIn("failed", f["evidence"])
        self.assertIn("pedal-uart", f["check"])

    def test_a_holder_is_named_as_the_service_it_is(self):
        """pedald is a python3 script: its comm is "python3", and the link's port is held by it."""
        s = sample()
        s["processes"]["pedald"] = {"running": True, "pid": 35704,
                                    "cmdline": "python3 /usr/local/sbin/pedald run"}
        s["link_device"] = {"name": "ttyAMA0", "node": "/dev/ttyAMA0", "node_exists": True,
                            "class_entry": True, "major_minor": "204:64",
                            "holders": ["python3 (35704)"]}
        f = finding(report_for(s).findings, "link.session")
        self.assertIn("pedald (pid 35704)", f["evidence"])


class TheProbeParsers(unittest.TestCase):
    """The two parsers that read the machine this tool runs on, against real output."""

    IOREG = textwrap.dedent("""\
        +-o Root  <class IORegistryEntry, id 0x100000100, retain 32>
          +-o AppleT8112USBXHCI@01000000  <class AppleT8112USBXHCI, id 0x100000471, registered>
          | +-o Debug Probe (CMSIS-DAP)@01100000  <class IOUSBHostDevice, id 0x10001ce1d, registered>
          |     {
          |       "USBSpeed" = 1
          |       "idProduct" = 12
          |       "USB Product Name" = "Debug Probe _CMSIS_DAP_"
          |       "USB Serial Number" = "E664A836A3366B37"
          |       "idVendor" = 11914
          |       "locationID" = 17825792
          |     }
        """)

    def test_ioreg_decimal_ids_become_the_hex_the_gatherer_reports(self):
        devices = pd.parse_ioreg_usb(self.IOREG)
        self.assertEqual(len(devices), 1, devices)
        self.assertEqual((devices[0]["vid"], devices[0]["pid"]), ("2e8a", "000c"))
        self.assertEqual(devices[0]["serial"], "E664A836A3366B37")
        self.assertIn("Debug Probe", devices[0]["path"])

    def test_ioreg_output_with_no_usb_device_is_empty_rather_than_wrong(self):
        self.assertEqual(pd.parse_ioreg_usb("+-o Root  <class IORegistryEntry>\n"), [])

    def test_lsof_output_becomes_command_and_pid(self):
        self.assertEqual(pd.parse_lsof("p4312\ncmeasure-boot.py\nn/dev/cu.usbmodem1102\n"),
                         ["measure-boot.py (4312)"])
        self.assertEqual(pd.parse_lsof(""), [])

    def test_the_pico_s_protocol_frames_identify_the_link_uart(self):
        target, because = pd.classify_serial_bytes(b"\xa5\x5a\x01\x07\x01\x00\x00\x00\x30")
        self.assertEqual(target, "the Pico's link UART")
        self.assertIn("a5 5a", because)

    def test_kernel_text_identifies_a_console(self):
        target, _ = pd.classify_serial_bytes(b"\r\nUbuntu 26.04 resolute vip ttyAMA10\r\n")
        self.assertEqual(target, "a Linux console")

    def test_kernel_log_lines_identify_a_console(self):
        """What the Debug Probe's UART lead caught when it was on vip's 3-pin header: the kernel's
        own log lines, timestamps and all."""
        target, because = pd.classify_serial_bytes(
            b"[  557.694768] OF: overlay: WARNING: memory leak will occur if overlay removed\n")
        self.assertEqual(target, "a Linux console")
        self.assertIn("kernel log lines", because)

    def test_silence_is_reported_as_silence_and_not_as_a_target(self):
        """An idle console and a link nobody is talking to both look like nothing, and the tool
        must not turn its own timing into a diagnosis."""
        target, because = pd.classify_serial_bytes(b"")
        self.assertIsNone(target)
        self.assertIn("nothing arrived", because)


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
        decoded = pd.decode_codec_registers({0x00: 0x0117, 0x04: 0x0005, 0x07: 0x004E})
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

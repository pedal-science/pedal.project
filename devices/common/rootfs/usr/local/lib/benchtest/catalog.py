"""The benchtests, the modules they exercise, the pass bars, and which module each failure paints.

This is the one table the plan asks for: a threshold or a "this failure paints that block" lives
here and nowhere else, so the page cannot invent a cause the numbers do not support. Everything
below is data plus pure functions over it; nothing here touches the pedal, a socket or a file.

A benchtest's result has one shape, real or fake:

    {"test": id, "name": str, "status": "pass" | "fail" | "not_run",
     "summary": str, "evidence": str | None, "next": str | None, "likely": [str],
     "checks": [{"component": id, "ok": bool, "check": str, "said": str}],
     "facts": {...}}

`checks` is how the result ties itself to blocks: one entry per block the benchtest exercised, with
`check` saying *how* it exercised that block (the check, not just the block's name) and `said`
what it found. A test is red if any of its checks failed; a block is red in a run if any check
in that run that names it failed (lamps.py). `not_run` is a benchtest that could not judge
anything — no helper, no codec, the engine unreachable — and leaves no mark on any lamp.
"""

import math

# ----------------------------------------------------------------------------------- the modules

#: The blocks on the page: only what a benchtest can exercise (the relay, MIDI, the footswitches,
#: the display and the mic stay on docs/diagrams/modules.html). Names and jobs are the map's, in
#: ordinary words; part numbers stay off the blocks. `line` is the one line drawn on the block,
#: `job` the sentence the detail shows. `zone` is where the page draws it.
COMPONENTS = [
    {"id": "interface", "name": "Audio interface", "zone": "outside_left", "kind": "ext",
     "line": "records the outputs",
     "job": "Listens to the pedal's outputs and plays into its input, for these tests"},
    {"id": "guitar_input", "name": "Guitar input", "zone": "audio", "kind": "module",
     "line": "buffers the guitar",
     "job": "Buffers the guitar, with its instrument/line switch"},
    {"id": "output_left", "name": "Left output", "zone": "audio", "kind": "module",
     "line": "line out, left",
     "job": "Line out, left: keeps the codec's DC off the jack"},
    {"id": "output_right", "name": "Right output", "zone": "audio", "kind": "module",
     "line": "line out, right",
     "job": "Line out, right: the same circuit as the left"},
    {"id": "codec", "name": "Codec", "zone": "audio", "kind": "module",
     "line": "sound to numbers",
     "job": "Turns sound into numbers and back; every audio ground meets here"},
    {"id": "codec_wires", "name": "Codec wires", "zone": "wires", "kind": "wire",
     "line": "power, I2C, clocks, sound",
     "job": "Core's header to the codec: its power, I2C, clocks and sound"},
    {"id": "uart_wires", "name": "Pico link wires", "zone": "wires", "kind": "wire",
     "line": "header pins 8 and 10",
     "job": "The UART between Core and the Pico, on header pins 8 and 10"},
    {"id": "core", "name": "Core", "zone": "digital", "kind": "module",
     "line": "runs the sound engine",
     "job": "Runs the sound engine and the pedal service"},
    {"id": "pico", "name": "Pico", "zone": "digital", "kind": "module",
     "line": "footswitches and controls",
     "job": "Reads the footswitches and controls, and talks to Core"},
    {"id": "mains", "name": "Core's mains power", "zone": "outside_right", "kind": "ext",
     "line": "the USB-C adapter",
     "job": "The USB-C adapter that powers Core"},
    {"id": "probe", "name": "Debug probe", "zone": "outside_right", "kind": "ext",
     "line": "on your computer's USB",
     "job": "Watches the Pico or Core, from your computer's USB"},
]

COMPONENT_IDS = [c["id"] for c in COMPONENTS]

# ------------------------------------------------------------------------------ the bench setup

#: The order a setup's sentences are said in: the lead first, then the codec, then the power.
SETUP_FACTS = ("lead", "codec_input", "core_power")

#: What the bench is before anybody has said otherwise. The lead has no assumption: nobody knows
#: where it is until the first noise test has asked for it.
SETUP_ASSUMED = {"codec_input": "board", "core_power": "mains"}

#: One plain sentence per change of a setup fact, worded as the plan words them.
SETUP_STEPS = {
    ("lead", "left_output"):
        "Plug the pedal's left output into input 1 of the audio interface. "
        "Take any lead out of the guitar input.",
    ("lead", "right_output"):
        "Plug the pedal's right output into input 1 of the audio interface (the same lead, moved "
        "from the left output). Take any lead out of the guitar input.",
    ("lead", "guitar_input"):
        "Take the lead out of the pedal's output. Plug output 1 of the audio interface into the "
        "guitar input, with nothing playing.",
    ("codec_input", "grounded"):
        "Unplug the guitar-input board from the codec, and join the codec's input pin to the pin "
        "beside it labelled GND.",
    ("codec_input", "board"):
        "Take the join off the codec's input pin and plug the guitar-input board back into the codec.",
    ("core_power", "battery"):
        "Run the Pi from a battery pack instead of its mains adapter.",
    ("core_power", "mains"):
        "Put the Pi back on its mains adapter.",
}

# ------------------------------------------------------------------------------- the benchtests

#: Every benchtest, in the order a run runs them (never the order they were ticked).
#:
#: components  the blocks it exercises; a click on one of them runs it (if `auto`)
#: exercises   how it exercises each block, said as the check
#: default     ticked when the page opens
#: offer       "always", or "after_hum": listed only once the guitar-input test has found mains hum
#: auto        a block click may run it ("Codec input on its own" is never chosen for you)
#: helper      needs scripts/benchtest running on the computer
#: setup       the bench it needs, as SETUP_FACTS values; None for no cables at all
#: bars        its pass bars
TESTS = [
    {"id": "codec", "name": "Codec", "group": "health", "kind": "diag",
     "line": "Power, I2C and clocks: is the codec there and answering?",
     "components": ["codec", "codec_wires"],
     "exercises": {"codec": "the codec answers on I2C and its sound card appears",
                   "codec_wires": "3V3, SDA and SCL reach the codec, and its clocks reach Core"},
     "pass_summary": "The codec is there: it answers on I2C and its clocks reach Core.",
     "default": True, "offer": "always", "auto": True, "helper": False, "setup": None},
    {"id": "audio", "name": "Sound device and engine", "group": "health", "kind": "diag",
     "line": "Streaming, format and xruns",
     "components": ["core", "codec"],
     "exercises": {"core": "the sound engine runs and keeps up, at 48 kHz with 64-frame periods",
                   "codec": "the engine has the codec's sound device open and streaming"},
     "pass_summary": "The engine has the sound device open and streaming, in the right format.",
     "default": True, "offer": "always", "auto": True, "helper": False, "setup": None},
    {"id": "link", "name": "Pico link", "group": "health", "kind": "diag",
     "line": "Is Core talking to the Pico?",
     "components": ["uart_wires", "pico", "core"],
     "exercises": {"uart_wires": "Core and the Pico hold a session over header pins 8 and 10",
                   "pico": "the Pico's messages arrive",
                   "core": "Core's header UART and the pedal service are up"},
     "pass_summary": "Core and the Pico are talking, with no bad frames.",
     "default": True, "offer": "always", "auto": True, "helper": False, "setup": None},
    {"id": "core", "name": "Core", "group": "health", "kind": "diag",
     "line": "Temperature, undervoltage, memory and tuning",
     "components": ["core", "mains"],
     "exercises": {"core": "Core's temperature, memory, card space and tuning",
                   "mains": "Core's supply holds its voltage: the low-voltage alarm is off"},
     "pass_summary": "Core is cool, has memory to spare, and its supply holds up.",
     "default": True, "offer": "always", "auto": True, "helper": False, "setup": None},
    {"id": "probe", "name": "Debug probe", "group": "health", "kind": "probe",
     "line": "Is the probe's USB plugged into this computer?",
     "components": ["probe"],
     "exercises": {"probe": "the Debug Probe's USB is on the computer running scripts/benchtest"},
     "default": False, "offer": "always", "auto": True, "helper": True, "setup": None},
    {"id": "noise_left", "name": "Left output noise", "group": "noise", "kind": "output_noise",
     "line": "The noise at the left output, with the engine muted",
     "components": ["output_left", "interface"],
     "exercises": {"output_left": "the noise at the left output, with the engine sending silence",
                   "interface": "the audio interface records the pedal's output"},
     "side": "left",
     "default": True, "offer": "always", "auto": True, "helper": True,
     "setup": {"lead": "left_output", "codec_input": "board"},
     "bars": {"max_rms_dbfs": -90.0, "baseline_rms_dbfs": -99.0,
              "hum_hz": [50.0, 100.0, 150.0], "hum_tolerance_hz": 3.0,
              "max_hum_line_dbfs": -110.0, "seconds": 20, "skip_seconds": 2}},
    {"id": "noise_right", "name": "Right output noise", "group": "noise", "kind": "output_noise",
     "line": "The same, at the right output (the last session only measured the left)",
     "components": ["output_right", "interface"],
     "exercises": {"output_right": "the noise at the right output, with the engine sending silence",
                   "interface": "the audio interface records the pedal's output"},
     "side": "right",
     "default": False, "offer": "always", "auto": True, "helper": True,
     "setup": {"lead": "right_output", "codec_input": "board"},
     "bars": {"max_rms_dbfs": -90.0, "baseline_rms_dbfs": -99.0,
              "hum_hz": [50.0, 100.0, 150.0], "hum_tolerance_hz": 3.0,
              "max_hum_line_dbfs": -110.0, "seconds": 20, "skip_seconds": 2}},
    {"id": "noise_input", "name": "Guitar input noise", "group": "noise", "kind": "input_noise",
     "line": "The noise Core records at the guitar input, with nothing playing",
     "components": ["guitar_input", "mains"],
     "exercises": {"guitar_input": "the noise Core records at the guitar input with nothing playing",
                   "mains": "whether the 50 Hz mains hum is at the guitar input"},
     "default": True, "offer": "always", "auto": True, "helper": True,
     "setup": {"lead": "guitar_input", "codec_input": "board", "core_power": "mains"},
     # The known mains case (2026-10-11, tests 2 and 8): 50 Hz at about -55 dBFS with the floor
     # near -50. On batteries the same input read -65.5 with 50 Hz at -84.
     "bars": {"dead_rms_dbfs": -100.0, "hum_hz": [50.0, 100.0, 150.0], "hum_tolerance_hz": 3.0,
              "hum_line_dbfs": -75.0, "mains_case_rms_dbfs": -45.0,
              "mains_case_line50_dbfs": -48.0, "max_hiss_rms_dbfs": -60.0,
              "seconds": 20, "skip_seconds": 2}},
    {"id": "noise_battery", "name": "Pi on a battery", "group": "noise", "kind": "battery",
     "line": "Does the hum follow the Pi's mains adapter?",
     "components": ["mains"],
     "exercises": {"mains": "the 50 Hz hum at the guitar input with the Pi on a battery instead"},
     "default": False, "offer": "after_hum", "auto": True, "helper": True,
     "setup": {"lead": "guitar_input", "codec_input": "board", "core_power": "battery"},
     "bars": {"min_drop_db": 15.0, "hum_tolerance_hz": 3.0, "seconds": 20, "skip_seconds": 2}},
    {"id": "noise_codec", "name": "Codec input on its own", "group": "further", "kind": "codec_only",
     "line": "Is the hiss the guitar input's or the codec's?",
     "components": ["guitar_input", "codec"],
     "exercises": {"guitar_input": "whether the noise drops with the guitar-input board unplugged",
                   "codec": "the codec's own hiss with its input joined to GND"},
     "default": False, "offer": "always", "auto": False, "helper": True,
     "setup": {"codec_input": "grounded"},
     "bars": {"min_drop_db": 6.0, "codec_only_rms_dbfs": -75.0, "tolerance_db": 3.0,
              "seconds": 20, "skip_seconds": 2}},
]

TEST_IDS = [t["id"] for t in TESTS]
NOISE_KINDS = ("output_noise", "input_noise", "battery", "codec_only")


def test(test_id):
    for entry in TESTS:
        if entry["id"] == test_id:
            return entry
    raise KeyError(test_id)


def component(component_id):
    for entry in COMPONENTS:
        if entry["id"] == component_id:
            return entry
    raise KeyError(component_id)


def is_noise(test_id):
    return test(test_id)["kind"] in NOISE_KINDS


def offered(entry, facts):
    """Whether the page lists this benchtest now: the battery test only after hum was found."""
    if entry["offer"] == "after_hum":
        return bool((facts or {}).get("hum"))
    return True


def tests_for_component(component_id, facts):
    """What a click on a block runs: every offered, automatic benchtest that exercises it."""
    return [t["id"] for t in TESTS
            if component_id in t["components"] and t["auto"] and offered(t, facts)]


def ordered(test_ids):
    """The tests asked for, in catalog order, each once."""
    wanted = set(test_ids)
    return [t for t in TEST_IDS if t in wanted]


def setup_steps(current, needed):
    """The sentences to say before a benchtest, or [] when the bench is already where it needs it."""
    if not needed:
        return []
    steps = []
    for fact in SETUP_FACTS:
        if fact not in needed:
            continue
        have = (current or {}).get(fact, SETUP_ASSUMED.get(fact))
        if have != needed[fact]:
            steps.append(SETUP_STEPS[(fact, needed[fact])])
    return steps

# ---------------------------------------------------------------------- results, in one shape


def make_result(test_id, checks, summary, evidence=None, next_step=None, likely=None, facts=None):
    """A pass or fail result. It fails when any check failed, which is the whole rule."""
    entry = test(test_id)
    ok = bool(checks) and all(c["ok"] for c in checks)
    return {"test": test_id, "name": entry["name"], "status": "pass" if ok else "fail",
            "summary": summary, "evidence": evidence, "next": next_step,
            "likely": list(likely or []), "checks": checks, "facts": dict(facts or {})}


def not_run(test_id, summary, evidence=None, facts=None):
    """A benchtest that could not judge anything: it paints no block and no test."""
    entry = test(test_id)
    return {"test": test_id, "name": entry["name"], "status": "not_run",
            "summary": summary, "evidence": evidence, "next": None, "likely": [],
            "checks": [], "facts": dict(facts or {})}


def check(component_id, ok, check_text, said):
    return {"component": component_id, "ok": bool(ok), "check": check_text, "said": said}


HELPER_MISSING = ("Not run: this test needs scripts/benchtest running on your computer. It records "
                  "the audio interface and does the sums, and nothing has heard from it in the last "
                  "minute. Start it on the computer and test again.")

CODEC_FIRST = ("Not started: the codec checks have to pass first. The codec is not answering, so "
               "there is nothing to measure through it.")

# -------------------------------------------------------------------------- health: pedal-diag

#: pedal-diag's findings, mapped onto benchtests and blocks. A finding whose severity is in
#: `fail_on` fails each listed block; any other severity passes them. `signals` names rows of
#: pedal-interface.json whose `check` becomes "what to check next", so a codec fault says the
#: header pin the way you would say it at the bench. A block of a test that no finding speaks to
#: is not listed in the result at all: pedal-diag could not see it, and the page says nothing.
DIAG_ROWS = [
    # Codec: power, I2C, clocks.
    {"key": "codec.i2c_absent", "test": "codec", "components": ["codec_wires", "codec"],
     "check": "Core asks for the codec on its I2C wires (address 0x1a)",
     "signals": ["codec:3V3", "codec:SDA", "codec:SCL"]},
    {"key": "codec.no_card", "test": "codec", "components": ["codec_wires", "codec"],
     "check": "the codec's sound card appears only when its clocks reach Core",
     "signals": ["codec:BCLK", "codec:DACLRC"]},
    {"key": "codec.answers", "test": "codec", "components": ["codec_wires", "codec"],
     "check": "the codec answers on I2C, so its 3V3, SDA and SCL wires are in"},
    {"key": "codec.registers_unreadable", "test": "codec", "components": ["codec_wires"],
     "check": "the codec is on the I2C bus"},
    {"key": "audio.streaming", "test": "codec", "components": ["codec_wires"],
     "check": "the codec's clocks reach Core: the recording side of the sound device runs"},
    {"key": "audio.capture_not_running", "test": "codec", "components": ["codec_wires"],
     "fail_on": ("fail", "warn"),
     "check": "the codec's clocks reach Core: playback runs, so recording should too",
     "signals": ["codec:BCLK", "codec:ADCDAT"]},
    # The sound device and the engine.
    {"key": "audio.streaming", "test": "audio", "components": ["core", "codec"],
     "check": "the engine has the codec's sound device open and streaming"},
    {"key": "audio.engine_down", "test": "audio", "components": ["core"],
     "check": "the sound engine (namchaind) is running on Core"},
    {"key": "audio.closed_with_codec", "test": "audio", "components": ["core"],
     "fail_on": ("fail", "warn"), "check": "the engine holds the codec's sound device open"},
    {"key": "audio.hw_params", "test": "audio", "components": ["core"],
     "fail_on": ("fail", "warn"), "check": "the sound device is open at 48 kHz with 64-frame periods"},
    {"key": "engine.xruns", "test": "audio", "components": ["core"],
     "check": "the engine keeps up with the sound device: no xruns"},
    # The Pico link.
    {"key": "link.session", "test": "link", "components": ["uart_wires", "pico"],
     "check": "Core and the Pico hold a session over the UART wires, with no bad frames"},
    {"key": "link.no_device", "test": "link", "components": ["core"],
     "check": "Core's header UART exists (pedal-uart turns it on at boot)"},
    {"key": "link.no_node", "test": "link", "components": ["core"],
     "check": "Core's header UART has its /dev/ttyAMA0 node"},
    {"key": "link.no_service", "test": "link", "components": ["core"], "fail_on": ("fail", "warn"),
     "check": "the pedal service, which reads the link, answers on Core"},
    {"key": "link.no_session", "test": "link", "components": ["uart_wires"],
     "check": "Core's replies reach the Pico on header pin 8", "signals": ["pico_link:GP1"]},
    {"key": "link.framing", "test": "link", "components": ["uart_wires"],
     "check": "the bytes on the link arrive whole, which needs the ground wire",
     "signals": ["pico_link:GND"]},
    {"key": "link.silent", "test": "link", "components": ["uart_wires", "pico"],
     "check": "the Pico's messages arrive on header pin 10", "signals": ["pico_link:GP0"]},
    {"key": "link.silent_now", "test": "link", "components": ["uart_wires", "pico"],
     "check": "the Pico's messages keep arriving on header pin 10", "signals": ["pico_link:GP0"]},
    # Core itself.
    {"key": "host.thermal", "test": "core", "components": ["core"],
     "check": "Core is below the temperature where it slows itself down"},
    {"key": "host.undervoltage", "test": "core", "components": ["mains"],
     "check": "Core's supply holds its voltage: the low-voltage alarm is off"},
    {"key": "host.memory", "test": "core", "components": ["core"], "check": "Core has memory to spare"},
    {"key": "host.storage", "test": "core", "components": ["core"], "check": "Core's card has space left"},
    {"key": "host.tuning", "test": "core", "components": ["core"],
     "check": "Core's CPU split and clock settings are in force"},
    {"key": "host.rt", "test": "core", "components": ["core"],
     "check": "the engine's sound thread runs at realtime priority"},
    {"key": "host.not_rt", "test": "core", "components": ["core"],
     "check": "the engine's sound thread runs at realtime priority"},
]

#: A block that passes because a finding is absent: the low-voltage alarm only ever speaks up.
DIAG_ABSENT = [
    {"test": "core", "component": "mains", "keys": ["host.undervoltage"],
     "check": "Core's supply holds its voltage: the low-voltage alarm is off",
     "said": "the low-voltage alarm is off"},
]

CODEC_ABSENT_KEYS = ("codec.i2c_absent", "codec.no_card")


def diag_findings(report):
    """pedal-diag's findings, plus the ones this tool reads from its sample itself (xruns)."""
    findings = list((report or {}).get("findings") or [])
    status = ((report or {}).get("sample") or {}).get("engine", {}) or {}
    status = status.get("status") or {}
    issues = status.get("issues") or []
    xrun_issues = [i for i in issues if isinstance(i, dict) and "xrun" in str(i.get("code", ""))]
    if status:
        if xrun_issues:
            findings.append({"severity": "fail", "key": "engine.xruns",
                             "what": "the engine reports xruns: it is missing its deadline",
                             "evidence": "; ".join(str(i.get("message") or i.get("code"))
                                                   for i in xrun_issues[:3]),
                             "likely": ["something else is running on the render cores",
                                        "the rig is heavier than the device can render"],
                             "check": "the engine's issues and its render numbers in pedal-diag"})
        else:
            findings.append({"severity": "ok", "key": "engine.xruns",
                             "what": "the engine reports no xrun issue",
                             "evidence": "xruns counted since it started: %s" % status.get("xruns"),
                             "likely": [], "check": None})
    return findings


def codec_present_from_diag(report):
    """False when pedal-diag says the codec is absent, None when it cannot say."""
    if not report or not isinstance(report.get("findings"), list):
        return None
    for finding in report["findings"]:
        if finding.get("key") in CODEC_ABSENT_KEYS and finding.get("severity") == "fail":
            return False
    return True


def interface_checks(interface, refs):
    """The `check` sentences of pedal-interface.json's rows, in the order asked: `codec:3V3`."""
    out = []
    for ref in refs or []:
        section, _, name = ref.partition(":")
        for row in ((interface or {}).get(section) or {}).get("signals") or []:
            signal = str(row.get("signal", ""))
            if signal == name or signal.startswith(name + " "):
                text = str(row.get("check") or "").strip()
                if text:
                    out.append(_sentence(text))
                break
    return " ".join(out) or None


def evaluate_diag(test_id, report, interface):
    """One health benchtest's result from one pedal-diag report."""
    entry = test(test_id)
    findings = diag_findings(report)
    by_component = {}
    failed = []
    passed = []
    for row in DIAG_ROWS:
        if row["test"] != test_id:
            continue
        for finding in findings:
            if finding.get("key") != row["key"]:
                continue
            bad = finding.get("severity") in row.get("fail_on", ("fail",))
            said = _sentence(finding.get("what") or row["check"])
            for comp in row["components"]:
                by_component.setdefault(comp, []).append(check(comp, not bad, row["check"], said))
            (failed if bad else passed).append((row, finding))
    keys = {f.get("key") for f in findings}
    for row in DIAG_ABSENT:
        if row["test"] == test_id and not keys.intersection(row["keys"]) and findings:
            by_component.setdefault(row["component"], []).append(
                check(row["component"], True, row["check"], _sentence(row["said"])))
    checks = []
    for comp in entry["components"]:
        entries = by_component.get(comp) or []
        if not entries:
            continue
        bad = [e for e in entries if not e["ok"]]
        checks.append(bad[0] if bad else entries[0])
    if not checks:
        return not_run(test_id, "Not run: pedal-diag said nothing about this, so there is "
                                "nothing to judge.")
    facts = {}
    if test_id == "codec":
        facts["codec_present"] = codec_present_from_diag(report) is not False
    if failed:
        row, finding = failed[0]
        next_step = (interface_checks(interface, row.get("signals"))
                     or _sentence(finding.get("check") or "") or None)
        evidence = "; ".join(str(f.get("evidence") or "") for _, f in failed[:3] if f.get("evidence"))
        likely = [str(x) for x in (finding.get("likely") or [])[:3]]
        summary = _sentence(finding.get("what") or row["check"])
        if len(failed) > 1:
            summary += " %d other check(s) failed too." % (len(failed) - 1)
        return make_result(test_id, checks, summary, evidence or None, next_step, likely, facts)
    evidence = "; ".join(str(f.get("evidence") or "") for _, f in passed[:2] if f.get("evidence"))
    return make_result(test_id, checks, entry.get("pass_summary") or "Passed.", evidence or None,
                       None, [], facts)

# ------------------------------------------------------------------------- noise: the analysis
#
# An analysis is what `scripts/codec-noise.py --json` prints on the workstation: dc_offset,
# rms_dbfs (unweighted, 20 Hz-20 kHz), rms_dbfs_a, peak_dbfs, lines_low and lines_high (lists of
# {"hz", "dbfs"}, the largest spectral lines below 1 kHz and from 1 to 20 kHz), seconds,
# sample_rate. A line that is not in lines_low is quieter than every line that is, which is all
# this can say about it: it is treated as absent, never guessed at.


def line_near(analysis, hz, tolerance):
    """The loudest listed line within `tolerance` of `hz`, in dBFS, or None."""
    best = None
    for line in (analysis or {}).get("lines_low") or []:
        try:
            f, level = float(line["hz"]), float(line["dbfs"])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(f - hz) <= tolerance and (best is None or level > best):
            best = level
    return best


def hum_lines(analysis, bars):
    """{50.0: dBFS or None, 100.0: ..., 150.0: ...} for the mains family."""
    return {hz: line_near(analysis, hz, bars["hum_tolerance_hz"]) for hz in bars["hum_hz"]}


def _num(analysis, key):
    value = (analysis or {}).get(key)
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return float(value)
    return None


def _db(value):
    if value is None:
        return "?"
    if value == float("-inf"):
        return "digital silence"
    return "%.1f dBFS" % value


def _hum_text(lines):
    found = ["%g Hz at %s" % (hz, _db(level)) for hz, level in sorted(lines.items()) if level is not None]
    return ", ".join(found) or "no line at 50, 100 or 150 Hz among the loudest"


def _evidence(analysis, lines=None):
    parts = ["unweighted %s" % _db(_num(analysis, "rms_dbfs")),
             "A-weighted %s" % _db(_num(analysis, "rms_dbfs_a")),
             "peak %s" % _db(_num(analysis, "peak_dbfs"))]
    if lines is not None:
        parts.append("mains lines: %s" % _hum_text(lines))
    seconds = _num(analysis, "seconds")
    if seconds:
        parts.append("%.0f s analysed" % seconds)
    return "; ".join(parts)


def classify_output(test_id, analysis):
    """Left or right output: quiet enough, and no mains comb. A fail paints that output."""
    entry = test(test_id)
    bars = entry["bars"]
    out = entry["components"][0]
    side = entry["side"]
    rms = _num(analysis, "rms_dbfs")
    lines = hum_lines(analysis, bars)
    hum = {hz: level for hz, level in lines.items()
           if level is not None and level > bars["max_hum_line_dbfs"]}
    loud = rms is None or rms > bars["max_rms_dbfs"]
    facts = {"rms_dbfs": rms, "hum_lines": {str(k): v for k, v in lines.items()}}
    seconds = _num(analysis, "seconds")
    record = check("interface", True, entry["exercises"]["interface"],
                   "It recorded %.0f s of the %s output." % (seconds, side) if seconds
                   else "It recorded the %s output." % side)
    if not loud and not hum:
        said = "Quiet: %s, against a bar of %.0f dBFS (the bench baseline was %.0f), and no mains hum." % (
            _db(rms), bars["max_rms_dbfs"], bars["baseline_rms_dbfs"])
        return make_result(test_id, [check(out, True, entry["exercises"][out], said), record],
                           "The %s output is quiet: %s, no mains hum." % (side, _db(rms)),
                           _evidence(analysis, lines), None, [], facts)
    problems = []
    if loud:
        problems.append("its noise is %s, above the %.0f dBFS bar (the bench baseline was %.0f)"
                        % (_db(rms), bars["max_rms_dbfs"], bars["baseline_rms_dbfs"]))
    if hum:
        problems.append("there is mains hum on it: %s, louder than the %.0f dBFS bar"
                        % (_hum_text(hum), bars["max_hum_line_dbfs"]))
    said = "The %s output is noisy: %s." % (side, "; and ".join(problems))
    return make_result(
        test_id, [check(out, False, entry["exercises"][out], said), record], said,
        _evidence(analysis, lines),
        "Check the lead from the pedal's %s output to input 1 of the audio interface, then the %s "
        "output board's two wires to the codec (its ground travels with its signal)." % (side, side),
        [], facts)


def classify_input(analysis):
    """The guitar input with nothing playing. Mains hum paints Core's mains power, not the input.

    The input goes red only if it looks dead, if the hum is louder than the recorded mains case,
    or if there is hiss with no hum that is worse than the bar.
    """
    test_id = "noise_input"
    entry = test(test_id)
    bars = entry["bars"]
    rms = _num(analysis, "rms_dbfs")
    lines = hum_lines(analysis, bars)
    line50 = lines.get(50.0)
    loudest_hum = max([v for v in lines.values() if v is not None], default=None)
    hum = loudest_hum is not None and loudest_hum > bars["hum_line_dbfs"]
    facts = {"rms_dbfs": rms, "line50_dbfs": line50, "hum": hum,
             "hum_lines": {str(k): v for k, v in lines.items()}}
    ex_in, ex_mains = entry["exercises"]["guitar_input"], entry["exercises"]["mains"]
    evidence = _evidence(analysis, lines)

    if rms is None or rms <= bars["dead_rms_dbfs"]:
        said = ("The guitar input looks dead: %s, where even a shorted codec input reads about "
                "-74 dBFS." % _db(rms))
        return make_result(test_id, [check("guitar_input", False, ex_in, said)], said, evidence,
                           "Check the guitar input board's wires to the codec (its LIN1 lead and "
                           "ground), then the lead in header pin 38, which carries the codec's "
                           "recording to Core.", [], facts)

    checks = []
    if hum:
        checks.append(check("mains", False, ex_mains,
                            "Mains hum at the guitar input: %s. This is the known hum: it follows "
                            "the Pi's mains adapter." % _hum_text(lines)))
        louder = rms > bars["mains_case_rms_dbfs"] or (
            line50 is not None and line50 > bars["mains_case_line50_dbfs"])
        if louder:
            checks.append(check("guitar_input", False, ex_in,
                                "The hum is louder than the recorded mains case (%s; that case was "
                                "below %.0f dBFS unweighted, with 50 Hz below %.0f), so the mains "
                                "adapter does not explain all of it."
                                % (_db(rms), bars["mains_case_rms_dbfs"],
                                   bars["mains_case_line50_dbfs"])))
            summary = ("Louder hum than the mains adapter alone explains: %s unweighted, 50 Hz at "
                       "%s." % (_db(rms), _db(line50)))
            next_step = ("Check the guitar input board: its ground wire to the codec, and the "
                         "instrument/line switch's wires, which are the input's most sensitive node.")
        else:
            checks.append(check("guitar_input", True, ex_in,
                                "Alive, and its hum is the mains case, not the input's own."))
            summary = ("Mains hum at the guitar input: %s. The hum follows the Pi's mains "
                       "adapter, not the guitar input. The battery test is now offered: it checks "
                       "that by running the Pi from a battery pack." % _hum_text(lines))
            next_step = "Tick \"Pi on a battery\" and test it."
        return make_result(test_id, checks, summary, evidence, next_step, [], facts)

    checks.append(check("mains", True, ex_mains, "No 50 Hz mains hum at the guitar input."))
    if rms > bars["max_hiss_rms_dbfs"]:
        said = ("Hiss with no hum at %s, worse than the %.0f dBFS bar."
                % (_db(rms), bars["max_hiss_rms_dbfs"]))
        checks.append(check("guitar_input", False, ex_in, said))
        return make_result(test_id, checks, said, evidence,
                           "\"Codec input on its own\", under Go further, says whether the hiss is "
                           "the guitar input's or the codec's.", [], facts)
    said = "Quiet: %s, and no mains hum." % _db(rms)
    checks.append(check("guitar_input", True, ex_in, said))
    return make_result(test_id, checks, "The guitar input is quiet: %s, no mains hum." % _db(rms),
                       evidence, None, [], facts)


def classify_battery(analysis, reference_line50):
    """The same input with the Pi on a battery: the 50 Hz line must fall by the bar or more."""
    test_id = "noise_battery"
    entry = test(test_id)
    bars = entry["bars"]
    line50 = line_near(analysis, 50.0, bars["hum_tolerance_hz"])
    if reference_line50 is None:
        return not_run(test_id, "Not run: there is no mains hum reading to compare with. Run "
                                "\"Guitar input noise\" on the mains adapter first.")
    # A line that dropped out of the loudest list is quieter than every listed one; the quietest
    # listed line is then the most this can claim it is at.
    listed = [float(l["dbfs"]) for l in (analysis or {}).get("lines_low") or []
              if isinstance(l, dict) and isinstance(l.get("dbfs"), (int, float))]
    level = line50 if line50 is not None else (min(listed) if listed else None)
    drop = None if level is None else reference_line50 - level
    facts = {"line50_dbfs": line50, "reference_line50_dbfs": reference_line50, "drop_db": drop}
    evidence = "50 Hz on the mains adapter: %s; on the battery: %s%s" % (
        _db(reference_line50), _db(line50) if line50 is not None else
        ("below %s (not among the loudest lines)" % _db(level) if level is not None else "?"),
        "; %s" % _evidence(analysis))
    ex = entry["exercises"]["mains"]
    if drop is not None and drop >= bars["min_drop_db"]:
        said = ("On a battery the 50 Hz hum is %.0f dB quieter: the hum comes in through the Pi's "
                "mains adapter, and the pedal is quiet without it." % drop)
        return make_result(test_id, [check("mains", True, ex, said)], said, evidence, None, [], facts)
    said = ("On a battery the 50 Hz hum fell by only %s, less than the %.0f dB bar: the mains "
            "adapter is not the whole cause." % ("%.0f dB" % drop if drop is not None else "an "
                                                 "unknown amount", bars["min_drop_db"]))
    return make_result(test_id, [check("mains", False, ex, said)], said, evidence,
                       "Check what else is plugged in: the computer's charger, the audio "
                       "interface's own supply, and any Debug Probe joining the computer to the pedal.",
                       [], facts)


def classify_codec_only(analysis, reference_rms):
    """The codec's input joined to GND. A drop of the bar or more blames the guitar input."""
    test_id = "noise_codec"
    entry = test(test_id)
    bars = entry["bars"]
    rms = _num(analysis, "rms_dbfs")
    facts = {"rms_dbfs": rms, "reference_rms_dbfs": reference_rms}
    evidence = _evidence(analysis)
    checks = []
    summary = []
    if reference_rms is not None and rms is not None:
        drop = reference_rms - rms
        facts["drop_db"] = drop
        evidence += "; with the guitar input board it was %s" % _db(reference_rms)
        if drop >= bars["min_drop_db"]:
            said = ("The noise fell by %.0f dB with the guitar-input board unplugged: the guitar "
                    "input is the part that failed." % drop)
            checks.append(check("guitar_input", False, entry["exercises"]["guitar_input"], said))
        else:
            said = ("The noise stayed within %.0f dB of the guitar input's reading: the guitar "
                    "input is cleared." % bars["min_drop_db"])
            checks.append(check("guitar_input", True, entry["exercises"]["guitar_input"], said))
        summary.append(said)
    limit = bars["codec_only_rms_dbfs"] + bars["tolerance_db"]
    codec_ok = rms is not None and rms <= limit
    said = ("The codec's own hiss is %s, against the %.0f dBFS codec-only figure from the "
            "2026-10-11 log." % (_db(rms), bars["codec_only_rms_dbfs"]))
    checks.append(check("codec", codec_ok, entry["exercises"]["codec"], said))
    summary.append(said)
    next_step = None
    if not codec_ok:
        next_step = ("Check the codec's supplies: 3.3 V at its 3V3 pin and 5 V at VIN, and both "
                     "ground wires from the header.")
    elif any(not c["ok"] for c in checks):
        next_step = ("Check the guitar input board: its ground wire to the codec, and the "
                     "instrument/line switch's wires.")
    return make_result(test_id, checks, " ".join(summary), evidence, next_step, [], facts)


def probe_result(found):
    """The helper's answer to "is the Debug Probe's USB on this computer?"."""
    entry = test("probe")
    ex = entry["exercises"]["probe"]
    if found and found.get("present"):
        where = ", ".join(x for x in (
            "serial %s" % found["serial"] if found.get("serial") else "",
            "port %s" % found["port"] if found.get("port") else "") if x)
        said = "The Debug Probe's USB is on this computer%s." % (" (%s)" % where if where else "")
        return make_result("probe", [check("probe", True, ex, said)], said, where or None)
    said = "The Debug Probe's USB is not on this computer."
    return make_result("probe", [check("probe", False, ex, said)], said, None,
                       "Plug the Debug Probe's USB into the computer running scripts/benchtest. "
                       "Its other lead goes to the Pico or to Core's debug header.")


def _sentence(text):
    text = str(text or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."

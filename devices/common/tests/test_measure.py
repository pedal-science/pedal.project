"""pedal-measure: what it chooses to measure, and when it refuses (P4).

The tool itself is `rootfs/usr/local/sbin/pedal-measure`, a root oneshot beside `pedal-diag`. What
matters and can be tested without a board is the *decision*: which row is worth measuring, and whether
this is a moment to spend an inactive core at all. The measurement itself is the bench's, and its own
tests are namchain's.
"""
import importlib.machinery
import importlib.util
import os
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TOOL_PATH = HERE.parent / "rootfs/usr/local/sbin/pedal-measure"

# What `python3-minimal` on vip has, as in test_diag.py: an import outside this list would fail on the
# host rather than here, which is the point of checking.
ALLOWED_IMPORTS = {"argparse", "hashlib", "json", "os", "re", "subprocess", "sys"}


def load_tool():
    loader = importlib.machinery.SourceFileLoader("pedal_measure", str(TOOL_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


measure = load_tool()


def status(**over):
    base = {"state": "running", "xruns": 0, "render": {"over_deadline": 0},
            "cost": {"cost": 0.41, "headroom": 0.8}, "warm": {"cores": [1, 2], "enabled": True},
            "issues": []}
    for key, value in over.items():
        base[key] = value
    return base


def issue(row, reference, code="cost_unknown"):
    return {"code": code, "row": row, "reference": reference, "chain": "one", "node": "n"}


class Worklist(unittest.TestCase):
    def test_rows_are_deduplicated_and_counted(self):
        rows = measure.worklist(status(issues=[issue("NAM.WaveNet.full", "/models/a.nam"),
                                               issue("NAM.WaveNet.full", "/models/b.nam"),
                                               issue("IR.8192", "/irs/c.wav"),
                                               {"code": "model_slimmed", "row": "NAM.WaveNet.lite"}]))
        self.assertEqual([row["row"] for row in rows], ["IR.8192", "NAM.WaveNet.full"])
        self.assertEqual(rows[1]["count"], 2)
        # The first reference wins: any file of the right kind measures the same row.
        self.assertEqual(rows[1]["reference"], "/models/a.nam")

    def test_a_measured_rig_has_nothing_to_do(self):
        self.assertEqual(measure.worklist(status()), [])


class Happy(unittest.TestCase):
    def test_a_quiet_pedal_is_a_moment_to_measure(self):
        ok, why = measure.happy(status())
        self.assertTrue(ok, why)

    def test_xruns_stop_it(self):
        ok, why = measure.happy(status(xruns=3))
        self.assertFalse(ok)
        self.assertIn("xruns", why)

    def test_blocks_over_the_deadline_stop_it(self):
        ok, why = measure.happy(status(render={"over_deadline": 2}))
        self.assertFalse(ok)
        self.assertIn("over the deadline", why)

    def test_the_warm_failsafe_stops_it(self):
        # The failsafe holds when the audible rig is already missing deadlines with a warm document
        # beside it: that pedal has no inactive core to spare (T5's own finding).
        ok, why = measure.happy(status(warm={"cores": [1, 2], "pressure_holding": True}))
        self.assertFalse(ok)
        self.assertIn("failsafe", why)

    def test_an_audible_rig_over_the_headroom_stops_it(self):
        ok, why = measure.happy(status(cost={"cost": 0.85, "headroom": 0.8}))
        self.assertFalse(ok)
        self.assertIn("headroom", why)


class TheInput(unittest.TestCase):
    """A row measured with a different signal is not the same row (2026-10-09)."""

    def _file(self, data=b"signal"):
        import tempfile
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(data)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_the_declared_input_matches(self):
        import hashlib
        path = self._file()
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        ok, why = measure.input_matches({"input": {"file": "guitar-di.wav", "bytes": 6,
                                                   "sha256": digest}}, path)
        self.assertTrue(ok, why)

    def test_another_signal_is_refused(self):
        path = self._file(b"something else")
        ok, why = measure.input_matches({"input": {"file": "guitar-di.wav", "bytes": 6,
                                                   "sha256": "0" * 64}}, path)
        self.assertFalse(ok)
        self.assertIn("not the input this table was measured with", why)

    def test_a_table_that_says_nothing_is_not_a_refusal(self):
        # Every table measured before the field existed: all of them measure-core's guitar-di.wav.
        ok, why = measure.input_matches({}, self._file())
        self.assertTrue(ok)
        self.assertIn("does not say", why)


class TheCommand(unittest.TestCase):
    def test_a_model_row_measures_a_model(self):
        args = type("A", (), {"input": "/i.wav", "seconds": 30.0})()
        command = measure.bench_command("NAM.WaveNet.full", "/models/a.nam", args, 2)
        self.assertIn("--unit", command)
        self.assertIn("nam", command)
        self.assertIn("/models/a.nam", command)
        self.assertIn("2", command)

    def test_an_ir_row_carries_its_tap_count(self):
        args = type("A", (), {"input": "/i.wav", "seconds": 30.0})()
        command = measure.bench_command("IR.8192", "/irs/c.wav", args, 2)
        self.assertIn("--taps", command)
        self.assertIn("8192", command)

    def test_a_row_it_does_not_know_is_refused_rather_than_guessed(self):
        args = type("A", (), {"input": "/i.wav", "seconds": 30.0})()
        self.assertIsNone(measure.bench_command("unknown.NAM", "/models/a.nam", args, 2))


class TheMeasuringCore(unittest.TestCase):
    def test_the_second_warm_core_is_the_one_a_warm_document_is_not_on(self):
        self.assertEqual(measure.measure_cpu(status()), 2)

    def test_a_device_with_one_warm_core_falls_back(self):
        self.assertEqual(measure.measure_cpu(status(warm={"cores": [1]})), 2)


class Imports(unittest.TestCase):
    def test_the_tool_only_imports_what_the_host_has(self):
        # The same promise test_diag.py makes: the Core host's python3 is `python3-minimal`, so an
        # import outside this list would fail on the host rather than here.
        source = TOOL_PATH.read_text()
        imported = set(re.findall(r"^import (\w+)", source, re.MULTILINE))
        imported |= set(re.findall(r"^from (\w+)", source, re.MULTILINE))
        self.assertEqual(imported - ALLOWED_IMPORTS, set())


if __name__ == "__main__":
    unittest.main()

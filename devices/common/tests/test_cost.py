"""The cost table: devices/common/cost-check against cost.schema.json and its invariants.

The table is one file per Core device (P2 of
docs/managing-processing-power-and-optimising-for-fast-switching.md), installed at
/etc/namchain/cost.json, where namchaind reads it. cost-check is what `devices/<host>/check` runs, so
these are the tests for the claim that a bad table fails the device check: missing rows' provenance,
a cost that is not 1/n, an `unknown` that is cheaper than a measured row (D8), and a table measured
against another engine.
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
COST_CHECK = HERE / "cost-check"
SCHEMA = HERE / "cost.schema.json"


def table(**overrides):
    """A valid vip table, before the overrides that make each test's point."""
    doc = {
        "host": "vip",
        "measured": "2026-10-07T12:00:00Z",
        "engine_commit": "c0e3f37",
        "kernel": "7.0.0-1017-raspi-realtime-numaemu1-trimmed",
        "rate": 48000,
        "quantum": 64,
        "deadline_us": 1333.333,
        "headroom": 0.8,
        "bar": "p99 under the deadline and zero overruns, paced offline, confirmed live",
        "core_percent": {"NAM": {"WaveNet": {"full": 0.125, "lite": 0.0333}}, "IR": {}, "node": {}},
        "unknown": {"NAM": 0.25, "IR": 0.1, "node": 0.05},
        "sources": {
            "NAM.WaveNet.full": {"n": 8, "p99_at_n": 0.891, "overruns_at_n": 0,
                                 "p99_at_n_plus_1": 1.129, "overruns_at_n_plus_1": 0},
            "NAM.WaveNet.lite": {"n": 30, "p99_at_n": 0.974, "overruns_at_n": 0,
                                 "p99_at_n_plus_1": 1.412, "overruns_at_n_plus_1": 0},
        },
    }
    doc.update(overrides)
    return doc


class CostCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def run_check(self, doc, *args):
        path = pathlib.Path(self.dir.name) / "cost.json"
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc, indent=2))
        return subprocess.run([sys.executable, str(COST_CHECK), str(path), *args],
                              capture_output=True, text=True)

    def assert_fails(self, result, *fragments):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for fragment in fragments:
            self.assertIn(fragment, result.stdout, result.stdout)

    def test_a_good_table_passes(self):
        result = self.run_check(table())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("cost.json host vip", result.stdout)
        self.assertIn("2 row(s): NAM 2, IR 0, node 0", result.stdout)

    def test_the_engine_commit_is_compared_with_what_the_device_runs(self):
        result = self.run_check(table(), "--engine-commit", "c0e3f37")
        self.assertEqual(result.returncode, 0, result.stdout)
        result = self.run_check(table(), "--engine-commit", "1c1d1cc")
        self.assert_fails(result, "engine_commit", "but the device runs 1c1d1cc")
        result = self.run_check(table(), "--kernel", "7.0.0-1017-raspi-realtime")
        self.assert_fails(result, "kernel", "but the device runs 7.0.0-1017-raspi-realtime")

    def test_the_host_must_be_the_device_the_table_is_in(self):
        result = self.run_check(table(host="piv"), "--host", "vip")
        self.assert_fails(result, "host", "not the device this table is in")

    def test_a_missing_provenance_fails(self):
        doc = table()
        del doc["sources"]["NAM.WaveNet.lite"]
        self.assert_fails(self.run_check(doc), "sources.NAM.WaveNet.lite", "no provenance")

    def test_a_cost_that_is_not_one_over_n_fails(self):
        doc = table()
        doc["core_percent"]["NAM"]["WaveNet"]["full"] = 0.2
        self.assert_fails(self.run_check(doc), "NAM.WaveNet.full", "is not 1/n for n=8")

    def test_a_row_that_fitted_is_not_the_largest(self):
        doc = table()
        doc["sources"]["NAM.WaveNet.full"]["p99_at_n_plus_1"] = 0.9
        self.assert_fails(self.run_check(doc), "is not the largest that fits")

    def test_a_row_that_fitted_is_not_the_largest_even_with_overruns(self):
        # The bar is p99 (see the note in namchain's namchain-warm-bench.cpp): a rare late block does
        # not decide n, so a row whose n+1 is under the deadline on p99 is a row that stopped early,
        # however many overruns n+1 happened to have.
        doc = table()
        doc["sources"]["NAM.WaveNet.full"]["p99_at_n_plus_1"] = 0.4
        doc["sources"]["NAM.WaveNet.full"]["overruns_at_n_plus_1"] = 1
        self.assert_fails(self.run_check(doc), "n+1 fitted too")

    def test_the_overrun_count_is_recorded_not_required(self):
        # A row whose own point had late blocks is still the row: the overruns are the cliff's shape.
        doc = table()
        doc["sources"]["NAM.WaveNet.full"]["overruns_at_n"] = 5
        self.assertEqual(self.run_check(doc).returncode, 0)

    def test_a_row_that_missed_at_n_fails(self):
        doc = table()
        doc["sources"]["NAM.WaveNet.full"]["p99_at_n"] = 1.2
        self.assert_fails(self.run_check(doc), "did not fit")

    def test_an_upper_bound_must_say_what_bounded_it(self):
        doc = table()
        doc["sources"]["NAM.WaveNet.full"]["at_most"] = True
        self.assert_fails(self.run_check(doc), "at_most needs a why")
        doc["sources"]["NAM.WaveNet.full"]["why"] = "--max 128 reached without a miss"
        self.assertEqual(self.run_check(doc).returncode, 0)

    def test_unknown_may_not_be_cheaper_than_a_measured_row(self):
        # D8: an unmeasured unit is treated as expensive, never as free. A table whose `unknown` is
        # below a measured row would admit the unmeasured unit as the cheap one.
        doc = table()
        doc["unknown"]["NAM"] = 0.1
        self.assert_fails(self.run_check(doc), "unknown.NAM", "D8")

    def test_a_provenance_for_a_row_that_is_not_there_fails(self):
        doc = table()
        doc["sources"]["IR.8192"] = {"n": 40, "p99_at_n": 0.9}
        self.assert_fails(self.run_check(doc), "sources.IR.8192", "not in core_percent")

    def test_an_ir_row_is_keyed_by_its_taps(self):
        doc = table()
        doc["core_percent"]["IR"] = {"8192": 0.025, "512": 0.002}
        doc["sources"]["IR.8192"] = {"n": 40, "p99_at_n": 0.9, "overruns_at_n": 0,
                                     "p99_at_n_plus_1": 1.05, "overruns_at_n_plus_1": 0}
        doc["sources"]["IR.512"] = {"n": 500, "p99_at_n": 0.6, "overruns_at_n": 0,
                                    "p99_at_n_plus_1": 1.02, "overruns_at_n_plus_1": 0}
        doc["unknown"]["IR"] = 0.1
        self.assertEqual(self.run_check(doc).returncode, 0)
        doc["core_percent"]["IR"]["999999"] = 0.001
        doc["sources"]["IR.999999"] = {"n": 1000, "p99_at_n": 0.5}
        self.assert_fails(self.run_check(doc), "IR.999999")  # nothing above 8192 is measured

    def test_the_deadline_is_quantum_over_rate(self):
        self.assert_fails(self.run_check(table(deadline_us=1000.0)), "deadline_us", "is not quantum/rate")
        self.assertEqual(self.run_check(table(quantum=32, deadline_us=666.667)).returncode, 0)

    def test_a_headroom_is_not_a_fit_point(self):
        self.assert_fails(self.run_check(table(headroom=1.0)), "headroom", "D3")

    def test_the_schema_is_the_one_that_is_checked(self):
        # A key the schema does not know is a table that has drifted from the format, not a table
        # that is silently carrying something the engine will not read.
        self.assert_fails(self.run_check(table(surprise=1)), "surprise", "not a key of this table")
        self.assert_fails(self.run_check("not json at all"), "is not JSON")
        self.assertTrue(SCHEMA.exists())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""scripts/fleet: the files are valid, a combination is judged on its parts, and proof goes stale."""

import datetime
import importlib.machinery
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "fleet"
loader = importlib.machinery.SourceFileLoader("fleet_tool", str(SCRIPT))
spec = importlib.util.spec_from_loader("fleet_tool", loader)
fleet_tool = importlib.util.module_from_spec(spec)
loader.exec_module(fleet_tool)


class Files(unittest.TestCase):
    def test_the_committed_fleet_is_valid(self):
        _, errors = fleet_tool.load()
        self.assertEqual(errors, [])

    def test_the_schema_refuses_an_undeclared_field(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}}}
        self.assertEqual(fleet_tool.validate({"id": "a"}, schema), [])
        self.assertTrue(fleet_tool.validate({"id": "a", "address": "x"}, schema))

    def test_the_schema_checks_types_and_enums(self):
        self.assertTrue(fleet_tool.validate(3, {"type": "string"}))
        self.assertTrue(fleet_tool.validate("c", {"enum": ["a", "b"]}))


class Combinations(unittest.TestCase):
    def setUp(self):
        self.fleet, _ = fleet_tool.load()

    def problems(self, build, core):
        return fleet_tool.combination_problems(self.fleet, self.fleet["builds"][build], core)

    def test_each_build_is_legal_with_its_own_core(self):
        for build in self.fleet["builds"].values():
            self.assertEqual(fleet_tool.combination_problems(self.fleet, build, build["core"]), [], build["id"])

    def test_vip_may_go_in_the_console(self):
        self.assertEqual(self.problems("console", "vip"), [])

    def test_pro_is_refused_by_the_box_with_reasons(self):
        problems = " ".join(self.problems("box", "pro"))
        self.assertIn("does not fit", problems)
        self.assertIn("i2s", problems)


class Ladder(unittest.TestCase):
    TODAY = datetime.date(2026, 11, 3)

    def rung(self, key, date, result="pass", runs=()):
        proofs = [{"rung": key, "date": date, "result": result, "evidence": "x", "note": "y"}] if date else []
        ladder = fleet_tool.rung_ladder(proofs, list(runs), self.TODAY)
        return next(r for r in ladder if r["key"] == key)

    def test_nothing_recorded_is_not_a_pass(self):
        self.assertEqual(self.rung("device", None)["age"], "none")

    def test_a_rung_ages(self):
        self.assertEqual(self.rung("install", "2026-10-30")["age"], "fresh")   # limit 45 days
        self.assertEqual(self.rung("install", "2026-09-01")["age"], "stale")
        self.assertEqual(self.rung("install", "2026-01-01")["age"], "expired")

    def test_played_shows_its_age_but_never_expires(self):
        rung = self.rung("played", "2025-01-01")
        self.assertEqual(rung["age"], "fresh")
        self.assertGreater(rung["days"], 600)

    def test_code_comes_from_ci_and_fails_when_any_does(self):
        good = {"workflow": "ci", "conclusion": "success", "date": "2026-11-02"}
        bad = {"workflow": "tsan", "conclusion": "failure", "date": "2026-11-03"}
        self.assertEqual(self.rung("code", None, runs=[good])["result"], "pass")
        self.assertEqual(self.rung("code", None, runs=[good, bad])["result"], "fail")


if __name__ == "__main__":
    unittest.main()

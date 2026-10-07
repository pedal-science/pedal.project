"""The bank, the position and the trigger→action tables (docs/pedal-service.md)."""
import sys
import pathlib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import mapping  # noqa: E402


class LibraryBank(unittest.TestCase):
    """With no bank.json the bank is the library by name, eight to a bank (R15)."""

    def setUp(self):
        self.logs = []
        self.rigs = [f"rig{i:02d}" for i in range(1, 11)]
        self.m = mapping.Mapping(self.rigs, log=self.logs.append)

    def test_two_banks_of_eight_and_two(self):
        self.assertEqual(len(self.m.banks), 2)
        self.assertEqual(len(self.m.banks[0]), 8)
        self.assertEqual(self.m.banks[1], ["rig09", "rig10"])
        # No bank.json and no engine yet: there is no position until the engine says which rig
        # is running (R3), and the first press then lands on the first rig.
        self.assertIsNone(self.m.current_name())
        self.m.note_rig("rig01")
        self.assertEqual(self.m.current_name(), "rig01")

    def test_rig_up_wraps_within_the_bank(self):
        self.m.note_rig("rig01")
        for _ in range(7):
            self.m.action("rig_up")
        self.assertEqual(self.m.current_name(), "rig08")
        self.assertEqual(self.m.action("rig_up")["rig"], "rig01")

    def test_rig_down_wraps_backwards(self):
        self.m.note_rig("rig01")
        self.assertEqual(self.m.action("rig_down")["rig"], "rig08")

    def test_rig_select_within_the_bank(self):
        self.assertEqual(self.m.action("rig_select", 3)["rig"], "rig04")
        self.assertIsNone(self.m.action("rig_select", 99))
        self.assertEqual(self.m.current_name(), "rig04")

    def test_bank_up_lands_on_the_first_rig(self):
        self.assertEqual(self.m.action("bank_up")["rig"], "rig09")
        self.assertEqual(self.m.bank, 1)
        self.assertEqual(self.m.action("bank_up")["rig"], "rig01")       # wraps
        self.assertEqual(self.m.action("bank_select", 1)["rig"], "rig09")

    def test_bypass_mirrors_and_calls_nothing(self):
        self.assertEqual(self.m.action("bypass_toggle"), {"action": "bypass", "on": True})
        self.assertEqual(self.m.action("bypass_set", 0), {"action": "bypass", "on": False})

    def test_unknown_kind_is_none(self):
        self.assertIsNone(self.m.action("expression", 1))


class BankFile(unittest.TestCase):
    def test_a_written_bank_wins_and_unknown_rigs_are_dropped(self):
        m = mapping.Mapping(["a", "b", "c", "d"],
                            bank={"banks": [[ "c", "a", "nope" ], ["d"]], "bank": 0, "rig": 1})
        self.assertEqual(m.banks, [["c", "a"], ["d"]])
        self.assertEqual(m.current_name(), "a")

    def test_a_broken_bank_file_falls_back_to_the_library(self):
        logs = []
        m = mapping.Mapping(["a", "b"], bank={"banks": "nonsense"}, log=logs.append)
        self.assertEqual(m.banks, [["a", "b"]])
        self.assertTrue(any("bank.json" in line for line in logs))


class Position(unittest.TestCase):
    def test_note_rig_finds_the_position_by_name(self):
        m = mapping.Mapping(["a", "b", "c"])
        self.assertEqual(m.note_rig("c"), 2)
        self.assertEqual(m.current_name(), "c")

    def test_a_rig_in_no_bank_keeps_the_hint(self):
        m = mapping.Mapping(["a", "b"], bank={"banks": [["a"]], "bank": 0, "rig": 0})
        self.assertEqual(m.note_rig("from-the-app"), -1)
        self.assertEqual(m.action("rig_down")["rig"], "a")     # steps from the hint

    def test_position_state_round_trips(self):
        m = mapping.Mapping(["a", "b", "c"])
        m.action("rig_select", 2)
        self.assertEqual(m.position_state()["rig"], 2)


class Map(unittest.TestCase):
    def test_the_footswitches_default_map(self):
        m = mapping.Mapping(["a", "b", "c"])
        m.note_rig("a")                                         # a position to step from
        self.assertEqual(m.action("cc", 81)["rig"], "b")        # rig_up
        self.assertEqual(m.action("cc", 80)["rig"], "a")        # rig_down
        self.assertIsNone(m.action("cc", 82))                   # assignable, unassigned

    def test_pc_by_name_moves_the_bank_window(self):
        m = mapping.Mapping([f"r{i}" for i in range(1, 11)],
                            midi_map={"pc": {"1": "r9"}})
        self.assertEqual(m.action("pc", 1)["rig"], "r9")
        self.assertEqual(m.bank, 1)

    def test_an_entry_may_name_another_kind(self):
        m = mapping.Mapping(["a", "b"], midi_map={"cc": {"20": {"action": "bypass_toggle"}}})
        self.assertEqual(m.action("cc", 20), {"action": "bypass", "on": True})

    def test_an_entry_naming_nothing_is_logged_not_raised(self):
        logs = []
        m = mapping.Mapping(["a"], midi_map={"pc": {"1": "no-such-rig"}}, log=logs.append)
        self.assertIsNone(m.action("pc", 1))
        self.assertTrue(any("no-such-rig" in line for line in logs))

    def test_load_json_survives_a_missing_or_broken_file(self):
        self.assertIsNone(mapping.load_json("/nonexistent/bank.json"))


class Over(unittest.TestCase):
    """The engine's verdicts, and the skip (P5, D9): a rig the engine will not play is not a
    place a press may land, and a rig it has not answered for yet is usable.

    The names are prefixed so they sort into bank order: `Mapping` sorts the library by name,
    so `d-over` is the fourth rig, not the second one written down.
    """

    def setUp(self):
        self.logs = []
        self.rigs = ["a-usable", "b-over", "c-usable", "d-over"]
        self.m = mapping.Mapping(self.rigs, log=self.logs.append)

    def over(self, cost=1.02, headroom=0.8):
        return {"verdict": "over", "cost": cost, "headroom": headroom, "trimmed": True,
                "over": True}

    def test_a_press_lands_past_an_unusable_rig(self):
        self.m.verdicts["b-over"] = self.over()
        self.m.note_rig("a-usable")
        self.assertEqual(self.m.action("rig_up")["rig"], "c-usable")
        self.assertEqual(self.m.rig, 2)
        self.assertTrue(any("b-over" in line for line in self.logs))

    def test_stepping_backwards_skips_too_and_wraps(self):
        self.m.verdicts["d-over"] = self.over()
        self.m.verdicts["b-over"] = self.over()
        self.m.note_rig("a-usable")
        self.assertEqual(self.m.action("rig_down")["rig"], "c-usable")   # past d-over, wrapping
        self.assertEqual(self.m.action("rig_down")["rig"], "a-usable")   # past b-over

    def test_a_bank_where_every_rig_is_unusable_does_nothing(self):
        for rig in self.rigs:
            self.m.verdicts[rig] = self.over()
        self.m.note_rig("a-usable")
        self.assertIsNone(self.m.action("rig_up"))
        self.assertIsNone(self.m.action("rig_down"))
        self.assertEqual(self.m.current_name(), "a-usable")     # nothing moved
        self.assertTrue(any("every rig in bank" in line for line in self.logs))

    def test_a_rig_with_no_verdict_is_usable(self):
        # The engine still refuses a publish it cannot play, so an unasked rig is not the
        # service's to refuse: only "over" skips.
        self.m.verdicts["b-over"] = None
        self.m.note_rig("a-usable")
        self.assertEqual(self.m.action("rig_up")["rig"], "b-over")
        self.m.verdicts["b-over"] = {"verdict": "trimmed", "cost": 0.67, "headroom": 0.8,
                                     "trimmed": True, "over": False}
        self.assertEqual(self.m.action("rig_up")["rig"], "c-usable")

    def test_select_refuses_an_unusable_position(self):
        self.m.verdicts["b-over"] = self.over()
        self.m.note_rig("a-usable")
        self.assertIsNone(self.m.action("rig_select", 1))
        self.assertEqual(self.m.current_name(), "a-usable")
        self.assertTrue(any("b-over" in line for line in self.logs))

    def test_a_bank_whose_rigs_are_all_unusable_moves_nothing(self):
        m = mapping.Mapping(["a", "b", "c", "d"],
                            bank={"banks": [["a", "b"], ["c", "d"]], "bank": 0, "rig": 0},
                            log=self.logs.append)
        for rig in ("c", "d"):
            m.verdicts[rig] = self.over()
        self.assertIsNone(m.action("bank_up"))
        self.assertEqual(m.bank, 1)                    # the window moved: the panel shows it
        self.assertIsNone(m.current_name())            # no position in a bank that cannot play
        self.assertTrue(any("every rig in bank" in line for line in self.logs))

    def test_a_bank_move_lands_on_its_first_usable_rig(self):
        m = mapping.Mapping(["a", "b", "c", "d"],
                            bank={"banks": [["a", "b"], ["c", "d"]], "bank": 0, "rig": 0})
        m.verdicts["c"] = self.over()
        self.assertEqual(m.action("bank_up")["rig"], "d")

    def test_a_midi_entry_naming_an_unusable_rig_is_refused(self):
        m = mapping.Mapping(["a", "b"], midi_map={"pc": {"1": "b"}}, log=self.logs.append)
        m.verdicts["b"] = self.over()
        self.assertIsNone(m.action("pc", 1))
        m.verdicts["b"] = {"verdict": "fits", "cost": 0.4, "headroom": 0.8, "trimmed": False,
                           "over": False}
        self.assertEqual(m.action("pc", 1)["rig"], "b")

    def test_first_usable_names_the_position_a_bank_move_gets(self):
        self.m.verdicts["a-usable"] = self.over()
        self.assertEqual(self.m.first_usable(), 1)


if __name__ == "__main__":
    unittest.main()

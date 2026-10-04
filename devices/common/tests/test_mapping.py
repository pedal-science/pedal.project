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


if __name__ == "__main__":
    unittest.main()

"""Which pedal this is: made once, kept, renamed, and never lost to a bad file."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import identity  # noqa: E402


class Identity(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name
        self.path = os.path.join(self.root, "pedal.json")
        self.lines = []

    def make(self):
        return identity.Identity(self.root, self.lines.append, hostname="vip")

    def test_the_first_start_makes_one_and_says_so(self):
        made = self.make()
        self.assertEqual(uuid.UUID(made.id).version, 4)
        self.assertEqual(made.name, "vip")
        with open(self.path) as handle:
            stored = json.load(handle)
        self.assertEqual(stored["id"], made.id)
        self.assertRegex(stored["created"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertTrue(any("new" in line for line in self.lines))

    def test_a_restart_is_the_same_pedal(self):
        self.assertEqual(self.make().id, self.make().id)

    def test_a_rename_lasts_and_keeps_the_id(self):
        made = self.make()
        made.rename("  Stage left ")
        again = self.make()
        self.assertEqual(again.name, "Stage left")
        self.assertEqual(again.id, made.id)

    def test_a_bad_name_is_refused_and_changes_nothing(self):
        made = self.make()
        for name in (None, "", "   ", 7, "x" * 65, "a\nb"):
            with self.assertRaises(identity.IdentityError):
                made.rename(name)
        self.assertEqual(self.make().name, "vip")

    def test_a_file_that_cant_be_read_is_moved_aside_not_overwritten(self):
        for broken in ("{not json", "[]", '{"id": "", "name": "x"}'):
            with open(self.path, "w") as handle:
                handle.write(broken)
            made = self.make()
            self.assertEqual(uuid.UUID(made.id).version, 4)
            with open(self.path + ".corrupt") as handle:
                self.assertEqual(handle.read(), broken)

    def test_an_unwritable_directory_still_answers(self):
        blocked = os.path.join(self.root, "blocked")
        with open(blocked, "w"):
            pass                               # a file where the directory should be
        made = identity.Identity(blocked, self.lines.append, hostname="vip")
        self.assertEqual(made.name, "vip")
        self.assertTrue(any("lasts until the next start" in line for line in self.lines))


if __name__ == "__main__":
    unittest.main()

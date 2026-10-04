"""Resume: the save rule, the quiet window, and atomic writes (docs/pedal-service.md)."""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import resume  # noqa: E402


class FakeEngine:
    """Just enough of the engine client: rig.get, and whatever it should fail with."""

    def __init__(self, document=None, error=None):
        self.document = document or {"name": "Crunch Lead", "chains": []}
        self.error = error
        self.calls = 0

    def rig_get(self):
        self.calls += 1
        if self.error:
            raise self.error
        return {"document": self.document}


class ResumeSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.rigs = os.path.join(self.tmp, "library", "rigs")
        self.state = os.path.join(self.tmp, "state")
        self.default = os.path.join(self.tmp, "default-rig.json")
        with open(self.default, "w") as handle:
            handle.write(json.dumps({"name": "Default", "chains": []}))
        self.r = resume.Resume(FakeEngine(), self.rigs, default_rig=self.default,
                               state_root=self.state, owner="does-not-exist")

    def test_seed_writes_last_json_from_the_default(self):
        self.assertEqual(self.r.seed(), 0)
        with open(os.path.join(self.rigs, "last.json")) as handle:
            self.assertEqual(json.load(handle)["name"], "Default")
        self.assertTrue(os.path.isdir(self.state))

    def test_seed_never_overwrites_a_saved_rig(self):
        self.r.seed()
        path = os.path.join(self.rigs, "last.json")
        with open(path, "w") as handle:
            handle.write(json.dumps({"name": "Mine"}))
        self.r.seed()
        with open(path) as handle:
            self.assertEqual(json.load(handle)["name"], "Mine")


class SaveRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.engine = FakeEngine()
        self.r = resume.Resume(self.engine, self.tmp, default_rig="/dev/null", settle_s=2.0,
                               state_root=os.path.join(self.tmp, "state"))
        self.path = os.path.join(self.tmp, "last.json")

    def test_nothing_is_written_while_the_engine_is_moving(self):
        self.r.tick(0, {"generation": 1, "params_applied": 0})
        self.r.tick(1000, {"generation": 1, "params_applied": 5})
        self.r.tick(2000, {"generation": 2, "params_applied": 5})
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(self.engine.calls, 0)

    def test_one_write_after_the_quiet_window(self):
        self.r.tick(0, {"generation": 1, "params_applied": 0})
        self.r.tick(1000, {"generation": 1, "params_applied": 0})   # inside the window
        self.assertFalse(os.path.exists(self.path))
        self.r.tick(3000, {"generation": 1, "params_applied": 0})   # still, and settled
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(self.engine.calls, 1)
        # ... and a second pass with nothing changed does not write again.
        self.r.tick(4000, {"generation": 1, "params_applied": 0})
        self.assertEqual(self.engine.calls, 1)

    def test_a_changed_document_is_written_and_the_previous_kept(self):
        self.r.tick(0, {"generation": 1, "params_applied": 0})
        self.r.tick(3000, {"generation": 1, "params_applied": 0})
        first = open(self.path).read()
        self.engine.document = {"name": "Something Else", "chains": []}
        self.r.tick(5000, {"generation": 2, "params_applied": 0})
        self.r.tick(8000, {"generation": 2, "params_applied": 0})
        self.assertNotEqual(open(self.path).read(), first)
        prev = os.path.join(self.tmp, "last.prev.json")
        self.assertTrue(os.path.exists(prev))
        self.assertEqual(json.loads(open(prev).read())["name"], "Crunch Lead")

    def test_a_rig_load_is_saved_even_though_the_counters_do_not_move(self):
        # Measured against namchaind 2026-10-02: rig.load moves `rig`/`rig_name` and leaves
        # generation and params_applied alone. Watching the counters alone would never save a
        # footswitch's switch.
        quiet = {"generation": 1, "params_applied": 0, "rig": "/rigs/One.json",
                 "rig_name": "One", "rig_source": "file"}
        self.r.tick(0, quiet)
        self.r.tick(3000, quiet)
        self.assertEqual(json.load(open(self.path))["name"], "Crunch Lead")
        loaded = dict(quiet, rig="/rigs/Two.json", rig_name="Two")
        self.engine.document = {"name": "Two", "chains": []}
        self.r.tick(4000, loaded)
        self.r.tick(7000, loaded)
        self.assertEqual(json.load(open(self.path))["name"], "Two")

    def test_an_engine_failure_does_not_raise_or_write(self):
        self.r.engine = FakeEngine(error=RuntimeError("engine unreachable"))
        self.r.tick(0, {"generation": 1, "params_applied": 0})
        self.r.tick(3000, {"generation": 1, "params_applied": 0})
        self.assertFalse(os.path.exists(self.path))

    def test_no_temporary_file_is_left_behind(self):
        self.r.tick(0, {"generation": 1, "params_applied": 0})
        self.r.tick(3000, {"generation": 1, "params_applied": 0})
        self.assertFalse(os.path.exists(self.path + ".tmp"))


if __name__ == "__main__":
    unittest.main()

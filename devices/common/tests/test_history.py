"""Undo's deltas and limits."""

import json
import os
import random
import tempfile
import unittest

from pedald import history


def doc(gains, extra_chain=False, name="Rig"):
    nodes = [{"id": f"n{i}", "type": "nc.gain", "gain_db": gain} for i, gain in enumerate(gains)]
    chains = [{"id": "a", "nodes": nodes, "connections": []}]
    if extra_chain:
        chains.append({"id": "b", "nodes": [{"id": "x", "type": "nc.gain"}], "connections": []})
    return {"name": name, "chains": chains}


class Deltas(unittest.TestCase):
    def roundtrip(self, a, b):
        change = history.delta(a, b)
        self.assertEqual(history.apply(a, change), b)
        self.assertEqual(history.apply(b, change, forwards=False), a)
        return change

    def test_the_same_document_is_no_delta(self):
        self.assertEqual(history.delta(doc([1]), doc([1])), {})

    def test_a_value(self):
        change = self.roundtrip(doc([1, 2]), doc([1, 3]))
        self.assertEqual(list(change["chains"]["a"]["nodes"]), ["n1"])

    def test_a_node_added_removed_and_moved(self):
        self.roundtrip(doc([1]), doc([1, 2]))
        self.roundtrip(doc([1, 2]), doc([1]))
        a = doc([1, 2, 3])
        b = doc([1, 2, 3])
        b["chains"][0]["nodes"].reverse()
        self.roundtrip(a, b)

    def test_a_chain_added_and_removed(self):
        self.roundtrip(doc([1]), doc([1], extra_chain=True))
        self.roundtrip(doc([1], extra_chain=True), doc([1]))

    def test_connections_and_meta_and_a_field(self):
        a, b = doc([1]), doc([1])
        b["chains"][0]["connections"] = [{"from": "n0", "to": "n0"}]
        b["meta"] = {"layout": 1}
        b["chains"][0]["meta"] = {"source": "guitar"}
        self.roundtrip(a, b)

    def test_a_bare_graph(self):
        self.roundtrip({"name": "x", "nodes": [{"id": "a"}]}, {"name": "x", "nodes": [{"id": "b"}]})

    def test_at_random(self):
        rng = random.Random(4)
        for _ in range(200):
            a = doc([rng.randint(0, 3) for _ in range(rng.randint(1, 6))], rng.random() < 0.3)
            b = doc([rng.randint(0, 3) for _ in range(rng.randint(1, 6))], rng.random() < 0.3)
            rng.shuffle(b["chains"][0]["nodes"])
            self.roundtrip(a, b)

    def test_the_input_isnt_changed(self):
        a = doc([1])
        before = json.dumps(a)
        history.apply(a, history.delta(a, doc([2])))
        self.assertEqual(json.dumps(a), before)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Steps(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.history = history.History(self.dir.name, clock=self.clock)
        self.history.use("Rig")
        self.key = {("a", "n0", "gain_db")}

    def edit(self, before, after, keys=None, gesture=None, wait=0.2):
        self.clock.now += wait
        self.history.note(doc([before]), doc([after]), keys or self.key, "ljoss", gesture)

    def test_a_run_on_one_control_is_one_step(self):
        self.edit(0, 1)
        self.edit(1, 2)
        self.edit(2, 3)
        self.assertEqual(self.history.counts()["undo"], 1)
        self.assertEqual(self.history.undo(doc([3])), doc([0]))

    def test_a_gap_is_a_second_step(self):
        self.edit(0, 1)
        self.edit(1, 2, wait=2.0)
        self.assertEqual(self.history.counts()["undo"], 2)

    def test_another_control_is_a_second_step(self):
        self.edit(0, 1)
        self.edit(1, 2, keys={("a", "n1", "gain_db")})
        self.assertEqual(self.history.counts()["undo"], 2)

    def test_one_gesture_is_one_step_across_controls_and_time(self):
        self.edit(0, 1, gesture="gesture:1")
        self.edit(1, 2, keys={("a", "n1", "gain_db")}, gesture="gesture:1", wait=5.0)
        self.assertEqual(self.history.counts()["undo"], 1)

    def test_undo_then_redo(self):
        self.edit(0, 1)
        self.assertEqual(self.history.undo(doc([1])), doc([0]))
        self.history.undone()
        self.assertEqual(self.history.counts(), {"undo": 0, "redo": 1})
        self.assertEqual(self.history.redo(doc([0])), doc([1]))
        self.history.redone()
        self.assertEqual(self.history.counts(), {"undo": 1, "redo": 0})

    def test_an_edit_after_undo_clears_redo(self):
        self.edit(0, 1)
        self.history.undo(doc([1]))
        self.history.undone()
        self.edit(0, 5)
        self.assertEqual(self.history.counts()["redo"], 0)

    def test_nothing_to_undo(self):
        self.assertIsNone(self.history.undo(doc([0])))
        self.assertIsNone(self.history.redo(doc([0])))

    def test_an_edit_that_ended_where_it_began_is_no_step(self):
        self.edit(0, 1)
        self.edit(1, 0)
        self.history.close()
        self.assertEqual(self.history.counts()["undo"], 0)

    def test_it_survives_a_restart(self):
        self.edit(0, 1)
        self.history.save()
        again = history.History(self.dir.name)
        again.use("Rig")
        self.assertEqual(again.undo(doc([1])), doc([0]))

    def test_a_listing(self):
        self.edit(0, 1)
        listing = self.history.listing()
        self.assertEqual(listing["undo"][0]["client"], "ljoss")
        self.assertEqual(listing["undo"][0]["keys"], [["a", "n0", "gain_db"]])
        self.assertNotIn("delta", listing["undo"][0])

    def test_rename_and_delete(self):
        self.edit(0, 1)
        self.history.save()
        self.history.renamed("Rig", "Other")
        self.assertEqual(os.listdir(self.dir.name), ["Other.json"])
        self.assertEqual(self.history.rig, "Other")
        self.history.deleted("Other")
        self.assertEqual(os.listdir(self.dir.name), [])

    def test_a_bad_file_is_only_lost_history(self):
        with open(os.path.join(self.dir.name, "Bad.json"), "w") as handle:
            handle.write("{nope")
        self.history.use("Bad")
        self.assertEqual(self.history.counts()["undo"], 0)


class Limits(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.history = history.History(self.dir.name, clock=self.clock)
        self.history.use("Rig")

    def steps(self, count, node_size=0):
        for index in range(count):
            self.clock.now += 5
            self.history.note(doc([index]), {**doc([index + 1]), "pad": "x" * node_size},
                              {("a", "n0", "gain_db")}, "ljoss")
            self.history.close()

    def test_100_steps(self):
        self.steps(130)
        self.assertEqual(len(self.history.undo_steps), history.MAX_STEPS)

    def test_64_kib_per_rig(self):
        self.steps(40, node_size=4000)
        self.assertLessEqual(len(json.dumps(self.history.undo_steps)), history.MAX_RIG_BYTES)
        self.assertGreater(len(self.history.undo_steps), 1)

    def test_2_mib_in_all_loses_the_oldest_file(self):
        for index in range(3):
            with open(os.path.join(self.dir.name, f"old-{index}.json"), "w") as handle:
                handle.write("x" * (1 << 20))
            os.utime(handle.name, (1000 + index, 1000 + index))
        self.steps(1)
        self.history.save()
        names = sorted(os.listdir(self.dir.name))
        self.assertNotIn("old-0.json", names)
        self.assertIn("old-2.json", names)
        self.assertIn("Rig.json", names)


if __name__ == "__main__":
    unittest.main()

"""What is playing, what is stored, and what counts as a performance. Pure: no engine here."""

import copy
import unittest

from pedald.running import PERFORMANCE, Running, compare


def doc(name="Clean", gain=-6.0, boost=0.0, bypass=None, extra=None):
    boost_node = {"id": "boost", "element": "boost", "type": "nc.gain", "gain_db": boost}
    if bypass is not None:
        boost_node["bypass"] = bypass
    nodes = [{"id": "in", "type": "nc.input"}, {"id": "amp", "element": "amp", "type": "nc.gain", "gain_db": gain},
             boost_node, {"id": "out", "type": "nc.output"}]
    if extra:
        nodes.insert(1, extra)
    return {"name": name, "chains": [{"id": "main", "nodes": nodes,
                                      "connections": [{"from": "in", "to": "amp"}, {"from": "amp", "to": "boost"}]}]}


def origin(client="ljoss", tag=None):
    out = {"connection": 3, "client": client}
    if tag:
        out["tag"] = tag
    return out


def replaced(document, seq, why="apply", who=None):
    return {"event": "rig.replaced", "why": why, "seq": seq, "name": document["name"], "document": document,
            "origin": who or origin()}


def patched(document, seq, who=None):
    return {"event": "rig.patched", "seq": seq, "document": document, "origin": who or origin()}


def params(seq, node, value, who=None, param="gain_db"):
    return {"event": "rig.params", "values": [{"chain": "main", "node": node, "param": param, "value": value,
                                               "seq": seq, "origin": who or origin()}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.files = {"Clean": doc(), "Lead": doc("Lead", -3.0)}
        self.state = Running(lambda name: copy.deepcopy(self.files.get(name)))
        self.state.on_frame(replaced(doc(), 1, why="startup", who=origin("namchaind")))

    def stored_gain(self, node="amp"):
        return next(n for n in self.state.stored["chains"][0]["nodes"] if n["id"] == node)["gain_db"]

    def played_gain(self, node="amp"):
        return next(n for n in self.state.document["chains"][0]["nodes"] if n["id"] == node)["gain_db"]


class Classifying(Base):
    def test_starting_is_a_load(self):
        self.assertEqual(self.state.name, "Clean")
        self.assertTrue(self.state.savable())
        self.assertEqual(self.state.overlay, {})

    def test_a_named_clients_value_is_an_edit(self):
        change = self.state.on_frame(params(2, "amp", -9.0))
        self.assertEqual(change.kind, "edit")
        self.assertEqual(change.keys, {("main", "amp", "gain_db")})
        self.assertEqual(self.stored_gain(), -9.0)
        self.assertEqual(self.played_gain(), -9.0)

    def test_a_performance_value_isnt_stored(self):
        change = self.state.on_frame(params(2, "boost", 6.0, origin("pedald", "perf:param")))
        self.assertEqual(change.kind, "performance")
        self.assertEqual(self.stored_gain("boost"), 0.0)
        self.assertEqual(self.played_gain("boost"), 6.0)
        self.assertEqual(self.state.performance()[0]["element"], "boost")

    def test_a_performance_back_at_the_stored_value_is_over(self):
        self.state.on_frame(params(2, "boost", 6.0, origin("pedald", "perf:param")))
        self.state.on_frame(params(3, "boost", 0.0, origin("pedald", "perf:param")))
        self.assertEqual(self.state.overlay, {})

    def test_an_edit_on_a_performance_key_takes_it_out(self):
        self.state.on_frame(params(2, "boost", 6.0, origin("pedald", "perf:param")))
        self.state.on_frame(params(3, "boost", 3.0))
        self.assertEqual(self.state.overlay, {})
        self.assertEqual(self.stored_gain("boost"), 3.0)

    def test_a_block_toggle_is_a_performance(self):
        change = self.state.on_frame(patched(doc(bypass=True), 2, origin("pedald", "perf:block")))
        self.assertEqual(change.kind, "performance")
        self.assertEqual(self.state.overlay, {("main", "boost", "bypass"): PERFORMANCE})
        self.state.on_frame(patched(doc(bypass=False), 3, origin("pedald", "perf:block")))
        self.assertEqual(self.state.overlay, {})

    def test_an_unnamed_client_is_foreign(self):
        change = self.state.on_frame(params(2, "amp", -20.0, origin("")))
        self.assertEqual(change.kind, "foreign")
        self.assertEqual(self.stored_gain(), -6.0)
        self.assertEqual(self.state.performance(), [])     # shown as foreign, not as a performance
        self.assertTrue(self.state.overlay)

    def test_a_foreign_structural_change_stops_saves_until_a_load(self):
        extra = {"id": "x", "element": "x", "type": "nc.gain", "gain_db": 1.0}
        self.state.on_frame(patched(doc(extra=extra), 2, origin("")))
        self.assertFalse(self.state.savable())
        self.state.on_frame(replaced(doc("Lead", -3.0), 3, why="switch", who=origin("pedald", "load:footswitch")))
        self.assertTrue(self.state.savable())

    def test_a_load_clears_the_overlay(self):
        self.state.on_frame(params(2, "boost", 6.0, origin("pedald", "perf:param")))
        change = self.state.on_frame(replaced(doc("Lead", -3.0), 3, why="switch", who=origin("pedald", "load:footswitch")))
        self.assertEqual(change.kind, "load")
        self.assertEqual(self.state.name, "Lead")
        self.assertEqual(self.state.overlay, {})

    def test_a_load_by_a_client_is_a_load(self):
        change = self.state.on_frame(replaced(doc("Lead", -3.0), 2, why="load"))
        self.assertEqual(change.kind, "load")

    def test_a_document_of_another_name_is_another_rig(self):
        change = self.state.on_frame(replaced(doc("Lead", -3.0), 2))
        self.assertEqual(change.kind, "load")
        self.assertEqual(self.state.name, "Lead")

    def test_one_the_library_lacks_isnt_saved(self):
        self.state.on_frame(replaced(doc("Sketch"), 2))
        self.assertEqual(self.state.name, "Sketch")
        self.assertFalse(self.state.savable())

    def test_one_that_differs_from_the_file_is_an_edit_of_it(self):
        change = self.state.on_frame(replaced(doc("Lead", -1.0), 2))
        self.assertEqual(change.kind, "edit")
        self.assertEqual(change.keys, {("main", "amp", "gain_db")})
        self.assertEqual(self.stored_gain(), -1.0)

    def test_a_tuner_changes_nothing(self):
        tuner = {"id": "tuner", "type": "nc.tuner", "meta": {"ephemeral": "tuner"}}
        document = doc(extra=tuner)
        self.assertEqual(self.state.on_frame(replaced(document, 2)).kind, "none")
        self.assertNotIn("tuner", str(self.state.stored))

    def test_a_tuner_on_top_of_an_edit_isnt_stored(self):
        tuner = {"id": "tuner", "type": "nc.tuner", "meta": {"ephemeral": "tuner"}}
        change = self.state.on_frame(replaced(doc(gain=-1.0, extra=tuner), 2))
        self.assertEqual(change.kind, "edit")
        self.assertNotIn("tuner", str(self.state.stored))

    def test_an_old_frame_is_ignored(self):
        self.state.on_frame(params(5, "amp", -9.0))
        self.assertEqual(self.state.on_frame(params(4, "amp", -2.0)).kind, "none")
        self.assertEqual(self.played_gain(), -9.0)

    def test_a_runtime_value_isnt_in_the_document(self):
        frame = params(2, None, 1.0)
        self.assertEqual(self.state.on_frame(frame).kind, "none")

    def test_pedalds_own_undo_is_bookkeeping(self):
        change = self.state.on_frame(replaced(doc(gain=-2.0), 2, who=origin("pedald", "undo")))
        self.assertEqual(change.kind, "bookkeeping")
        self.assertEqual(self.stored_gain(), -6.0)        # pedald already set stored itself


class Merging(Base):
    def setUp(self):
        super().setUp()
        self.state.on_frame(patched(doc(bypass=True), 2, origin("pedald", "perf:block")))

    def test_an_app_that_left_the_performance_alone_keeps_it(self):
        change = self.state.on_frame(replaced(doc(gain=-9.0, bypass=True), 3))
        self.assertEqual(change.kind, "edit")
        self.assertEqual(change.keys, {("main", "amp", "gain_db")})
        self.assertIn(("main", "boost", "bypass"), self.state.overlay)
        self.assertEqual(self.stored_gain(), -9.0)
        stored_boost = next(n for n in self.state.stored["chains"][0]["nodes"] if n["id"] == "boost")
        self.assertFalse(stored_boost.get("bypass"))

    def test_an_app_that_turned_it_back_ends_it(self):
        change = self.state.on_frame(replaced(doc(bypass=False), 3))
        self.assertEqual(change.kind, "edit")
        self.assertEqual(self.state.overlay, {})

    def test_an_app_that_removed_the_node_ends_it(self):
        document = doc()
        document["chains"][0]["nodes"] = [n for n in document["chains"][0]["nodes"] if n["id"] != "boost"]
        self.state.on_frame(replaced(document, 3))
        self.assertEqual(self.state.overlay, {})


class Comparing(unittest.TestCase):
    def test_absent_and_false_bypass_are_the_same(self):
        self.assertEqual(compare(doc(), doc(bypass=False)), (set(), False))

    def test_a_value(self):
        self.assertEqual(compare(doc(), doc(gain=1.0)), ({("main", "amp", "gain_db")}, False))

    def test_a_node_is_structural(self):
        extra = {"id": "x", "type": "nc.gain"}
        self.assertTrue(compare(doc(), doc(extra=extra))[1])

    def test_the_name_alone_is_nothing(self):
        self.assertEqual(compare(doc("A"), doc("B")), (set(), False))


class Starting(unittest.TestCase):
    def state(self):
        return Running(lambda _name: None)

    def test_the_record_matches_and_the_overlay_comes_back(self):
        state = self.state()
        played = doc(bypass=True)
        record = {"rig": "Clean", "overlay": [["main", "boost", "bypass", PERFORMANCE]]}
        change = state.start(played, "Clean", 4, doc(), copy.deepcopy(played), record)
        self.assertEqual(change.kind, "none")
        self.assertIn(("main", "boost", "bypass"), state.overlay)
        self.assertFalse(next(n for n in state.stored["chains"][0]["nodes"] if n["id"] == "boost").get("bypass"))

    def test_an_edit_while_pedald_was_down_is_one_edit(self):
        state = self.state()
        change = state.start(doc(gain=-18.0), "Clean", 4, doc(), doc(), {"rig": "Clean", "overlay": []})
        self.assertEqual(change.kind, "edit")

    def test_no_record_means_nothing_is_baked_in(self):
        state = self.state()
        state.start(doc(gain=-18.0), "Clean", 4, doc(), doc(gain=-18.0), None)
        self.assertEqual(state.overlay, {("main", "amp", "gain_db"): PERFORMANCE})
        self.assertEqual(next(n for n in state.stored["chains"][0]["nodes"] if n["id"] == "amp")["gain_db"], -6.0)
        self.assertTrue(state.savable())

    def test_no_record_and_another_shape_keeps_the_engines(self):
        state = self.state()
        played = doc(gain=-18.0, extra={"id": "x", "type": "nc.gain"})
        state.start(played, "Clean", 4, doc(), None, None)
        self.assertTrue(state.savable())
        self.assertIn("x", [n["id"] for n in state.stored["chains"][0]["nodes"]])
        self.assertEqual(state.overlay, {("main", "amp", "gain_db"): PERFORMANCE})

    def test_a_rig_the_library_lacks(self):
        state = self.state()
        state.start(doc("Sketch"), "Sketch", 4, None, None, None)
        self.assertFalse(state.savable())


class Undoing(Base):
    def test_with_overlay_puts_the_performance_on_top(self):
        self.state.on_frame(patched(doc(bypass=True), 2, origin("pedald", "perf:block")))
        document = self.state.with_overlay(doc(gain=-1.0))
        boost = next(n for n in document["chains"][0]["nodes"] if n["id"] == "boost")
        self.assertTrue(boost["bypass"])

    def test_a_key_whose_node_went_leaves_the_overlay(self):
        self.state.on_frame(patched(doc(bypass=True), 2, origin("pedald", "perf:block")))
        target = doc()
        target["chains"][0]["nodes"] = [n for n in target["chains"][0]["nodes"] if n["id"] != "boost"]
        self.state.with_overlay(target)
        self.assertEqual(self.state.overlay, {})

    def test_the_library_changing_under_it_wins(self):
        self.state.on_frame(params(2, "amp", -9.0))
        self.state.take_stored(doc(gain=-1.0))
        self.assertEqual(self.stored_gain(), -1.0)


if __name__ == "__main__":
    unittest.main()

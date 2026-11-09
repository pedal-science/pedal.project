"""Autosave, the bank and the commands, with no engine: these run where namchain isn't built."""

import json
import os
import unittest

from pedald.engine import EngineError
from test_uploads import Service


def rig(name, gain=-6.0):
    return {"name": name, "chains": [{"id": "main", "nodes": [
        {"id": "amp", "element": "amp", "type": "nc.gain", "gain_db": gain}], "connections": []}]}


class Rigs(Service):
    autosave = False

    def setUp(self):
        super().setUp()
        self.rigs = self.service.cfg.rigs_root
        self.service.cfg.autosave = self.autosave
        self.engine.switched = []
        self.engine.rig_switch = lambda rig, fallback=True, tag=None: self.switched(rig, tag)
        self.engine.rig_get = lambda: {"document": rig("Clean"), "seq": 1}
        for name, gain in (("Clean", -6.0), ("Lead", -3.0)):
            self.ask_ok("PUT", f"/library/rigs/{name}", json.dumps(rig(name, gain)))
        self.feed(("frame", self.replaced(rig("Clean"), 2, "startup", "namchaind")))

    def switched(self, name, tag):
        self.engine.switched.append((name, tag))
        return {"switched": "cold"}

    def ask_ok(self, method, path, body=None):
        status, data, _ = self.ask(method, path, body)
        self.assertIn(status, (200, 201), data)
        return json.loads(data)

    def replaced(self, document, seq, why, client, tag=None):
        return {"event": "rig.replaced", "why": why, "seq": seq, "name": document["name"], "document": document,
                "origin": {"client": client, "tag": tag}}

    def feed(self, item):
        self.service.follower.queue.put(item)
        self.service.wake()
        self.service.on_loop(lambda: None)      # it has run by the time this returns
        self.service.on_loop(lambda: None)

    def edit(self, gain, seq):
        self.feed(("frame", {"event": "rig.params", "values": [
            {"chain": "main", "node": "amp", "param": "gain_db", "value": gain, "seq": seq,
             "origin": {"client": "ljoss"}}]}))

    def filed(self, name="Clean"):
        with open(os.path.join(self.rigs, f"{name}.json"), encoding="utf-8") as handle:
            return json.load(handle)["chains"][0]["nodes"][0]["gain_db"]


class AutosaveOff(Rigs):
    def test_nothing_is_written(self):
        self.edit(-12.0, 3)
        self.service.on_loop(self.service.save_now)
        self.assertEqual(self.filed(), -6.0)
        self.assertEqual(json.loads(self.ask("GET", "/running")[1])["undo"], 1)
        self.assertFalse(os.path.exists(os.path.join(self.service.cfg.state_root, "history", "Clean.json")))


class AutosaveOn(Rigs):
    autosave = True

    def test_an_edit_is_written_with_its_history(self):
        self.edit(-12.0, 3)
        self.service.on_loop(self.service.save_now)
        self.assertEqual(self.filed(), -12.0)
        self.assertTrue(os.path.exists(os.path.join(self.service.cfg.state_root, "history", "Clean.json")))

    def test_a_saved_event_goes_out(self):
        got = []
        self.service.publish = lambda kind, data: got.append(kind)
        self.edit(-12.0, 3)
        self.service.on_loop(self.service.save_now)
        self.assertIn("saved", got)

    def test_nothing_to_write_is_no_write(self):
        before = os.stat(os.path.join(self.rigs, "Clean.json")).st_mtime_ns
        self.service.on_loop(self.service.save_now)
        self.assertEqual(os.stat(os.path.join(self.rigs, "Clean.json")).st_mtime_ns, before)

    def test_a_rig_going_saves_its_edit_first(self):
        self.edit(-12.0, 3)
        self.feed(("frame", self.replaced(rig("Lead", -3.0), 4, "switch", "pedald", "load:footswitch")))
        self.assertEqual(self.filed(), -12.0)
        self.assertEqual(self.filed("Lead"), -3.0)

    def test_a_stale_undo_is_409(self):
        self.edit(-12.0, 3)
        def refuse(*_args, **_kwargs):
            raise EngineError("conflict", "the document moved")
        self.engine.rig_apply = refuse
        self.assertEqual(self.ask("POST", "/undo")[0], 409)
        self.assertEqual(json.loads(self.ask("GET", "/running")[1])["undo"], 1)

    def test_nothing_to_undo_is_409(self):
        self.assertEqual(self.ask("POST", "/undo")[0], 409)
        self.assertEqual(self.ask("POST", "/redo")[0], 409)


class Commands(Rigs):
    def test_picking_a_rig_goes_the_footswitchs_way(self):
        self.ask_ok("PUT", "/running", json.dumps({"rig": "Lead"}))
        self.assertEqual(self.engine.switched[-1], ("Lead.json", "load:app"))

    def test_no_such_rig_is_404(self):
        self.assertEqual(self.ask("PUT", "/running", json.dumps({"rig": "Nope"}))[0], 404)

    def test_a_rig_the_engine_says_is_over_is_409(self):
        self.service.on_loop(lambda: self.service.cost.verdicts.__setitem__(
            "Lead", {"verdict": "over", "cost": 2, "headroom": 1, "over": True}))
        self.service.cost.verdict = lambda name: {"verdict": "over", "cost": 2, "headroom": 1, "over": True}
        self.assertEqual(self.ask("PUT", "/running", json.dumps({"rig": "Lead"}))[0], 409)
        self.assertEqual(self.engine.switched, [])

    def test_a_bad_body_is_400(self):
        self.assertEqual(self.ask("PUT", "/running", b"{nope")[0], 400)
        self.assertEqual(self.ask("PUT", "/bank", b"{nope")[0], 400)
        self.assertEqual(self.ask("POST", "/library/rigs", b"{nope")[0], 400)

    def test_a_new_rigs_name_is_checked(self):
        for name, wanted in (("last", 400), ("a/b", 400), ("Clean", 409), ("clean", 409)):
            status = self.ask("POST", "/library/rigs", json.dumps({"name": name, "from": None}))[0]
            self.assertEqual(status, wanted, name)

    def test_a_new_rig_from_nothing_duplicates_nothing_of_the_running_rig(self):
        self.ask_ok("POST", "/library/rigs", json.dumps({"name": "Empty", "from": None}))
        with open(os.path.join(self.rigs, "Empty.json"), encoding="utf-8") as handle:
            self.assertEqual([n["type"] for n in json.load(handle)["chains"][0]["nodes"]], ["nc.input", "nc.output"])

    def test_a_migrated_rig_takes_its_document_and_the_new_name(self):
        self.ask_ok("POST", "/library/rigs", json.dumps({"name": "Moved", "document": rig("Old", -1.0)}))
        self.assertEqual(self.filed("Moved"), -1.0)

    def test_from_a_rig_that_doesnt_exist_is_404(self):
        self.assertEqual(self.ask("POST", "/library/rigs", json.dumps({"name": "X", "from": "Nope"}))[0], 404)


class Placing(Rigs):
    def placed(self, banks, current):
        self.service.mapping.banks = banks
        self.service.mapping.bank = next((i for i, b in enumerate(banks) if current in b), 0)
        self.service.mapping.rig = banks[self.service.mapping.bank].index(current) if current in banks[self.service.mapping.bank] else -1
        return self.service.placed("New")

    def test_right_after_the_running_rig(self):
        self.assertEqual(self.placed([["A", "B"]], "A"), [["A", "New", "B"]])

    def test_at_the_end_of_the_last_bank_if_its_bank_is_full(self):
        full = [f"r{i}" for i in range(8)]
        self.assertEqual(self.placed([full, ["z"]], "r0"), [full, ["z", "New"]])

    def test_a_new_bank_if_the_last_is_full_too(self):
        full = [f"r{i}" for i in range(8)]
        self.assertEqual(self.placed([full], "r0"), [full, ["New"]])


class Banks(Rigs):
    def test_set_and_read(self):
        self.ask_ok("PUT", "/bank", json.dumps({"banks": [["Lead"], ["Clean"]]}))
        self.assertEqual(json.loads(self.ask("GET", "/bank")[1])["banks"], [["Lead"], ["Clean"]])

    def test_it_lasts(self):
        self.ask_ok("PUT", "/bank", json.dumps({"banks": [["Lead"], ["Clean"]]}))
        with open(os.path.join(self.service.cfg.state_root, "bank.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["banks"], [["Lead"], ["Clean"]])

    def test_every_refusal(self):
        for banks in ([], [[]], [["Nope"]], [["Lead"] * 9], "x", [["Lead"], []]):
            self.assertEqual(self.ask("PUT", "/bank", json.dumps({"banks": banks}))[0], 400, banks)


del Rigs, Service


if __name__ == "__main__":
    unittest.main()

"""The rig library API (v3's rig half, docs/pedal-service.md "The upload API"): the files, the
routes, and what a change does to the bank and the verdicts."""
import http.client
import json
import os
import pathlib
import queue
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import daemon, library, mapping  # noqa: E402
from pedald.httpd import Request, Server  # noqa: E402

TOKEN = "library-test-token-0123456789"


def document(name, **extra):
    doc = {"name": name, "chains": [{"id": "c", "nodes": [{"id": "in", "type": "nc.input"},
                                                           {"id": "out", "type": "nc.output"}],
                                     "connections": [{"from": "in", "to": "out"}]}]}
    doc.update(extra)
    return doc


class Files(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.lib = library.RigLibrary(self.root)

    def put(self, name, doc=None):
        return self.lib.put(name, json.dumps(doc if doc is not None else document(name)).encode())

    def test_put_get_list(self):
        self.assertFalse(self.put("Clean"))
        self.assertTrue(self.put("Clean"))  # overwrite is the default, and says so
        self.put("Lead")
        self.assertEqual(self.lib.names(), ["Clean", "Lead"])
        self.assertEqual(self.lib.get("Lead")["name"], "Lead")
        self.assertEqual([r["name"] for r in self.lib.listing()], ["Clean", "Lead"])

    def test_resume_files_and_staged_files_are_not_rigs(self):
        for name in ("last.json", "last.prev.json", ".Half.json.part", "notes.txt"):
            pathlib.Path(self.root, name).write_text("{}")
        self.assertEqual(self.lib.names(), [])

    def test_a_document_without_a_name_takes_the_paths(self):
        doc = document("x")
        del doc["name"]
        self.put("Named", doc)
        self.assertEqual(self.lib.get("Named")["name"], "Named")

    def test_refusals(self):
        cases = {
            "": 400, "last": 400, "last.prev": 400, ".hidden": 400, "a/b": 400, "a\\b": 400,
            "tab\there": 400, "x" * 201: 400,
        }
        for name, status in cases.items():
            with self.assertRaises(library.LibraryError) as caught:
                self.put(name)
            self.assertEqual(caught.exception.status, status, name)
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.put("Clean", json.dumps(document("Other")).encode())
        self.assertEqual(caught.exception.status, 400)   # the document's name must match
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.put("Clean", b"[1, 2]")
        self.assertEqual(caught.exception.status, 400)
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.put("Clean", b'{"name": "Clean"}')
        self.assertEqual(caught.exception.status, 400)   # no chains, no nodes
        small = library.RigLibrary(self.root, max_bytes=10)
        with self.assertRaises(library.LibraryError) as caught:
            small.put("Clean", json.dumps(document("Clean")).encode())
        self.assertEqual(caught.exception.status, 413)

    def test_names_differing_only_in_case_are_one_name(self):
        self.put("Clean")
        with self.assertRaises(library.LibraryError) as caught:
            self.put("clean")
        self.assertEqual(caught.exception.status, 409)

    def test_delete(self):
        self.put("Clean")
        self.lib.delete("Clean")
        self.assertEqual(self.lib.names(), [])
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.delete("Clean")
        self.assertEqual(caught.exception.status, 404)

    def test_rename_moves_the_file_and_the_documents_name(self):
        self.put("Clean")
        self.put("Lead")
        self.lib.rename("Clean", "Sparkle")
        self.assertEqual(self.lib.names(), ["Lead", "Sparkle"])
        self.assertEqual(self.lib.get("Sparkle")["name"], "Sparkle")
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.rename("Sparkle", "Lead")
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(library.LibraryError) as caught:
            self.lib.rename("Nope", "Other")
        self.assertEqual(caught.exception.status, 404)
        self.lib.rename("Sparkle", "sparkle")  # a change of case is a rename of the same rig
        self.assertEqual(self.lib.names(), ["Lead", "sparkle"])

    def test_nothing_is_left_staged(self):
        self.put("Clean")
        self.assertEqual([n for n in os.listdir(self.root) if n.startswith(".")], [])


class Bank(unittest.TestCase):
    def test_rename_and_delete_in_the_bank(self):
        bank = {"bank": 0, "rig": 1, "banks": [["Clean", "Lead"], ["Solo"]]}
        renamed, changed = library.rename_in_bank(bank, "Lead", "Lead 2")
        self.assertTrue(changed)
        self.assertEqual(renamed["banks"], [["Clean", "Lead 2"], ["Solo"]])
        deleted, changed = library.rename_in_bank(bank, "Solo", None)
        self.assertTrue(changed)
        self.assertEqual(deleted["banks"], [["Clean", "Lead"]])  # an emptied bank goes
        same, changed = library.rename_in_bank(bank, "Nope", "x")
        self.assertFalse(changed)


class PrefixRoutes(unittest.TestCase):
    def setUp(self):
        self.seen = []
        routes = {
            "/status": lambda r: (200, {"exact": True}),
            "/library/rigs/*": lambda r: (self.seen.append((r.method, r.path)) or (200, {"path": r.path})),
            "GET /library/rigs": lambda r: (200, {"list": True}),
        }
        self.server = Server("127.0.0.1", 0, TOKEN, routes, log=lambda _m: None)
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, json.loads(data) if data else None

    def test_prefix_answers_below_itself_only(self):
        self.assertEqual(self.request("GET", "/library/rigs")[1], {"list": True})
        self.assertEqual(self.request("GET", "/library/rigs/Clean")[1], {"path": "/library/rigs/Clean"})
        self.assertEqual(self.request("DELETE", "/library/rigs/Clean")[0], 200)
        self.assertEqual(self.request("PUT", "/library/rigs/Clean", b"{}")[0], 200)
        self.assertEqual(self.request("GET", "/library/rigsx")[0], 404)
        self.assertEqual(self.request("GET", "/library/rigs/")[0], 404)  # nothing below it
        self.assertEqual([m for m, _ in self.seen], ["GET", "DELETE", "PUT"])


def library_service(root):
    """A Service with the library, the bank and the verdicts, and no engine or link."""
    logs = []
    service = object.__new__(daemon.Service)
    service.log = logs.append
    service.logs = logs
    service.cfg = types.SimpleNamespace(rigs_root=root, state_root=tempfile.mkdtemp())
    service.status = {}
    service.bank_at = 0.0
    service.library = library.RigLibrary(root, log=logs.append)
    service.library_changes = queue.SimpleQueue()
    service.mapping = mapping.Mapping(service._rig_names(), log=logs.append)
    service.cost = daemon.RigCost(types.SimpleNamespace(), log=logs.append)
    service.cost.note_rigs(service._rig_names(), time.monotonic())
    service.mapping.verdicts = service.cost.verdicts
    return service


def request(method, name, body=b"", suffix=""):
    path = "/library/rigs/" + name.replace(" ", "%20") + suffix
    return Request(method, path, {}, {}, body)


class Routes(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for name in ("Clean", "Lead"):
            pathlib.Path(self.root, name + ".json").write_text(json.dumps(document(name)))
        self.service = library_service(self.root)

    def test_listing_says_which_rig_runs(self):
        self.service.status = {"rig": os.path.join(self.root, "Lead.json"), "rig_name": "Lead"}
        status, body = self.service.handle_rigs(None)
        self.assertEqual(status, 200)
        self.assertEqual([r["name"] for r in body["rigs"]], ["Clean", "Lead"])
        self.assertEqual(body["running"], "Lead")
        # After a reboot the engine runs last.json; the document's name is the link (R3).
        self.service.status = {"rig": os.path.join(self.root, "last.json"), "rig_name": "Clean"}
        self.assertEqual(self.service.handle_rigs(None)[1]["running"], "Clean")
        # A document the library doesn't have isn't a library rig.
        self.service.status = {"rig": "", "rig_name": "From ljoss"}
        self.assertIsNone(self.service.handle_rigs(None)[1]["running"])

    def test_put_get_and_a_name_with_a_space(self):
        body = json.dumps(document("Big Hall")).encode()
        status, reply = self.service.handle_rig(request("PUT", "Big Hall", body))
        self.assertEqual((status, reply["replaced"]), (201, False))
        status, doc = self.service.handle_rig(request("GET", "Big Hall"))
        self.assertEqual((status, doc["name"]), (200, "Big Hall"))
        self.assertEqual(self.service.handle_rig(request("GET", "Nope"))[0], 404)

    def test_put_invalidates_that_rigs_verdict_only(self):
        self.service.cost.verdicts.update({"Clean": {"verdict": "fits"}, "Lead": {"verdict": "fits"}})
        self.service.handle_rig(request("PUT", "Clean", json.dumps(document("Clean")).encode()))
        self.service.apply_library_changes(time.monotonic())
        self.assertNotIn("Clean", self.service.cost.verdicts)
        self.assertIn("Lead", self.service.cost.verdicts)

    def test_a_new_rig_joins_the_bank(self):
        self.service.handle_rig(request("PUT", "Ambient", json.dumps(document("Ambient")).encode()))
        self.service.apply_library_changes(time.monotonic())
        self.assertEqual(self.service.cost.rigs, ["Ambient", "Clean", "Lead"])
        self.assertIn("Ambient", self.service.mapping.current_bank())

    def test_rename_rewrites_the_bank_and_keeps_the_position(self):
        bank_path = os.path.join(self.service.cfg.state_root, "bank.json")
        pathlib.Path(bank_path).write_text(json.dumps({"bank": 0, "rig": 1, "banks": [["Clean", "Lead"]]}))
        self.service.mapping = mapping.Mapping(["Clean", "Lead"], bank=mapping.load_json(bank_path))
        self.assertEqual(self.service.mapping.current_name(), "Lead")
        status, reply = self.service.handle_rig(request("POST", "Lead", json.dumps({"to": "Lead 2"}).encode(),
                                                        "/rename"))
        self.assertEqual((status, reply["name"]), (200, "Lead 2"))
        self.service.apply_library_changes(time.monotonic())
        self.assertEqual(json.loads(pathlib.Path(bank_path).read_text())["banks"], [["Clean", "Lead 2"]])
        self.assertEqual(self.service.mapping.current_name(), "Lead 2")
        self.assertTrue(pathlib.Path(self.root, "Lead 2.json").exists())

    def test_delete_takes_the_rig_out_of_the_bank(self):
        bank_path = os.path.join(self.service.cfg.state_root, "bank.json")
        pathlib.Path(bank_path).write_text(json.dumps({"bank": 0, "rig": 0, "banks": [["Clean", "Lead"]]}))
        self.assertEqual(self.service.handle_rig(request("DELETE", "Clean"))[0], 200)
        self.service.apply_library_changes(time.monotonic())
        self.assertEqual(json.loads(pathlib.Path(bank_path).read_text())["banks"], [["Lead"]])
        self.assertEqual(self.service.cost.rigs, ["Lead"])

    def test_refusals_come_back_as_their_status(self):
        self.assertEqual(self.service.handle_rig(request("PUT", "last", b"{}"))[0], 400)
        self.assertEqual(self.service.handle_rig(request("PUT", "Lead", json.dumps(document("Clean")).encode()))[0], 400)
        self.assertEqual(self.service.handle_rig(request("POST", "Lead", b'{"to": "Clean"}', "/rename"))[0], 409)
        self.assertEqual(self.service.handle_rig(request("GET", "Lead", b"", "/rename"))[0], 405)
        self.assertTrue(self.service.library_changes.empty())  # a refusal changes nothing


if __name__ == "__main__":
    unittest.main()

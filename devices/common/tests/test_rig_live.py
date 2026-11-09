"""The rig against a real namchaind on the null backend. Skipped if namchain hasn't been built here."""

import http.client
import json
import os
import pathlib
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from pedald import config, daemon
from pedald.engine import EngineClient

NAMCHAIN = pathlib.Path(__file__).resolve().parents[4] / "namchain" / "build-mac"
NAMCHAIND = NAMCHAIN / "namchaind"
TOKEN = "t" * 32


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def rig(name, gain=-6.0):
    def chain(block="amp"):
        return {"id": "main", "name": "Guitar", "input_channel": 0, "output_channel": 0,
                "nodes": [{"id": "in", "element": "in", "type": "nc.input"},
                          {"id": "amp-gain", "element": "amp", "type": "nc.gain", "gain_db": gain},
                          {"id": "boost-gain", "element": "boost", "type": "nc.gain", "gain_db": 0.0},
                          {"id": "out", "element": "out", "type": "nc.output"}],
                "connections": [{"from": "in", "from_port": 0, "to": "amp-gain", "to_port": 0},
                                {"from": "amp-gain", "from_port": 0, "to": "boost-gain", "to_port": 0},
                                {"from": "boost-gain", "from_port": 0, "to": "out", "to_port": 0}]}
    return {"name": name, "chains": [chain()]}


@unittest.skipUnless(NAMCHAIND.exists(), "namchain isn't built here")
class Live(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = root = pathlib.Path(self.dir.name)
        (root / "lib" / "rigs").mkdir(parents=True)
        (root / "lib" / "models").mkdir()
        (root / "lib" / "irs").mkdir()
        self.rigs = root / "lib" / "rigs"
        for name, gain in (("Clean", -6.0), ("Lead", -3.0)):
            self.store(name, gain)
        (self.rigs / "last.json").write_text(json.dumps(rig("Clean", -6.0)))
        (root / "state").mkdir()
        (root / "state" / "midi-map.json").write_text(json.dumps({"cc": {
            "82": {"block": "boost"}, "90": {"param": {"element": "boost", "slot": "gain", "param": "gain_db"}}}}))
        (root / "token").write_text(TOKEN)
        self.engine_port = free_port()
        (root / "namchaind.json").write_text(json.dumps({
            "backend": "null", "sample_rate": 48000, "capture_channels": 2, "playback_channels": 2,
            "rig": "last.json", "rigs_root": str(self.rigs), "models_root": str(root / "lib" / "models"),
            "irs_root": str(root / "lib" / "irs"), "socket": str(root / "n.sock"), "lock_memory": False,
            "rt_priority": 0, "tcp_listen": True, "tcp_address": "127.0.0.1", "tcp_port": self.engine_port,
            "tcp_token_file": str(root / "token"), "tcp_max_connections": 8}))
        self.engine_process = None
        self.service = None
        self.lines = []
        self.addCleanup(self.stop_all)
        self.start_engine()
        self.start_service()

    def store(self, name, gain):
        (self.rigs / f"{name}.json").write_text(json.dumps(rig(name, gain)))

    def start_engine(self):
        log = open(self.root / "namchaind.log", "a")
        self.addCleanup(log.close)
        self.engine_process = subprocess.Popen([str(NAMCHAIND), "--config", str(self.root / "namchaind.json")],
                                               stdout=log, stderr=log, cwd=self.root)
        self.wait(lambda: self._port_open(), 10, "namchaind didn't start")

    def _port_open(self):
        try:
            socket.create_connection(("127.0.0.1", self.engine_port), 0.2).close()
            return True
        except OSError:
            return False

    def start_service(self):
        cfg = config.Config()
        cfg.uart_device = str(self.root / "no-uart")
        cfg.http_host, cfg.http_port = "127.0.0.1", 0
        cfg.engine_port = self.engine_port
        cfg.engine_token_file = str(self.root / "token")
        cfg.rigs_root, cfg.models_root, cfg.irs_root = str(self.rigs), str(self.root / "lib" / "models"), str(self.root / "lib" / "irs")
        cfg.state_root, cfg.cache_root = str(self.root / "state"), str(self.root / "cache")
        cfg.autosave = True
        self.service = daemon.Service(cfg, self.lines.append)
        self.thread = threading.Thread(target=self.service.run, daemon=True)
        self.thread.start()
        self.wait(lambda: self.service.http.port and self.service.followed, 10, "pedald didn't follow the engine")

    def stop_service(self):
        if self.service is not None:
            self.service.stop()
            self.thread.join(10)
            self.service = None

    def stop_all(self):
        self.stop_service()
        if self.engine_process is not None:
            self.engine_process.send_signal(signal.SIGTERM)
            self.engine_process.wait(10)

    def wait(self, check, seconds=5, why="timed out"):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(0.02)
        self.fail(f"{why}\n" + "\n".join(self.lines[-12:]))

    def ask(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.service.http.port, timeout=15)
        self.addCleanup(conn.close)
        conn.request(method, path, body=None if body is None else json.dumps(body),
                     headers={"Authorization": "Bearer " + TOKEN, "Pedal-Client": "test"})
        reply = conn.getresponse()
        return reply.status, json.loads(reply.read() or b"null")

    def client(self, name="ljoss"):
        client = EngineClient("127.0.0.1", self.engine_port, TOKEN, timeout=5.0, client=name)
        self.addCleanup(client.close)
        return client

    def filed(self, name, node="amp-gain"):
        document = json.loads((self.rigs / f"{name}.json").read_text())
        return next(n for n in document["chains"][0]["nodes"] if n["id"] == node)

    def set_gain(self, client, value, node="amp-gain", tag=None):
        client.rig_patch([{"op": "set_param", "node": node, "param": "gain_db", "value": value}], chain="main", tag=tag)

    def playing(self, node="amp-gain"):
        document = self.client("reader").rig_get()["document"]
        return next(n for n in document["chains"][0]["nodes"] if n["id"] == node)

    def test_an_edit_reaches_the_file_within_a_second_or_so(self):
        started = time.monotonic()
        self.set_gain(self.client(), -12.0)
        self.wait(lambda: self.filed("Clean")["gain_db"] == -12.0, 3, "the edit wasn't saved")
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(self.ask("GET", "/running")[1]["undo"], 1)

    def test_a_structural_edit_is_saved(self):
        self.client().rig_patch([{"op": "bypass", "node": "amp-gain", "bypass": True}], chain="main")
        self.wait(lambda: self.filed("Clean").get("bypass") is True, 3, "the bypass wasn't saved")

    def test_a_mapped_press_is_a_performance_and_isnt_saved(self):
        status, reply = self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply["result"]["bypass"], True)
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3, "it isn't listed")
        self.assertEqual(self.ask("GET", "/running")[1]["performance"][0]["element"], "boost")
        self.assertTrue(self.playing("boost-gain").get("bypass"))
        self.set_gain(self.client(), -9.0)          # an edit beside it is saved, without the performance
        self.wait(lambda: self.filed("Clean")["gain_db"] == -9.0, 3, "the edit wasn't saved")
        self.assertFalse(self.filed("Clean", "boost-gain").get("bypass"))
        self.assertTrue(self.playing("boost-gain").get("bypass"))

    def test_a_press_again_ends_the_performance(self):
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3)
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: not self.ask("GET", "/running")[1]["performance"], 3)

    def test_a_mapped_cc_drives_a_parameter_and_isnt_saved(self):
        for value in (10, 60, 127):
            self.ask("POST", "/event", {"kind": 0x10, "a": 90, "b": value})
        self.wait(lambda: self.playing("boost-gain")["gain_db"] == 24.0, 3, "the value didn't arrive")
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3, "it isn't listed")
        self.assertEqual(self.filed("Clean", "boost-gain")["gain_db"], 0.0)

    def test_undo_and_redo(self):
        client = self.client()
        self.set_gain(client, -12.0)
        self.wait(lambda: self.filed("Clean")["gain_db"] == -12.0, 3)
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})   # a performance stays on top
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3)
        status, reply = self.ask("POST", "/undo")
        self.assertEqual(status, 200, reply)
        self.assertEqual(self.filed("Clean")["gain_db"], -6.0)
        self.assertEqual(self.playing()["gain_db"], -6.0)
        self.assertTrue(self.playing("boost-gain").get("bypass"))
        self.assertFalse(self.filed("Clean", "boost-gain").get("bypass"))
        status, reply = self.ask("POST", "/redo")
        self.assertEqual(status, 200, reply)
        self.assertEqual(self.filed("Clean")["gain_db"], -12.0)
        self.assertEqual(self.playing()["gain_db"], -12.0)
        self.assertEqual(self.ask("POST", "/redo")[0], 409)

    def test_a_run_on_one_knob_is_one_step_and_another_knob_is_another(self):
        client = self.client()
        for value in (-7.0, -8.0, -9.0):
            self.set_gain(client, value)
            time.sleep(0.15)
        self.wait(lambda: self.ask("GET", "/running")[1]["undo"] == 1 and self.playing()["gain_db"] == -9.0, 3)
        self.set_gain(client, 3.0, node="boost-gain")
        self.wait(lambda: self.ask("GET", "/running")[1]["undo"] == 2, 3, "a second control is a second step")
        self.ask("POST", "/undo")
        self.assertEqual(self.playing("boost-gain")["gain_db"], 0.0)
        self.assertEqual(self.playing()["gain_db"], -9.0)
        self.ask("POST", "/undo")
        self.assertEqual(self.playing()["gain_db"], -6.0)

    def test_a_gesture_is_one_step(self):
        client = self.client()
        self.set_gain(client, -7.0, tag="gesture:1")
        self.set_gain(client, 2.0, node="boost-gain", tag="gesture:1")
        self.wait(lambda: self.playing("boost-gain")["gain_db"] == 2.0, 3)
        self.wait(lambda: self.ask("GET", "/running")[1]["undo"] == 1, 3)
        time.sleep(0.2)
        self.assertEqual(self.ask("GET", "/running")[1]["undo"], 1)

    def test_after_both_restart_the_document_and_the_overlay_are_kept(self):
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3)
        self.wait(lambda: (self.root / "state" / "resume.json").exists()
                  and json.loads((self.root / "state" / "resume.json").read_text())["overlay"], 8, "no record")
        self.stop_service()
        self.engine_process.send_signal(signal.SIGTERM)
        self.engine_process.wait(10)
        self.start_engine()
        self.start_service()
        self.assertTrue(self.playing("boost-gain").get("bypass"))
        self.wait(lambda: self.ask("GET", "/running")[1]["performance"], 3, "the overlay wasn't kept")
        self.set_gain(self.client(), -9.0)
        self.wait(lambda: self.filed("Clean")["gain_db"] == -9.0, 3)
        self.assertFalse(self.filed("Clean", "boost-gain").get("bypass"))

    def test_switching_away_and_back_restores_the_stored_values(self):
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: self.playing("boost-gain").get("bypass"), 3)
        self.assertEqual(self.ask("PUT", "/running", {"rig": "Lead"})[0], 200)
        self.wait(lambda: self.ask("GET", "/running")[1]["rig"] == "Lead", 3)
        self.assertEqual(self.ask("GET", "/running")[1]["performance"], [])
        self.assertEqual(self.ask("PUT", "/running", {"rig": "Clean"})[0], 200)
        self.wait(lambda: self.ask("GET", "/running")[1]["rig"] == "Clean", 3)
        self.assertFalse(self.playing("boost-gain").get("bypass"))

    def test_an_edit_made_just_before_a_switch_is_saved_to_its_own_rig(self):
        self.set_gain(self.client(), -14.0)
        self.wait(lambda: self.ask("GET", "/running")[1]["undo"] == 1, 3)
        self.ask("PUT", "/running", {"rig": "Lead"})
        self.wait(lambda: self.filed("Clean")["gain_db"] == -14.0, 3)
        self.assertEqual(self.filed("Lead")["gain_db"], -3.0)

    def test_an_unnamed_client_is_shown_and_never_saved(self):
        self.client(None).rig_patch([{"op": "set_param", "node": "amp-gain", "param": "gain_db", "value": -20.0}], chain="main")
        self.wait(lambda: self.service.rig_state.overlay, 3, "it wasn't seen")
        time.sleep(1.5)
        self.assertEqual(self.filed("Clean")["gain_db"], -6.0)

    def test_a_whole_document_from_an_app_is_merged_key_by_key(self):
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: self.service.rig_state.overlay, 3)
        client = self.client()
        document = client.rig_get()["document"]
        document["chains"][0]["nodes"][1]["gain_db"] = -15.0      # the bypass is left as it saw it
        client.rig_apply(document)
        self.wait(lambda: self.filed("Clean")["gain_db"] == -15.0, 3, "the edit wasn't saved")
        self.assertFalse(self.filed("Clean", "boost-gain").get("bypass"))
        self.assertTrue(self.service.rig_state.overlay)

    def test_a_tuners_mount_is_nothing(self):
        client = self.client()
        document = client.rig_get()["document"]
        chain = document["chains"][0]
        chain["nodes"].insert(1, {"id": "tuner", "type": "nc.tuner", "meta": {"ephemeral": "tuner"}})
        for connection in chain["connections"]:
            if connection["from"] == "in":
                connection["from"] = "tuner"
        chain["connections"].append({"from": "in", "from_port": 0, "to": "tuner", "to_port": 0})
        client.rig_apply(document)
        self.wait(lambda: any(n["type"] == "nc.tuner" for n in client.rig_get()["document"]["chains"][0]["nodes"]), 3)
        time.sleep(1.5)
        self.assertEqual(self.ask("GET", "/running")[1]["undo"], 0)
        self.assertNotIn("nc.tuner", (self.rigs / "Clean.json").read_text())

    def test_a_stale_undo_is_409(self):
        self.set_gain(self.client(), -12.0)
        self.wait(lambda: self.ask("GET", "/running")[1]["undo"] == 1, 3)
        state = self.service.rig_state
        state.seq -= 1
        self.assertEqual(self.ask("POST", "/undo")[0], 409)
        state.seq += 1

    def test_new_duplicate_and_from_running(self):
        status, reply = self.ask("POST", "/library/rigs", {"name": "Blank", "from": None})
        self.assertEqual(status, 201, reply)
        self.assertEqual(self.ask("GET", "/bank")[1]["banks"], [["Clean", "Blank", "Lead"]])
        status, reply = self.ask("POST", "/library/rigs", {"name": "Blank", "from": None})
        self.assertEqual(status, 409)
        status, reply = self.ask("POST", "/library/rigs", {"name": "Dup", "from": "Lead"})
        self.assertEqual(status, 201)
        self.assertEqual(self.filed("Dup")["gain_db"], -3.0)
        self.ask("POST", "/event", {"kind": 0x10, "a": 82, "b": 127})
        self.wait(lambda: self.service.rig_state.overlay, 3)
        status, reply = self.ask("POST", "/library/rigs", {"name": "Copy", "from": ":running", "load": True})
        self.assertEqual(status, 201, reply)
        self.assertFalse(self.filed("Copy", "boost-gain").get("bypass"))
        self.wait(lambda: self.ask("GET", "/running")[1]["rig"] == "Copy", 3)
        status, reply = self.ask("PUT", "/running", {"rig": "Blank"})
        self.assertEqual(status, 200, reply)                      # the blank rig plays

    def test_renaming_the_running_rig(self):
        self.set_gain(self.client(), -12.0)
        self.wait(lambda: self.filed("Clean")["gain_db"] == -12.0, 3)
        status, reply = self.ask("POST", "/library/rigs/Clean/rename", {"to": "Sparkle"})
        self.assertEqual(status, 200, reply)
        self.wait(lambda: self.ask("GET", "/running")[1]["rig"] == "Sparkle", 3, "it wasn't renamed")
        self.wait(lambda: self.client("reader").rig_get()["document"]["name"] == "Sparkle", 3)
        self.assertEqual(self.ask("GET", "/bank")[1]["banks"], [["Lead", "Sparkle"]] )
        self.assertEqual(self.ask("GET", "/running")[1]["undo"], 1)
        self.assertEqual(self.ask("POST", "/undo")[0], 200)
        self.assertEqual(self.filed("Sparkle")["gain_db"], -6.0)
        self.assertTrue((self.root / "state" / "history" / "Sparkle.json").exists())

    def test_deleting_the_playing_rig_moves_to_its_neighbour(self):
        self.set_gain(self.client(), -12.0)
        self.wait(lambda: (self.root / "state" / "history" / "Clean.json").exists(), 3)
        self.assertEqual(self.ask("DELETE", "/library/rigs/Clean")[0], 200)
        self.wait(lambda: self.ask("GET", "/running")[1]["rig"] == "Lead", 3, "the pedal didn't move")
        self.assertFalse((self.root / "state" / "history" / "Clean.json").exists())

    def test_the_bank_routes(self):
        self.assertEqual(self.ask("PUT", "/bank", {"banks": [["Lead"], ["Clean"]]})[0], 200)
        self.assertEqual(self.ask("GET", "/bank")[1], {"banks": [["Lead"], ["Clean"]], "bank": 1, "rig": 0})
        self.assertEqual(self.ask("PUT", "/bank", {"banks": [["Nope"]]})[0], 400)
        self.assertEqual(self.ask("PUT", "/bank", {"banks": [[]]})[0], 400)
        self.assertEqual(self.ask("PUT", "/bank", {"banks": [["Lead"] * 9]})[0], 400)

    def test_playing_a_rig_that_doesnt_exist_is_404(self):
        self.assertEqual(self.ask("PUT", "/running", {"rig": "Nope"})[0], 404)

    def test_an_edit_while_pedald_is_down_is_found(self):
        self.wait(lambda: (self.root / "state" / "resume.json").exists(), 8, "no record")
        self.stop_service()
        self.set_gain(self.client(), -18.0)
        self.start_service()
        self.wait(lambda: self.filed("Clean")["gain_db"] == -18.0, 4, "the edit wasn't found")
        self.assertEqual(self.ask("GET", "/running")[1]["undo"], 1)


if __name__ == "__main__":
    unittest.main()


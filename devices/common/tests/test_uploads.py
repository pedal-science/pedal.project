"""Files over HTTP: every refusal, nothing overwritten, and a large upload in flat memory."""

import hashlib
import http.client
import json
import os
import pathlib
import socket
import tempfile
import threading
import time
import tracemalloc
import types
import unittest

from pedald import config, daemon, files
from pedald.engine import EngineError

TOKEN = "t" * 32


def model(rate=48000, name="Twin"):
    return json.dumps({"version": "0.5", "architecture": "WaveNet", "metadata": {"name": name},
                       "weights": [0.1] * 400, "sample_rate": rate}).encode()


class Engine:
    """The calls pedald makes for files, answered from the directories, as the engine's scan would."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.scan = 1
        self.refreshes = 0
        self.schema_calls = 0
        self.down = False

    def entries(self, root, kind):
        rows = []
        for directory, directories, names in os.walk(root):
            directories[:] = [d for d in directories if not d.startswith(".")]
            for name in names:
                if name.startswith("."):
                    continue
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, root)
                stat = os.stat(path)
                rows.append({"id": files.file_id(relative), "relative": relative, "path": path, "kind": kind,
                             "size": stat.st_size, "mtime": int(stat.st_mtime)})
        return sorted(rows, key=lambda row: row["relative"])

    def assets(self, refresh=False):
        if self.down:
            raise EngineError("engine_unreachable", "it has gone")
        if refresh:
            self.scan += 1
            self.refreshes += 1
        return {"ok": True, "scan": self.scan, "files_parsed": 0,
                "roots": {"models": {"readable": True, "error": None}, "irs": {"readable": True, "error": None}},
                "models": self.entries(self.cfg.models_root, "model"),
                "irs": self.entries(self.cfg.irs_root, "ir")}

    def status(self):
        if self.down:
            raise EngineError("engine_unreachable", "it has gone")
        return {"ok": True, "status": {"state": "running", "assets": {"scan": self.scan}}}

    def call(self, method, **_params):
        self.schema_calls += method == "engine.schema"
        return {"ok": True, "nodes": []}

    def close(self):
        pass

    def hello(self):
        return {"protocol": 2}

    def __getattr__(self, name):
        def refuse(*_args, **_kwargs):
            raise EngineError("nothing", f"{name}: no rigs here")
        return refuse


class Service(unittest.TestCase):
    statvfs = staticmethod(os.statvfs)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = pathlib.Path(self.dir.name)
        for name in ("rigs", "models", "irs"):
            (root / name).mkdir()
        self.models, self.irs = root / "models", root / "irs"
        (root / "token").write_text(TOKEN)
        cfg = config.Config()
        cfg.uart_device = str(root / "no-uart")
        cfg.http_host, cfg.http_port = "127.0.0.1", 0
        cfg.engine_port = 1
        cfg.engine_token_file = str(root / "token")
        cfg.rigs_root, cfg.models_root, cfg.irs_root = str(root / "rigs"), str(self.models), str(self.irs)
        cfg.state_root, cfg.cache_root = str(root / "state"), str(root / "cache")
        self.lines = []
        self.service = daemon.Service(cfg, self.lines.append)
        self.engine = Engine(cfg)
        self.service.engine = self.engine
        self.service.cost.engine = self.engine
        self.service.warm.engine = self.engine
        self.service.resume.engine = self.engine
        self.service.files.statvfs = self.statvfs
        self.thread = threading.Thread(target=self.service.run, daemon=True)
        self.thread.start()
        self.addCleanup(self.finish)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.service.files.scan_number:
            time.sleep(0.01)

    def finish(self):
        self.service.stop()
        self.thread.join(5)

    def ask(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.service.http.port, timeout=15)
        self.addCleanup(conn.close)
        conn.request(method, path, body=body, headers=dict({"Authorization": "Bearer " + TOKEN}, **(headers or {})))
        reply = conn.getresponse()
        data = reply.read()
        return reply.status, data, reply

    def put(self, path, body, headers=None):
        status, data, _ = self.ask("PUT", path, body, dict({"If-None-Match": "*"}, **(headers or {})))
        return status, json.loads(data or b"null")

    def raw(self, path, length, extra=""):
        sock = socket.create_connection(("127.0.0.1", self.service.http.port))
        self.addCleanup(sock.close)
        sock.settimeout(15)
        sock.sendall((f"PUT {path} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n"
                      f"If-None-Match: *\r\nContent-Length: {length}\r\n{extra}\r\n").encode())
        return sock

    def answer_head(self, sock):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data


class Stored(Service):
    def test_a_model_is_stored_and_the_engine_rescans(self):
        scan = self.engine.scan
        body = model()
        status, reply = self.put("/library/models/fender/Twin.nam", body)
        self.assertEqual(status, 201, reply)
        self.assertEqual(reply["id"], "fender/Twin")
        self.assertEqual(reply["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(reply["metadata"]["name"], "Twin")
        self.assertEqual(reply["scan"], scan + 1)
        self.assertEqual((self.models / "fender" / "Twin.nam").read_bytes(), body)
        self.assertEqual(oct((self.models / "fender" / "Twin.nam").stat().st_mode & 0o777), "0o644")

    def test_it_is_listed_with_its_hash_at_once(self):
        body = model()
        self.put("/library/models/Twin.nam", body)
        hashed = self.service.files.hashed
        status, data, _ = self.ask("GET", "/library/models")
        row = json.loads(data)["files"][0]
        self.assertEqual(row["id"], "Twin")
        self.assertEqual(row["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(self.service.files.hashed, hashed)   # the upload already knew it

    def test_an_ir_of_any_rate_is_stored(self):
        self.assertEqual(self.put("/library/irs/v30/57.wav", b"RIFF....WAVEfmt ")[0], 201)
        self.assertEqual(self.put("/library/irs/lin.nam", model(rate=44100))[0], 201)

    def test_a_percent_encoded_path(self):
        status, reply = self.put("/library/irs/My%20Cabs/4x12%20%C3%A9.wav", b"RIFF")
        self.assertEqual(status, 201, reply)
        self.assertTrue((self.irs / "My Cabs" / "4x12 é.wav").exists())

    def test_a_model_that_declares_no_rate_is_stored(self):
        self.assertEqual(self.put("/library/models/a.nam", b'{"weights": []}')[0], 201)

    def test_views_are_told(self):
        sock = socket.create_connection(("127.0.0.1", self.service.http.port))
        self.addCleanup(sock.close)
        sock.settimeout(5)
        sock.sendall(f"GET /events HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n\r\n".encode())
        self.answer_head(sock)
        self.put("/library/models/Told.nam", model())
        data = b""
        deadline = time.monotonic() + 5
        while b'"added"' not in data and time.monotonic() < deadline:
            data += sock.recv(65536)
        self.assertIn(b'"id": "Told"', data)

    def test_the_engine_being_down_doesnt_lose_the_file(self):
        self.engine.down = True
        status, reply = self.put("/library/models/Twin.nam", model())
        self.assertEqual(status, 201)
        self.assertIsNone(reply["scan"])
        self.assertTrue((self.models / "Twin.nam").exists())

    def test_a_rescan_by_someone_else_is_followed(self):
        (self.models / "by-hand.nam").write_bytes(model())
        self.engine.scan += 1
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.service.files.scan_number != self.engine.scan:
            time.sleep(0.02)
        ids = [row["id"] for row in json.loads(self.ask("GET", "/library/models")[1])["files"]]
        self.assertEqual(ids, ["by-hand"])

    def test_refresh(self):
        before = self.engine.refreshes
        status, data, _ = self.ask("POST", "/library/refresh", b"")
        self.assertEqual(status, 200)
        self.assertEqual(self.engine.refreshes, before + 1)
        self.assertEqual(json.loads(data)["models"], 0)

    def test_refresh_with_no_engine(self):
        self.engine.down = True
        self.assertEqual(self.ask("POST", "/library/refresh", b"")[0], 503)

    def test_the_catalogue(self):
        status, data, _ = self.ask("GET", "/catalogue")
        self.assertEqual(status, 200)
        self.assertIn("templates", json.loads(data))

    def test_status_counts_the_library(self):
        self.put("/library/irs/a.wav", b"RIFF")
        library = json.loads(self.ask("GET", "/status")[1])["library"]
        self.assertEqual((library["models"], library["irs"]), (0, 1))


class Refused(Service):
    def assertRefused(self, status, reply, wanted):
        self.assertEqual(status, wanted, reply)
        self.assertEqual(self.service.files._in_flight, {})

    def staged(self, root):
        return [name for name in os.listdir(root) if name.startswith(".")]

    def test_no_precondition_is_428(self):
        status, data, _ = self.ask("PUT", "/library/models/a.nam", model())
        self.assertEqual(status, 428)
        self.assertFalse((self.models / "a.nam").exists())

    def test_an_existing_path_is_412_and_is_left_alone(self):
        self.put("/library/models/a.nam", model(name="first"))
        before = (self.models / "a.nam").read_bytes()
        status, reply = self.put("/library/models/a.nam", model(name="second"))
        self.assertRefused(status, reply, 412)
        self.assertEqual((self.models / "a.nam").read_bytes(), before)

    def test_a_second_file_for_an_id_is_409(self):
        self.put("/library/irs/cab.wav", b"RIFF")
        status, reply = self.put("/library/irs/cab.nam", model())
        self.assertRefused(status, reply, 409)
        self.assertIn("cab.wav", reply["error"])

    def test_a_name_differing_only_in_case_is_409(self):
        self.put("/library/models/Twin.nam", model())
        status, reply = self.put("/library/models/twin.nam", model())
        # On a case-insensitive filesystem the path itself exists, and that is 412.
        self.assertIn(status, (409, 412), reply)

    def test_a_folder_that_is_a_file_is_409(self):
        self.put("/library/irs/a.wav", b"RIFF")
        status, reply = self.put("/library/irs/a.wav/b.wav", b"RIFF")
        self.assertIn(status, (409, 412), reply)

    def test_too_large_is_413_without_reading_it(self):
        cap = self.service.files.caps["models"]
        sock = self.raw("/library/models/big.nam", cap + 1, "Expect: 100-continue\r\n")
        head = self.answer_head(sock)
        self.assertIn(b"413", head.split(b"\r\n")[0])
        self.assertNotIn(b"100 Continue", head)

    def test_a_model_that_isnt_48k_is_422_and_nothing_stays(self):
        status, reply = self.put("/library/models/deep/er/slow.nam", model(rate=44100))
        self.assertRefused(status, reply, 422)
        self.assertIn("44100", reply["error"])
        self.assertEqual(os.listdir(self.models), [])     # no staged file, and no empty folders

    def test_bad_paths_are_400(self):
        for path in ("/library/models/a.wav", "/library/irs/a.txt", "/library/models/..%2Fescape.nam",
                     "/library/models/../escape.nam", "/library/models/.hidden.nam", "/library/models/a/.b/c.nam",
                     "/library/models/a//b.nam", "/library/models/%2Fetc%2Fx.nam", "/library/models/back%5Cslash.nam",
                     "/library/models/ctl%01.nam", "/library/models/bad%FF.nam", "/library/models/.nam",
                     "/library/models/" + "x" * 200 + ".nam"):
            status, reply = self.put(path, model())
            self.assertEqual(status, 400, path)
        self.assertEqual(os.listdir(self.models), [])
        self.assertFalse(os.path.exists(os.path.dirname(self.dir.name) + "/escape.nam"))

    def test_the_same_path_twice_at_once_is_409(self):
        body = model()
        sock = self.raw("/library/models/twice.nam", len(body))
        sock.sendall(body[:10])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.staged(self.models):
            time.sleep(0.01)
        status, reply = self.put("/library/models/twice.nam", body)
        self.assertEqual(status, 409, reply)
        sock.sendall(body[10:])
        self.assertIn(b"201", self.answer_head(sock).split(b"\r\n")[0])

    def test_deleting_a_file_isnt_offered(self):
        self.put("/library/irs/a.wav", b"RIFF")
        self.assertEqual(self.ask("DELETE", "/library/irs/a.wav")[0], 405)
        self.assertTrue((self.irs / "a.wav").exists())

    def test_a_connection_dropped_part_way_leaves_nothing(self):
        body = model()
        sock = self.raw("/library/models/half.nam", len(body))
        sock.sendall(body[:20])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.staged(self.models):
            time.sleep(0.01)
        self.assertEqual(self.staged(self.models)[0][:8], ".upload-")
        sock.close()
        while time.monotonic() < deadline and self.staged(self.models):
            time.sleep(0.01)
        self.assertEqual(os.listdir(self.models), [])
        self.assertEqual(self.put("/library/models/half.nam", body)[0], 201)

    def test_a_staged_file_isnt_listed(self):
        body = model()
        sock = self.raw("/library/models/half.nam", len(body))
        sock.sendall(body[:20])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.staged(self.models):
            time.sleep(0.01)
        self.ask("POST", "/library/refresh", b"")
        self.assertEqual(json.loads(self.ask("GET", "/library/models")[1])["files"], [])

    def test_a_restart_clears_what_a_power_cut_left(self):
        (self.models / ".upload-dead.part").write_bytes(b"x")
        (self.models / "kept.nam").write_bytes(model())
        self.service.files._sweep_staged("models")
        self.assertEqual(os.listdir(self.models), ["kept.nam"])


class FullCard(Service):
    @staticmethod
    def statvfs(_path):
        return types.SimpleNamespace(f_bavail=1000, f_frsize=4096)

    def test_a_full_card_is_507_before_reading(self):
        status, reply = self.put("/library/irs/a.wav", b"RIFF")
        self.assertEqual(status, 507, reply)
        self.assertEqual(os.listdir(self.irs), [])


class Downloads(Service):
    def setUp(self):
        super().setUp()
        self.body = model()
        self.put("/library/models/fender/Twin.nam", self.body)
        self.sha = hashlib.sha256(self.body).hexdigest()

    def test_the_file_with_its_hash_as_the_etag(self):
        status, data, reply = self.ask("GET", "/library/models/fender/Twin.nam")
        self.assertEqual(status, 200)
        self.assertEqual(data, self.body)
        self.assertEqual(reply.getheader("ETag"), f'"{self.sha}"')

    def test_head(self):
        status, data, reply = self.ask("HEAD", "/library/models/fender/Twin.nam")
        self.assertEqual((status, data), (200, b""))
        self.assertEqual(reply.getheader("Content-Length"), str(len(self.body)))

    def test_a_matching_etag_is_304(self):
        status, data, _ = self.ask("GET", "/library/models/fender/Twin.nam", headers={"If-None-Match": f'"{self.sha}"'})
        self.assertEqual((status, data), (304, b""))

    def test_a_file_dropped_in_by_hand_is_hashed_when_asked_for(self):
        (self.models / "hand.nam").write_bytes(b"{}")
        _, _, reply = self.ask("GET", "/library/models/hand.nam")
        self.assertEqual(reply.getheader("ETag"), f'"{hashlib.sha256(b"{}").hexdigest()}"')

    def test_missing_is_404(self):
        self.assertEqual(self.ask("GET", "/library/models/nope.nam")[0], 404)

    def test_a_link_out_of_the_root_is_404(self):
        secret = pathlib.Path(self.dir.name) / "secret.nam"
        secret.write_bytes(b"secret")
        (self.models / "out.nam").symlink_to(secret)
        status, data, _ = self.ask("GET", "/library/models/out.nam")
        self.assertEqual(status, 404)
        self.assertNotIn(b"secret", data.replace(b"out.nam", b""))

    def test_a_token_is_needed(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.service.http.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/library/models/fender/Twin.nam")
        self.assertEqual(conn.getresponse().status, 401)


class LargeUpload(Service):
    def test_64_mib_in_flat_memory(self):
        size = self.service.files.caps["irs"]
        self.assertEqual(size, 64 << 20)
        block = os.urandom(1 << 16)
        digest = hashlib.sha256()
        sock = self.raw("/library/irs/huge.wav", size)
        tracemalloc.start()
        self.addCleanup(tracemalloc.stop)
        for _ in range(size // len(block)):
            sock.sendall(block)
            digest.update(block)
        head = self.answer_head(sock)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertIn(b"201", head.split(b"\r\n")[0])
        self.assertLess(peak, 4 << 20)
        self.assertEqual((self.irs / "huge.wav").stat().st_size, size)
        with open(self.irs / "huge.wav", "rb") as handle:
            self.assertEqual(hashlib.file_digest(handle, "sha256").hexdigest(), digest.hexdigest())

    def test_expect_continue_is_answered_when_reading_starts(self):
        body = model()
        sock = self.raw("/library/models/asked.nam", len(body), "Expect: 100-continue\r\n")
        self.assertIn(b"100 Continue", self.answer_head(sock))
        sock.sendall(body)
        self.assertIn(b"201", self.answer_head(sock).split(b"\r\n")[0])

    def test_expect_continue_refused_early_saves_the_upload(self):
        self.put("/library/models/there.nam", model())
        sock = self.raw("/library/models/there.nam", 1 << 20, "Expect: 100-continue\r\n")
        head = self.answer_head(sock)
        self.assertIn(b"412", head.split(b"\r\n")[0])


class EngineComesBack(Service):
    def wait_for(self, check):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not check():
            time.sleep(0.02)
        self.assertTrue(check())

    def test_the_templates_are_judged_on_connecting_and_again_after_a_restart(self):
        self.wait_for(lambda: self.engine.schema_calls == 1)
        self.engine.scan = 0                  # a new process's scans start again
        self.wait_for(lambda: self.engine.schema_calls == 2)
        self.wait_for(lambda: self.service.files.scan_number == 0)

    def test_an_upload_doesnt_judge_them_again(self):
        self.wait_for(lambda: self.engine.schema_calls == 1)
        for index in range(3):
            self.put(f"/library/irs/{index}.wav", b"RIFF")
        self.assertEqual(self.engine.schema_calls, 1)


if __name__ == "__main__":
    unittest.main()

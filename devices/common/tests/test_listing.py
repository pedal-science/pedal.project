"""What a library listing adds to the engine's scan, and that hashing happens once."""

import hashlib
import json
import os
import pathlib
import tempfile
import unittest

from pedald import files


def model_bytes(rate=48000, metadata=None):
    metadata = metadata or {"name": "Top", "gear_type": "amp"}
    nested = {"metadata": {"name": "Inner"}, "weights": [0.5] * 50}
    return json.dumps({"version": "0.5", "architecture": "SlimmableContainer",
                       "config": {"submodels": [nested]}, "weights": [0.25] * 200,
                       "metadata": metadata, "sample_rate": rate}).encode()


def entry(root, relative):
    stat = os.stat(os.path.join(root, relative))
    return {"id": files.file_id(relative), "relative": relative, "path": os.path.join(root, relative),
            "size": stat.st_size, "mtime": int(stat.st_mtime), "kind": "model", "sample_rate": 48000.0}


class Listing(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = pathlib.Path(self.dir.name)
        self.models, self.irs = root / "models", root / "irs"
        self.models.mkdir()
        self.irs.mkdir()
        (self.models / "a.nam").write_bytes(model_bytes())
        (self.models / "group").mkdir()
        (self.models / "group" / "b.nam").write_bytes(model_bytes(metadata={"name": "B"}))
        (self.irs / "c.wav").write_bytes(b"RIFF....WAVE")
        self.cache = root / "cache" / "hashes.json"
        self.scan_number = 0

    def service(self):
        return files.Files({"models": str(self.models), "irs": str(self.irs)},
                           {"models": 1 << 20, "irs": 1 << 20}, str(self.cache))

    def scan(self):
        self.scan_number += 1
        return {"scan": self.scan_number,
                "roots": {"models": {"readable": True, "error": None}, "irs": {"readable": True, "error": None}},
                "models": [entry(str(self.models), "a.nam"), entry(str(self.models), "group/b.nam")],
                "irs": [entry(str(self.irs), "c.wav")]}

    def test_a_file_not_hashed_yet_says_so(self):
        library = self.service()
        library.set_scan(self.scan())
        listing = library.listing("models")
        self.assertEqual(listing["hashing"], 2)
        self.assertIsNone(listing["files"][0]["sha256"])

    def test_before_the_first_scan_there_is_no_listing(self):
        self.assertIsNone(self.service().listing("models"))

    def test_a_listing_has_hash_and_metadata_and_no_path(self):
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        listing = library.listing("models")
        self.assertEqual(listing["hashing"], 0)
        first = listing["files"][0]
        self.assertEqual(first["sha256"], hashlib.sha256(model_bytes()).hexdigest())
        self.assertEqual(first["metadata"]["name"], "Top")   # the file's own, not a submodel's
        self.assertEqual(first["sample_rate"], 48000.0)
        self.assertNotIn("path", first)

    def test_a_second_listing_hashes_nothing(self):
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        self.assertEqual(library.hashed, 3)
        library.listing("models")
        library.set_scan(self.scan())
        library._hash_pass()
        library.listing("models")
        self.assertEqual(library.hashed, 3)

    def test_a_restart_hashes_nothing(self):
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        again = self.service()
        again.set_scan(self.scan())
        again._hash_pass()
        self.assertEqual(again.hashed, 0)
        self.assertEqual(again.listing("irs")["hashing"], 0)

    def test_a_changed_file_is_hashed_again(self):
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        (self.models / "a.nam").write_bytes(model_bytes(metadata={"name": "Changed!"}))
        library.set_scan(self.scan())
        self.assertIsNone(library.listing("models")["files"][0]["sha256"])
        library._hash_pass()
        self.assertEqual(library.hashed, 4)
        self.assertEqual(library.listing("models")["files"][0]["metadata"]["name"], "Changed!")

    def test_a_file_gone_leaves_the_cache(self):
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        reply = self.scan()
        reply["models"] = reply["models"][:1]
        library.set_scan(reply)
        library._hash_pass()
        self.assertNotIn("group/b.nam", json.loads(self.cache.read_text())["models"])

    def test_a_bad_cache_is_only_a_cache(self):
        self.cache.parent.mkdir()
        self.cache.write_text("{not json")
        library = self.service()
        library.set_scan(self.scan())
        library._hash_pass()
        self.assertEqual(library.hashed, 3)

    def test_the_thread_comes_and_goes(self):
        library = self.service()
        library.start()
        self.assertEqual(len(library.threads()), 1)
        library.stop()
        self.assertEqual(library.threads(), [])


class Sniffing(unittest.TestCase):
    def write(self, data):
        handle = tempfile.NamedTemporaryFile(suffix=".nam", delete=False)
        self.addCleanup(os.unlink, handle.name)
        handle.write(data)
        handle.close()
        return handle.name

    def test_the_rate_at_the_tail(self):
        self.assertEqual(files.declared_rate(self.write(model_bytes(44100))), 44100)

    def test_no_rate_is_none(self):
        self.assertIsNone(files.declared_rate(self.write(b'{"weights": [1, 2]}')))

    def test_metadata_past_the_cap_or_broken_is_none(self):
        self.assertIsNone(files.nam_metadata(self.write(b'{"metadata": "a string"}')))
        self.assertIsNone(files.nam_metadata(self.write(b'{"metadata": {"name": ')))
        self.assertIsNone(files.nam_metadata(self.write(b'')))


if __name__ == "__main__":
    unittest.main()

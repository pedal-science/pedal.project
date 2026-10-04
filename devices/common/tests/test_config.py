"""Tests for pedald's configuration loader.

The loader has to hold two lines at once: pedald.json may set only the service's own keys, and
the engine's port, token file and three roots may come from nowhere but namchaind.json (R12 in
docs/pedal-service.md). These tests write both files into a temporary directory and check the
defaults, the engine's values, and every refusal the loader promises.

Run with:
    python3 -m unittest discover -s devices/common/tests -t devices/common/tests \
        -p 'test_config.py' -v
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald.config import Config, ConfigError  # noqa: E402


def engine_document(**overrides):
    """A namchaind.json's five values as the service reads them, with room to move them."""
    document = {
        "tcp_port": 47810,
        "tcp_token_file": "/etc/namchain/token",
        "rigs_root": "/var/lib/pedal/library/rigs",
        "models_root": "/var/lib/pedal/library/models",
        "irs_root": "/var/lib/pedal/library/irs",
    }
    document.update(overrides)
    return document


class ConfigTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.pedal_path = os.path.join(self.directory, "pedald.json")
        self.engine_path = self.write_engine(engine_document())

    def write(self, name, contents):
        """Write a file into the temporary directory; `contents` is text as it stands."""
        path = os.path.join(self.directory, name)
        with open(path, "w") as f:
            f.write(contents)
        return path

    def write_json(self, name, document):
        return self.write(name, json.dumps(document))

    def write_engine(self, document, name="namchaind.json"):
        return self.write_json(name, document)

    def write_pedal(self, document):
        return self.write_json("pedald.json", document)

    def load(self, pedal=None):
        """Load the pedald.json written for this test, or the one at self.pedal_path."""
        return Config.load(pedal or self.pedal_path, self.engine_path)

    def test_defaults_are_the_documented_ones(self):
        self.write_pedal({})
        config = self.load()
        self.assertEqual(config.uart_device, "/dev/ttyAMA0")
        self.assertEqual(config.uart_baud, 115200)
        self.assertEqual(config.http_host, "0.0.0.0")
        self.assertEqual(config.http_port, 47820)
        self.assertEqual(config.max_model_bytes, 16 << 20)
        self.assertEqual(config.max_ir_bytes, 64 << 20)
        self.assertEqual(config.max_rig_bytes, 1 << 20)
        self.assertEqual(config.log_level, "info")
        self.assertEqual(config.engine_host, "127.0.0.1")
        self.assertEqual(config.state_root, "/var/lib/pedal/state")

    def test_engine_values_come_from_namchaind(self):
        self.write_engine(
            engine_document(
                tcp_port=12345,
                tcp_token_file=os.path.join(self.directory, "token"),
                rigs_root="/srv/rigs",
                models_root="/srv/models",
                irs_root="/srv/irs",
            )
        )
        self.write_pedal({})
        config = self.load()
        self.assertEqual(config.engine_host, "127.0.0.1")
        self.assertEqual(config.engine_port, 12345)
        self.assertEqual(config.engine_token_file, os.path.join(self.directory, "token"))
        self.assertEqual(config.rigs_root, "/srv/rigs")
        self.assertEqual(config.models_root, "/srv/models")
        self.assertEqual(config.irs_root, "/srv/irs")

    def test_the_service_keys_are_read(self):
        self.write_pedal(
            {
                "uart_device": "/dev/ttyS0",
                "uart_baud": 921600,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "max_model_bytes": 1024,
                "max_ir_bytes": 2048,
                "max_rig_bytes": 512,
                "log_level": "debug",
                "engine_host": "10.0.0.2",
                "state_root": "/tmp/pedal-state",
            }
        )
        config = self.load()
        self.assertEqual(config.uart_device, "/dev/ttyS0")
        self.assertEqual(config.uart_baud, 921600)
        self.assertEqual(config.http_host, "127.0.0.1")
        self.assertEqual(config.http_port, 8080)
        self.assertEqual(config.max_model_bytes, 1024)
        self.assertEqual(config.max_ir_bytes, 2048)
        self.assertEqual(config.max_rig_bytes, 512)
        self.assertEqual(config.log_level, "debug")
        self.assertEqual(config.engine_host, "10.0.0.2")
        self.assertEqual(config.state_root, "/tmp/pedal-state")
        # The engine's side is untouched by any of it.
        self.assertEqual(config.engine_port, 47810)
        self.assertEqual(config.rigs_root, "/var/lib/pedal/library/rigs")

    def test_an_unknown_key_is_an_error_naming_it(self):
        self.write_pedal({"uart_baud_rate": 9600})
        with self.assertRaises(ConfigError) as caught:
            self.load()
        self.assertIn("uart_baud_rate", str(caught.exception))

    def test_a_misspelt_key_is_not_silently_the_default(self):
        # The whole point of refusing unknown keys: this file looks right and is not.
        self.write_pedal({"http_prot": 47820})
        with self.assertRaises(ConfigError) as caught:
            self.load()
        self.assertIn("http_prot", str(caught.exception))

    def test_the_engine_values_are_not_overridable_from_pedald(self):
        for key in ("engine_port", "engine_token_file", "rigs_root", "models_root", "irs_root",
                    "tcp_port", "tcp_token_file"):
            with self.subTest(key=key):
                self.write_pedal({key: "/somewhere/else" if "root" in key else 1})
                with self.assertRaises(ConfigError) as caught:
                    self.load()
                self.assertIn(key, str(caught.exception))

    def test_a_missing_pedald_file_raises(self):
        missing = os.path.join(self.directory, "not-there.json")
        with self.assertRaises(ConfigError):
            Config.load(missing, self.engine_path)

    def test_a_missing_engine_file_raises(self):
        self.write_pedal({})
        missing = os.path.join(self.directory, "not-there.json")
        with self.assertRaises(ConfigError):
            Config.load(self.pedal_path, missing)

    def test_malformed_json_raises(self):
        self.write("pedald.json", "{ this is not json ")
        with self.assertRaises(ConfigError):
            self.load()

    def test_an_engine_file_missing_a_key_raises(self):
        document = engine_document()
        del document["tcp_port"]
        self.write_engine(document)
        self.write_pedal({})
        with self.assertRaises(ConfigError) as caught:
            self.load()
        self.assertIn("tcp_port", str(caught.exception))

    def test_a_value_of_the_wrong_type_raises(self):
        self.write_pedal({"http_port": "47820"})
        with self.assertRaises(ConfigError) as caught:
            self.load()
        self.assertIn("http_port", str(caught.exception))

    def test_an_out_of_range_value_raises(self):
        self.write_pedal({"http_port": 70000})
        with self.assertRaises(ConfigError):
            self.load()

    def test_an_empty_value_raises(self):
        self.write_pedal({"log_level": ""})
        with self.assertRaises(ConfigError):
            self.load()

    def test_token_trims_the_file_and_is_read_each_time(self):
        token_path = self.write("token", "  s3cret-token\n")
        self.write_engine(engine_document(tcp_token_file=token_path))
        self.write_pedal({})
        config = self.load()
        self.assertEqual(config.token(), "s3cret-token")
        # Rotating the token is a file change and a restart, not a new Config object.
        self.write("token", "rotated-token\n")
        self.assertEqual(config.token(), "rotated-token")

    def test_token_prefers_systemds_credential_over_the_root_only_file(self):
        # The unit runs as `pedal` and LoadCredential hands it a readable copy, because the
        # file it points at is root's 0600. The credential wins when it is there.
        credential_dir = os.path.join(self.directory, "credentials")
        os.makedirs(credential_dir)
        with open(os.path.join(credential_dir, "token"), "w") as f:
            f.write("from-the-credential\n")
        self.write_engine(engine_document(tcp_token_file=os.path.join(self.directory, "gone")))
        self.write_pedal({})
        config = self.load()
        previous = os.environ.get("CREDENTIALS_DIRECTORY")
        os.environ["CREDENTIALS_DIRECTORY"] = credential_dir
        try:
            self.assertEqual(config.token(), "from-the-credential")
        finally:
            if previous is None:
                del os.environ["CREDENTIALS_DIRECTORY"]
            else:
                os.environ["CREDENTIALS_DIRECTORY"] = previous

    def test_token_reports_an_unreadable_file(self):
        self.write_engine(engine_document(tcp_token_file=os.path.join(self.directory, "gone")))
        self.write_pedal({})
        config = self.load()
        with self.assertRaises(ConfigError):
            config.token()

    def test_token_reports_a_file_that_is_not_text(self):
        path = os.path.join(self.directory, "token")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\x00not a token\n")
        self.write_engine(engine_document(tcp_token_file=path))
        self.write_pedal({})
        with self.assertRaises(ConfigError):
            self.load().token()


if __name__ == "__main__":
    unittest.main()

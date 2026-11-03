#!/usr/bin/env python3
"""scripts/public-check: planted values are caught, reported without being repeated, and allowed
only where a repository says so."""

import importlib.machinery
import importlib.util
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "public-check"
loader = importlib.machinery.SourceFileLoader("public_check", str(SCRIPT))
spec = importlib.util.spec_from_loader("public_check", loader)
public_check = importlib.util.module_from_spec(spec)
loader.exec_module(public_check)

# Planted, and made up: the documentation prefixes, and a locally administered MAC address.
LAN = b"192.168.55.23"
IPV6 = b"2a02:ffff:1234:0:1:2:3:4"
MAC = b"02:11:22:33:44:55"
WIFI = "planted-network-name"


class Patterns(unittest.TestCase):
    def kinds(self, line, live=None):
        return public_check.findings_in(line, live or {})

    def test_a_lan_address(self):
        self.assertEqual(self.kinds(b"inet " + LAN + b"/24 brd"), ["LAN address"])

    def test_a_global_ipv6_address(self):
        self.assertEqual(self.kinds(b"inet6 " + IPV6 + b"/64"), ["global IPv6 address"])

    def test_a_mac_address(self):
        self.assertEqual(self.kinds(b"link/ether " + MAC), ["MAC address"])

    def test_secrets(self):
        self.assertEqual(self.kinds(b"-----BEGIN OPENSSH PRIVATE KEY-----"), ["private key"])
        self.assertEqual(self.kinds(b"token=ghp_" + b"a" * 36), ["GitHub token"])

    def test_this_households_own_details(self):
        self.assertEqual(self.kinds(b"joined " + WIFI.encode(), {"Wi-Fi name": WIFI}), ["Wi-Fi name"])

    def test_what_is_not_a_leak(self):
        for line in (
            b"10.0.0.0/8 and 192.168.0.0/16",        # networks
            b"virbr0 192.168.122.1, docker0 172.17.0.1",
            b"inet6 2001:db8:1:2:3:4:5:6",           # the documentation prefix
            b"link/ether 00:00:00:00:00:00",
            b"kernel 7.0.0-1017 at 12:30:45, version 10.2.1",
            b"Rik Hemsley <rik@hemsley.cc>",         # the owner is content to publish these
        ):
            self.assertEqual(self.kinds(line), [], line)


class Repository(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.repo = self.dir.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        self.git("config", "core.hooksPath", "/dev/null")
        self.commit("clean.txt", b"nothing here\n")
        self.first = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True, check=True).stdout

    def commit(self, path, content, message="a commit"):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(content)
        self.git("add", path)
        self.git("commit", "-q", "-m", message)

    def added(self):
        return public_check.scan_commits(self.repo, [f"{self.first}..HEAD"], {}, public_check.allowed_paths(self.repo))

    def test_a_commit_that_adds_one_is_found_on_its_line(self):
        self.commit("logs/run.txt", b"ok\nwlan0 " + LAN + b"\n")
        self.assertEqual(self.added(), [("logs/run.txt", 2, "LAN address")])

    def test_binary_files_are_read_too(self):
        self.commit("logs/console.log", b"\x00\x01\xff binary\nether " + MAC + b"\n")
        self.assertEqual([kind for _, _, kind in self.added()], ["MAC address"])

    def test_a_commit_message_is_read_too(self):
        self.commit("a.txt", b"fine\n", message="moved it to " + LAN.decode())
        self.assertEqual(self.added(), [("commit message", 0, "LAN address")])

    def test_removing_one_is_not_a_finding(self):
        self.commit("a.txt", LAN + b"\n")
        base = self.git("rev-parse", "HEAD").strip()
        self.commit("a.txt", b"gone\n")
        self.assertEqual(public_check.scan_commits(self.repo, [f"{base}..HEAD"], {}, []), [])

    def test_a_tree_scan_finds_what_is_already_there(self):
        self.commit("a.txt", MAC + b"\n")
        self.assertEqual(public_check.scan_tree(self.repo, {}, []), [("a.txt", 1, "MAC address")])

    def test_the_allow_file_is_by_path_and_ignores_reasons(self):
        self.commit(".public-check-allow", b"# a comment\nlogs/*   # old logs\n")
        self.commit("logs/old/run.txt", MAC + b"\n")
        self.commit("elsewhere.txt", MAC + b"\n")
        self.assertEqual(self.added(), [("elsewhere.txt", 1, "MAC address")])

    def test_the_report_never_repeats_a_value(self):
        self.commit("a.txt", b"inet " + LAN + b" on " + WIFI.encode() + b"\n")
        done = subprocess.run(
            [str(SCRIPT), "--no-live", "--repo", self.repo, "--range", f"{self.first}..HEAD"],
            capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 1)
        self.assertIn("a.txt", done.stdout)
        self.assertNotIn(LAN.decode(), done.stdout + done.stderr)

    def test_a_clean_push_passes(self):
        self.commit("a.txt", b"fine\n")
        done = subprocess.run([str(SCRIPT), "--no-live", "--repo", self.repo, "--range", f"{self.first}..HEAD"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stdout)


if __name__ == "__main__":
    unittest.main()

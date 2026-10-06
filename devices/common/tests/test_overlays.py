"""The overlay loads: one lock, because dtoverlay is not reentrant.

dtoverlay keeps its stack of applied overlays in /tmp/.dtoverlays and refuses to start when that
directory is already there, so two services loading an overlay at boot race for it. On 2026-10-06
`pedal-uart` failed with `Failed to create '/tmp/.dtoverlays' - 17` while `pedal-codec` was running,
and the link came up only because the firmware had honoured `enable_uart=1` by itself.

`dtoverlay-locked` is the fix, and these tests hold both halves of it: every caller in the tree goes
through that helper, and the helper really does wait for the lock before it runs anything. The
second half needs `flock`, which the device has and macOS does not, so it is worth running there.
"""
import fcntl
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = ROOT / "devices/common/rootfs/usr/local/sbin/dtoverlay-locked"

# A call, not a mention: `dtoverlay-locked -d ...` has a dash after the name and does not match, and
# comment lines are skipped, so prose about dtoverlay is free.
INVOCATION = re.compile(r"(?<![\w-])dtoverlay\s")


def callers_of_dtoverlay():
    """Every line in the image's rootfs that invokes dtoverlay itself."""
    found = []
    for path in sorted(ROOT.glob("devices/*/rootfs/**/*")):
        if not path.is_file() or path.name == HELPER.name or path.is_symlink():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            code = line.strip()
            if not code or code.startswith("#"):
                continue
            if INVOCATION.search(code):
                found.append("%s:%d: %s" % (path.relative_to(ROOT), number, code))
    return found


class TheOverlayLoads(unittest.TestCase):
    def test_every_caller_goes_through_the_locked_helper(self):
        self.assertEqual(
            [], callers_of_dtoverlay(),
            "these invoke dtoverlay directly; dtoverlay is not reentrant, so they have to go "
            "through %s (see its comment)" % HELPER.name)

    def test_the_helper_is_there_and_executable(self):
        self.assertTrue(HELPER.is_file(), "%s is missing" % HELPER)
        self.assertTrue(HELPER.stat().st_mode & stat.S_IXUSR, "%s is not executable" % HELPER)

    def test_the_stub_behaves_like_dtoverlay(self):
        """The hazard is real: the stub the next test uses refuses to start on an existing stack."""
        with tempfile.TemporaryDirectory() as tmp:
            stack = os.path.join(tmp, ".dtoverlays")
            stub = make_stub(tmp, stack)
            os.mkdir(stack)
            failed = subprocess.run([stub], capture_output=True, text=True)
            self.assertEqual(1, failed.returncode)
            self.assertIn("Failed to create '%s'" % stack, failed.stderr)

    @unittest.skipUnless(shutil.which("flock"),
                         "no flock on this machine (macOS has none): run this on the device")
    def test_the_helper_waits_for_the_lock_and_passes_its_arguments_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = os.path.join(tmp, "pedal-dtoverlay.lock")
            stub = make_stub(tmp, os.path.join(tmp, ".dtoverlays"))
            env = dict(os.environ,
                       PATH=os.path.dirname(stub) + os.pathsep + os.environ["PATH"],
                       PEDAL_DTOVERLAY_LOCK=lock)

            holder = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(holder, fcntl.LOCK_EX)
            try:
                loading = subprocess.Popen([str(HELPER), "-d", "/somewhere", "an-overlay"],
                                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                time.sleep(0.4)
                self.assertIsNone(loading.poll(), "the helper ran while the lock was held")
            finally:
                fcntl.flock(holder, fcntl.LOCK_UN)
                os.close(holder)

            output = loading.communicate(timeout=10)[0].decode()
            self.assertEqual(0, loading.returncode, output)
            self.assertIn("stub dtoverlay: -d /somewhere an-overlay", output)


def make_stub(tmp, stack):
    """A dtoverlay that keeps a stack directory the way the real one does."""
    bin_dir = os.path.join(tmp, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    stub = os.path.join(bin_dir, "dtoverlay")
    pathlib.Path(stub).write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        if [[ -e {stack} ]]; then
          echo "Failed to create '{stack}' - 17" >&2
          exit 1
        fi
        mkdir {stack}
        sleep 0.3
        rmdir {stack}
        echo "stub dtoverlay: $*"
        """))
    os.chmod(stub, 0o755)
    return stub


if __name__ == "__main__":
    unittest.main()

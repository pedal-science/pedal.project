"""Resume: come back after a power cycle with the rig you left (docs/pedal-service.md, "Resume").

This is `pedal-resume`'s job, folded into the service so that there is one writer of
`last.json` rather than two. `seed()` runs as root before namchaind starts (its
`ExecStartPre`), so it is also the place that makes the tree under `/var/lib/pedal` belong
to the service's user; `tick()` runs in the service, at the same 1 Hz the engine is polled.

The save rule is the design's, with one addition the engine made necessary: watch
`generation`, `params_applied` **and the rig the engine says it is running** (`rig`,
`rig_name`, `rig_source`), read `rig.get` once those have been still for `settle_s`, and write
only if the document differs from what is already on the card. The extra three are not
decoration: a `rig.load` — what the service itself does for a footswitch, and what ljoss does
when it sends a rig — moves the rig's path and name and leaves `generation` and
`params_applied` exactly where they were (measured against namchaind 2026-10-02, `--backend
null`). Watching the counters alone would never save a switch. A knob drag, meanwhile, moves
neither the path nor the name, so the counters are still what make that one write instead of
hundreds.
"""
import json
import os
import shutil
import subprocess


def write_atomic(path, text):
    """Temp file, fsync, rename, fsync the directory — a power cut costs the write, not the file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if os.path.exists(path):
        shutil.copy2(path, os.path.join(directory, "last.prev.json"))
    os.replace(tmp, path)
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def canonical(document):
    """A stable rendering, so 'did the document change' is a string compare."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


class Resume:
    def __init__(self, engine, rigs_root, *, name="last.json",
                 default_rig="/etc/pedal/default-rig.json", settle_s=2.0,
                 state_root="/var/lib/pedal/state", owner="pedal", log=None):
        self.engine = engine
        self.rigs_root = rigs_root
        self.name = name
        self.default_rig = default_rig
        self.settle_s = settle_s
        self.state_root = state_root
        self.owner = owner
        self.log = log or (lambda _msg: None)
        self.written = None       # canonical form of the document on the card
        self.last_key = None      # the engine's own account of what is running, as last seen
        self.quiet_since = None   # when that key last changed
        self.saved_key = None     # the key we have already saved for

    # ------------------------------------------------------------------ seed (root)
    def _own(self, path):
        """Give the service's user the directories it writes. Best effort, root only: seed
        runs from namchaind's ExecStartPre, which is root, and the design asks it to keep the
        tree that way so the service itself never has to be root."""
        if os.geteuid() != 0:
            return
        try:
            subprocess.run(["chown", "-R", f"{self.owner}:{self.owner}", path],
                           check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"could not chown {path} to {self.owner}: {exc}")

    def seed(self):
        path = os.path.join(self.rigs_root, self.name)
        os.makedirs(self.rigs_root, exist_ok=True)
        os.makedirs(self.state_root, exist_ok=True)
        self._own(self.rigs_root)
        self._own(self.state_root)
        if os.path.exists(path):
            self.log(f"resuming {path}")
            return 0
        with open(self.default_rig) as handle:
            write_atomic(path, handle.read())
        self.log(f"no saved rig yet; seeded {path} from {self.default_rig}")
        return 0

    # ------------------------------------------------------------------ run (the service)
    def running_document(self):
        try:
            reply = self.engine.rig_get()
        except Exception as exc:                      # EngineError; never fatal here
            self.log(f"rig.get failed: {exc}")
            return None
        document = reply.get("document")
        return document if isinstance(document, dict) else None

    def tick(self, now_ms, status):
        """One pass of the save rule. `status` is an engine.status report; never raises."""
        key = (status.get("generation"), status.get("params_applied"), status.get("rig"),
               status.get("rig_name"), status.get("rig_source"))
        if key != self.last_key:
            self.last_key = key
            self.quiet_since = now_ms
            return
        if key == self.saved_key:
            return
        if self.quiet_since is None or now_ms - self.quiet_since < self.settle_s * 1000:
            return
        document = self.running_document()
        if document is None:
            return
        text = canonical(document)
        if text == self.written:
            self.saved_key = key
            return
        path = os.path.join(self.rigs_root, self.name)
        try:
            write_atomic(path, json.dumps(document, indent=2) + "\n")
        except OSError as exc:
            self.log(f"could not save {path}: {exc}")
            return
        self.written = text
        self.saved_key = key
        self.log(f"saved {path} (generation {key[0]}, params_applied {key[1]}, rig {key[3]!r})")

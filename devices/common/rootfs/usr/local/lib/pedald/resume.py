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


def write_atomic_plain(path, text):
    """`write_atomic` without the resume-only step of keeping the previous file as last.prev."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def strip_ephemeral(document):
    """`document` without the nodes a client mounted around a view of its own.

    The tuner is a UI element, not a block (namchain docs/tuner.md): while its view is up a client
    puts one `nc.tuner` after each chain's input, marked `meta.ephemeral`, and that node's output is
    silence -- which is how a pedal tuner mutes the rig. Saving that document as it stands would
    bring the pedal back from a power cycle *muted*, playing a node nobody can see in any editor.

    So the resume record is the document the player left, without them. The wiring is healed the way
    the client mounted it: each consumer of an ephemeral node is repointed at whatever fed it, and
    the node goes with its own wires. A return value of `document` itself when there was nothing to
    do keeps the caller's "did it change" comparison honest.
    """
    def strip_graph(graph):
        nodes = graph.get("nodes")
        connections = graph.get("connections")
        if not isinstance(nodes, list) or not isinstance(connections, list):
            return graph, False
        ephemeral = {n.get("id") for n in nodes
                     if isinstance(n, dict) and isinstance(n.get("meta"), dict)
                     and n["meta"].get("ephemeral")}
        ephemeral.discard(None)
        if not ephemeral:
            return graph, False
        source, source_port, healed = {}, {}, []
        for c in connections:
            if not isinstance(c, dict):
                continue
            if c.get("to") in ephemeral and c["to"] not in source:
                source[c["to"]] = c.get("from")
                source_port[c["to"]] = c.get("from_port", 0)
        for c in connections:
            if not isinstance(c, dict):
                continue
            if c.get("to") in ephemeral:
                continue
            if c.get("from") in ephemeral:
                origin = c["from"]
                if origin not in source:
                    continue
                c = dict(c)
                c["from"] = source[origin]
                if source_port[origin] != 0 or "from_port" in c:
                    c["from_port"] = source_port[origin]
            healed.append(c)
        out = dict(graph)
        out["nodes"] = [n for n in nodes
                        if not (isinstance(n, dict) and n.get("id") in ephemeral)]
        out["connections"] = healed
        return out, True

    chains = document.get("chains")
    if not isinstance(chains, list):
        out, changed = strip_graph(document)
        return out if changed else document
    stripped, changed = [], False
    for chain in chains:
        if isinstance(chain, dict):
            chain, one = strip_graph(chain)
            changed = changed or one
        stripped.append(chain)
    if not changed:
        return document
    out = dict(document)
    out["chains"] = stripped
    return out


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
        # A client's view node is never part of the rig that comes back (namchain docs/tuner.md):
        # saving it would boot the pedal muted, with a node no editor draws.
        document = strip_ephemeral(document)
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

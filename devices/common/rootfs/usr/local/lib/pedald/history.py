"""One undo history per rig, on the card (docs/pedal-service.md, "Keeping the rig").

A step holds a delta with both directions, at the level of a node, so a step is small however large the
rig is. `delta` and `apply` are pure. `History` keeps each rig's stacks, and is told about edits as they
land: one gesture, or a run of edits to one control with gaps under 1.5 s, is one step.
"""

import copy
import json
import os
import time

from .resume import write_atomic_plain

MAX_STEPS = 100
MAX_RIG_BYTES = 64 << 10
MAX_TOTAL_BYTES = 2 << 20
GAP_S = 1.5


def _by_id(items):
    return {item.get("id"): item for item in items if isinstance(item, dict)}


def _chain_delta(a, b):
    out = {}
    fields = {key: [a.get(key), b.get(key)] for key in set(a) | set(b)
              if key not in ("nodes", "id") and a.get(key) != b.get(key)}
    if fields:
        out["fields"] = fields
    nodes_a, nodes_b = _by_id(a.get("nodes") or ()), _by_id(b.get("nodes") or ())
    nodes = {node: [nodes_a.get(node), nodes_b.get(node)] for node in set(nodes_a) | set(nodes_b)
             if nodes_a.get(node) != nodes_b.get(node)}
    if nodes:
        out["nodes"] = nodes
    order_a, order_b = list(nodes_a), list(nodes_b)
    if order_a != order_b:
        out["order"] = [order_a, order_b]
    return out


def delta(a, b):
    """What takes document `a` to document `b`, and back. Empty when they are the same."""
    out = {}
    fields = {key: [a.get(key), b.get(key)] for key in set(a) | set(b)
              if key != "chains" and a.get(key) != b.get(key)}
    if fields:
        out["fields"] = fields
    chains_a, chains_b = a.get("chains"), b.get("chains")
    if not isinstance(chains_a, list) or not isinstance(chains_b, list):
        if chains_a != chains_b:
            out.setdefault("fields", {})["chains"] = [chains_a, chains_b]
        return out
    by_a, by_b = _by_id(chains_a), _by_id(chains_b)
    chains = {}
    for chain in set(by_a) | set(by_b):
        if chain not in by_a or chain not in by_b:
            chains[chain] = {"whole": [by_a.get(chain), by_b.get(chain)]}
        else:
            one = _chain_delta(by_a[chain], by_b[chain])
            if one:
                chains[chain] = one
    if chains:
        out["chains"] = chains
    if list(by_a) != list(by_b):
        out["order"] = [list(by_a), list(by_b)]
    return out


def _put(target, key, value):
    if value is None:
        target.pop(key, None)
    else:
        target[key] = copy.deepcopy(value)


def _apply_chain(chain, change, side):
    for key, pair in (change.get("fields") or {}).items():
        _put(chain, key, pair[side])
    nodes = _by_id(chain.get("nodes") or ())
    for node, pair in (change.get("nodes") or {}).items():
        if pair[side] is None:
            nodes.pop(node, None)
        else:
            nodes[node] = copy.deepcopy(pair[side])
    order = change["order"][side] if "order" in change else list(nodes)
    chain["nodes"] = [nodes[node] for node in order if node in nodes]
    chain["nodes"] += [nodes[node] for node in nodes if node not in order]


def apply(document, change, forwards=True):
    """`document` with a delta applied. Backwards is what undo does. The input isn't changed."""
    side = 1 if forwards else 0
    out = copy.deepcopy(document)
    for key, pair in (change.get("fields") or {}).items():
        _put(out, key, pair[side])
    if "chains" in change or "order" in change:
        chains = _by_id(out.get("chains") or ())
        for chain, one in (change.get("chains") or {}).items():
            if "whole" in one:
                if one["whole"][side] is None:
                    chains.pop(chain, None)
                else:
                    chains[chain] = copy.deepcopy(one["whole"][side])
            elif chain in chains:
                _apply_chain(chains[chain], one, side)
        order = change["order"][side] if "order" in change else list(chains)
        out["chains"] = [chains[chain] for chain in order if chain in chains]
        out["chains"] += [chains[chain] for chain in chains if chain not in order]
    return out


class History:
    def __init__(self, root, log=None, clock=time.monotonic, wall=time.time):
        self.root = root
        self.log = log or (lambda _message: None)
        self.clock = clock
        self.wall = wall
        self.rig = None
        self.undo_steps = []         # oldest first
        self.redo_steps = []         # the next redo last
        self._open = None            # the step still growing: {before, gesture, keys, last}

    def _path(self, rig):
        return os.path.join(self.root, rig + ".json")

    # ------------------------------------------------------------------ which rig
    def use(self, rig):
        """Make this rig's history the current one. A step still growing is closed against its stored
        state by `close` first, which the daemon does when it saves."""
        if rig == self.rig:
            return
        self.rig, self.undo_steps, self.redo_steps, self._open = rig, [], [], None
        if not rig:
            return
        try:
            with open(self._path(rig), encoding="utf-8") as handle:
                document = json.load(handle)
            self.undo_steps = document.get("undo") or []
            self.redo_steps = document.get("redo") or []
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError) as exc:
            self.log(f"ignoring the history of '{rig}': {exc}")

    # ------------------------------------------------------------------ edits
    def note(self, before, after, keys, client, gesture=None):
        """An edit landed: `before` and `after` are the stored document either side of it."""
        now = self.clock()
        step = self._open
        if step is not None and gesture is not None and step["gesture"] == gesture:
            same = True
        elif step is not None and gesture is None and step["gesture"] is None:
            same = keys and step["keys"] == set(keys) and now - step["last"] < GAP_S
        else:
            same = False
        if not same:
            self.close(before)
            self._open = {"before": before, "gesture": gesture, "keys": set(keys), "client": client, "last": now}
            self.redo_steps = []
        self._open["last"] = now
        self._open["after"] = after

    def close(self, _stored=None):
        """End the growing step, so the next edit starts another and it can be undone."""
        step, self._open = self._open, None
        if step is None:
            return
        change = delta(step["before"], step["after"])
        if not change:
            return
        self.undo_steps.append({"at": round(self.wall(), 3), "client": step["client"],
                                "keys": [list(key) for key in sorted(step["keys"])], "delta": change})
        self._trim()

    def _trim(self):
        del self.undo_steps[:-MAX_STEPS]
        while len(self.undo_steps) > 1 and len(json.dumps(self.undo_steps)) > MAX_RIG_BYTES:
            del self.undo_steps[0]

    # ------------------------------------------------------------------ undo and redo
    def undo(self, stored):
        """The stored document one step back, or None. The step moves to redo once it has landed."""
        self.close()
        if not self.undo_steps:
            return None
        return apply(stored, self.undo_steps[-1]["delta"], forwards=False)

    def undone(self):
        self.redo_steps.append(self.undo_steps.pop())

    def redo(self, stored):
        self.close()
        if not self.redo_steps:
            return None
        return apply(stored, self.redo_steps[-1]["delta"], forwards=True)

    def redone(self):
        self.undo_steps.append(self.redo_steps.pop())

    def counts(self):
        return {"undo": len(self.undo_steps) + (1 if self._open else 0), "redo": len(self.redo_steps)}

    def listing(self):
        def row(step):
            return {"at": step.get("at"), "client": step.get("client"), "keys": step.get("keys")}
        self.close()
        return {"rig": self.rig, "undo": [row(s) for s in reversed(self.undo_steps)],
                "redo": [row(s) for s in reversed(self.redo_steps)]}

    # ------------------------------------------------------------------ the card
    def save(self):
        """Write this rig's history, including the step still growing, which stays open."""
        if not self.rig:
            return
        steps = list(self.undo_steps)
        if self._open is not None:
            change = delta(self._open["before"], self._open["after"])
            if change:
                steps.append({"at": round(self.wall(), 3), "client": self._open["client"],
                              "keys": [list(key) for key in sorted(self._open["keys"])], "delta": change})
        os.makedirs(self.root, exist_ok=True)
        write_atomic_plain(self._path(self.rig), json.dumps({"undo": steps, "redo": self.redo_steps}, ensure_ascii=False))
        self._trim_all()

    def _trim_all(self):
        """All rigs together stay under the limit, losing the file touched longest ago."""
        try:
            files = [os.path.join(self.root, name) for name in os.listdir(self.root) if name.endswith(".json")]
            stats = sorted(((os.stat(path).st_mtime, os.stat(path).st_size, path) for path in files))
        except OSError:
            return
        total = sum(size for _, size, _ in stats)
        for _, size, path in stats:
            if total <= MAX_TOTAL_BYTES or path == self._path(self.rig):
                continue
            os.unlink(path)
            total -= size
            self.log(f"history over its limit: dropped {os.path.basename(path)}")

    def renamed(self, old, new):
        try:
            os.replace(self._path(old), self._path(new))
        except FileNotFoundError:
            pass
        except OSError as exc:
            self.log(f"could not move the history of '{old}': {exc}")
        if self.rig == old:
            self.rig = new

    def deleted(self, rig):
        try:
            os.unlink(self._path(rig))
        except OSError:
            pass
        if self.rig == rig:
            self.rig, self.undo_steps, self.redo_steps, self._open = None, [], [], None

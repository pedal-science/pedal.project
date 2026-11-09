"""What is playing, what is stored, and which differences are only a performance.

docs/pedal-service.md, "Keeping the rig". Pure: it files, sockets and clocks nothing. `read_stored(name)`
is how it learns a library rig's document, and everything it decides comes back as a `Change`.

A **key** is `(chain, node, parameter)`, and `bypass` is a parameter. The overlay is the set of keys whose
played value isn't the stored one because of a performance or a client that didn't name itself. The stored
document is what gets saved, so nothing here ever has to take a performance value back out.
"""

import copy
import json

from .resume import canonical, strip_ephemeral

#: A node's fields that aren't its values.
NOT_VALUES = ("id", "type", "element", "role", "meta")
#: How a document came to be running, when it isn't somebody's edit.
LOADS = ("load", "switch", "startup", "reload")
PERFORMANCE = "perf"
FOREIGN = "foreign"


def chains_of(document):
    """(chain id, graph) for each chain. A bare graph is one chain, whose id is "". """
    chains = document.get("chains")
    if isinstance(chains, list):
        return [(chain.get("id", ""), chain) for chain in chains if isinstance(chain, dict)]
    return [("", document)]


def nodes_of(document):
    """{(chain, node id): node}"""
    return {(chain_id, node.get("id")): node
            for chain_id, chain in chains_of(document)
            for node in chain.get("nodes") or () if isinstance(node, dict)}


def values_of(node):
    return {key: value for key, value in node.items() if key not in NOT_VALUES}


def same_value(a, b):
    """Bypass absent and bypass false mean the same thing, as does any parameter absent and null."""
    return (a or False) == (b or False) if isinstance(a, (bool, type(None))) and isinstance(b, (bool, type(None))) else a == b


def compare(a, b):
    """(the value keys that differ, whether anything else does) between two documents."""
    keys, structural = set(), False
    nodes_a, nodes_b = nodes_of(a), nodes_of(b)
    if set(nodes_a) != set(nodes_b):
        structural = True
    for where in set(nodes_a) & set(nodes_b):
        one, other = nodes_a[where], nodes_b[where]
        if any(one.get(field) != other.get(field) for field in NOT_VALUES):
            structural = True
        values_one, values_other = values_of(one), values_of(other)
        for param in set(values_one) | set(values_other):
            if not same_value(values_one.get(param), values_other.get(param)):
                keys.add((where[0], where[1], param))
    if _shape(a) != _shape(b):
        structural = True
    return keys, structural


def _shape(document):
    """Everything in a document but its nodes' values, as a stable string."""
    def graph(chain):
        rest = {key: value for key, value in chain.items() if key != "nodes"}
        rest["order"] = [node.get("id") for node in chain.get("nodes") or () if isinstance(node, dict)]
        return rest
    chains = document.get("chains")
    if not isinstance(chains, list):
        return canonical(graph(document))
    top = {key: value for key, value in document.items() if key not in ("chains", "name")}
    top["chains"] = [graph(chain) for chain in chains if isinstance(chain, dict)]
    return canonical(top)


def _set(node, param, value):
    if value is None:
        node.pop(param, None)
    else:
        node[param] = value


class Change:
    """What an engine event turned out to be. `kind` is none, load, edit, performance, foreign or
    bookkeeping; `keys` are the values it moved; `gesture` is the app's gesture, for one undo step."""

    def __init__(self, kind, keys=(), structural=False, before=None, client=None, gesture=None):
        self.kind = kind
        self.keys = set(keys)
        self.structural = structural
        self.before = before        # the stored document before an edit
        self.client = client
        self.gesture = gesture

    def __repr__(self):
        return f"Change({self.kind}, {sorted(self.keys)}, structural={self.structural})"


def _origin(frame_or_value):
    origin = frame_or_value.get("origin")
    return origin if isinstance(origin, dict) else {}


def _who(origin):
    """How an origin's changes are treated: performance, bookkeeping, foreign, or an edit."""
    client, tag = origin.get("client") or "", origin.get("tag") or ""
    if client == "pedald":
        return "performance" if tag.startswith("perf:") else "bookkeeping"
    if client == "" or client == "namchaind":
        return "foreign"
    return "edit"


def _gesture(origin):
    tag = origin.get("tag") or ""
    return tag if tag.startswith("gesture:") else None


class Running:
    def __init__(self, read_stored):
        self.read_stored = read_stored
        self.document = None
        self.stored = None
        self.name = None
        self.seq = -1
        self.overlay = {}               # key -> PERFORMANCE or FOREIGN
        self.in_library = False
        self.saves_stopped = False      # a foreign structural change the overlay can't hold

    # ------------------------------------------------------------------ what views see
    @property
    def modified(self):
        return bool(self.overlay)

    def performance(self):
        nodes = nodes_of(self.document) if self.document else {}
        rows = []
        for (chain, node, param), why in sorted(self.overlay.items()):
            if why == PERFORMANCE:
                element = (nodes.get((chain, node)) or {}).get("element")
                rows.append({"chain": chain, "node": node, "element": element, "param": param})
        return rows

    def savable(self):
        return self.in_library and not self.saves_stopped and self.stored is not None

    # ------------------------------------------------------------------ the rig changing
    def _load(self, document, name):
        self.document = strip_ephemeral(document)
        self.name = name
        self.overlay = {}
        self.saves_stopped = False
        stored = self.read_stored(name) if name else None
        self.in_library = stored is not None
        # The engine's parse of the file, not the file: a saved rig is then what `rig.get` says.
        self.stored = copy.deepcopy(self.document)
        return Change("load")

    def _replaced_by_another(self, document, name, origin):
        """A document of another name, applied. If the library knows the name, what differs is an edit."""
        document = strip_ephemeral(document)
        stored = self.read_stored(name) if name else None
        self.name, self.overlay, self.saves_stopped = name, {}, False
        self.in_library = stored is not None
        self.document = document
        if stored is None or _who(origin) != "edit":
            self.stored = copy.deepcopy(document)
            return Change("load")
        keys, structural = compare(stored, document)
        self.stored = copy.deepcopy(document)
        if keys or structural:
            return Change("edit", keys, structural, before=stored, client=origin.get("client"), gesture=_gesture(origin))
        return Change("load")

    # ------------------------------------------------------------------ a whole document
    def _merge(self, document, origin):
        """A new whole document for this rig, classified by who sent it."""
        document = strip_ephemeral(document)
        keys, structural = compare(self.document, document)
        who = _who(origin)
        if not keys and not structural:
            self.document = document
            return Change("none")
        if who == "bookkeeping":
            self.document = document
            return Change("bookkeeping", keys, structural)
        if who == "performance":
            nodes = nodes_of(self.stored)
            for key in keys:
                self._mark(key, document, nodes, PERFORMANCE)
            self.document = document
            return Change("performance", keys, structural)
        if who == "foreign":
            nodes = nodes_of(self.stored)
            for key in keys:
                self._mark(key, document, nodes, FOREIGN)
            self.document = document
            self.saves_stopped = self.saves_stopped or structural
            return Change("foreign", keys, structural, client=origin.get("client"))
        return self._edit(document, keys, structural, origin)

    def _edit(self, document, keys, structural, origin):
        """A named client's document. An overlay key it left at the played value is still a performance:
        the app was only echoing what it saw. Anything else it set is its edit."""
        before = copy.deepcopy(self.stored)
        kept = {key: why for key, why in self.overlay.items() if key not in keys}
        stored = copy.deepcopy(document)
        nodes_stored, nodes_before = nodes_of(stored), nodes_of(before)
        overlay = {}
        for key, why in kept.items():
            where = (key[0], key[1])
            if where in nodes_stored and where in nodes_before:
                _set(nodes_stored[where], key[2], nodes_before[where].get(key[2]))
                overlay[key] = why
        self.document, self.stored, self.overlay = document, stored, overlay
        return Change("edit", keys, structural, before=before, client=origin.get("client"), gesture=_gesture(origin))

    def _mark(self, key, document, stored_nodes, why):
        """A value moved by a performance: in the overlay, unless it is back at the stored value."""
        where = (key[0], key[1])
        played = (nodes_of(document).get(where) or {}).get(key[2])
        stored = (stored_nodes.get(where) or {}).get(key[2])
        if same_value(played, stored):
            self.overlay.pop(key, None)
        else:
            self.overlay[key] = why

    # ------------------------------------------------------------------ engine events
    def on_frame(self, frame):
        """One event from the engine. Anything older than the document in hand is ignored."""
        event = frame.get("event")
        if event == "rig.params":
            return self._params(frame)
        if event not in ("rig.replaced", "rig.patched"):
            return Change("none")
        seq = frame.get("seq")
        if isinstance(seq, int):
            if seq <= self.seq:
                return Change("none")
            self.seq = seq
        document = frame.get("document")
        if not isinstance(document, dict):
            return Change("none")
        if event == "rig.replaced":
            return self._replaced(document, frame)
        return self._merge(document, _origin(frame))

    def _replaced(self, document, frame):
        name = frame.get("name") or document.get("name")
        origin = _origin(frame)
        if frame.get("why") in LOADS:
            return self._load(document, name)
        if self.document is None or name != self.name:
            return self._replaced_by_another(document, name, origin)
        return self._merge(document, origin)

    def _params(self, frame):
        """Ramped values, which carry no document. Each has its own origin."""
        if self.document is None:
            return Change("none")
        nodes, stored_nodes = nodes_of(self.document), nodes_of(self.stored)
        moved = {"edit": set(), "performance": set(), "foreign": set(), "bookkeeping": set()}
        before = None
        client = gesture = None
        for value in frame.get("values") or ():
            node_id = value.get("node")
            seq = value.get("seq")
            if isinstance(seq, int):
                if seq <= self.seq:
                    continue
                self.seq = seq
            if node_id is None:
                continue                # runtime state, not in the document
            where = (value.get("chain") or "", node_id)
            if where not in nodes:
                where = next((w for w in nodes if w[1] == node_id), None)
                if where is None:
                    continue
            key = (where[0], where[1], value.get("param"))
            origin = _origin(value)
            who = _who(origin)
            _set(nodes[where], key[2], value.get("value"))
            if who == "edit":
                if before is None:
                    before = copy.deepcopy(self.stored)
                    stored_nodes = nodes_of(self.stored)
                _set(stored_nodes[where], key[2], value.get("value")) if where in stored_nodes else None
                self.overlay.pop(key, None)
                client, gesture = origin.get("client"), _gesture(origin)
            elif who == "performance":
                self._mark(key, self.document, stored_nodes, PERFORMANCE)
            elif who == "foreign":
                self._mark(key, self.document, stored_nodes, FOREIGN)
            moved[who].add(key)
        for kind in ("edit", "performance", "foreign", "bookkeeping"):
            if moved[kind]:
                return Change(kind, moved[kind], before=before, client=client, gesture=gesture)
        return Change("none")

    # ------------------------------------------------------------------ catching up
    def catch_up(self, document, name, seq):
        """`rig.get` after a reconnect or a `resync`, when events may have been missed. What differs
        was somebody's, and nobody can say whose, so it counts as one edit, as the plan asks."""
        self.seq = seq if isinstance(seq, int) else self.seq
        if self.document is None or name != self.name:
            return self._load(document, name)
        return self._merge(document, {"client": "unknown"})

    def start(self, document, name, seq, file_document, last_document, saved):
        """The first look at the engine after pedald starts. `saved` is `state/resume.json`, read and
        already matched against `last.json` (None if it didn't match). See "Resume"."""
        self.seq = seq if isinstance(seq, int) else -1
        document = strip_ephemeral(document)
        self.name = name
        self.in_library = file_document is not None
        self.saves_stopped = False
        self.overlay = {}
        if file_document is None:
            self.document, self.stored = document, copy.deepcopy(document)
            return Change("load")
        if saved is not None and saved.get("rig") == name and last_document is not None:
            self.document, self.stored = last_document, file_document
            for row in saved.get("overlay") or ():
                self.overlay[(row[0], row[1], row[2])] = row[3]
            return self._merge(document, {"client": "unknown"})
        # No record to trust: nothing may be baked in. Values are performance, and a different shape
        # is something this can't file away, so saving stops.
        keys, structural = compare(file_document, document)
        self.document, self.stored = document, file_document
        self.overlay = {key: PERFORMANCE for key in keys}
        self.saves_stopped = structural
        return Change("load")

    # ------------------------------------------------------------------ what pedald itself decides
    def resume_record(self, written):
        """What `state/resume.json` holds, given the canonical form of `last.json` as written."""
        return {"rig": self.name, "overlay": [[*key, why] for key, why in sorted(self.overlay.items())]}

    def with_overlay(self, stored):
        """A stored document with the overlay's played values on top: what undo publishes."""
        document = copy.deepcopy(stored)
        played, target = nodes_of(self.document), nodes_of(document)
        for key in list(self.overlay):
            where = (key[0], key[1])
            if where in played and where in target:
                _set(target[where], key[2], played[where].get(key[2]))
            else:
                self.overlay.pop(key)
        return document

    def set_stored(self, stored):
        """Undo, redo or a rename: pedald changes stored, and the engine's event follows as bookkeeping."""
        self.stored = stored

    def take_stored(self, document):
        """The library's file changed under the running rig (a client's `PUT`): the file wins."""
        self.stored = copy.deepcopy(document)
        self.in_library = True
        keys, _ = compare(self.stored, self.document)
        self.overlay = {key: why for key, why in self.overlay.items() if key in keys}

    def rename(self, name):
        self.name = name
        for document in (self.document, self.stored):
            if isinstance(document, dict):
                document["name"] = name

    def as_text(self):
        return json.dumps(self.stored, indent=2, ensure_ascii=False) + "\n"

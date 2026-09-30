#!/usr/bin/env python3
"""Rebuild the 2026-09-28 ljoss editing session (22:17-22:37 on piv) as a replayable session.

The session wasn't recorded. What survives is the watch that ran beside it
(bench-results/2026-09-28-ljoss-edits-watch.log, from scripts/soak/watch-edits.py): every
~260 ms poll that saw a change, with how many ramps landed and the parameter's value before and
after. That, and the two rigs ljoss saved at the end of each half, are enough to rebuild what
ljoss sent, closely but not exactly:

- The end documents are exact. ljoss saved "Ambient Wash" at 22:19:28 and "Crunch Lead" at
  22:37:27, at the log's last values, and its own encoder turned each file into the document it
  sends (ljoss Tools/dump-engine-document.sh --file, ljoss ac61dd9). piv's own last.json
  matches the second.
- Walking the log backwards from them gives each starting document and every step.
- A poll that saw k ramps becomes k set_param patches spread evenly over the poll before it,
  going in a straight line from the old value to the new. The real drag's shape inside those
  ~260 ms is lost, and the values are the log's 4 significant figures.
- Each rebuild becomes a rig.apply 130 ms before the poll that saw it (the middle of the poll),
  then one engine.mute per chain, as ljoss sends them.
- ljoss's engine.status every 500 ms runs throughout.
- The amp removed at 22:17:36 (element F7795F...) was never saved. Its full id is invented from
  the six characters the log shows, and its tone stack gets ljoss's new-amp values (bass 0,
  mid 0, treble 2.4), because the log never showed them. It is placed straight after the gain
  block, where its replacement ended up; the replacement is placed straight after it.

    rebuild-2026-09-28-ljoss.py > 2026-09-28-ljoss.session.jsonl
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LOG = os.path.join(REPO, "bench-results", "2026-09-28-ljoss-edits-watch.log")
AMBIENT_END = os.path.join(HERE, "2026-09-28-ljoss", "ambient-wash-end.json")
CRUNCH_END = os.path.join(HERE, "2026-09-28-ljoss", "crunch-lead-end.json")

POLL = 0.26              # the watch's poll period: 0.2 s sleep plus two namchainctl calls
STATUS_EVERY = 0.5       # ljoss's engine.status poll
NEW_AMP_TONE = {"bass": 0.0, "mid": 0.0, "treble": 2.4000000000000004}
REMOVED_AMP = "F7795F00-0000-4000-8000-000000000000"   # invented: the log shows only F7795F
MACROS = ("fx.",)        # fx.* are namchain macros: a ramp names the element, not the node

HEAD = re.compile(r"^(\d\d):(\d\d):(\d\d\.\d{3}) (.*)$")
PARAM = re.compile(r"^chains\[(\w+)\]\.nodes\[([\w.]+)#(\w{6})\]\.(\w+): (\S+) -> (\S+)$")


def seconds(h, m, s):
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_log():
    """[(t, head, [detail lines])] for every poll the watch printed."""
    polls = []
    for line in open(LOG):
        line = line.rstrip("\n")
        m = HEAD.match(line)
        if m:
            polls.append([seconds(*m.groups()[:3]), m.group(4), []])
        elif line.strip() and polls:
            polls[-1][2].append(line.strip())
    return polls


def chain(doc, name):
    return next(c for c in doc["chains"] if c["name"] == name)


def node(doc, chain_name, type_, short):
    for n in chain(doc, chain_name)["nodes"]:
        if n["type"] == type_ and n["id"].startswith(short):
            return n
    raise KeyError("%s %s#%s" % (chain_name, type_, short))


def remove_amp(doc, element):
    """Take an amp's two nodes out of Guitar and join what was either side of them."""
    c = chain(doc, "Guitar")
    ids = {n["id"] for n in c["nodes"] if n.get("element") == element}
    before = next(x["from"] for x in c["connections"] if x["to"] in ids and x["from"] not in ids)
    after = next(x["to"] for x in c["connections"] if x["from"] in ids and x["to"] not in ids)
    c["nodes"] = [n for n in c["nodes"] if n["id"] not in ids]
    c["connections"] = [x for x in c["connections"] if x["from"] not in ids and x["to"] not in ids]
    c["connections"].append({"from": before, "from_port": 0, "to": after, "to_port": 0})
    order_connections(c)


def insert_amp(doc, element, model, tone, after_id):
    """Put an amp (nc.nam then fx.amp.tonestack, as ljoss encodes one) straight after a node."""
    c = chain(doc, "Guitar")
    nam, ton = element + "-nam", element + "-tone"
    at = next(i for i, n in enumerate(c["nodes"]) if n["id"] == after_id) + 1
    c["nodes"][at:at] = [
        {"id": nam, "element": element, "type": "nc.nam", "model": model},
        dict({"id": ton, "element": element, "type": "fx.amp.tonestack"}, **tone),
    ]
    link = next(x for x in c["connections"] if x["from"] == after_id)
    old_to = link["to"]
    link["to"] = nam
    c["connections"] += [{"from": nam, "from_port": 0, "to": ton, "to_port": 0},
                         {"from": ton, "from_port": 0, "to": old_to, "to_port": 0}]
    order_connections(c)


def order_connections(c):
    """Connections in signal order, as ljoss writes them."""
    by_from = {x["from"]: x for x in c["connections"]}
    ordered, at = [], "in"
    while at in by_from:
        ordered.append(by_from[at])
        at = by_from[at]["to"]
    assert len(ordered) == len(c["connections"]), "Guitar is no longer one line"
    c["connections"] = ordered


def same_as(want, got):
    """The rebuilt document matches the saved one: the same nodes, links, and values to the
    log's four significant figures."""
    for cw, cg in zip(want["chains"], got["chains"]):
        assert [n["id"] for n in cw["nodes"]] == [n["id"] for n in cg["nodes"]], cw["name"]
        assert cw["connections"] == cg["connections"], cw["name"]
        for nw, ng in zip(cw["nodes"], cg["nodes"]):
            for k, v in nw.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    assert abs(ng[k] - v) <= abs(v) * 1e-3 + 1e-3, (nw["id"], k, v, ng[k])
                else:
                    assert ng.get(k) == v, (nw["id"], k, v, ng.get(k))
    assert len(want["chains"]) == len(got["chains"])


def nam_by_short(doc, short):
    return node(doc, "Guitar", "nc.nam", short)


def value(text):
    return float(text)


def build():
    polls = parse_log()
    ambient_end = json.load(open(AMBIENT_END))
    crunch_end = json.load(open(CRUNCH_END))
    rebuilds = [p for p in polls if p[1].startswith("REBUILD")]
    assert len(rebuilds) == 5, "expected the log's five rebuilds"
    switch_t = rebuilds[3][0]

    # Parameter changes, in order, for walking back from each end document.
    changes = []   # (t, chain, type, short, param, old, new)
    for t, head, details in polls:
        for d in details:
            m = PARAM.match(d)
            if m:
                changes.append((t,) + m.groups()[:4] + (value(m.group(5)), value(m.group(6))))

    def unwind(doc, changes_after):
        """Set every parameter back to its value before the first of these changes."""
        seen = set()
        for t, ch, type_, short, param, old, new in changes_after:
            if (ch, type_, short, param) not in seen:
                seen.add((ch, type_, short, param))
                try:
                    node(doc, ch, type_, short)[param] = old
                except KeyError:
                    pass   # a node that didn't exist yet: its first value is set when it's added

    # --- Ambient Wash, as it was at 22:17:08, before the watch saw anything.
    a0 = copy.deepcopy(ambient_end)
    unwind(a0, [c for c in changes if c[0] < switch_t])
    sm75 = nam_by_short(a0, "A78A22")
    assert sm75["model"] == "Ampeg SVT Classic with 6x10/Ampeg SVT - SM75"
    gain_id = next(n["id"] for n in chain(a0, "Guitar")["nodes"] if n["type"] == "nc.gain")
    remove_amp(a0, sm75["element"])
    insert_amp(a0, REMOVED_AMP, "000 Unsorted/ORNG-V30-e609-Center", NEW_AMP_TONE, gain_id)

    # --- Crunch Lead, as ljoss first sent it at the switch.
    c0 = copy.deepcopy(crunch_end)
    unwind(c0, [c for c in changes if c[0] > switch_t])
    lo_hi = nam_by_short(c0, "49A791")
    assert lo_hi["model"].startswith("Ampeg SVT Classic with 6x10/Ampeg SVT - Gain 10 Ultra Lo")
    remove_amp(c0, lo_hi["element"])

    # The five rebuilds, as functions of the document before them.
    def r1(doc):   # 22:17:12: the amp's model changed
        nam_by_short(doc, "F7795F")["model"] = "Ampeg GVT52 - Channel 2/AMPEG_CH 2 NEUTRAL G7"

    def r2(doc):   # 22:17:25: a second amp added, after the first
        tone = node(doc, "Guitar", "fx.amp.tonestack", "F7795F")["id"]
        insert_amp(doc, sm75["element"], sm75["model"], NEW_AMP_TONE, tone)

    def r3(doc):   # 22:17:36: the first amp removed
        remove_amp(doc, REMOVED_AMP)

    def r4(doc):   # 22:36:45: switched to Crunch Lead
        same_as(ambient_end, doc)   # Ambient Wash has reached what ljoss saved
        doc.clear()
        doc.update(copy.deepcopy(c0))

    def r5(doc):   # 22:36:56: an amp added after the gain block
        gain = next(n["id"] for n in chain(doc, "Guitar")["nodes"] if n["type"] == "nc.gain")
        insert_amp(doc, lo_hi["element"], lo_hi["model"], NEW_AMP_TONE, gain)

    steps = dict(zip([r[0] for r in rebuilds], (r1, r2, r3, r4, r5)))

    # --- Walk forward, emitting what ljoss would have sent.
    start = polls[0][0]
    doc = copy.deepcopy(a0)
    events = []
    prev_t = start
    last_param = None

    def hidden(d):
        # ljoss's layout "single" shows only the first chain, and mutes the rest.
        return {c["id"]: i > 0 for i, c in enumerate(d["chains"])}

    def emit(t, request):
        events.append({"t": round(t - start, 4), "request": request})

    for t, head, details in polls[1:]:
        if t in steps:
            steps[t](doc)
            at = max(prev_t, t - POLL / 2)
            emit(at, {"method": "rig.apply", "document": copy.deepcopy(doc)})
            for i, (chain_id, muted) in enumerate(hidden(doc).items()):
                emit(at + 0.005 * (i + 1), {"method": "engine.mute", "mute": muted, "chain": chain_id})
        m = re.match(r"\+(\d+) ramps", head)
        if m:
            k = int(m.group(1))
            params = [PARAM.match(d).groups() for d in details if PARAM.match(d)]
            if not params and last_param:
                # Ramps with no visible change: the last value sent again as the finger lifted.
                ch, type_, short, param = last_param
                v = node(doc, ch, type_, short)[param]
                params = [(ch, type_, short, param, repr(v), repr(v))]
            window = min(POLL, t - prev_t)
            share = [k // len(params) + (1 if i < k % len(params) else 0) for i in range(len(params))]
            slot = 0
            for (ch, type_, short, param, old, new), n in zip(params, share):
                n = max(n, 1)
                target = node(doc, ch, type_, short)
                for j in range(1, n + 1):
                    v = value(old) + (value(new) - value(old)) * j / n
                    slot += 1
                    op = {"op": "set_param", "param": param, "value": v}
                    if type_.startswith(MACROS):
                        op["element"] = target["element"]
                    else:
                        op["node"] = target["id"]
                    emit(t - window + window * slot / (sum(share) or 1),
                         {"method": "rig.patch", "chain": chain(doc, ch)["id"], "ops": [op]})
                target[param] = value(new)
                last_param = (ch, type_, short, param)
        prev_t = t

    same_as(crunch_end, doc)   # and Crunch Lead has reached what ljoss saved

    t = 0.0
    end_t = polls[-1][0] - start
    while t < end_t:
        events.append({"t": round(t, 4), "request": {"method": "engine.status"}})
        t += STATUS_EVERY
    events.sort(key=lambda e: e["t"])

    header = {
        "namchain_session": 1,
        "name": "2026-09-28-ljoss",
        "source": "rebuilt",
        "recorded_at": "2026-09-28T21:17:08+00:00",
        "upstream": "piv:47810",
        "notes": [
            "ljoss editing Ambient Wash, then Crunch Lead, on piv, 22:17-22:37 BST (ljoss ba50ad2).",
            "Rebuilt from bench-results/2026-09-28-ljoss-edits-watch.log and the rigs ljoss saved, by "
            "scripts/soak/sessions/rebuild-2026-09-28-ljoss.py; its docstring lists what is approximate.",
        ],
        "initial": {"document": a0, "muted": hidden(a0)},
    }
    return header, events


def main():
    header, events = build()
    out = sys.stdout
    out.write(json.dumps(header, separators=(",", ":")) + "\n")
    for e in events:
        out.write(json.dumps(e, separators=(",", ":")) + "\n")
    counts = {}
    for e in events:
        counts[e["request"]["method"]] = counts.get(e["request"]["method"], 0) + 1
    print("%d requests over %.0f s: %s" % (len(events), events[-1]["t"], counts), file=sys.stderr)


if __name__ == "__main__":
    main()

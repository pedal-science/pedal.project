#!/usr/bin/env python3
# o1-stream.py SECONDS OUT.json [--no-stream] [--no-subscriber]: O1's load on the engine (namchain docs/daemon.md, "Events").
# Runs on the Core host as root, beside soak-monitor.sh. Two connections to namchaind's local socket:
#   a subscriber to every event (as a view would be), counting frames, bytes and resyncs, and
#   a knob: a ramped parameter of the playing rig swept at 100 Hz, a small way either side of where it
#   was, and put back at the end -- the stream a slider produces.
# --no-subscriber leaves the subscriber out: the knob alone, the control that separates what the knob
# costs the render thread (its ramps) from what the events cost (bench-results/2026-11-08-events-vip, knob).
# Writes what it saw as one JSON object.
import json, math, select, socket, sys, time

# TCP with the token, as rigpa and ljoss connect: a reply as large as engine.schema does not fit one
# datagram on the local socket (bench-results/2026-11-08-events-vip/README.md).
ADDR = ("127.0.0.1", 47810)
TOKEN = open("/etc/namchain/token").read().split()[0]
seconds, out = float(sys.argv[1]), sys.argv[2]
stream = "--no-stream" not in sys.argv
subscribe = "--no-subscriber" not in sys.argv

class Conn:
    def __init__(self):
        self.s = socket.create_connection(ADDR)
        self.buf = b""
    def send(self, obj):
        body = json.dumps(obj).encode()
        self.s.sendall(len(body).to_bytes(4, "little") + body)
    def ready(self):
        if len(self.buf) >= 4 and len(self.buf) >= 4 + int.from_bytes(self.buf[:4], "little"):
            return True
        r, _, _ = select.select([self.s], [], [], 0)
        return bool(r)
    def recv(self):
        while len(self.buf) < 4 or len(self.buf) < 4 + int.from_bytes(self.buf[:4], "little"):
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise EOFError("namchaind closed the connection")
            self.buf += chunk
        n = int.from_bytes(self.buf[:4], "little")
        body, self.buf = self.buf[4:4 + n], self.buf[4 + n:]
        return body

def connect(name):
    c = Conn()
    r = call(c, {"method": "engine.hello", "token": TOKEN, "client": {"name": name}})
    assert r.get("ok"), r
    return c

ids = [0]
def call(c, req, events=None):
    ids[0] += 1
    req = dict(req, id="o1-%d" % ids[0])
    c.send(req)
    while True:
        msg = json.loads(c.recv())
        if "event" in msg and "id" not in msg:
            if events is not None:
                events.append(msg)
            continue
        if msg.get("id") == req["id"]:
            return msg

knob = connect("o1-knob")
viewer = None
if subscribe:
    viewer = connect("o1-viewer")
    sub = call(viewer, {"method": "engine.subscribe"})
    assert sub["ok"], sub

# A rampable numeric parameter in the playing document, and its current value.
types = {t["id"]: t for t in call(knob, {"method": "engine.schema"})["nodes"]}
doc = call(knob, {"method": "rig.get"})["document"]
target = None
for chain in doc["chains"]:
    for node in chain["nodes"]:
        for p in types.get(node["type"], {}).get("params", []):
            if not (p.get("rampable") and p.get("kind") == "number"):
                continue
            if p.get("min") is None or p.get("max") is None:
                continue
            cur = node.get(p["id"], (node.get("params") or {}).get(p["id"], p.get("default")))
            if isinstance(cur, (int, float)):
                # By element where the node has one, as ljoss and rigpa address a block: a macro
                # addressed by its node id goes the structural way.
                address = {"element": node["element"]} if node.get("element") else {"node": node["id"]}
                target = (chain["id"], address, p["id"], float(cur), float(p["min"]), float(p["max"]))
                break
        if target:
            break
    if target:
        break
assert target, "no rampable parameter in the playing rig"
chain, node, param, start, lo, hi = target
swing = 0.05 * (hi - lo)

counts, sizes, resyncs, ops, refused, kinds = {}, 0, 0, 0, 0, {}
t0 = time.monotonic(); nxt = t0
def drain():
    global sizes, resyncs
    while viewer is not None and viewer.ready():
        b = viewer.recv(); sizes += len(b)
        m = json.loads(b); e = m.get("event", "reply")
        counts[e] = counts.get(e, 0) + 1
        resyncs += e == "resync"

while time.monotonic() - t0 < seconds:
    if stream:
        v = min(hi, max(lo, start + swing * math.sin(2 * math.pi * 0.5 * (time.monotonic() - t0))))
        r = call(knob, {"method": "rig.patch", "chain": chain, "tag": "o1-knob",
                        "ops": [dict(node, op="set_param", param=param, value=v)]})
        ops += 1; refused += not r.get("ok"); kinds[r.get("kind")] = kinds.get(r.get("kind"), 0) + 1
    drain()
    nxt += 0.01
    time.sleep(max(0, nxt - time.monotonic()))
if stream:
    call(knob, {"method": "rig.patch", "chain": chain, "ops": [dict(node, op="set_param", param=param, value=start)]})
time.sleep(0.3); drain()
json.dump({"seconds": seconds, "stream": stream, "subscriber": subscribe, "target": {"chain": chain, "node": node, "param": param,
           "start": start, "swing": swing}, "ops": ops, "refused": refused, "kinds": kinds, "events": counts,
           "event_bytes": sizes, "resyncs": resyncs}, open(out, "w"), indent=1)
print("ops %d refused %d events %s resyncs %d" % (ops, refused, counts, resyncs))

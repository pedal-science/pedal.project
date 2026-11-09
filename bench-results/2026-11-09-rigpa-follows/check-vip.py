#!/usr/bin/env python3
"""O5 on vip: an app's edit is saved by pedald, shows in pedald's history, and undo puts it back.

    scripts/host-lock --host vip -- python3 bench-results/2026-11-09-rigpa-follows/check-vip.py

Leaves Bob as it found it (the undo, then a check of the file). Writes run/check-vip.json.
"""
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "devices/common/rootfs/usr/local/lib"))
from pedald.engine import EngineClient  # noqa: E402

TOKEN = subprocess.run(["ssh", "vip", "sudo cat /etc/namchain/token"], capture_output=True, text=True, check=True).stdout.strip()
ADDRESS = subprocess.run(["ssh", "vip", "hostname -I"], capture_output=True, text=True, check=True).stdout.split()[0]
out = {"checks": []}


def ask(method, path, body=None):
    request = urllib.request.Request(f"http://{ADDRESS}:47820{path}", method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + TOKEN, "Pedal-Client": "o5-check"})
    with urllib.request.urlopen(request, timeout=10) as reply:
        return json.load(reply)


def filed(node_id, param):
    text = subprocess.run(["ssh", "vip", "sudo cat /var/lib/pedal/library/rigs/Bob.json"], capture_output=True, text=True).stdout
    for chain in json.loads(text)["chains"]:
        for node in chain["nodes"]:
            if node["id"] == node_id:
                return node.get(param)


def want(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name, detail)
    out["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})


running = ask("GET", "/running")
want("Bob is playing", running["rig"] == "Bob", running)
client = EngineClient(ADDRESS, 47810, TOKEN, timeout=5, client="o5-check")
document = client.rig_get()["document"]
chain = document["chains"][0]
node = next(n for n in chain["nodes"] if n["type"] == "nc.gain")
before = node.get("gain_db", 0.0)
edited = before - 1.0
undo_before = running["undo"]
started = time.monotonic()
client.rig_patch([{"op": "set_param", "node": node["id"], "param": "gain_db", "value": edited}], chain=chain["id"])
saved_after = None
while time.monotonic() - started < 6:
    if filed(node["id"], "gain_db") == edited:
        saved_after = round(time.monotonic() - started, 2)
        break
    time.sleep(0.2)
want("pedald saved the edit to Bob.json", saved_after is not None, f"{saved_after} s")
running = ask("GET", "/running")
want("one more undo step", running["undo"] == undo_before + 1, running)
ask("POST", "/undo")
time.sleep(2.5)
want("undo put Bob back, in the file too", filed(node["id"], "gain_db") == before, filed(node["id"], "gain_db"))
log = subprocess.run(["ssh", "vip", "sudo journalctl -u pedald --since '-2min' --no-pager -o cat | grep -E \"saved rig|following\" | tail -4"],
                     capture_output=True, text=True).stdout
print(log)
out["pedald_log"] = log
rigpa = subprocess.run(["ssh", "vip", "systemctl is-active rigpa; readlink /opt/rigpa/current"], capture_output=True, text=True).stdout.split()
out["rigpa"] = rigpa
want("rigpa runs the O5 build", rigpa == ["active", "/opt/rigpa/f32bb2a"], rigpa)
(HERE / "run").mkdir(exist_ok=True)
(HERE / "run" / "check-vip.json").write_text(json.dumps(out, indent=1) + "\n")
print("FAILED" if not all(c["ok"] for c in out["checks"]) else "all passed")

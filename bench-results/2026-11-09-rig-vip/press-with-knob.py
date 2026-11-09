#!/usr/bin/env python3
"""A press timed on the pedal: alone, then with an app streaming a knob at 50 Hz beside it.

    scripts/host-lock --host vip -- python3 bench-results/2026-11-09-rig-vip/press-with-knob.py

The knob's values go through pedald's follower, so this is what O4 adds to the loop. Uses O3's probe.
Puts the rig back on Bob at the end. Writes run/press-with-knob.json.
"""

import json
import pathlib
import statistics
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "devices/common/rootfs/usr/local/lib"))
from pedald.engine import EngineClient, EngineError  # noqa: E402

TOKEN = subprocess.run(["ssh", "vip", "sudo cat /etc/namchain/token"], capture_output=True, text=True, check=True).stdout.strip()
# The host says: vip's name doesn't always resolve to IPv4 from here, and the engine listens on IPv4.
ADDRESS = subprocess.run(["ssh", "vip", "hostname -I"], capture_output=True, text=True, check=True).stdout.split()[0]
PROBE = HERE.parents[0] / "2026-11-09-files-vip" / "probe.py"
SECONDS = 25


def probe():
    done = subprocess.run(["ssh", "vip", f"sudo python3 - {SECONDS}"], stdin=open(PROBE), capture_output=True, text=True)
    values = sorted(float(line.split()[1]) for line in done.stdout.splitlines())
    return {"n": len(values), "median": statistics.median(values), "p95": values[int(len(values) * 0.95)], "max": values[-1]}


out = {"alone": probe()}
print("alone", out["alone"])

stop = threading.Event()
sent = {"ok": 0, "refused": 0}


def knob():
    client = EngineClient(ADDRESS, 47810, TOKEN, timeout=5.0, client="o4-check")
    tick = 0
    while not stop.is_set():
        tick += 1
        try:
            document = client.rig_get()["document"] if tick % 25 == 1 else document
            chain = document["chains"][0]
            node = next(n for n in chain["nodes"] if n["type"] in ("nc.gain", "fx.amp.tonestack") and "gain_db" in n)
            value = node["gain_db"] + (0.1 if tick % 2 else 0.0)
            client.rig_patch([{"op": "set_param", "node": node["id"], "param": "gain_db", "value": value}], chain=chain["id"])
            sent["ok"] += 1
        except EngineError:
            sent["refused"] += 1
            tick = 0
        time.sleep(0.02)
    client.close()


thread = threading.Thread(target=knob)
thread.start()
out["with_a_knob"] = probe()
stop.set()
thread.join()
out["knob_values"] = sent
print("with a knob", out["with_a_knob"], sent)
subprocess.run(["ssh", "vip", "sudo /opt/namchain/current/bin/namchainctl --host 127.0.0.1 --token-file /etc/namchain/token --client o4-check --quiet load Bob.json"])
(HERE / "run" / "press-with-knob.json").write_text(json.dumps(out, indent=1) + "\n")
print("median added by following a knob: %.1f ms" % (out["with_a_knob"]["median"] - out["alone"]["median"]))

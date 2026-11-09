#!/usr/bin/env python3
"""O3's check from the Mac: upload a model and an IR, play a rig that uses them, download one.

    scripts/host-lock --host vip -- bench-results/2026-11-09-files-vip/check.py

Leaves the pedal as it found it: the test rig and files go at the end, by ssh, since the API deletes
no model or IR. Writes run/check.json.
"""

import hashlib
import http.client
import json
import os
import pathlib
import socket
import statistics
import subprocess
import threading
import time
import urllib.parse

HOST = "vip"
PORT = 47820
HERE = pathlib.Path(__file__).parent
DIR = "o3-check"
TOKEN = subprocess.run(["ssh", HOST, "sudo cat /etc/namchain/token"], capture_output=True, text=True, check=True).stdout.strip()
# Once: a .local lookup per connection takes over a second here, and would hide what is measured.
ADDRESS = socket.gethostbyname("vip.local")
out = {}


def ask(method, path, body=None, headers=None, raw=False):
    conn = http.client.HTTPConnection(ADDRESS, PORT, timeout=60)
    start = time.monotonic()
    conn.request(method, path if raw else urllib.parse.quote(path, safe="/?=&"), body=body,
                 headers=dict({"Authorization": "Bearer " + TOKEN, "Pedal-Client": "o3-check"}, **(headers or {})))
    reply = conn.getresponse()
    data = reply.read()
    seconds = time.monotonic() - start
    conn.close()
    return reply.status, data, reply, seconds


def want(name, got, expected):
    ok = got == expected
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got}")
    out.setdefault("checks", []).append({"name": name, "got": got, "ok": ok})


def ssh(command):
    return subprocess.run(["ssh", HOST, command], capture_output=True, text=True).stdout.strip()


def rss():
    return int(ssh("grep VmRSS /proc/$(systemctl show -p MainPID --value pedald)/status | tr -s ' ' | cut -d' ' -f2 | tr -d '\\t' || true").split()[0])


def ctl(*args):
    return json.loads(ssh("sudo /opt/namchain/current/bin/namchainctl --host 127.0.0.1 --token-file /etc/namchain/token --client o3-check --compact "
                          + " ".join(f"'{a}'" for a in args)) or "null")


def status():
    return json.loads(ask("GET", "/status")[1])


# The catalogue
_, data, _, _ = ask("GET", "/catalogue")
catalogue = json.loads(data)
want("catalogue checked", catalogue["checked"], True)
want("templates", len(catalogue["templates"]), 27)
want("refused", catalogue["refused"], [])

# Listings
models = json.loads(ask("GET", "/library/models")[1])
irs = json.loads(ask("GET", "/library/irs")[1])
want("nothing left to hash", models["hashing"] + irs["hashing"], 0)
out["listing"] = {"models": len(models["files"]), "irs": len(irs["files"]),
                  "ms": [round(ask("GET", "/library/irs")[3] * 1000, 1) for _ in range(5)],
                  "bytes": len(json.dumps(irs))}
source_model = next(f for f in models["files"] if f["sample_rate"] == 48000 and f["metadata"])
source_ir = next(f for f in irs["files"] if f["relative"].endswith(".wav"))
print("  model:", source_model["id"], source_model["metadata"].get("name"))

# Download what the pedal has, and check it against its listing
code, model_bytes, reply, seconds = ask("GET", f"/library/models/{source_model['relative']}")
want("download's hash matches the listing", hashlib.sha256(model_bytes).hexdigest(), source_model["sha256"])
want("download's ETag", reply.getheader("ETag"), f'"{source_model["sha256"]}"')
want("a matching ETag", ask("GET", f"/library/models/{source_model['relative']}", headers={"If-None-Match": reply.getheader("ETag")})[0], 304)
ir_bytes = ask("GET", f"/library/irs/{source_ir['relative']}")[1]

# Upload a model and an IR
new_model, new_ir = f"{DIR}/Model.nam", f"{DIR}/IR.wav"
hashed_before = ssh("sudo journalctl -u pedald --no-pager -o cat | grep -c 'library: hashed'")
try:
    code, data, _, seconds = ask("PUT", f"/library/models/{new_model}", model_bytes, {"If-None-Match": "*"})
    stored = json.loads(data)
    want("model stored", code, 201)
    want("its hash", stored["sha256"], source_model["sha256"])
    out["upload_model_s"] = round(seconds, 3)
    code, data, _, seconds = ask("PUT", f"/library/irs/{new_ir}", ir_bytes, {"If-None-Match": "*"})
    want("IR stored", code, 201)
    out["upload_ir_s"] = round(seconds, 3)

    # Refusals, on the real thing
    want("again: never replaced", ask("PUT", f"/library/models/{new_model}", b"x", {"If-None-Match": "*"})[0], 412)
    want("no precondition", ask("PUT", f"/library/models/{DIR}/Other.nam", b"x")[0], 428)
    want("a second file for the id", ask("PUT", f"/library/irs/{DIR}/IR.nam", b"{}", {"If-None-Match": "*"})[0], 409)
    slow = model_bytes.replace(b'"sample_rate": 48000', b'"sample_rate": 44100').replace(b'"sample_rate":48000', b'"sample_rate":44100')
    want("a 44.1 kHz model", ask("PUT", f"/library/models/{DIR}/Slow.nam", slow, {"If-None-Match": "*"})[0], 422)
    want("a path out of the root", ask("PUT", f"/library/models/{DIR}/%2E%2E/%2E%2E/x.nam", b"x", {"If-None-Match": "*"}, raw=True)[0], 400)

    # Listed, with its hash, and nothing hashed again
    listed = {f["id"]: f for f in json.loads(ask("GET", "/library/models")[1])["files"]}
    want("listed with its hash", listed[f"{DIR}/Model"]["sha256"], source_model["sha256"])
    want("listing kept no staged file", any(f["relative"].startswith(".") for f in listed.values()), False)
    want("nothing hashed again", ssh("sudo journalctl -u pedald --no-pager -o cat | grep -c 'library: hashed'"), hashed_before)

    # Play a rig that names them
    before = status()
    # Standard has a model and an IR, so the rig uses both uploads.
    text = ask("GET", "/library/rigs/Standard")[1].decode()
    named = {}
    def swap(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "meta":
                    continue
                if value.get("type") == "nc.nam" and key == "model":
                    value[key] = f"{DIR}/Model"
                    named["model"] = True
                elif value.get("type") in ("nc.cab.ir", "fx.cab.ir") and key == "ir":
                    value[key] = f"{DIR}/IR"
                    named["ir"] = True
                swap(item)
        elif isinstance(value, list):
            for item in value:
                swap(item)
    rig = json.loads(text)
    swap(rig)
    rig["name"] = "o3-check-rig"
    print("  the rig names:", named)
    want("the rig uses both", sorted(named), ["ir", "model"])
    want("rig stored", ask("PUT", "/library/rigs/o3-check-rig", json.dumps(rig))[0], 201)
    load = ctl("load", "o3-check-rig.json")
    print("  load:", json.dumps(load)[:200])
    time.sleep(3)
    now = status()["engine"]
    want("the engine plays it", now["rig_name"], "o3-check-rig")
    want("no stand-ins", [i["code"] for i in now["issues"] if i["code"] in ("asset_missing", "missing_asset")], [])
    out["played"] = {k: now.get(k) for k in ("rig", "state", "health", "xruns", "generation", "audible_generation")}
    ctl("load", "Bob.json")
    time.sleep(1)

    # 64 MiB, then a run of small files, with presses timed on the pedal itself throughout. Five
    # seconds of nothing first, to compare with.
    size = 64 << 20
    block = os.urandom(1 << 16)
    def body():
        for _ in range(size // len(block)):
            yield block
    samples = [rss()]
    done = {}
    marks = {}
    probe = subprocess.Popen(["ssh", HOST, "sudo python3 - 75"], stdin=open(HERE / "probe.py"),
                             stdout=subprocess.PIPE, text=True)
    began = time.monotonic()
    def upload():
        conn = http.client.HTTPConnection(ADDRESS, PORT, timeout=300)
        start = time.monotonic()
        conn.request("PUT", f"/library/irs/{DIR}/Huge.wav", body=body(),
                     headers={"Authorization": "Bearer " + TOKEN, "If-None-Match": "*", "Content-Length": str(size)})
        done["status"] = conn.getresponse().status
        done["seconds"] = time.monotonic() - start
    thread = threading.Thread(target=upload)
    def watch():
        while thread.is_alive():
            samples.append(rss())
            time.sleep(0.5)
    time.sleep(6)
    marks["upload_from"] = time.monotonic() - began
    thread.start()
    watcher = threading.Thread(target=watch)
    watcher.start()
    thread.join()
    watcher.join()
    marks["upload_to"] = time.monotonic() - began
    samples.append(rss())
    want("64 MiB stored", done["status"], 201)
    out["large_upload"] = {"seconds": round(done["seconds"], 2), "rss_kb": samples[:60],
                           "rss_peak_over_start_kb": max(samples) - samples[0]}
    marks["small_from"] = time.monotonic() - began
    times = []
    for index in range(20):
        code, _, _, seconds = ask("PUT", f"/library/irs/{DIR}/small-{index}.wav", ir_bytes, {"If-None-Match": "*"})
        times.append(seconds)
    marks["small_to"] = time.monotonic() - began
    out["small_uploads_s"] = {"median": round(statistics.median(times), 3), "max": round(max(times), 3)}
    subprocess.run(["ssh", HOST, "sudo pkill -f 'python3 - 75'"])
    presses = [tuple(map(float, line.split())) for line in probe.communicate()[0].splitlines() if len(line.split()) == 2]
    def stats(low, high):
        values = sorted(ms for at, ms in presses if low <= at < high)
        if not values:
            return None
        return {"n": len(values), "median": values[len(values) // 2], "p95": values[int(len(values) * 0.95)], "max": values[-1]}
    out["press_on_the_pedal_ms"] = {"idle": stats(0, marks["upload_from"]),
                                    "during_64_mib": stats(marks["upload_from"], marks["upload_to"]),
                                    "during_small_uploads": stats(marks["small_from"], marks["small_to"])}
    out["press_on_the_pedal_ms"]["slowest_five"] = sorted(presses, key=lambda p: -p[1])[:5]
    out["press_on_the_pedal_ms"]["marks"] = {k: round(v, 2) for k, v in marks.items()}
    print(json.dumps(out["press_on_the_pedal_ms"]))
    print("64 MiB:", out["large_upload"]["seconds"], "s, RSS up", out["large_upload"]["rss_peak_over_start_kb"], "KB; small:", out["small_uploads_s"])
    out["after"] = {k: status()["engine"].get(k) for k in ("xruns", "guard_trips", "state", "health")}
    want("no xruns", out["after"]["xruns"], before["engine"]["xruns"])
finally:
    # The test's own files. The API deletes no model or IR, so this is the escape hatch.
    ask("DELETE", "/library/rigs/o3-check-rig")
    if status()["bank"]["current"] != "Bob":
        ask("POST", "/event", json.dumps({"kind": 1}))
    ctl("load", "Bob.json")
    ssh(f"sudo rm -rf '/var/lib/pedal/library/models/{DIR}' '/var/lib/pedal/library/irs/{DIR}'")
    ask("POST", "/library/refresh", b"")
    time.sleep(1)
    final = status()
    out["left"] = {"rig": final["engine"]["rig_name"], "library": final["library"], "bypass": final["bypass"]}
    print("left:", out["left"])

(HERE / "run").mkdir(exist_ok=True)
(HERE / "run" / "check.json").write_text(json.dumps(out, indent=1) + "\n")
print("FAILED" if any(not c["ok"] for c in out["checks"]) else "all passed")

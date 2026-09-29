"""Watch namchaind on piv while someone edits: every ramp and every rebuild, and what
changed in the engine's document for each. Prints diffs only, never the document.

    ssh piv python3 - [seconds] < watch-edits.py
"""
import json, subprocess, sys, time

CTL = ["sudo", "-n", "/opt/namchain/current/bin/namchainctl", "--compact"]
POLL = 0.2
LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 900


def ctl(cmd):
    r = subprocess.run(CTL + [cmd], capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "exit %d" % r.returncode)
    return json.loads(r.stdout)


def stamp():
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + ".%03d" % (int(t * 1000) % 1000)


def show(v):
    if isinstance(v, float):
        return "%.4g" % v
    s = json.dumps(v)
    return s if len(s) <= 70 else s[:67] + "..."


def name(x):
    if "type" in x:
        return "%s#%s" % (x["type"], str(x["id"])[:6])
    return str(x.get("name") or x["id"])[:24]


def keyed(xs):
    return all(isinstance(x, dict) and "id" in x for x in xs)


def diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = path + "." + k if path else k
            if k not in a:
                out.append("%s added = %s" % (p, show(b[k])))
            elif k not in b:
                out.append("%s removed (was %s)" % (p, show(a[k])))
            else:
                diff(a[k], b[k], p, out)
    elif isinstance(a, list) and isinstance(b, list) and (a or b) and keyed(a + b):
        ia = {x["id"]: x for x in a}
        ib = {x["id"]: x for x in b}
        for x in a:
            if x["id"] not in ib:
                out.append("%s: removed %s" % (path, name(x)))
        for x in b:
            if x["id"] not in ia:
                rest = {k: v for k, v in x.items() if k not in ("id", "type", "element")}
                out.append("%s: added %s %s" % (path, name(x), show(rest)))
        for x in a:
            if x["id"] in ib:
                diff(x, ib[x["id"]], "%s[%s]" % (path, name(x)), out)
        if [x["id"] for x in a if x["id"] in ib] != [x["id"] for x in b if x["id"] in ia]:
            out.append("%s: reordered" % path)
    elif isinstance(a, list) and isinstance(b, list):
        if a != b:
            out.append("%s: changed (%d -> %d items)" % (path, len(a), len(b)))
    elif a != b:
        out.append("%s: %s -> %s" % (path, show(a), show(b)))


def counters(s):
    r = s.get("render", {})
    return {"gen": s["generation"], "ramps": s["params_applied"], "trans": s["transitions_started"],
            "xruns": s["xruns"], "over_deadline": r.get("over_deadline", 0),
            "stale": s["params_stale"], "failed_nodes": s["failed_nodes"]}


s = ctl("status")["status"]
doc = ctl("get")["document"]
last = counters(s)
print(stamp(), "watching %r: generation %d, %d ramps so far, %d transitions, %d xruns, worst block %.0f%%"
      % (s.get("rig_name"), last["gen"], last["ramps"], last["trans"], last["xruns"],
         s.get("render", {}).get("worst_percent", 0)), flush=True)

start = time.time()
while time.time() - start < LIMIT:
    time.sleep(POLL)
    try:
        s = ctl("status")["status"]
    except Exception as e:
        print(stamp(), "status failed:", e, flush=True)
        continue
    now = counters(s)
    if now["gen"] != last["gen"] or now["ramps"] != last["ramps"]:
        try:
            new = ctl("get")["document"]
        except Exception as e:
            print(stamp(), "get failed:", e, flush=True)
            continue
        what = []
        if now["ramps"] != last["ramps"]:
            what.append("+%d ramps" % (now["ramps"] - last["ramps"]))
        if now["gen"] != last["gen"]:
            what.append("REBUILD generation %d -> %d" % (last["gen"], now["gen"]))
        out = []
        diff(doc, new, "", out)
        print(stamp(), ", ".join(what), "| %s" % s.get("rig_name"), flush=True)
        for line in out[:40]:
            print("        ", line, flush=True)
        if len(out) > 40:
            print("         ... and %d more" % (len(out) - 40), flush=True)
        doc = new
    for k in ("xruns", "over_deadline", "stale", "failed_nodes"):
        if now[k] != last[k]:
            print(stamp(), "%s %d -> %d" % (k, last[k], now[k]), flush=True)
    last = now

print(stamp(), "done: generation %d, %d ramps, %d transitions, %d xruns"
      % (last["gen"], last["ramps"], last["trans"], last["xruns"]), flush=True)

#!/usr/bin/env python3
"""analyse-v2.py RUN_DIR — the V2 arms side by side, from what run-v2 left in RUN_DIR.

Per arm: the soak gate (soak-summary.py's PASS/FAIL and its counts), the render core's load tail, the
engine's worst block in the window, per-core busy over the arm (/proc/stat), rigpa's CPU share and its
PSS, MemAvailable, and the temperature range.
"""
import json
import os
import re
import sys

ARMS = ["off", "idle", "meters", "animate", "off2"]
TICK = 100  # USER_HZ


def proc_stat(lines):
    out = {}
    for l in lines:
        if re.match(r"^cpu\d", l):
            f = l.split()
            vals = list(map(int, f[1:]))
            idle = vals[3] + vals[4]
            out[f[0]] = (sum(vals), idle)
    return out


def side(path):
    lines = open(path).read().splitlines()
    d = {"cpu": proc_stat(lines)}
    for l in lines:
        if l.startswith("MemAvailable:"):
            d["mem_kb"] = int(l.split()[1])
        elif l.startswith("Pss:"):
            d["pss_kb"] = int(l.split()[1])
        elif l.startswith("Rss:"):
            d["rss_kb"] = int(l.split()[1])
        elif l.startswith("ticks "):
            d["ticks"] = int(l.split()[1])
    return d


def histogram(s):
    return {int(p): int(n) for p, n in s["render"]["load_histogram"]}


def soak(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    good = [r for r in rows if r.get("engine") and r["engine"].get("ok")]
    a, b = good[0]["engine"]["status"], good[-1]["engine"]["status"]
    span = good[-1]["t"] - good[0]["t"]
    h0, h1 = histogram(a), histogram(b)
    w = {p: h1.get(p, 0) - h0.get(p, 0) for p in set(h0) | set(h1)}
    w = {p: n for p, n in w.items() if n > 0}
    total = sum(w.values())

    def pct(q):
        run = 0
        for p in sorted(w):
            run += w[p]
            if run >= q * total:
                return p
        return max(w)

    temps = [r["temp_c"] for r in rows if isinstance(r.get("temp_c"), (int, float))]
    return {
        "span": span, "blocks": total, "p50": pct(0.5), "p99": pct(0.99), "p999": pct(0.999),
        "worst": max(w) if w else 0,
        "xruns": b["xruns"] - a["xruns"],
        "over": b["render"]["over_deadline"] - a["render"]["over_deadline"],
        "over90": b["render"]["over_90_percent"] - a["render"]["over_90_percent"],
        "guard": b["guard_trips"] - a["guard_trips"],
        "temp": (min(temps), max(temps)) if temps else (None, None),
        "tail40": sum(n for p, n in w.items() if p >= 40),
    }


def main():
    d = sys.argv[1]
    rows = []
    for arm in ARMS:
        if not os.path.exists(os.path.join(d, arm + ".jsonl")):
            continue
        s = soak(os.path.join(d, arm + ".jsonl"))
        before, after = side(os.path.join(d, arm + ".before.txt")), side(os.path.join(d, arm + ".after.txt"))
        busy = {}
        for cpu in sorted(after["cpu"]):
            t0, i0 = before["cpu"][cpu]
            t1, i1 = after["cpu"][cpu]
            busy[cpu] = 100.0 * (1 - (i1 - i0) / (t1 - t0)) if t1 > t0 else 0.0
        rigpa_cpu = None
        if "ticks" in before and "ticks" in after:
            rigpa_cpu = 100.0 * (after["ticks"] - before["ticks"]) / TICK / s["span"]
        summary = open(os.path.join(d, arm + ".summary.txt")).read().strip().splitlines()[-1]
        rows.append((arm, s, busy, rigpa_cpu, after, summary))

    print("| arm | gate | xruns / over deadline / over 90% / guard | load p50 / p99 / p99.9 / worst | blocks >= 40% "
          "| core 0 / 1 / 2 / 3 busy | rigpa CPU | rigpa PSS | MemAvailable | temp |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for arm, s, busy, rc, after, summary in rows:
        cores = " / ".join("%.1f%%" % busy.get("cpu%d" % i, 0) for i in range(4))
        print("| %s | %s | %d / %d / %d / %d | %d%% / %d%% / %d%% / %d%% | %d | %s | %s | %s | %d MB | %.1f..%.1f °C |" % (
            arm, summary, s["xruns"], s["over"], s["over90"], s["guard"], s["p50"], s["p99"], s["p999"], s["worst"],
            s["tail40"], cores, "%.1f%% of a core" % rc if rc is not None else "—",
            "%d MB" % (after["pss_kb"] // 1024) if "pss_kb" in after else "—", after.get("mem_kb", 0) // 1024,
            s["temp"][0], s["temp"][1]))


if __name__ == "__main__":
    main()

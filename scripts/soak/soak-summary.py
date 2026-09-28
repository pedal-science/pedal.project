#!/usr/bin/env python3
# Summarise a soak-monitor.sh log against plan Phase 1 step 8's gate: 0 driver xruns, 0 deadline
# overruns, 0 guard trips, and the worst block inside 90% of the deadline.
#   soak-summary.py OUT.jsonl
import json
import sys

rows = []
for line in open(sys.argv[1]):
    line = line.strip()
    if line:
        rows.append(json.loads(line))
good = [r for r in rows if r.get("engine") and r["engine"].get("ok")]
if len(good) < 2:
    sys.exit("fewer than two good samples")
first, last = good[0]["engine"]["status"], good[-1]["engine"]["status"]
span = good[-1]["t"] - good[0]["t"]
missing = len(rows) - len(good)


def delta(key, sub=None):
    a = first[sub][key] if sub else first[key]
    b = last[sub][key] if sub else last[key]
    return b - a


def histogram(s):
    return {int(p): int(n) for p, n in s["render"]["load_histogram"]}


h0, h1 = histogram(first), histogram(last)
window = {p: h1.get(p, 0) - h0.get(p, 0) for p in set(h0) | set(h1)}
window = {p: n for p, n in window.items() if n > 0}
blocks = sum(window.values())


def percentile(q):
    target = q * blocks
    run = 0
    for p in sorted(window):
        run += window[p]
        if run >= target:
            return p
    return max(window)


restarted = any(r["engine"]["status"]["blocks"] < p["engine"]["status"]["blocks"]
                for p, r in zip(good, good[1:]))
worst_in_window = max(window) if window else 0
worst_us_changed = last["render"]["worst_us"] > first["render"]["worst_us"]

print(f"{len(rows)} samples over {span / 60:.1f} min ({missing} without an answer from namchaind)")
if restarted:
    print("namchaind RESTARTED during the soak: the deltas below are not meaningful")
print(f"rig {last['rig_name'] or last['rig']}, period {last['period_size']}, "
      f"deadline {last['render']['deadline_us']:.1f} us")
print(f"blocks {delta('blocks')} (timed {blocks})")
print(f"load: p50 {percentile(0.5)}%, p99 {percentile(0.99)}%, p99.9 {percentile(0.999)}%, "
      f"worst bucket {worst_in_window}%")
if worst_us_changed:
    print(f"worst block: {last['render']['worst_us']:.1f} us ({last['render']['worst_percent']:.1f}%), during the soak")
else:
    print(f"worst block during the soak: in the {worst_in_window}% bucket "
          f"(the daemon's all-time worst, {last['render']['worst_us']:.1f} us, came before it)")
print("tail:", {p: window[p] for p in sorted(window) if p >= 30})

temps = [r["temp_c"] for r in rows if isinstance(r.get("temp_c"), (int, float))]
throttles = sorted({r.get("throttled") for r in rows})
print(f"temperature {min(temps):.1f}..{max(temps):.1f} C, throttled flags seen: {throttles}")
print(f"edits: generation {first['generation']} -> {last['generation']}, "
      f"params_applied +{delta('params_applied')}, transitions +{delta('transitions_started')}, "
      f"max TCP connections seen {max(r['engine']['status']['control']['tcp_connections'] for r in good)}")
print(f"queue: drops +{delta('output_drops', 'queue')}, insertions +{delta('floor_insertions', 'queue')}, "
      f"capture bursts +{delta('capture_bursts', 'queue')}")

gate = {
    "driver xruns": delta("xruns"),
    "deadline overruns": delta("over_deadline", "render"),
    "guard trips": delta("guard_trips"),
    "blocks over 90%": delta("over_90_percent", "render"),
    "render errors": delta("render_errors"),
    "device lost": delta("device_lost"),
}
print("gate:", ", ".join(f"{k} {v}" for k, v in gate.items()))
passed = all(v == 0 for v in gate.values()) and not restarted and missing == 0
print("PASS" if passed else "FAIL")

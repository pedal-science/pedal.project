#!/usr/bin/env python3
# Which soak-monitor.sh samples saw slow blocks, and whether a rig transition happened in the same
# interval.
#   soak-events.py OUT.jsonl
import json
import sys

rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
t0 = rows[0]["t"]
prev = None
counts = {"with a transition": 0, "without": 0}
transition_intervals = 0
for r in rows:
    s = r["engine"]["status"]
    if prev is not None:
        over90 = s["render"]["over_90_percent"] - prev["render"]["over_90_percent"]
        over = s["render"]["over_deadline"] - prev["render"]["over_deadline"]
        trans = s["transitions_started"] - prev["transitions_started"]
        transition_intervals += trans > 0
        if over90:
            counts["with a transition" if trans else "without"] += 1
            print(f"t+{r['t'] - t0:5d} s  over 90% +{over90}  over deadline +{over}  transitions +{trans}")
    prev = s
print(f"intervals with a block over 90%: {counts}; intervals with any transition: {transition_intervals}")

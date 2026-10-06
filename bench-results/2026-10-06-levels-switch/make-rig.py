#!/usr/bin/env python3
"""Generate the synthetic rig the levels campaign measures with.

Why a generated rig and not a real one: this is the *second* series of the campaign, and its job is
to make the per-sample cost of measuring a level visible. That cost is per probe per sample, so it
scales with the number of nodes -- and a rig of plain `nc.gain` nodes isolates it exactly. Each gain
is one multiply per sample, which is close to free, so a chain of them is a rig whose own cost is
negligible beside the cost of *watching* it. That is the measurement: not a realistic pedal rig's
number, but the upper bound on what turning the measurement off can save.

A model node (nc.nam) would make the number smaller and less legible, because an A2 inference
dominates any probe. If you want that number, measure it: the campaign's first series is what a real
rig does, and a real rig's saving is between the two.

Usage:
  make-rig.py --nodes 32 > heavy-rig.json
"""

import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--nodes", type=int, default=32, help="gain nodes in the chain")
parser.add_argument("--gain", type=float, default=1.0,
                    help="linear gain per node; 1.0 keeps the level steady along the chain")
args = parser.parse_args()

nodes = [{"id": "in", "type": "nc.input"}]
connections = []

previous = "in"
for index in range(args.nodes):
    node_id = f"g{index}"
    nodes.append({"id": node_id, "type": "nc.gain", "gain": args.gain, "ramp_ms": 0})
    connections.append({"from": previous, "to": node_id})
    previous = node_id

nodes.append({"id": "out", "type": "nc.output"})
connections.append({"from": previous, "to": "out"})

print(json.dumps({"nodes": nodes, "connections": connections}, indent=2))

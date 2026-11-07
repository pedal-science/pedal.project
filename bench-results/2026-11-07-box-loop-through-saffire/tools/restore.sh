#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -I nc.py rig.apply restore2.json | python3 -c 'import json,sys;d=json.load(sys.stdin);print("restored",d["ok"],d.get("name"),"gen",d.get("generation"))'
sleep 1; python3 -I nc.py engine.levels >/dev/null; sleep 1.5
python3 -I nc.py engine.levels | python3 -c 'import json,sys;d=json.load(sys.stdin);l=d.get("levels",d);print("New Rig, no signal: engine in",l["input"]["peak"],"out",l["output"]["peak"])'

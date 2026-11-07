#!/usr/bin/env bash
cd "$(dirname "$0")"
echo '{"rig":"Standard.json"}' | python3 -I nc.py rig.load - >/dev/null; sleep 2
echo '{"action":"start","name":"idle-standard-'$(date +%H%M%S)'","seconds":4}' | python3 -I nc.py engine.record - | tee rec.start.json | python3 -c 'import json,sys;d=json.load(sys.stdin);print("record",d["ok"],d.get("record",{}).get("path"),d.get("error"))'
sleep 5
python3 -I nc.py rig.apply restore2.json | python3 -c 'import json,sys;d=json.load(sys.stdin);print("restored",d["ok"],d.get("name"))'

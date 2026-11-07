#!/usr/bin/env bash
# run.sh <name> <rig-args.json> [level]: publish a rig on vip, then loop it through piv's Saffire.
set -euo pipefail
cd "$(dirname "$0")"
name=$1 rig=$2 lvl=${3:--20}
if [[ $rig == load:* ]]; then echo "{\"rig\":\"${rig#load:}\"}" | python3 -I nc.py rig.load - > "$name.publish.json"
else python3 -I nc.py rig.apply "$rig" > "$name.publish.json"; fi
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print("publish",d.get("ok"),d.get("generation"),d.get("error"),d.get("slimmed_models"))' "$name.publish.json"
sleep 1.5
python3 -I nc.py engine.status > "$name.status-before.json"
ssh piv "cd /tmp && python3 loop.py $name $lvl" > "$name.result.json"
python3 -I nc.py engine.status > "$name.status-after.json"
scp -q "piv:/tmp/$name.in.raw" .
python3 - "$name" <<'PY'
import json,sys
n=sys.argv[1]; r=json.load(open(n+".result.json"))
for c in r["channels"]: print(json.dumps(c))
b,a=(json.load(open(f"{n}.status-{w}.json"))["status"] for w in ("before","after"))
print("engine: health",a.get("health"),"issues",a.get("issues"),"xruns",b.get("xruns"),"->",a.get("xruns"),
      "guard",a.get("guard_trips"),"failed",a.get("failed_nodes"),"render worst%",a.get("render",{}).get("worst_percent"),
      "over_deadline",b.get("render",{}).get("over_deadline"),"->",a.get("render",{}).get("over_deadline"))
print("rig",a.get("rig"),"gen",a.get("generation"),"chains",[(c["id"],c.get("output_channel"),c.get("failed_nodes")) for c in a.get("chains",[])])
PY

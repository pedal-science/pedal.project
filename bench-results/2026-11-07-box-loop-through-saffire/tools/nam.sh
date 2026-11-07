#!/usr/bin/env bash
cd "$(dirname "$0")"
echo '{"rig":"Standard.json"}' | python3 -I nc.py rig.load - > std.publish.json
python3 -c 'import json;d=json.load(open("std.publish.json"));print("load",d.get("ok"),d.get("rig"),"gen",d.get("generation"),d.get("error"),"slimmed",d.get("slimmed_models"),"missing",d.get("missing_assets"))'
sleep 2; python3 -I nc.py engine.status > std.before.json
ssh piv 'cd /tmp; aplay -q -D hw:CARD=USB,DEV=0 -f S24_3LE -r 48000 -c 4 -t raw tone8.raw' &
for i in 1 2 3 4; do sleep 1.5; python3 -I nc.py engine.levels > std.levels.$i.json; done; wait
python3 -I nc.py engine.status > std.after.json
python3 - <<'PY'
import json
l=json.load(open("std.levels.3.json")); l=l.get("levels",l)
print("in",l["input"]["peak"],"out",l["output"]["peak"])
for c in l["chains"]:
  for n in c["nodes"]: print("  ",(n.get("role") or n["node"])[:40].ljust(40),"peak",n["peak"],"rms",n["rms"])
b,a=(json.load(open(f))["status"] for f in ("std.before.json","std.after.json"))
r=a["render"]; print("health",a["health"],a["issues"],"xruns",b["xruns"],"->",a["xruns"],"guard",a["guard_trips"],"failed",a["failed_nodes"])
print("render worst%",round(r["worst_percent"],1),"over_90",b["render"]["over_90_percent"],"->",r["over_90_percent"],"over_deadline",b["render"]["over_deadline"],"->",r["over_deadline"])
print("cost",json.dumps({k:a["cost"][k] for k in a["cost"] if not isinstance(a["cost"][k],(list,dict))}))
PY

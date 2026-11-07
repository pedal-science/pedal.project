#!/usr/bin/env bash
cd "$(dirname "$0")"
lv() { python3 -I nc.py engine.levels | python3 -c 'import json,sys;d=json.load(sys.stdin);l=d.get("levels",d);print(sys.argv[1].ljust(22),"engine in",l["input"]["peak"][0],"out",l["output"]["peak"][0])' "$1"; }
python3 -I nc.py engine.levels >/dev/null; sleep 1; lv "Standard, no signal"
echo '{"mute":true}' | python3 -I nc.py engine.mute - >/dev/null; sleep 1; python3 -I nc.py engine.levels >/dev/null; sleep 1; lv "engine muted"
echo '{"mute":false}' | python3 -I nc.py engine.mute - >/dev/null; sleep 1.5; python3 -I nc.py engine.levels >/dev/null; sleep 1; lv "unmuted again"

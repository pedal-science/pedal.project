#!/usr/bin/env bash
cd "$(dirname "$0")"
ssh piv 'cd /tmp; aplay -q -D hw:CARD=USB,DEV=0 -f S24_3LE -r 48000 -c 4 -t raw tone8.raw' &
for i in 1 2 3 4; do sleep 1.5; python3 -I nc.py engine.levels | python3 -c 'import json,sys;d=json.load(sys.stdin);l=d.get("levels",d);print("in",l["input"]["peak"],l["input"]["rms"],"out",l["output"]["peak"],"chains",[(c["id"],c["out"]["peak"]) for c in l["chains"]])'; done; wait

#!/usr/bin/env bash
# Standard with no signal: engine meters, then a 2 s capture on piv, then muted, then put the rig back.
cd "$(dirname "$0")"
lv() { python3 -I nc.py engine.levels | python3 -c 'import json,sys;d=json.load(sys.stdin);l=d.get("levels",d);print(sys.argv[1].ljust(22),"engine in",l["input"]["peak"][0],"out",l["output"]["peak"][0])' "$1"; }
echo '{"rig":"Standard.json"}' | python3 -I nc.py rig.load - | python3 -c 'import json,sys;print("load",json.load(sys.stdin)["ok"])'
sleep 2; python3 -I nc.py engine.levels >/dev/null; sleep 1; lv "Standard, no signal"
ssh piv 'arecord -q -D hw:CARD=USB,DEV=0 -f S24_3LE -r 48000 -c 2 -t raw -d 2 /tmp/fb.raw; python3 -c "
import numpy as np
b=np.frombuffer(open(\"/tmp/fb.raw\",\"rb\").read(),np.uint8);b=b[:len(b)//6*6].reshape(-1,3);v=(b[:,0].astype(np.int32)|b[:,1].astype(np.int32)<<8|b[:,2].astype(np.int32)<<16);v=np.where(v&0x800000,v-0x1000000,v)/8388608.0;x=v.reshape(-1,2)
for c in range(2):
  y=x[:,c];S=np.abs(np.fft.rfft(y*np.hanning(len(y))))**2;f=np.fft.rfftfreq(len(y),1/48000)
  print(\"  Saffire in\",c+1,\"rms %.1f dBFS, strongest %.0f Hz\"%(10*np.log10(np.mean(y**2)+1e-20),f[np.argmax(S)]))
"; rm -f /tmp/fb.raw'
echo '{"mute":true}' | python3 -I nc.py engine.mute - >/dev/null; sleep 1; python3 -I nc.py engine.levels >/dev/null; sleep 1; lv "engine muted"
echo '{"mute":false}' | python3 -I nc.py engine.mute - >/dev/null
python3 -I nc.py rig.apply restore2.json | python3 -c 'import json,sys;d=json.load(sys.stdin);print("restored",d["ok"],d.get("name"))'

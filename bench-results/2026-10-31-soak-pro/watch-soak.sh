#!/usr/bin/env bash
# Run on pro: a soak with turbostat (SMI, clock, power, temperature) and kernel messages logged beside it.
# usage: watch-soak.sh <seconds> <out-dir>
set -u
secs=$1 out=$2
mkdir -p "$out"
cd ~/pedal-bench
sudo -n systemctl stop namchaind
sudo -n turbostat --quiet --show Core,Busy%,Bzy_MHz,SMI,PkgWatt,PkgTmp --interval 5 \
  --num_iterations $((secs / 5 + 2)) >"$out/turbostat.txt" 2>&1 &
ts=$!
date -u +%FT%TZ >"$out/start.txt"
sudo -n /opt/namchain/current/bin/namchain-soak --backend alsa_raw --device 'hw:CARD=U192k,DEV=0' \
  --channels 2 --periods 6 --quantum 64 --seconds "$secs" --model ORNG-V30-421-Center.nam \
  --instances 2 --cpu 5 --rt-priority 80 --max-p99-percent 80 guitar-di.wav >"$out/soak.txt" 2>&1
echo "soak-exit=$?" >>"$out/soak.txt"
date -u +%FT%TZ >"$out/end.txt"
kill "$ts" 2>/dev/null; wait "$ts" 2>/dev/null
journalctl -k --since "$(cat "$out/start.txt")" --no-pager >"$out/kernel.txt"
sudo -n systemctl start namchaind

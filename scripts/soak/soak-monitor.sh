#!/bin/sh
# Log namchaind's engine.status, the SoC temperature and the throttle flags, one JSON line per
# sample, for a soak. Run as root on the Core host, under scripts/host-lock:
#   soak-monitor.sh OUT.jsonl [SECONDS=3600] [INTERVAL=10]
# soak-summary.py OUT.jsonl reads it.
set -u
OUT=$1
SECS=${2:-3600}
INTERVAL=${3:-10}
CTL=/opt/namchain/current/bin/namchainctl
end=$(( $(date +%s) + SECS ))
while :; do
  now=$(date +%s)
  status=$($CTL --compact status 2>/dev/null) || status=null
  [ -n "$status" ] || status=null
  throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
  temp=$(vcgencmd measure_temp 2>/dev/null | sed 's/temp=//; s/.C$//')
  printf '{"t":%s,"throttled":"%s","temp_c":%s,"engine":%s}\n' \
    "$now" "${throttled:-?}" "${temp:-null}" "$status" >> "$OUT"
  [ "$now" -ge "$end" ] && break
  sleep "$INTERVAL"
done

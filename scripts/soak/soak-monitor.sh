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
  # vip has no vcgencmd (no Pi userland in its image): the kernel's thermal zone for the
  # temperature, and the cores' current clock against their cap for thermal throttling, which on
  # a Pi 5 shows as the clock dropping below it.
  if [ -z "$temp" ] && [ -r /sys/class/thermal/thermal_zone0/temp ]; then
    temp=$(awk '{printf "%.1f", $1 / 1000}' /sys/class/thermal/thermal_zone0/temp)
  fi
  [ -n "$throttled" ] || throttled=n/a
  khz=$(cat /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq 2>/dev/null | sort -n | head -1)
  printf '{"t":%s,"throttled":"%s","temp_c":%s,"min_khz":%s,"engine":%s}\n' \
    "$now" "${throttled:-?}" "${temp:-null}" "${khz:-null}" "$status" >> "$OUT"
  [ "$now" -ge "$end" ] && break
  sleep "$INTERVAL"
done

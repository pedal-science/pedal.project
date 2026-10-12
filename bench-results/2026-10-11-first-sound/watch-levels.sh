#!/usr/bin/env bash
# watch-levels.sh — the engine's device levels, once every two seconds, to a log.
#
# Reads only: no lock, no state change. Used while the owner flips the Inst/Line switch or
# moves a lead, so the reading and the action line up in one file.
#
#   ./watch-levels.sh <log> <samples>
set -uo pipefail
LOG=${1:?log path}
N=${2:-450}
: > "$LOG"
for _ in $(seq "$N"); do
  ts=$(date +%H:%M:%S)
  v=$(ssh -o BatchMode=yes -o ConnectTimeout=5 vip \
      'sudo -n /opt/namchain/current/bin/namchainctl levels' 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)["levels"]
    i, o = d["input"], d["output"]
    print("inL rms %7.1f peak %7.1f | inR rms %7.1f | outL rms %7.1f" %
          (i["rms"][0], i["peak"][0], i["rms"][1], o["rms"][0]))
except Exception:
    print("(no reply)")
')
  echo "$ts $v" >> "$LOG"
  sleep 2
done

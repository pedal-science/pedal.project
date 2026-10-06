#!/usr/bin/env bash
# The levels campaign: what measuring audio levels costs namchaind, and what a client polling them
# costs on top.
#
# Run from the Mac, against vip. It is deliberately one script that does everything -- put the rig
# in place, change the switch, restart, settle, measure, repeat -- because a measurement assembled
# from hand-typed steps is a measurement nobody can repeat.
#
# Two series, because the switch has two costs and they are not visible in the same place:
#
#   A. no rig loaded ("idle"). No chain runs, so there is nothing per sample to measure: this series
#      is the cost of *answering* -- the JSON for the device's channels, built and sent once per
#      poll. Conditions 1-8.
#   B. a 32-gain rig loaded ("heavy"). The chain runs, so every node's probe folds a sample per
#      sample: this series is the cost of *measuring*, which is what --no-levels removes. Conditions
#      9-16, the same eight switches. The rig is synthetic and its own cost is ~one multiply per
#      node, which is the point: it is an upper bound on what turning the measurement off can save,
#      not a realistic rig's number.
#
# Each condition runs at the same window length, so every CPU figure is an average over a window
# that means the same thing. CPU is the daemon process's own utime+stime, every thread included,
# read from /proc/<pid>/stat before and after -- the kernel's accounting, not a sampled estimate.
#
# Restores the unit when it finishes, including on failure.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
HOST=vip
SECONDS_PER_RUN=${SECONDS_PER_RUN:-120}
SETTLE_SECONDS=${SETTLE_SECONDS:-8}
RESULTS=${RESULTS:-$HERE/results.jsonl}
POLLER=$HERE/poll-levels.py
RIG_GEN=$HERE/make-rig.py

# --only 1,2,3 runs a subset: for a smoke test before spending half an hour on the whole thing.
ONLY=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --only) ONLY=$2; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
wanted() { [[ -z $ONLY ]] || [[ ",$ONLY," == *",$1,"* ]]; }

# What this campaign varies, and nothing else. systemd replaces ExecStart wholesale, so the path and
# --config have to be restated -- but everything else stays where the device put it: vip's
# /etc/namchain/namchaind.json, and the device's own drop-in (10-pedal.conf: the realtime slice, the
# CPU affinity, the control thread's policy, `pedald seed`). Spelling those out here as well would be
# a second place for the device's configuration to drift from, which is what devices/vip exists to
# prevent. The path is the one 10-pedal.conf uses; the unit file's own /usr/bin/namchaind does not
# exist on vip.
UNIT_PATH=/opt/namchain/current/bin/namchaind
UNIT_FLAGS=(--config /etc/namchain/namchaind.json)
DROPIN=/etc/systemd/system/namchaind.service.d/50-levels-campaign.conf

log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }

: > "$RESULTS"

# --- put the instrument and both rig documents on the host ------------------
log "installing the poller and the rigs on $HOST"
scp -q "$POLLER" "$HOST:/tmp/poll-levels.py"
# Two rigs, both absolute paths. A bare name would resolve under the pedal's own rig library
# (/var/lib/pedal/library/rigs, what the service resumes), and a campaign has no business writing
# into that: it is the owner's rigs, and a measurement that leaves a file there has changed the
# pedal. Both rigs are passed with --rig, which wins over the daemon's own startup rig, so every
# condition runs the same document rather than whatever `pedald seed` last left behind.
"$RIG_GEN" --nodes 32 | ssh "$HOST" 'cat > /tmp/levels-heavy-rig.json'
"$RIG_GEN" --nodes 0 | ssh "$HOST" 'cat > /tmp/levels-minimal-rig.json'
ssh "$HOST" 'sudo -n install -d /etc/namchain/rigs && sudo -n install -m 0644 /tmp/levels-heavy-rig.json /etc/namchain/rigs/levels-heavy.json && sudo -n install -m 0644 /tmp/levels-minimal-rig.json /etc/namchain/rigs/levels-minimal.json && sudo -n install -m 0600 /etc/namchain/token /etc/namchain/token.campaign && echo "rigs installed: heavy $(wc -c < /etc/namchain/rigs/levels-heavy.json) bytes, minimal $(wc -c < /etc/namchain/rigs/levels-minimal.json) bytes"'

RIG_MINIMAL=/etc/namchain/rigs/levels-minimal.json
RIG_HEAVY=/etc/namchain/rigs/levels-heavy.json

# --- the unit, and putting it back ----------------------------------------
# The drop-in is a configuration change to the pedal's service, so it always goes: whatever happens,
# namchaind is left starting the way devices/vip says it starts. The rig documents and the token copy
# are inert files that the next run overwrites, so they stay unless KEEP_INSTRUMENT=0 is asked for --
# removing them on every exit is what made the second run of this campaign fail with a rig that was
# no longer there.
restore_unit() {
  log "restoring the unit"
  ssh "$HOST" 'sudo -n rm -f /etc/systemd/system/namchaind.service.d/50-levels-campaign.conf; sudo -n systemctl daemon-reload; sudo -n systemctl reset-failed namchaind 2>/dev/null; sudo -n systemctl restart namchaind; sleep 3; systemctl is-active namchaind'
  if [[ ${KEEP_INSTRUMENT:-1} == 0 ]]; then
    log "removing the campaign's rigs from $HOST"
    ssh "$HOST" 'sudo -n rm -f /etc/namchain/token.campaign /etc/namchain/rigs/levels-heavy.json /etc/namchain/rigs/levels-minimal.json'
  fi
}
trap restore_unit EXIT

# --- one condition ---------------------------------------------------------
# start_daemon <levels:on|off> <rig path> <expected nodes>
start_daemon() {
  local levels=$1 rig=$2 expected_nodes=$3 flags=("${UNIT_FLAGS[@]}")
  [[ $levels == off ]] && flags+=(--no-levels) || flags+=(--levels)
  flags+=(--rig "$rig")

  ssh "$HOST" "sudo -n install -d /etc/systemd/system/namchaind.service.d && printf '%s\n' '[Service]' 'ExecStart=' 'ExecStart=$UNIT_PATH ${flags[*]}' | sudo -n tee $DROPIN >/dev/null && sudo -n systemctl daemon-reload && sudo -n systemctl reset-failed namchaind 2>/dev/null; sudo -n systemctl restart namchaind" >/dev/null

  # Settle, and *check* -- not just "the daemon is up". The window must be the window this condition
  # claims, so two things are confirmed before it starts: the switch took the value asked for, and
  # the rig that loaded is the rig the campaign asked for. Neither is ceremony. The first attempt at
  # this measured whatever `pedald seed` had resumed -- a different document, with a different node
  # count -- and nothing in the CPU numbers would have said so.
  local ready=no
  for _ in $(seq 1 60); do
    if ssh "$HOST" "sudo -n /opt/namchain/current/bin/namchainctl --socket /run/namchain/namchaind.sock status --compact" 2>/dev/null | grep -q '"state": *"running"'; then
      ready=yes; break
    fi
    sleep 0.5
  done
  [[ $ready == yes ]] || { echo "the daemon never reached running with levels=$levels rig=$rig" >&2; return 1; }
  sleep "$SETTLE_SECONDS"

  # One call decides both checks, and which check it is depends on the switch:
  #   on  -- engine.levels answers, and the number of nodes in the reply is the rig's shape;
  #   off -- engine.levels is *refused*. A daemon that answers here is a daemon whose --no-levels
  #          did not take, and measuring it would be measuring the wrong thing under the wrong name.
  local seen refusal_flag=""
  [[ $levels == off ]] && refusal_flag=--expect-refusal
  seen=$(ssh "$HOST" "sudo -n python3 /tmp/poll-levels.py --seconds 1 --hz 10 --pid \$(pgrep -x namchaind | head -1) --token-file /etc/namchain/token.campaign $refusal_flag")
  if [[ $levels == on ]]; then
    local reported
    reported=$(echo "$seen" | python3 -c 'import sys,json; print(json.load(sys.stdin)["nodes"])' 2>/dev/null)
    if [[ $reported != "$expected_nodes" ]]; then
      echo "the rig did not load: expected $expected_nodes nodes, the daemon reports '${reported:-nothing}'" >&2
      echo "  raw: $seen" >&2
      return 1
    fi
  else
    if ! echo "$seen" | grep -q '"refused": true'; then
      echo "levels=off but engine.levels answered: $seen" >&2
      return 1
    fi
  fi
}

# cpu_sample <seconds> -- the same window as a polling run, so the no-poll conditions are comparable
cpu_sample() {
  ssh "$HOST" "pid=\$(pgrep -x namchaind | head -1); before=\$(awk '{print \$14+\$15}' /proc/\$pid/stat); sleep $1; after=\$(awk '{print \$14+\$15}' /proc/\$pid/stat); echo \$((after-before))"
}

# poll_run <hz> <pid-owned-by-remote>
poll_run() {
  ssh "$HOST" "sudo -n python3 /tmp/poll-levels.py --seconds $SECONDS_PER_RUN --hz $1 --pid \$(pgrep -x namchaind | head -1) --token-file /etc/namchain/token.campaign --label '$2'"
}

# run_condition <n> <series> <levels on|off> <rig path> <expected nodes> <hz|none>
run_condition() {
  local n=$1 series=$2 levels=$3 rig=$4 expected_nodes=$5 hz=$6 label
  wanted "$n" || return 0
  label=$(printf '%s-%s-%s' "$series" "$levels" "${hz}hz")
  log "condition $n: $label (rig=$rig, $expected_nodes nodes)"
  if ! start_daemon "$levels" "$rig" "$expected_nodes"; then
    echo "{\"condition\": $n, \"label\": \"$label\", \"error\": \"the condition never became ready\"}" >> "$RESULTS"
    return 1
  fi

  local daemon_pid
  daemon_pid=$(ssh "$HOST" "pgrep -x namchaind | head -1")

  local ticks
  if [[ $hz == none ]]; then
    ticks=$(cpu_sample "$SECONDS_PER_RUN")
    echo "{\"condition\": $n, \"label\": \"$label\", \"series\": \"$series\", \"levels\": \"$levels\", \"rig\": \"$rig\", \"nodes\": $expected_nodes, \"hz\": null, \"seconds\": $SECONDS_PER_RUN, \"cpu_ticks\": $ticks, \"ticks\": 0}" >> "$RESULTS"
  else
    local out
    out=$(poll_run "$hz" "$label")
    echo "$out" | python3 -c "
import json, sys
r = json.load(sys.stdin)
r['condition'] = $n
r['series'] = '$series'
r['levels'] = '$levels'
r['rig'] = '$rig'
r['daemon_pid'] = $daemon_pid
print(json.dumps(r))
" >> "$RESULTS"
  fi
  tail -1 "$RESULTS" | python3 -c 'import json,sys; r=json.load(sys.stdin); print("    cpu_ticks=%s ticks=%s achieved=%s Hz empty=%s nodes=%s" % (r.get("cpu_ticks"), r.get("ticks"), r.get("achieved_hz"), r.get("empty_windows"), r.get("nodes")), file=sys.stderr)'
}

log "host lock: $(cd /Users/rik/code.local/pedal/pedal.project && scripts/host-lock --host vip --who 2>&1 | head -1)"
log "window: ${SECONDS_PER_RUN}s per condition"

# --- series A: a minimal rig. The cost of answering. -----------------------
# Two nodes (input, output): the chain runs and the device's channels are real, so this is a working
# engine with nothing to measure inside it. What varies between these conditions is therefore the
# cost of the levels *reply* -- the JSON built and sent once per poll -- and not the cost of folding
# samples into probes, which needs nodes to exist.
run_condition 1  minimal off "$RIG_MINIMAL" 2 none
run_condition 2  minimal on  "$RIG_MINIMAL" 2 none
run_condition 3  minimal on  "$RIG_MINIMAL" 2 20
run_condition 4  minimal on  "$RIG_MINIMAL" 2 10
run_condition 5  minimal on  "$RIG_MINIMAL" 2 5
run_condition 6  minimal on  "$RIG_MINIMAL" 2 4
run_condition 7  minimal on  "$RIG_MINIMAL" 2 3
run_condition 8  minimal on  "$RIG_MINIMAL" 2 2
run_condition 9  minimal on  "$RIG_MINIMAL" 2 1

# --- series B: a 32-gain rig. The cost of measuring. ----------------------
# The same eight switches over a rig whose own cost is one multiply per node, so that what the
# conditions differ by is dominated by the probes rather than by the audio. This is the series that
# answers the question the switch exists for: what does turning the measurement off actually buy.
run_condition 10 heavy off "$RIG_HEAVY" 34 none
run_condition 11 heavy on  "$RIG_HEAVY" 34 none
run_condition 12 heavy on  "$RIG_HEAVY" 34 20
run_condition 13 heavy on  "$RIG_HEAVY" 34 10
run_condition 14 heavy on  "$RIG_HEAVY" 34 5
run_condition 15 heavy on  "$RIG_HEAVY" 34 4
run_condition 16 heavy on  "$RIG_HEAVY" 34 3
run_condition 17 heavy on  "$RIG_HEAVY" 34 2
run_condition 18 heavy on  "$RIG_HEAVY" 34 1

log "done: $RESULTS"

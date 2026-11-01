#!/usr/bin/env bash
# The hour that failed on the stock kernel, run again on the RT kernel with isolation.
#
# Usage, from the Mac:   bench-results/2026-11-01-soak-pro-rt/soak.sh [seconds] [--arms a,b]
#
# This is deliberately the SAME load as bench-results/2026-10-31-soak-pro: namchain-soak against the
# UMC202HD, two A2-Full instances, 64-frame period, `namchaind` stopped. The only things that have
# changed are the kernel and the tuning, which is what makes the two comparable — and the earlier
# run's failure was a burst of 2.0 ms *CPU time* per block at 22 min 51 s, so anything shorter than
# about half an hour cannot say whether it is gone.
#
# Three differences in how it is run, all consequences of the host now being tuned:
#   * under scripts/host-lock, so nothing else touches pro while it runs;
#   * through `pedal-rt`, because user.slice's cpuset is core 0 now and `--cpu 5` from an ssh
#     session would otherwise be refused (that is the point of the slice);
#   * with the isolation state, the throttle counters and turbostat recorded beside it, because "it
#     passed" and "it passed for the reason we think" are different claims.
#
# TWO ARMS, and they answer different questions (added 2026-11-01):
#
#   bare   no output-queue options. This is what the nine committed runs here and in
#          bench-results/2026-10-31-soak-pro used, so it is the RT baseline and its flags must not
#          change — re-flagging it would make every future run incomparable with those nine.
#   queue  --output-queue-periods 4 --output-queue-floor-periods 2, which is what every pedal host
#          actually configures (devices/{vip,piv,pro}/rootfs/etc/namchain/namchaind.json). Until
#          this arm existed the harness had never measured the stream the engine really runs.
#
# The difference is not cosmetic. `prime_playback` primes ONE period with no target and the target's
# worth with one, so `bare` starts with a single period of cushion and reports `bring-up xruns: 1`,
# while `queue` starts with four and reports none. The target also brings the cap's refusals and the
# floor's insertions with it (namchain plan §9.5 item 8: 8 playback underruns at a 4-period target
# against 92 for the bare 4-period ring), so neither arm subsumes the other.
#
# Both arms run by default, one after the other, each for [seconds] — so the default is TWO hours.
# `--arms bare` reproduces the old behaviour exactly.
set -euo pipefail

SECS=3600
ARMS=bare,queue
while [[ $# -gt 0 ]]; do
  case $1 in
    --arms) ARMS=$2; shift 2 ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *[!0-9]*) echo "soak.sh: unknown argument: $1" >&2; exit 2 ;;
    *) SECS=$1; shift ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HOST=pro
OUT="$HERE/run-$(date -u +%Y%m%dT%H%M%SZ)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST")

# The flags each arm adds to the baseline invocation. An empty value is the baseline itself.
arm_flags() {
  case $1 in
    bare)  printf '%s' "" ;;
    queue) printf '%s' "--output-queue-periods 4 --output-queue-floor-periods 2" ;;
    *)     echo "soak.sh: unknown arm '$1' (known: bare, queue)" >&2; return 1 ;;
  esac
}

IFS=',' read -r -a ARM_LIST <<< "$ARMS"
(( ${#ARM_LIST[@]} )) || { echo "soak.sh: --arms is empty" >&2; exit 2; }
for a in "${ARM_LIST[@]}"; do arm_flags "$a" >/dev/null || exit 2; done

[[ ${PEDAL_HOST_LOCK:-} == "$HOST" ]] || exec "$REPO/scripts/host-lock" --host "$HOST" -- "$0" "$@"

mkdir -p "$OUT"
printf '==> %s arm(s) [%s] x %s s on %s = %s min total, into %s\n' \
  "${#ARM_LIST[@]}" "$ARMS" "$SECS" "$HOST" "$(( ${#ARM_LIST[@]} * SECS / 60 ))" "${OUT#"$REPO"/}" >&2

# What the host looked like going in. A soak whose conditions nobody wrote down is a number without
# a claim attached.
"${SSH[@]}" 'bash -s' > "$OUT/before.txt" <<'REMOTE'
echo "== kernel";    uname -r; uname -v
echo "== cmdline";   cat /proc/cmdline
echo "== isolation"; echo "isolated=$(cat /sys/devices/system/cpu/isolated) nohz_full=$(cat /sys/devices/system/cpu/nohz_full)"
echo "== engine";    sed -n 's/^\(commit\|flags\)=/\1=/p' /opt/namchain/current/MANIFEST
echo "== clock";     for p in /sys/devices/system/cpu/cpufreq/policy*; do echo "${p##*/} $(cat $p/scaling_governor) max=$(cat $p/scaling_max_freq)"; done
echo "== idle";      for s in /sys/devices/system/cpu/cpu5/cpuidle/state*; do printf '%s(%sus,dis=%s) ' "$(cat $s/name)" "$(cat $s/latency)" "$(cat $s/disable)"; done; echo
echo "== audio irq"; grep xhci /proc/interrupts
echo "== irq thread"; ps -eLo tid,cls,rtprio,psr,comm= | grep 'irq/.*xhci' || echo "(none: not a threaded-IRQ kernel?)"
echo "== throttle";  for t in /sys/devices/system/cpu/cpu[0-9]*/thermal_throttle; do echo "${t%/thermal_throttle} core=$(cat $t/core_throttle_count) pkg=$(cat $t/package_throttle_count)"; done
echo "== workqueue"; cat /sys/devices/virtual/workqueue/cpumask
echo "== pedal-tune"; /usr/local/sbin/pedal-tune check 2>&1 || true
# What ELSE is on the machine. The host's lock keeps other *measurements* away, but it cannot stop a
# compilation, and pro is used for those (the owner, 2026-11-01). A soak that shared the machine with
# a build is not a measurement of a quiet host, and without this nobody could tell afterwards which
# kind of run they were reading.
echo "== load";      cat /proc/loadavg
echo "== busiest";   ps -eo pcpu,psr,comm --sort=-pcpu | head -8
REMOTE

# turbostat alongside it: the SMI count is the one candidate for the earlier stall that nothing else
# would show, and the clock and package power say whether a limit was hit.
#
# Checked before the hour starts, not after. `linux-tools-common` alone installs a wrapper that
# prints "turbostat not found for kernel 7.0.0-38" and exits 1, so the first run of this script
# produced a turbostat.txt containing only that warning — an hour spent without the one measurement
# it was there to take. The versioned package follows the kernel's ABI and rtpi's pro-rt.sh installs
# it with the kernel (devices/pro/device.env, RT_APT_TOOLS).
if ! "${SSH[@]}" "sudo -n turbostat --quiet --show SMI --num_iterations 1 --interval 1" >/dev/null 2>&1; then
  echo "turbostat does not work on $HOST's running kernel ($("${SSH[@]}" uname -r))." >&2
  echo "Install linux-tools-\$(uname -r) there first — without it this run cannot report the SMI" >&2
  echo "count, which is the whole reason for measuring alongside the soak." >&2
  exit 1
fi

"${SSH[@]}" "sudo -n systemctl stop namchaind.service"
# Started again once every arm has run, including on the way out of a failure.
trap '"${SSH[@]}" "sudo -n systemctl start namchaind.service" || true' EXIT

# EVERYTHING THE RUN PRODUCES IS WRITTEN ON THE HOST, and fetched afterwards. The obvious shape —
# let the soak's output come back over the ssh channel — lost a whole hour on 2026-11-01: pro's WiFi
# roamed to the other access point in the house at 02:26, took two minutes to get an address back,
# and `namchain-soak` prints its report only at the very end, into what was by then a dead socket.
# The machine was fine; the measurement was gone. An hour-long unattended run over WiFi has to
# assume the link will blink.
#
# setsid, so the run survives the connection dropping rather than taking SIGHUP with it.
run_arm() {
  local arm=$1 flags
  flags=$(arm_flags "$arm")
  echo "==> arm '$arm' (${flags:-no queue options}), ${SECS}s" >&2

  # The arm's extra flags reach namchain-soak as separate words: the remote shell is bash (`bash -s`),
  # which splits the command line, and each layer passes them on positionally rather than re-quoting.
  "${SSH[@]}" "bash -s -- $SECS $flags" <<'REMOTE'
set -u
secs=$1; shift
cd ~/pedal-bench
rm -f soak-out.txt turbostat.txt soak-done
setsid bash -c '
  secs=$1; shift
  # Time_Of_Day_Seconds, so an SMI burst can be put against the journal to the second. Without it,
  # attributing the 726 SMIs of attempt 1 to fwupd meant counting sample numbers and hoping the
  # interval had not drifted.
  sudo -n turbostat --quiet --show Core,Busy%,Bzy_MHz,SMI,PkgWatt,PkgTmp \
    --enable Time_Of_Day_Seconds --interval 10 \
    --num_iterations $((secs / 10 + 2)) > ~/pedal-bench/turbostat.txt 2>&1 &
  ts=$!
  # Through pedal-rt: the only slice whose cpuset reaches core 5. The extra flags for this arm are
  # in "$@", placed before the WAV, which is positional.
  sudo -n /usr/local/bin/pedal-rt /opt/namchain/current/bin/namchain-soak \
    --backend alsa_raw --device "hw:CARD=U192k,DEV=0" \
    --channels 2 --periods 6 --quantum 64 --seconds "$secs" \
    --model ORNG-V30-421-Center.nam --instances 2 \
    --cpu 5 --rt-priority 80 --max-p99-percent 80 "$@" guitar-di.wav \
    > ~/pedal-bench/soak-out.txt 2>&1
  echo "soak-exit=$?" >> ~/pedal-bench/soak-out.txt
  kill "$ts" 2>/dev/null
  echo done > ~/pedal-bench/soak-done
' _ "$secs" "$@" < /dev/null > /dev/null 2>&1 &
echo "started; it writes ~/pedal-bench/soak-out.txt and leaves soak-done when finished"
REMOTE

  # Wait for it from here, reconnecting as often as it takes. A dropped connection is now a retry
  # rather than a lost run, and the host is asked whether it is finished rather than whether it is
  # reachable — the two were conflated once, and an unreachable host looked exactly like a finished
  # soak (2026-11-01).
  echo "==> waiting for '$arm' to finish on $HOST (it survives this connection dropping)" >&2
  local deadline=$(( $(date +%s) + SECS + 600 ))
  until "${SSH[@]}" "test -e ~/pedal-bench/soak-done" 2>/dev/null; do
    (( $(date +%s) < deadline )) || { echo "==> gave up waiting on '$arm'; it may still be going" >&2; break; }
    sleep 30
  done

  # Per arm, because the flags are what the run is about and the throttle counters are per run.
  "${SSH[@]}" "cat ~/pedal-bench/soak-out.txt" > "$OUT/$arm-soak.txt" 2>/dev/null || true
  "${SSH[@]}" "cat ~/pedal-bench/turbostat.txt" > "$OUT/$arm-turbostat.txt" || true
  "${SSH[@]}" 'bash -s' > "$OUT/$arm-after.txt" <<'REMOTE'
echo "== throttle";  for t in /sys/devices/system/cpu/cpu[0-9]*/thermal_throttle; do echo "${t%/thermal_throttle} core=$(cat $t/core_throttle_count) pkg=$(cat $t/package_throttle_count)"; done
echo "== load";      cat /proc/loadavg
echo "== busiest";   ps -eo pcpu,psr,comm --sort=-pcpu | head -8
echo "== kernel log"; sudo -n journalctl -k -b --no-pager | grep -iE 'hog|i915|xhci|snd|throttl|watchdog|nvme|iwl|rcu|sched' | tail -40 || true
REMOTE

  printf '==> arm %s done. flags: %s\n' "$arm" "${flags:-(none)}" >&2
  tail -25 "$OUT/$arm-soak.txt" >&2
  grep -q 'soak-exit=0' "$OUT/$arm-soak.txt" || echo "==> arm '$arm' did NOT exit 0" >&2
}

for arm in "${ARM_LIST[@]}"; do run_arm "$arm"; done

echo "==> all arms done, in ${OUT#"$REPO"/}" >&2
for arm in "${ARM_LIST[@]}"; do
  printf '    %-6s %s\n' "$arm" "$(grep -E '^(result|bring-up xruns|deadline overruns|driver xruns):' "$OUT/$arm-soak.txt" 2>/dev/null | tr -s ' ' | paste -sd';' - || echo '(no output)')" >&2
done

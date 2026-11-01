#!/usr/bin/env bash
# The hour that failed on the stock kernel, run again on the RT kernel with isolation.
#
# Usage, from the Mac:   bench-results/2026-11-01-soak-pro-rt/soak.sh [seconds]
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
set -euo pipefail

SECS=${1:-3600}
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
HOST=pro
OUT="$HERE/run-$(date -u +%Y%m%dT%H%M%SZ)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST")

[[ ${PEDAL_HOST_LOCK:-} == "$HOST" ]] || exec "$REPO/scripts/host-lock" --host "$HOST" -- "$0" "$@"

mkdir -p "$OUT"
echo "==> $SECS s soak on $HOST, into ${OUT#"$REPO"/}" >&2

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

# EVERYTHING THE RUN PRODUCES IS WRITTEN ON THE HOST, and fetched afterwards. The obvious shape —
# let the soak's output come back over the ssh channel — lost a whole hour on 2026-11-01: pro's WiFi
# roamed to the other access point in the house at 02:26, took two minutes to get an address back,
# and `namchain-soak` prints its report only at the very end, into what was by then a dead socket.
# The machine was fine; the measurement was gone. An hour-long unattended run over WiFi has to
# assume the link will blink.
#
# setsid, so the run survives the connection dropping rather than taking SIGHUP with it.
"${SSH[@]}" "bash -s -- $SECS" <<'REMOTE'
set -u
secs=$1
cd ~/pedal-bench
rm -f soak-out.txt turbostat.txt soak-done
setsid bash -c '
  secs=$1
  # Time_Of_Day_Seconds, so an SMI burst can be put against the journal to the second. Without it,
  # attributing the 726 SMIs of attempt 1 to fwupd meant counting sample numbers and hoping the
  # interval had not drifted.
  sudo -n turbostat --quiet --show Core,Busy%,Bzy_MHz,SMI,PkgWatt,PkgTmp \
    --enable Time_Of_Day_Seconds --interval 10 \
    --num_iterations $((secs / 10 + 2)) > ~/pedal-bench/turbostat.txt 2>&1 &
  ts=$!
  # Through pedal-rt: the only slice whose cpuset reaches core 5.
  sudo -n /usr/local/bin/pedal-rt /opt/namchain/current/bin/namchain-soak \
    --backend alsa_raw --device "hw:CARD=U192k,DEV=0" \
    --channels 2 --periods 6 --quantum 64 --seconds "$secs" \
    --model ORNG-V30-421-Center.nam --instances 2 \
    --cpu 5 --rt-priority 80 --max-p99-percent 80 guitar-di.wav \
    > ~/pedal-bench/soak-out.txt 2>&1
  echo "soak-exit=$?" >> ~/pedal-bench/soak-out.txt
  kill "$ts" 2>/dev/null
  echo done > ~/pedal-bench/soak-done
' _ "$secs" < /dev/null > /dev/null 2>&1 &
echo "started; it writes ~/pedal-bench/soak-out.txt and leaves soak-done when finished"
REMOTE

# Wait for it from here, reconnecting as often as it takes. A dropped connection is now a retry
# rather than a lost run, and the host is asked whether it is finished rather than whether it is
# reachable — the two were conflated once, and an unreachable host looked exactly like a finished
# soak (2026-11-01).
echo "==> waiting for the run to finish on $HOST (it survives this connection dropping)" >&2
deadline=$(( $(date +%s) + SECS + 600 ))
until "${SSH[@]}" "test -e ~/pedal-bench/soak-done" 2>/dev/null; do
  (( $(date +%s) < deadline )) || { echo "==> gave up waiting; the run may still be going" >&2; break; }
  sleep 30
done

"${SSH[@]}" "cat ~/pedal-bench/soak-out.txt" > "$OUT/soak.txt" 2>/dev/null || true
"${SSH[@]}" "cat ~/pedal-bench/turbostat.txt" > "$OUT/turbostat.txt" || true
"${SSH[@]}" 'bash -s' > "$OUT/after.txt" <<'REMOTE'
echo "== throttle";  for t in /sys/devices/system/cpu/cpu[0-9]*/thermal_throttle; do echo "${t%/thermal_throttle} core=$(cat $t/core_throttle_count) pkg=$(cat $t/package_throttle_count)"; done
echo "== kernel log"; sudo -n journalctl -k -b --no-pager | grep -iE 'hog|i915|xhci|snd|throttl|watchdog|nvme|iwl|rcu|sched' | tail -40 || true
REMOTE
"${SSH[@]}" "sudo -n systemctl start namchaind.service"

echo "==> done. soak-exit: $(grep -c 'soak-exit=0' "$OUT/soak.txt" || true)" >&2
tail -25 "$OUT/soak.txt" >&2

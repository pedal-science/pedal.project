#!/usr/bin/env bash
# collect.sh — read-only capture of one live vip boot, to replace this report's estimates.
#
#   pedal.project/scripts/host-lock -- ./collect.sh
#   ./collect.sh --dry-run            # print the commands, connect to nothing
#   ./collect.sh --host vip --out runs/2026-11-15T120000Z
#
# It never reboots, restarts or writes anything on the host: every command below is a read.
# The output is a directory beside this script (runs/<UTC stamp>/ by default) holding one file
# per command, an INDEX.txt, a summary.txt and unit-stamps.tsv.
#
# What one boot can and cannot settle:
#   * kernel, initrd, userspace, unit stamps and the rigpa qInfo startup marks: yes, all here.
#   * the bootloader's own stages (first byte, SD wait, initrd read, vmlinuz read): no. Those
#     lines are on the debug UART only. Attach the Debug Probe and run, from the repository root,
#     tools/measure-boot.py --seconds 600 --out <this directory>, then pull the power and boot.
#   * "audible at the jack": no. That needs the tone/interface chain of
#     bench-results/2026-10-02-boot-time-vip/jack and tools/measure-audio.py; this script does
#     not touch the audio path.
#
# Run it from the repository root under scripts/host-lock (rule 8: one measurement at a time).
# The lock is the caller's; this script refuses to run against a host it does not see locked,
# unless --force is given, so two captures cannot quietly overlap.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

HOST="${DEV_HOST:-vip}"
OUT=""
DRY=0
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "collect.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
[[ -n "$OUT" ]] || OUT="$HERE/runs/$STAMP"

# Units whose start stamps answer "what waits for what". Missing units are harmless: systemctl
# reports the failure per unit and the capture carries on.
UNITS=(
  namchaind.service pedald.service rigpa.service pedal-codec.service pedal-uart.service
  pedal-tune.service pedal-guard.service pedal-guard-maint.service pedal-wifi.service
  systemd-networkd.service wpa_supplicant@wlan0.service ssh.service
  plymouth-start.service plymouth-quit.service plymouth-quit-wait.service getty@tty1.service
  multi-user.target sysinit.target basic.target
)

note() { printf '%s\n' "$*"; }
die() { printf 'collect.sh: %s\n' "$*" >&2; exit 2; }

# name | remote command. Everything here is a read on the host. @UNITS@ is expanded locally;
# every other $ is expanded by the host's shell, on the host.
COMMANDS=$(cat <<'EOF'
meta-boot-identity|uname -a; echo; cat /proc/uptime; echo; date -u +%FT%TZ; echo; cat /proc/cmdline
meta-pedal-image|sudo -n cat /etc/pedal-image 2>/dev/null || cat /etc/pedal-image 2>/dev/null || true
meta-vip-boot|sudo -n vip-boot status 2>&1 || vip-boot status 2>&1 || true
kernel-dmesg|sudo -n dmesg --time-format=monotonic 2>&1 || dmesg --time-format=monotonic 2>&1 || true
journal-kernel|journalctl -b -k -o short-monotonic --no-pager
journal-full|journalctl -b -o short-monotonic --no-pager
journal-pedal-units|journalctl -b -o short-monotonic --no-pager -u namchaind -u pedald -u rigpa -u pedal-codec -u pedal-uart -u pedal-tune -u pedal-guard
journal-plymouth|journalctl -b -o short-monotonic --no-pager -u plymouth-start -u plymouth-quit -u plymouth-quit-wait 2>&1 || true
journal-rigpa|journalctl -b -o short-monotonic --no-pager -u rigpa
journal-rigpa-startup|journalctl -b -o short-monotonic --no-pager -u rigpa -g 'startup' 2>&1 || true
analyze-time|systemd-analyze
analyze-blame|systemd-analyze blame --no-pager
analyze-critical-chain|systemd-analyze critical-chain --no-pager
analyze-plot|systemd-analyze plot
manager-timestamps|systemctl show -p FirmwareTimestampMonotonic -p LoaderTimestampMonotonic -p KernelTimestampMonotonic -p InitRDTimestampMonotonic -p UserspaceTimestampMonotonic -p FinishTimestampMonotonic -p SecurityStartTimestampMonotonic -p SecurityFinishTimestampMonotonic -p GeneratorsStartTimestampMonotonic -p GeneratorsFinishTimestampMonotonic -p UnitsLoadStartTimestampMonotonic -p UnitsLoadFinishTimestampMonotonic systemd
units-running|systemctl list-units --type=service --state=running --no-pager --no-legend
units-failed|systemctl --failed --no-pager --no-legend
unit-stamps|systemctl show -p Id -p ActiveState -p SubState -p ActiveEnterTimestampMonotonic -p InactiveEnterTimestampMonotonic -p ExecMainStartTimestampMonotonic -p ExecMainExitTimestampMonotonic @UNITS@
unit-enabled|systemctl is-enabled getty@tty1.service plymouth-quit.service plymouth-quit-wait.service plymouth-start.service 2>&1 || true
masked-units|cat /etc/pedal/masked-units 2>/dev/null || true
drm-connectors|for f in /sys/class/drm/card*-*/status; do printf '%s: %s\n' "$f" "$(cat "$f")"; done; echo; ls -l /sys/class/drm/; echo; ls -l /dev/dri/by-path/ 2>/dev/null || true
drm-modes|for f in /sys/class/drm/card*-*/modes; do printf '%s: %s\n' "$f" "$(head -c 120 "$f")"; done
rigpa-config|cat /etc/rigpa/rigpa.json 2>/dev/null; echo; cat /etc/rigpa/kms.json 2>/dev/null
audio-cards|cat /proc/asound/cards; echo; cat /proc/asound/pcm
boot-files|sudo -n ls -l /boot/firmware/a/ /boot/firmware/b/ 2>/dev/null || ls -l /boot/firmware/a/ /boot/firmware/b/ 2>/dev/null || true
boot-profile|sudo -n cat /boot/firmware/profile.txt /boot/firmware/config.txt 2>/dev/null || true
network|networkctl status --no-pager 2>&1 || true; echo; ip -br addr 2>&1 || true
EOF
)
COMMANDS="${COMMANDS//@UNITS@/${UNITS[*]}}"

if (( DRY )); then
  IFS=$'\n'
  for line in $COMMANDS; do
    printf '%s\n' "${line#*|}"
  done
  unset IFS
  note ""
  note "dry run: nothing connected to, nothing written."
  exit 0
fi

if [[ "${PEDAL_HOST_LOCK:-}" != "$HOST" ]]; then
  if (( FORCE == 0 )); then
    die "not under scripts/host-lock for $HOST (rule 8). Run:
  $REPO/scripts/host-lock --host $HOST -- $HERE/collect.sh
or pass --force if the host is already known quiet."
  fi
  note "warning: not visibly under host-lock; continuing because --force"
fi
"${SSH[@]}" "$HOST" true >/dev/null 2>&1 \
  || die "cannot ssh to $HOST. Check ~/.ssh/config and that vip is up; nothing was written."

if [[ -e "$OUT" ]] && [[ -n "$(ls -A "$OUT" 2>/dev/null)" ]]; then
  die "output directory is not empty: $OUT"
fi
mkdir -p "$OUT/raw"

index=0
IFS=$'\n'
for line in $COMMANDS; do
  name="${line%%|*}"
  cmd="${line#*|}"
  index=$((index + 1))
  file=$(printf '%s/raw/%02d-%s.txt' "$OUT" "$index" "$name")
  status=0
  "${SSH[@]}" "$HOST" -- "$cmd" >"$file" 2>&1 || status=$?
  printf '%02d\t%s\t%s\t%s\n' "$index" "$name" "$status" "$cmd" >>"$OUT/INDEX.txt"
done
unset IFS

# ---- derive the small facts a reader wants first ---------------------------
{
  echo "# boot capture: $HOST, $STAMP"
  echo
  echo "## systemd-analyze"
  cat "$OUT/raw/"*"-analyze-time.txt" 2>/dev/null || true
  echo
  echo "## systemd manager timestamps (microseconds from kernel start; divide by 1e6)"
  cat "$OUT/raw/"*"-manager-timestamps.txt" 2>/dev/null || true
  echo
  echo "## kernel command line"
  tail -1 "$OUT/raw/"*"-meta-boot-identity.txt" 2>/dev/null || true
  echo
  echo "## rigpa startup qInfo marks (scene built / first frame / engine / document / ready / dismissed)"
  cat "$OUT/raw/"*"-journal-rigpa-startup.txt" 2>/dev/null || true
  echo
  echo "## plymouth"
  cat "$OUT/raw/"*"-journal-plymouth.txt" 2>/dev/null || true
  cat "$OUT/raw/"*"-unit-enabled.txt" 2>/dev/null || true
  echo
  echo "## DRM connectors (what rigpa's ExecCondition sees)"
  cat "$OUT/raw/"*"-drm-connectors.txt" 2>/dev/null || true
  echo
  echo "## initrd / vmlinuz sizes in the booted slots"
  cat "$OUT/raw/"*"-boot-files.txt" 2>/dev/null || true
} >"$OUT/summary.txt"

# unit stamps: systemctl's monotonic values are microseconds since kernel start. Convert to
# seconds and keep one row per unit. This is the table that replaces the ordering estimates.
awk '
  function flush() {
    if (id != "") printf "%s\t%s\t%s\t%.3f\t%.3f\t%.3f\t%.3f\n", id, state, subst, ae, ie, ms, mx
    id=""; state=""; subst=""; ae=0; ie=0; ms=0; mx=0
  }
  /^Id=/ { flush(); id=$0; sub(/^Id=/, "", id) }
  /^ActiveState=/ { state=$0; sub(/^ActiveState=/, "", state) }
  /^SubState=/ { subst=$0; sub(/^SubState=/, "", subst) }
  /^ActiveEnterTimestampMonotonic=/ { a=$0; sub(/^ActiveEnterTimestampMonotonic=/, "", a); ae=a/1e6 }
  /^InactiveEnterTimestampMonotonic=/ { i=$0; sub(/^InactiveEnterTimestampMonotonic=/, "", i); ie=i/1e6 }
  /^ExecMainStartTimestampMonotonic=/ { m=$0; sub(/^ExecMainStartTimestampMonotonic=/, "", m); ms=m/1e6 }
  /^ExecMainExitTimestampMonotonic=/ { x=$0; sub(/^ExecMainExitTimestampMonotonic=/, "", x); mx=x/1e6 }
  END { flush() }
' "$OUT/raw/"*"-unit-stamps.txt" 2>/dev/null \
  | { printf 'unit\tstate\tsubstate\tactive_enter_s\tinactive_enter_s\texec_start_s\texec_exit_s\n'; cat; } \
  >"$OUT/unit-stamps.tsv" || true

# ---- how to read it --------------------------------------------------------
cat >"$OUT/README.txt" <<EOF
# What this capture is

Read-only capture of $HOST's current boot ($STAMP), for
bench-results/2026-11-15-boot-timeline-vip/. Nothing was rebooted, restarted or written on the
host. raw/ has one file per command; INDEX.txt lists the commands and their exit status;
summary.txt is the short version; unit-stamps.tsv is systemctl's start stamps in seconds from
kernel start.

# Replacing this report's estimates

* kernel / initrd / userspace split ......... raw/*-analyze-time.txt, raw/*-manager-timestamps.txt
* which unit held the post-audio tail ....... raw/*-analyze-blame.txt, raw/*-analyze-critical-chain.txt
* per-unit start and settle times ............ unit-stamps.tsv
* rigpa first frame / ready .................. summary.txt "rigpa startup qInfo marks"
* splash start and dismissal ................. summary.txt "plymouth"
* the DSI panel was up at boot .............. summary.txt "DRM connectors"
* initrd size in the booted slot ............ summary.txt "initrd / vmlinuz sizes"
* the firmware half of the boot ............. NOT here: attach the Debug Probe and run
  tools/measure-boot.py --seconds 600 --out <this directory>, then pull power and boot. Its log
  has the bootloader's first byte, SD wait, initrd read and vmlinuz read.
* audible at the jack ....................... NOT here: the tone/interface chain in
  bench-results/2026-10-02-boot-time-vip/jack plus tools/measure-audio.py.

# The exact commands, if you want to run one by hand

  sudo systemctl show -p ActiveEnterTimestampMonotonic -p ExecMainStartTimestampMonotonic namchaind.service
  systemd-analyze critical-chain --no-pager
  journalctl -b -u rigpa -o short-monotonic --no-pager -g 'startup'
  cat /sys/class/drm/card*-DSI-*/status
EOF

printf '\nwrote %s\n' "$OUT"
printf '  %s\n' "$OUT/summary.txt" "$OUT/unit-stamps.tsv" "$OUT/INDEX.txt"

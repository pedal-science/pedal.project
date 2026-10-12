#!/usr/bin/env bash
# roundtrip.sh — the pedal's round trip, measured at the SSL.
#
# A 1 kHz tone leaves interface output 1, goes into the pedal's IN jack, through board 1 and
# the codec's ADC, through the engine's loaded document, out of the codec's left DAC channel
# and the pedal's OUT L jack, and back into interface input 1. All eight of the interface's
# channels are recorded, because the SSL 2+ Mk II puts its own playback on inputs 3-8: a
# channel that carries the tone with the pedal unplugged is the interface talking to itself.
#
#   TONE=<file> OUT=<file> SECS=<n> CH=<n> LIVE=<0|1> ./roundtrip.sh
#
# LIVE=1 (the default) unmutes the engine for the recording and mutes it again afterwards,
# because a rig with a gain node makes the pedal's output continuous noise at rest. LIVE=0
# leaves it muted throughout: the tone then reaches the pedal's input and the codec's ADC but
# nothing drives the output jack — the control that says which capture channel is the analog
# input and which is the interface's own monitor mix. CH is the capture width (2 or 8).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/bench-results/2026-10-11-first-sound"
DEV="SSL 2+ Mk II"
TONE=${TONE:-$D/tone-1k-m60.wav}
OUT=${OUT:-$D/roundtrip-line.wav}
SECS=${SECS:-10}
CH=${CH:-8}
LIVE=${LIVE:-1}
TONE_AT=${TONE_AT:-3}
TONE_FOR=${TONE_FOR:-4}

ctl() { "$ROOT/scripts/host-lock" -- ssh vip "sudo -n /opt/namchain/current/bin/namchainctl $1"; }

(( LIVE )) && ctl "mute off" >/dev/null
sox -q -t coreaudio "$DEV" -r 48000 -c "$CH" -b 24 "$OUT" trim 0 "$SECS" &
REC=$!
sleep "$TONE_AT"
sox -q "$TONE" -t coreaudio "$DEV" &
TONE_PID=$!
sleep "$TONE_FOR"
kill "$TONE_PID" 2>/dev/null || true
wait "$REC" || true
(( LIVE )) && ctl "mute on" >/dev/null
echo "wrote $OUT"

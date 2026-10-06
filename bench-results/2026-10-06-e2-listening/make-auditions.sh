#!/usr/bin/env bash
# The listening half of E2 item 1: each model's two submodels and an alternating handover between
# them, 16 s from 20 s in, a switch every 2 s.
set -euo pipefail
E2=/Users/rik/code.local/pedal/pedal.project/build/e2
"$E2/in-container.sh" slim --input /data/guitar-di.wav --switch-every 2 \
  --audition /data/audition --audition-start 20 --audition-seconds 16 \
  "/models/000 Unsorted/Ampeg SVT VR _ 8x10 _ Beta52A + DI.nam" \
  "/models/Ampeg SVT Classic with 6x10/Ampeg SVT - MD 421.nam" \
  "/models/NAM Ampeg VT-40/Ampeg VT-40 - Vol 4, Bass 6, Mid 5, Treble 8, M160.nam" \
  "/models/Ampeg GVT52 - Channel 2/AMPEG_CH 2 NEUTRAL G5.nam" \
  "/models/Boss SD-1 Super Overdrive/APP-SD1-Boost-I.nam"

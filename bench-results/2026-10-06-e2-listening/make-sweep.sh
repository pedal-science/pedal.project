#!/usr/bin/env bash
# E2 item 1 over every model in the shipping library, through the bench's own slim mode, so the
# table and the glitch judgement come from one tool.
set -euo pipefail
E2=/Users/rik/code.local/pedal/pedal.project/build/e2
models=()
while IFS= read -r rel; do models+=("/models/$rel"); done < "$E2/vip-models.txt"
"$E2/in-container.sh" slim --input /data/guitar-di.wav --switch-every 5 "${models[@]}"

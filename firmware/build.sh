#!/bin/sh
# Build the Pico firmware for the Pico 2 W. Leaves build/pedal-firmware.uf2.
#
# Pins, for the record (plan Phase 3, step 1):
#   SDK 2.3.1, Arm GNU Toolchain 15.3.rel1, board pico2_w.
set -e
cd "$(dirname "$0")"

PICO_TOOLCHAIN_PATH="${PICO_TOOLCHAIN_PATH:-$HOME/pico/arm-gnu-toolchain-15.3.rel1}"
export PICO_TOOLCHAIN_PATH
PATH="$PICO_TOOLCHAIN_PATH/bin:$PATH"
export PATH

PICO_SDK_PATH="${PICO_SDK_PATH:-$HOME/pico/pico-sdk}"
export PICO_SDK_PATH

cmake -S . -B build -G Ninja -DPICO_BOARD=pico2_w
cmake --build build
ls -l build/pedal-firmware.uf2

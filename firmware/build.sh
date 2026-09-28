#!/bin/sh
# Build the Pico firmware for the Pico 2 W. Leaves build/pedal-firmware.uf2.
#
# Pins, for the record (plan Phase 3, step 1):
#   SDK 2.3.1, Arm GNU Toolchain 15.3.rel1, board pico2_w.
#
# FW_ECHO=1 builds step 1's byte echo instead of the protocol firmware, for
# firmware/tools/echo-test.py.
set -e
cd "$(dirname "$0")"

PICO_TOOLCHAIN_PATH="${PICO_TOOLCHAIN_PATH:-$HOME/pico/arm-gnu-toolchain-15.3.rel1}"
export PICO_TOOLCHAIN_PATH
PATH="$PICO_TOOLCHAIN_PATH/bin:$PATH"
export PATH

PICO_SDK_PATH="${PICO_SDK_PATH:-$HOME/pico/pico-sdk}"
export PICO_SDK_PATH

if [ "${FW_ECHO:-0}" = "1" ]; then
    ECHO_OPT=ON
else
    ECHO_OPT=OFF
fi

cmake -S . -B build -G Ninja -DPICO_BOARD=pico2_w -DFW_ECHO="$ECHO_OPT"
cmake --build build
ls -l build/pedal-firmware.uf2

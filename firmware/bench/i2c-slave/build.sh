#!/bin/sh
# Build the bench I2C slave for the Pico 2 W. Leaves build/i2c-slave.uf2.
#
# Same environment as the pedal firmware (firmware/build.sh): SDK 2.3.1, Arm GNU Toolchain
# 15.3.rel1, board pico2_w. This is a bench instrument, not the pedal: flashing it into the pedal's
# Pico would take the pedal's controls away, which is why it is its own project and its own UF2.
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
ls -l build/i2c-slave.uf2

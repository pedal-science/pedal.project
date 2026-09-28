#!/bin/sh
# Flash build/pedal-firmware.uf2.
#
# A running program with USB stdio can be reflashed without touching BOOTSEL
# (picotool reboots it itself). For a cold board (BOOTSEL + plug in) the
# mounted RP2350 volume is used instead.
set -e
cd "$(dirname "$0")"
if [ -d /Volumes/RP2350 ]; then
    cp build/pedal-firmware.uf2 /Volumes/RP2350/
    echo "flashed via /Volumes/RP2350"
else
    picotool load -f -x build/pedal-firmware.uf2
    echo "flashed via picotool"
fi

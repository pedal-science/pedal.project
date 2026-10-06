#!/bin/sh
# Flash build/i2c-slave.uf2 into the *bench* Pico.
#
# The pedal's own Pico must not be plugged into this Mac when this runs: picotool flashes whatever
# is on the other end of the USB cable, and this firmware would take the pedal's controls away.
# (Its UART firmware is firmware/build.sh + firmware/flash.sh.)
set -e
cd "$(dirname "$0")"
if [ -d /Volumes/RP2350 ]; then
    cp build/i2c-slave.uf2 /Volumes/RP2350/
    echo "flashed via /Volumes/RP2350"
else
    picotool load -f -x build/i2c-slave.uf2
    echo "flashed via picotool"
fi

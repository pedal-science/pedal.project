#!/usr/bin/env bash
set -uo pipefail
ssh vip 'sudo systemctl stop namchaind' || exit 1
trap 'ssh vip "sudo systemctl start namchaind"; echo "namchaind restarted: $(ssh vip systemctl is-active namchaind)"' EXIT
sleep 1
ssh vip 'arecord -q -D hw:CARD=wm8960,DEV=0 -f S16_LE -r 48000 -c 2 -t raw -d 7 /tmp/vip-in.raw & aplay -q -D hw:CARD=wm8960,DEV=0 -f S16_LE -r 48000 -c 2 -t raw /tmp/vip440.raw & wait' &
ssh piv 'cd /tmp; arecord -q -D hw:CARD=USB,DEV=0 -f S24_3LE -r 48000 -c 2 -t raw -d 7 piv-in.raw & sleep 0.3; aplay -q -D hw:CARD=USB,DEV=0 -f S24_3LE -r 48000 -c 4 -t raw tone8.raw & wait' &
wait

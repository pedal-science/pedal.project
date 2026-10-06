#!/usr/bin/env bash
# Controller or codec: the measurement that decides it. Read-only.
#
# Every read of the WM8960 aborts in the RP1 I2C controller — lost arbitration, SDA stuck at low —
# while writes have been clean for hours, and the codec is the only device on that bus, so nothing
# could separate "this controller cannot read" from "this codec cannot be read". The bench I2C slave
# (firmware/bench/i2c-slave/, at 0x2a on the same two wires) is the second device: its register map
# is known because we wrote it, and its counter register is live, so a read path that returns stale
# bytes fails a test that the identity words alone would pass.
#
# Run it on the Mac, under the Core host's lock, with the slave wired and powered from the header:
#
#   scripts/host-lock --host vip --wait 1800 -- bench-results/2026-10-06-i2c-read-fault/probe-reads.sh
#
# Nothing here writes to any device: i2cget only. The codec's reads are the ones that abort, and the
# recovery that frees a stuck bus is armed on vip (rtpi devices/vip/dt/rp1-i2c1-recovery.dts).
set -uo pipefail

HOST=vip
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST")
say() { printf '%s\n' "$*"; }
on() { "${SSH[@]}" "sudo -n $*"; }
read_reg() { "${SSH[@]}" "sudo -n i2cget -f -y $1 $2 $3 w" 2>&1; }

say "controller or codec — $(date -u +%FT%TZ)"
say
say "--- the bench slave, $HOST bus 1 address 0x2a (the device with a known map) ---"
r0=$(read_reg 1 0x2a 0x00); say "  0x00 identity      = $r0    (want 0xdead)"
r1=$(read_reg 1 0x2a 0x01); say "  0x01 complement    = $r1    (want 0x2152)"
c1=$(read_reg 1 0x2a 0x02); say "  0x02 counter       = $c1"
sleep 1.2
c2=$(read_reg 1 0x2a 0x02); say "  0x02 counter again = $c2    (must differ from the line above)"

say
say "--- the codec, bus 1 address 0x1a (the device under suspicion) ---"
k0=$(read_reg 1 0x1a 0x00); say "  0x00 = $k0"
k7=$(read_reg 1 0x1a 0x07); say "  0x07 = $k7"

say
say "--- the controller's own account since those reads ---"
aborts=$(on dmesg | grep -c i2c_dw_handle_tx_abort 2>/dev/null || echo "?")
say "  i2c_dw_handle_tx_abort lines in dmesg: $aborts"
on dmesg | grep i2c_dw_handle_tx_abort | tail -4 | sed 's/^/  /'

say
say "--- the bus lines, and whether recovery is armed ---"
on pinctrl 2,3 | sed 's/^/  /'
on dmesg | grep "GPIO recovery mode" | tail -1 | sed 's/^/  /'
say

say "--- what this says ---"
# "No answer" first, and separately from "answered wrongly": on the first run every read failed and
# an earlier version of this summary claimed the slave had answered. A measurement that misreports
# its own failure is worse than no measurement.
nothing=0
for v in "$r0" "$r1" "$c1" "$c2" "$k0" "$k7"; do
    case "$v" in Error*|error*|"") nothing=1 ;; esac
done
if [ "$nothing" = 1 ]; then
    say "  Nothing answered, or not everything did: slave $r0 / $r1 / $c1 -> $c2; codec $k0 / $k7."
    say "  This run says nothing about the read path. If dmesg shows aborts, the controller is"
    say "  still misbehaving and it is worth repeating; a clean NAK means a device is off the bus"
    say "  (power, a lead, or the firmware), and that has to be fixed before this test can decide"
    say "  anything. Check the wiring and run it again."
elif [ "$r0" = "0xdead" ] && [ "$r1" = "0x2152" ] && [ "$c1" != "$c2" ]; then
    say "  The controller read a known device, three registers, and the live counter moved."
    say "  So the controller's read path, the bus and the pins are fine, and the codec is the"
    say "  fault: its read protocol, its board, or the part itself."
else
    say "  The slave answered, but not with what it should: $r0 / $r1 / $c1 -> $c2."
    say "  That is suspicious of the transfer itself rather than of either device — treat these"
    say "  numbers as evidence, not as a verdict, and repeat the run."
fi
say
say "done — $(date -u +%FT%TZ)"

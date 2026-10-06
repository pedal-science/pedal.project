# Controller or codec: answered

2026-10-06. The question: every read of the WM8960 aborts in the RP1 controller — `lost arbitration`,
`SDA stuck at low` — while writes are clean, and the codec is the only device on that bus, so nothing
could separate "this controller cannot read" from "this codec cannot be read".

The answer, from [output.txt](output.txt), one run on one bus:

```
the bench slave, 0x2a   0x00 = 0xadde (= 0xdead)   0x01 = 0x5221 (= 0x2152)   0x02 = moving
the codec, 0x1a         0x00 = Error: Read failed  0x07 = Error: Read failed
dmesg                   i2c_dw_handle_tx_abort: lost arbitration / SDA stuck at low
```

**The controller reads a device whose answers we wrote, perfectly, while every read of the codec
fails on the same pins in the same second. The codec's read is the fault — its protocol, its board,
or the part — and not the controller's read path.**

## How it was decided

The instrument is `firmware/bench/i2c-slave/`: the spare Pico 2 W as an I2C slave at `0x2a` with a
register map we wrote — an identity word `0xDEAD`, its bitwise complement `0x2152`, a live seconds
counter, and a writable register — hanging on the same two wires as the codec. Its answers are known,
so the codec's can be compared with them.

The first attempt settled nothing ([output-first-run.txt](output-first-run.txt)): every read failed,
including the slave's, because neither device was on vip's pins at all. Reaching a bus that could
answer took four faults, each found by evidence rather than by rewiring at random:

1. **No link from the breadboard to vip's header pins 3 and 5.** With the codec's leads out, the bus
   had lost its 2.2 kΩ pull-ups (they are on the codec board), so the lines were held only by weak
   internal pull-ups — which is why nothing answered and why the instrument's counter never moved.
2. **The lead from header pin 5 did not conduct.** Driving vip's pins low one at a time and reading
   the slave's own report of its line levels showed SDA following and SCL not.
3. **The Pico's pads were cleared by swapping the two leads at the Pico end**: the fault followed the
   wire, not the pin. A replaced wire fixed it, and both links then followed.
4. **The instrument's own register addressing.** It treated the selection byte as a byte offset, so a
   read of `R1` returned `R0`; fixed in the firmware. Separately, `i2cget ... w` prints an SMBus word
   low byte first, which is why the slave's `0xdead` reads back as `0xadde`.

## What this does not say, and what would

It does not say *why* the codec's read aborts. The evidence cannot separate the codec's read protocol
on the wire (a repeated start followed by a 16-bit read) from its board's pull-ups and rise times,
from the part's own read timing. A scope on SDA and SCL during one read, or a second controller known
to read the same part, would separate them. The bench slave has ruled out the half that did not need a
scope.

## State of the pedal

The codec answers its own address (a scan shows `1a`) and takes writes, which is why the pedal could
be brought back without touching the bus: after the reboot its driver probe had failed and the card
was gone, so the probe was retried in place — `echo 1-001a > /sys/bus/i2c/drivers/wm8960/bind`, then
`systemctl start pedal-codec` — and the pedal reports 10 ok, 1 info. Its **reads still fail exactly as
before**.

The bus now self-clears: the GPIO recovery overlay is armed from boot (rtpi's
`devices/vip/dt/rp1-i2c1-recovery.dts`, installed into every boot tree and enabled by `vip-boot`), so
after the aborts both lines are left idle high and the codec stays bound.

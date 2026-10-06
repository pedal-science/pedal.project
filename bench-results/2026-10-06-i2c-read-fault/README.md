# Controller or codec: the first run, and why it is not the answer

2026-10-06, 16:54Z. The measurement that was supposed to settle controller-versus-codec ran under the
Core host's lock, unattended, exactly as `probe-reads.sh` in this directory writes it. The output is
[output.txt](output.txt). It settles nothing, for a reason worth recording: **nothing on the bus
answered at all.**

## What it found

```
0x2a identity      = Error: Read failed     (the bench slave: want 0xdead)
0x1a 0x00          = Error: Read failed     (the codec)
i2c_dw_handle_tx_abort lines in dmesg: 0
2: a3 pu | hi     3: a3 pu | hi
```

No aborts at all — so this is not the failure the earlier session measured. Then, in the same
window, the codec's *driver* was failing its own writes:

```
wm8960 1-001a: ASoC error (-121): at snd_soc_component_update_bits() ... register: [0x00000019]
```

`-121` is `EREMOTEIO`: the chip did not acknowledge. So the codec was not answering reads *or*
writes, and `i2cdetect -y 1` found nothing anywhere: `1a` shown as `UU` (the driver holds the
address, so i2cdetect never probes it) and **nothing at `2a`**.

## What that means

Two separate physical faults, and neither is the read-path question:

1. **The codec has gone deaf on I2C.** Its audio still works — the pedal reports 48 kHz streaming
   with live input and output levels, and the codec is the I2S *master*, so it is powered and
   clocking. Only its control interface is silent, which is what a missing or badly seated SDA/SCL
   lead looks like from the master's side (the Pi's own pull-ups keep both lines high, so nothing
   looks stuck). This is new: earlier the same day writes were clean, and every read aborted with
   `lost arbitration`; a NAK on everything is a different fault with a different cause.
2. **The bench slave does not answer at all.** Absent from the scan, so: power, the four leads, or
   the firmware not running. Its own console is the way to tell, which needs its USB lead (and
   therefore the 5 V lead out, since one supply at a time).

Both faults are in the same place — header pins 3 and 5, which the codec's SDA/SCL and the bench
slave's now share — and the wiring was done between the last clean write and this run.

## The warning this leaves

**Do not reboot vip until the codec answers again.** Its driver's probe issues a reset write, and a
codec that NAKs fails that probe: the sound card would not register and the pedal would come back
mute, where right now it plays on its last good configuration (register changes fail, the audio path
does not).

## To get back to the measurement

1. The codec: check its 3V3 (header pin 1), its SDA and SCL (pins 3 and 5) and its ground, at both
   ends. Its PWR LED should be lit — it must be, since the chip is clocking I2S. `sudo i2cdetect -y
   1` should then show `UU` at `1a` and (once the slave answers) `2a`.
2. The bench slave: unplug its 5 V lead and power it from the Mac's USB, and read its console. If
   the banner is there, the firmware runs and it is wiring or power; if there is nothing, it is not
   running. Its firmware now blinks the onboard LED once a second, so a reflash makes it visibly
   alive without a console at all.
3. Then run this directory's script again, under the lock. The decision it makes is unchanged: the
   slave's identity words and a moving counter mean the controller can read, so the codec is the
   fault; the same aborts as the codec's reads mean the controller's read path is; a clean NAK means
   the slave is not on the bus yet, and nothing should be read into the result until it is.

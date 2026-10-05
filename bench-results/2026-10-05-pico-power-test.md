# Phase 3.6: the Pico keeps its power on the header feed, and not on the USB-A port

**Date:** 2026-10-05
**Question:** the Pico takes its 5 V from the Core host. Of 3.6's two ways — **form 1**, one of vip's
USB-A ports into the Pico's micro-B, and **form 2**, vip's header pin 2 through a 1N5817 into VSYS —
which one holds while vip reboots, and which while it shuts down? The answer decides whether the
bypass relay's rule may lean on a Pico that is still up while the engine is not.

## Result

| | Form 1 (USB-A) | Form 2 (header pin 2 → 1N5817 → VSYS) |
|---|---|---|
| Control | passes (48,850 → 48,880 s; 48,890 → 48,920 s) | passes (60 → 90 s; 420 → 450 s) |
| `sudo reboot` | **fails**: 48,930 s → **20 s** — the Pico restarted | **passes**: 100 s → **135 s** across a 26 s outage |
| `sudo shutdown` | not run (form 1 was already out) | **passes**: 190 s → **295 s** across a 95 s outage |
| Verdict | out | **kept** |

Form 2 was tested with the **USB cable left in vip's USB-A** for the console: the reboot cuts that
rail either way (form 1 proves it), so a Pico that survives is surviving on the header. It survived
both legs, so the header feed works and **the diode is the right way round** — a reversed 1N5817
would have left the Pico on USB alone, and it would have restarted exactly as form 1 did.

The pedal came back each time: `namchaind` `running`/`ok` on `hw:CARD=wm8960,DEV=0`, ljoss's "New
Rig" resumed from `last.json`. Form 1's reboot cost **2 xruns** (the stream stopping and starting);
nothing else was disturbed.

## The instrument, and why nothing else can answer this

The Pico's firmware prints, on its USB CDC console every 5 s:

    fw: up 48790 s, session=1, frames ok=198694 bad=0

`up` counts from the Pico's own reset, so it measures **power**. The two obvious alternatives do not:

- **`dmesg` cannot.** The host re-enumerates the device on every boot whether or not the Pico lost
  power, because the USB host controller is reset either way. Form 2's boot shows the Pico appearing
  as `2e8a:0009` again — and it had never stopped running.
- **A `HELLO` from the Pico cannot.** The Pico returns to `HELLO` after a 1 s link timeout, so it
  sends one whenever its UART partner goes away, restart or not. Form 2 demonstrates it: `pedald`
  logged `Pico says hello: fw '0.1', protocol 1.0, caps 0x0000` on the boot after the shutdown leg,
  from a Pico whose counter proves it never reset. (In form 1's run the same line appeared, and there
  it *was* a restart.)

Reading it, on the Core host as root:

    sudo -n stty -F /dev/ttyACM0 raw -echo     # echo off first: an echoed byte is a real EVENT
    sudo -n timeout 8 cat /dev/ttyACM0         # to the firmware's bench stand-in, which reads e/d/b
    # fw: up 48790 s, session=1, frames ok=198694 bad=0

`scripts/pico-power-test` does this, issues the reboot or shutdown, waits for the host to answer on a
new boot id, reads again, and prints a verdict. `--leg read` is the control: two reads 20 s apart
must show the counter advancing, or the read itself resets the Pico and no other leg means anything.
The console is the Pico's *debug* CDC and is free; the *link* is the header UART (`ttyAMA0`), which
`pedald` owns.

Two facts learned on the way, both recorded because they cost time:

- **vip's journal is volatile** (`/run/log/journal`, tmpfs): `journalctl -b -1` after a reboot says
  "no persistent journal was found", so a previous boot's shutdown sequence is not recoverable.
  Yesterday's pedald lines were still readable only because vip had not rebooted since.
- The console must be opened with `stty raw -echo` **before** it is read: with echo on, the host
  echoes what it receives back down the port and the firmware's stand-in answers its own output in a
  loop ([2026-10-04-rewire-faults-and-the-pico-console.md](2026-10-04-rewire-faults-and-the-pico-console.md)).

## What this means

- **Form 2 is the arrangement.** The Pico stays up through both a Core host reboot and a shutdown, so
  `docs/pedal-service.md`'s relay rule (R4) keeps its "the Pico stays up" case: on link loss it can
  hold — or take — bypass on its own timer rather than relying on having restarted into a safe state.
- **The USB cable stays, but only as the console and the flashing path.** It is not the Pico's power.
- **The header now has two 5 V consumers**, the codec board's VIN (pin 2, `docs/codec-bringup-2a.md`
  stage 4) and the Pico's feed. Put the Pico's on **pin 4**, the other 5 V pin, and leave pin 2 to the
  codec alone: pin 1 (3.3 V), pin 2 (5 V), pin 3 (SDA) and pin 5 (SCL) are neighbours, and a second
  lead in pin 2 is a lead's width from the codec's I²C.

## Open at the end of this session: the codec stopped answering

The test is green, but the pedal is not playing: at the end of the session `pedal-codec` fails with
`card wm8960 did not appear`, `/proc/asound/cards` is empty, and the engine is `lost`/`error`.

What the fault is **not**: the I²C bus is not held. The driver's reset write to `0x1a` came back
`-121` (`EREMOTEIO`, a NACK) rather than the `-110` (`ETIMEDOUT`, the controller's 1.024 s timeout)
that a held line gives — the signature of the October 4th fault
([2026-10-04-rewire-faults-and-the-pico-console.md](2026-10-04-rewire-faults-and-the-pico-console.md)).
So the Pi drives the bus and gets an answer of "nobody here": the codec board is not answering at its
address.

The timeline points at the rewire: the engine was `running`/`ok` at 10:12, before the Pico's feed was
added, and the card has not appeared since the power cycle that followed it. Retrying
`systemctl restart pedal-codec` fails the same way. The board's supplies and its I²C are four
adjacent header pins (1, 2, 3 and 5), and its VIN shares pin 2 with the new feed, so the first things
to check are those leads and the board's seating in its socket strips. The chip's digital supply is
the one that matters for this symptom: the I²C interface is in the DBVDD domain, fed from **3V3 on
pin 1**, so a displaced pin 1 stops it acknowledging while pin 2 alone would not.

Every lead is in the checklist above; nothing has been changed at the bench from here.

Evidence, verbatim: [2026-10-05-pico-power-test.log](2026-10-05-pico-power-test.log).

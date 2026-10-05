# Phase 3.6: the Pico does not keep its power across a Core host reboot

**Date:** 2026-10-05
**Question:** the Pico takes its 5 V from the Core host. On vip's USB-A (form 1 of 3.6's two), does
it stay powered while vip reboots — or does it restart with it? The answer decides whether the
bypass relay's rule may lean on a Pico that is still up while the engine is not.

## Result

**It restarts with the reboot. Form 1 does not hold.**

| | |
|---|---|
| Form under test | **1**: one of vip's USB-A ports → the Pico's micro-B (what the bench is wired as) |
| Instrument | the Pico's own uptime, printed on its USB CDC console every 5 s: `fw: up 48790 s, session=1, frames ok=198694 bad=0` |
| Control (read the console twice, 20 s apart) | 48,850 s → 48,880 s, and again 48,890 s → 48,920 s: the counter advances, so **reading the console does not reset the Pico**, and the instrument is sound |
| Before the reboot | Pico up **48,930 s**; vip's boot id `3c33404e` |
| After | Pico up **20 s**; vip's boot id `2b745dc1`; vip's kernel came up 10:10:17 UTC |
| Verdict | the counter began again — the Pico **restarted** during the reboot |

The host side agrees: the Pico re-enumerated on vip's USB as `2e8a:0009` at 10:10:20 UTC, and
`pedald`, which starts 5.9 s into the boot, logged

    [    6.527975] vip pedald[844]: pedald: Pico says hello: fw '0.1', protocol 1.0, caps 0x0000

— a HELLO from a Pico that has just booted. (A HELLO alone would not prove a restart: the Pico also
returns to HELLO after a 1 s link timeout, so `docs/uart-protocol.md`'s session rule makes it
ambiguous. The uptime counter is what distinguishes the two.)

Nothing else was disturbed: the engine came back `running`/`ok` on `hw:CARD=wm8960,DEV=0`, resumed
ljoss's "New Rig" from `last.json`, worst block 18.9% of the deadline, **2 xruns** (the stream
stopping and starting again — the only cost a reboot left behind).

## The instrument, and why dmesg cannot answer this

The host **re-enumerates** the Pico on every boot whether or not the Pico lost power, because the
USB host controller is reset either way. So "did the device appear in dmesg?" is not evidence. The
Pico's `up N s` counter is: it counts from the Pico's own reset, so it measures *power*.

Reading it, on the Core host as root:

    sudo -n stty -F /dev/ttyACM0 raw -echo     # echo off first: an echoed byte is a real EVENT
    sudo -n timeout 8 cat /dev/ttyACM0         # to the firmware's bench stand-in, which reads e/d/b
    # fw: up 48790 s, session=1, frames ok=198694 bad=0

`scripts/pico-power-test` does this, issues the reboot or shutdown, waits for the host to answer on a
new boot id, reads again, and prints a verdict. `--leg read` is the control. The console is the Pico's
*debug* CDC and is free; the *link* is the header UART (`ttyAMA0`), which `pedald` owns.

Two facts learned on the way, both recorded because they cost time:

- **vip's journal is volatile** (`/run/log/journal`, tmpfs): `journalctl -b -1` after the reboot says
  "no persistent journal was found", so the previous boot's shutdown sequence is not recoverable.
  Yesterday's pedald lines were still readable only because vip had not rebooted since.
- `sudo -n stty` needs the port free, and the read must not write: with echo on, the host echoes what
  it receives back down the port and the firmware's stand-in answers its own output in a loop
  ([2026-10-04-rewire-faults-and-the-pico-console.md](2026-10-04-rewire-faults-and-the-pico-console.md)).

## What this means, and what is left

- **Form 1 is out** for the case the relay rule wants — a Pico that stays up while the Core host
  reboots. It is not a fault: a Pico that restarts with the host comes back with a clean session, and
  the relay is de-energised throughout anyway, which is bypass. What is lost is the option of holding
  bypass *on link loss* across a host reboot, and `docs/pedal-service.md`'s relay rule (R4) must be
  read with that.
- **Form 2 is next: vip's header pin 2 → a 1N5817 → the Pico's VSYS.** The header's 5 V is not the
  switched USB-A rail, so it is the one that might hold. The USB cable can stay in place for the
  console while it is tested — the reboot cuts the USB-A rail either way, so a Pico that survives is
  surviving on the header.
- **The shutdown leg is not run yet.** The plan asks for it; it needs the host powering back on by
  hand, so it waits for form 2 rather than being run twice.
- If form 2 also fails, the plan's fallback stands: the Pico restarting with the host is safe, and
  the relay drops to bypass.

Evidence, verbatim: [2026-10-05-pico-power-test.log](2026-10-05-pico-power-test.log).

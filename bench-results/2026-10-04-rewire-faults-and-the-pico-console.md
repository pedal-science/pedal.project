# After the rewire: the codec's I²C bus, the missing BCLK, and the Pico's USB console

**Date:** 2026-10-04
**Question:** ljoss reports errors from `namchaind`, and the Pico is on vip's USB but nothing
sees it. What is actually broken — the wiring, the engine, or the host?

## Result

Three disturbed leads, found in sequence, and one host configuration gap.

1. **The codec's I²C bus was dead.** `namchaind` was `active (running)` but reported
   `state: lost`, `device_lost: 1` against `hw:CARD=wm8960,DEV=0`: there was no sound card
   at all. Fixed at the bench (the codec's I²C leads re-seated): card 0 `wm8960` came back.
2. **BCLK was out of the header.** With the card back, every capture ran to
   `device: capture timed out after 1000 ms (last state 3, ring 0 frames)`: the PCM was
   `RUNNING` but no frames ever arrived. Fixed at the bench; the engine went green and
   stayed there.
3. **The ADAT (ADCDAT) lead was in the wrong socket**, which only showed once the clock was
   back: the card running and the ADC alive, but the capture exact zeros rather than a
   timeout. Fixed and measured the same day in
   [2026-10-04-case-no-audio-diagnosis.md](2026-10-04-case-no-audio-diagnosis.md), which also
   settles the output side: the rig leaves on channel 0 = HPL, so the interface's cable
   belongs in OUT L until a chain's `output_channel` is bound.
4. **The trimmed kernel has no `cdc_acm`.** The Pico enumerates on vip's USB but no driver
   binds its CDC interfaces, so there is no `/dev/ttyACM0`. Fixed in rtpi (rtpi `e873c9c`),
   rebuilt, installed and tried on vip.

## 1. The codec's I²C (the fatal one)

| Check | Result |
|---|---|
| `systemctl status namchaind` | `active (running)` — the daemon is written to survive a missing device, which is why it looked well |
| `namchainctl status` | `state: lost`, `health: error`, `device_lost: 1`, blocks 0 |
| `/proc/asound/cards`, `aplay -l` | no sound cards |
| `pedal-codec.service` | failed: `card wm8960 did not appear` |
| `dmesg` | `i2c_designware 1f00074000.i2c: controller timed out` ×2, `wm8960 1-001a: Failed to issue reset`, `probe with driver wm8960 failed with error -110` |
| Raw probe of `/dev/i2c-1` | every address 0x08–0x77, and the driver's own reset write to 0x1a, ran to the 1.024 s controller timeout (`ETIMEDOUT`) |
| Device tree / pin mux | overlay applied, `i2c1` `okay` on GPIO2/3, `i2s1` `okay` on GPIO18–21 |
| Deployed config vs the repo | `/etc/pedal/codec/wm8960-codec-master.dts`, `/etc/namchain/namchaind.json`, `/etc/pedal/tune.conf`, `/usr/local/sbin/pedal-codec` all byte-identical |

Every address timing out is the finding that matters. A healthy bus with no target at an
address answers with a NACK in microseconds; a bus that never completes a transfer has a line
being held. That is wiring, not configuration, and it is the
[codec-bringup-2a](codec-bringup-2a.md) "`i2cdetect` doesn't show `1a`" row: SDA/SCL swapped,
a lead not seated, or no 3.3 V at the board.

`mlockall` was reported refused at the same time (`memory_not_locked`, warn). It is a
knock-on, not a second fault: `namchaind` only attempts the lock after the device opens
(`src/daemon/daemon.cpp`, `lock_process_memory`), and it reports the warning whenever memory
was never locked and the device is not closed. It cleared by itself — `memory_locked: true` —
once the card was back.

## 2. BCLK out of the header

With the card up, `namchaind` reported the device lost again, every ~1.3 s, each time with:

```
[namchaind] device: capture timed out after 1000 ms (last state 3, ring 0 frames)
```

`/proc/asound/card0/pcm0c/sub0/status` showed `state: RUNNING`, `S32_LE`, 48000, q64 × 6 —
so the stream was open and the format was right, and no period ever completed. A disconnected
bit clock is exactly that: the RP1's I²S receiver makes no DMA requests, so the capture ring
stays empty. It is not the codec and not the mixer — a data lead (ADAT) would give silence or
garbage, not a timeout. The BCLK lead had come out of the header; once it was back in:

| | |
|---|---|
| `namchainctl` | `state: running`, `health: ok`, `issues: []`, `device_lost: 0`, `render_errors: 0` |
| blocks | 750/s (q64 at 48 kHz), steady |
| render | worst 3.4% of the 1333 µs period, 0 over deadline |
| `scripts/status` | `namchaind: running, ok, hw:CARD=wm8960,DEV=0, 48000 Hz / 64` |

The leads were not done moving: with the clock back the capture was exact zeros, and that
turned out to be the **ADAT (ADCDAT)** lead in the wrong socket on the codec board —
diagnosed, fixed and measured in
[2026-10-04-case-no-audio-diagnosis.md](2026-10-04-case-no-audio-diagnosis.md). Zeros and a
timeout look similar from the engine's side and are not the same fault: a timeout means no
clock (this section), zeros mean the clock is there and the data is not (that one).

## 4. The Pico on USB, and the trim

The Pico 2 W (`2e8a:0009`, "Raspberry Pi", serial `5988E9A10C2344D7`) enumerates over USB and
nobody binds it:

| Interface | Class | Driver |
|---|---|---|
| 3-2:1.0 | 02/02 CDC communications (ACM) | none |
| 3-2:1.1 | 0a CDC data | none |
| 3-2:1.2 | ff/00/01 vendor-specific | none |

No `/dev/ttyACM0`, no `/dev/ttyUSB*`, no `cdc_acm` in dmesg. The cause is the trimmed kernel:
`7.0.0-1017-raspi-realtime-numaemu1-trimmed` has `# CONFIG_USB_ACM is not set`, `modprobe
cdc_acm` answers "Module cdc_acm not found", and there is no `drivers/usb/class/` in its
module tree — while both other installed kernels (stock and the full `-numaemu1`) carry
`cdc-acm.ko` and `CONFIG_USB_ACM=m`.

It is the sharpest case of the self-fulfilling absence `vip-keep.fragment` already describes
for `inet_diag`: while the module is missing, nothing can bind the Pico, so `cdc_acm` can
never appear in the board's `/proc/modules` and the trim can never learn it is wanted.

**Fixed** in rtpi `e873c9c`: `CONFIG_USB_ACM=m` is the fragment's fifth deliberate exception.
Rebuilt in the container on the Mac (native aarch64, 6 vCPU), installed and tried through
vip-boot:

- build: 106 modules, `[ok] all 71 modules the board loads are present or built in`, no debug
  info; `drivers/usb/class/cdc-acm.ko` present
- install: 106 `.ko`, `trimmed tree covers every module the board loads`, built
  `bcm2712-rpi-5-b.dtb` byte-identical to stock, `vip-guard.sh` in the new initramfs
- try: candidate in slot a, `back after 21 s`, settled on the expected release, promoted;
  slot b good, nothing armed, guard 0 of 3
- after: `Linux version 7.0.0-...-trimmed ... #1 SMP PREEMPT_RT Sun Oct 4 20:32:26 UTC 2026`,
  `cdc_acm 3-2:1.0: ttyACM0: USB ACM device`, `/dev/ttyACM0` present (166:0, `root:dialout`)
- codec and engine unchanged by the reboot: card 0 `wm8960`, `pedal-codec` active, engine
  `running/ok`, blocks 750/s, `issues: []`

The release string is unchanged — a trimmed rebuild is still
`7.0.0-1017-raspi-realtime-numaemu1-trimmed` — so `devices/vip/components.lock` still matches
the host, and the build's identity is the module record in rtpi's
`results/vip-trimmed-modules-7.0.0-1017-raspi-realtime-numaemu1-trimmed.txt`.

**One thing this rebuild also changed:** it drops `crypto/af_alg`, `crypto/algif_hash`,
`crypto/sm4` and `crypto/sm4_generic`, which the 109-module build had only because they
happened to be loaded when its `/proc/modules` was fetched (today's fetch lists 71 modules and
none of these). Nothing on vip loads them now. If they are wanted for their own sake they
belong in the keep fragment like `cdc_acm`; they were not added, because no consumer on this
box is known. The candidate gate is what makes trying such a change safe:
`vip-boot-validate` requires a physical interface with a routable address before it promotes,
so a candidate that loses a driver rolls back rather than locking the box out.

## 5. vip can talk to it — over the console, and only carefully

With the driver bound, both directions were proved:

| Direction | Evidence |
|---|---|
| Pico → vip | the console's own lines: `fw: up 1060 s, session=0, frames ok=0 bad=0` every 5 s, and `proto: hello sent (v1.0 caps=0x0000)` once a second |
| vip → Pico | a written `?` answered `proto: frames ok=0 bad=0 events lost=0 session=0 rig=-1 name=''` |

**Open it raw with echo off, or it loops.** The first attempt (`exec 3<>/dev/ttyACM0` with the
default termios) came back as a storm of `proto: event refused, no session` at ~12/s, and it was
self-inflicted: ECHO on the host echoes what the tty *receives* back down the port, and the
firmware's bench stand-in reads `e`, `d`, `b` from that same console — the refusal text itself
contains those letters, so it sustains itself. With `stty -F /dev/ttyACM0 raw -echo` the same
port is clean: 6 HELLOs in 6 s, one heartbeat, **zero** refusals. This matters beyond tidiness:
with a session up, an echoed `e`/`d`/`b` is a real `rig_up`/`rig_down`/`bypass_toggle` EVENT, so
anything that opens this console — the pedal service included — must turn echo off and must
never leave stray bytes on it.

**The link now runs on vip** (same day, later). The Pico's UART was moved off the Debug Probe
onto the header — GP0 → pin 10 (RXD), GP1 → pin 8 (TXD), pin 3 → GND — and the first placement
was dead in both directions: silence on `ttyAMA0`, and `frames ok=0 bad=0` on the Pico after
valid PINGs sent from vip, so it was not even receiving mangled bytes. vip's side was already
right (pins 14/15 muxed to `uart0`, 115200, no getty, nothing else claiming them), and no
`/dev/cu.usbmodem*` existed on the Mac, so no third party was on the net. After the leads were
re-seated, `ttyAMA0` carried HELLO once a second — `a5 5a 01 07 01 00 00 00 30 2e 31 16 4a`,
i.e. v1.0, caps 0x0000, fw "0.1" — and three PINGs took the Pico's counter to `frames ok=3`.

A full session was then driven from vip by hand (WELCOME, STATE, PINGs) with the console open
to watch it:

    proto: session up (service v1.0, heartbeat 250 ms)
    proto: state audio_ready=1 bypass=0 health=0 rig=2 bank=0/3 name='Crunch Lead'
    proto: ping 66 -> pong                                    (x11)
    proto: frames ok=15 bad=0 events lost=0 session=1 rig=2 name='Crunch Lead'
    proto: link down                                          (1 s after the frames stopped)

So the Core side of the link works end to end from vip — with `stty` and raw file descriptors
rather than the Mac's `firmware/tools/protocol-test.py`, because vip's python3 is
`python3-minimal` and has no `termios`. Two things follow: the pedal service (Phase 3.2) is what
the link still waits for, and the firmware reports itself as fw **"0.1"**, which no current
checkout's `git describe` can produce (both give a commit hash), so the Pico is running an older
build than the tree — reflash from a known commit before trusting firmware-side numbers.

## Note for the link, not the console

The Pico's USB CDC is its debug console (`firmware/CMakeLists.txt`: "USB CDC for the console.
UART stdio must stay off: the link UART is ours"). The pedal's protocol link is the header
UART, and on vip that is `ttyAMA0` on pins 8/10, which is idle: the kernel console and its
getty are on `ttyAMA10`. So unlike piv — where step 4 had to move the console off `ttyAMA0` —
vip's link UART is already clean.

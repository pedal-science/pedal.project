# V2: the D14 gate — rigpa on the Core host, drawing the screen, beside the render core — PASS

**rigpa costs the render core nothing the gate can see.** Five ten-minute arms on vip, the same heavy
rig playing in all of them (0.553 of the render core, three chains, with pedald's warm document on
core 1), and in every arm: **0 xruns, 0 blocks over the deadline, 0 blocks over 90%, 0 guard trips**,
the clock at 2400 MHz and the throttle flags clear. rigpa ran as its real unit, on eglfs on vc4, scanning
out 1920×480 at 60 Hz and rendering on the GPU.

It is not free. The render core's tail moves with what rigpa draws — p99 23% with rigpa off, 25% idle,
28% with the live meters, 31% animating every frame — and the render core's own busy share rises with
it (22.6% → 24.8%) for the same rig, which is the memory-traffic effect D14 was written to watch for.
The worst block in any arm was 58%, against the 90% the gate allows.

## The arms

| arm | gate | xruns / over deadline / over 90% / guard | load p50 / p99 / p99.9 / worst | blocks ≥ 40% | core 0 / 1 / 2 / 3 busy | rigpa CPU | rigpa PSS | MemAvailable | temp |
|---|---|---|---|---|---|---|---|---|---|
| off | PASS | 0 / 0 / 0 / 0 | 21% / 23% / 33% / 50% | 145 | 6.7% / 9.7% / 0.0% / 22.6% | — | — | 775 MB | 58.2..61.5 °C |
| idle | PASS | 0 / 0 / 0 / 0 | 21% / 25% / 34% / 52% | 176 | 7.8% / 9.7% / 0.0% / 22.8% | 0.4% of a core | 141 MB | 713 MB | 58.7..62.0 °C |
| meters | PASS | 0 / 0 / 0 / 0 | 21% / 28% / 38% / 57% | 373 | 11.9% / 9.9% / 0.0% / 23.2% | 3.0% of a core | 142 MB | 712 MB | 58.2..61.5 °C |
| animate | PASS | 0 / 0 / 0 / 0 | 22% / 31% / 35% / 58% | 170 | 28.7% / 10.5% / 0.0% / 24.8% | 18.6% of a core | 143 MB | 710 MB | 59.3..63.7 °C |
| off2 | PASS | 0 / 0 / 0 / 0 | 21% / 23% / 33% / 55% | 161 | 6.9% / 9.7% / 0.0% / 22.6% | — | — | 775 MB | 56.5..60.9 °C |

- **off / off2** are the control, before and after: they agree (p99 23% both), so nothing drifted over
  the hour and the movement in between is rigpa's.
- **idle** is what the pedal will do almost all the time: a static screen, scan-out only. It costs
  0.4% of core 0 and two points of render-core p99.
- **meters** redraws the info panel about ten times a second: 3% of core 0, five points of p99, and
  the most blocks at or over 40% (373 against 145) — small, frequent redraws are what spread the tail.
- **animate** is the worst case, `--demo-animate`: a node lifted and swept through the editor and
  back, for ever, so the whole content area is redrawn every frame. 18.6% of core 0, eight points of
  p99, and still nothing near the gate. Nobody uses the pedal like this; a drag is seconds long.

rigpa's memory is **141–143 MB PSS** (plan target: under about 150 MB), and MemAvailable falls by
62–65 MB with it running: the rest of its pages are the Qt and Mesa libraries, shared and file-backed.
That is the number to set `MemoryMax` from, with headroom: 256 MB would be generous.

## How it ran

- **The screen isn't fitted yet**, so vc4 was told one is: HDMI-A-1 forced on (`/sys/class/drm/card1-HDMI-A-1/status`)
  with a generated 1920×480, 60 Hz EDID (`make-edid.py`, through DRM's debugfs `edid_override`). The
  frame is the real one: vc4's state showed a 1920×480 framebuffer allocated by Qt's render thread on
  the plane being scanned out. The timing is a reduced-blanking stand-in, not the panel's own (V3
  reads that from the real EDID); the pixels per frame, which are what scan-out costs, are the same.
- **rigpa as its real unit**: `rigpa.service` with the pedal's drop-ins (core 0, nice 5, idle IO,
  `OOMScoreAdjust=500`, its own user, the token through `LoadCredential`), plus a runtime drop-in in
  `/run` for each arm's config (live meters on or off) and `--demo-animate`.
- **The rig**: built as `scripts/measure-housekeeping` builds T5's — the playing rig's chain repeated
  until `rig.cost` was just under 0.70; three chains made 0.553, the same weight as T11's. It is in
  `run/v2-heavy.json`. pedald was restarted so its bank included it, and held Standard warm on core 1
  throughout (the engine's warm set says so in every sample).
- **The measurement**: `scripts/soak/soak-monitor.sh` on vip (engine.status every 10 s) and
  `soak-summary.py` on each arm; `/proc/stat`, MemAvailable and rigpa's `smaps_rollup` and CPU ticks
  before and after each arm (`run/<arm>.{before,after}.txt`); `analyse-v2.py run` makes the table.
- **Put back**, by the harness's own cleanup: pedald's resume files and the rig they name (Standard),
  the test rig removed, the runtime drop-in removed and rigpa stopped, the connector un-forced.

`run-v2` is the harness; `run/env.txt` records the kernel, the commits and the boot slots. A 30-second
rehearsal ran first to shake the harness out (two bugs fixed before the real run: rigpa's unit has
`PrivateTmp`, so its config moved to `/run`; and the cleanup now puts the resume files back *before*
reloading the rig they name).

## What getting here changed

- **The kernel.** With `dtoverlay=vc4-kms-v3d` on numaemu2, vc4 never finished binding: the Pi 5's HDMI
  DDC buses are `brcm,brcmstb-i2c`, whose driver the trim had removed (nothing loaded it before), and
  HDMI waits for its DDC adapter. Booting the stock kernel with the overlay and diffing its modules
  against the trimmed tree found backlight and CEC too. rtpi `c797e84` keeps all three; **numaemu3** is
  the result, promoted through `try-kernel` (rtpi `d4779ff`, image.lock).
- **The overlay** is on, through `vip-boot try-config 'dtoverlay=vc4-kms-v3d'`: its first real use,
  validated and promoted, and carried into both slots.
- **rigpa's unit** starts only when a screen is *connected* (`ExecCondition` on the connector's
  status, not just its existence, which would have restarted it every two seconds with no screen),
  gives up after five failed starts, and on vip uses `kms.json` to drive vc4 rather than v3d (card0 on
  the Pi 5 is the GPU, render-only).
- **The boot slots** now hold the stock kernel in a and numaemu3 in b (active); `devices/vip/check`
  reads them by role rather than by letter, since every validated trial moves the pedal kernel to the
  other letter.

## Not measured here

- Ten minutes an arm, once each. The earlier soaks ran an hour; the control arms agreeing before and
  after is what this run has instead.
- A rig at the headroom (0.78): this one is 0.553. T5's sweeps are where a fuller render core was
  measured; the question here was the delta rigpa makes, at a realistic load.
- Touch, and the real panel's timing: V3, with the screen.

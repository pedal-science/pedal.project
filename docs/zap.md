# zap: the small-pedal host

**zap** is a Raspberry Pi Zero 2 W, the Core host of a small pedal that may run on its own battery.
Recorded 2026-11-03, **before the board has arrived**: everything below about how it performs is
unmeasured, and nothing here has run on one. This page grows as the machine is set up, as
[pro.md](pro.md) did. What the pedal around it might be is still open
([operations-plan.md](operations-plan.md), `pocket`).

## What it is

| Part | Detail |
|---|---|
| Computer | Raspberry Pi Zero 2 W: RP3A0, four Cortex-A53 at 1 GHz, 512 MB, aarch64 |
| Hostname | `zap` |
| Compared with vip | A dual-issue in-order core at under half the clock, against vip's out-of-order A76 at 2.4 GHz. It has half vip's memory |

**The expectation, which is a guess:** one A2-Full costs 0.111 of a vip core, and clock and core
design together may make it 5-7× dearer here, about 0.55-0.8 of a zap core. So perhaps one A2-Full and
a cab per core. The first measurement replaces this paragraph.

## The bench is ready

`devices/zap/image.env` holds the flags (`-march=armv8-a+crc -mtune=cortex-a53`), and the bench is built
by the same route as vip's, in the same container:

```bash
scripts/measure-core --host zap --build-only --out build/zap/measure/bench
```

It is static, because zap's userland is not decided and the container's glibc is too new for most
Pi images. The engine will not be. What the build was checked against:
[bench-results/2026-11-03-zap-bench-build](../bench-results/2026-11-03-zap-bench-build/README.md).

## When it arrives

None of this has been exercised on a Zero 2 W, so expect to fix something.

1. Flash Ubuntu Server 26.04 arm64 (decided 2026-11-03: the same userland as vip) with the hostname
   `zap` and your SSH key, and give `rik` passwordless `sudo`, as vip and pro have. Add `zap` to
   `~/.ssh/config`.
2. Install `rsync` if it is missing, then copy the library. The whole of it is small (55 MB):
   ```bash
   rsync -rt ~/Documents/Audio/NAM/ zap:/var/lib/pedal/library/models/
   ```
   ```bash
   rsync -rt ~/Documents/Audio/IRs/ zap:/var/lib/pedal/library/irs/
   ```
3. Put the clock in a known state for a first look: `performance` governor, then check it stays at
   1 GHz. A heatsink is worth having, and use a supply that can really deliver 5 V under load, because
   undervoltage and thermal throttling both show up as slow DSP.
4. Measure, with the already-built bench:
   ```bash
   scripts/measure-core --host zap --no-build --out build/zap/measure/bench --dry-run
   scripts/measure-core --host zap --no-build --out build/zap/measure/bench
   ```
5. Check `vcgencmd get_throttled` afterwards, if the OS has it, and keep the result beside the numbers.
6. Merge with `devices/common/cost-merge --device zap`, and record the kernel in the evidence.

**What a first number is worth.** This is a stock kernel with nothing isolated, so it is a first look at
what `pocket` could be, not the table of record. That table waits for zap's real kernel and core split.

## Not done

- No real-time kernel. Whether one is available for this SoC, or `rtpi` has to build it, is open.
- No `devices/zap/` beyond the bench's needs: `namchaind.json` is vip's with the cost table removed, and
  only its library paths are read so far. No `apply`, `check`, `backup`, `lib.sh` or `packages`, so
  `scripts/status --host zap`, `components-lock` and `deploy-engine --host zap` will not work yet.
- No image: `devices/common/make-card` is written for the Pi 5's boot layout.
- The audio path is untried on this SoC, though I2S is on the same header pins.

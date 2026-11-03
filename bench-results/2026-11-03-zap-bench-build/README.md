# zap's bench, built before zap exists (2026-11-03)

`namchain-warm-bench` for a Raspberry Pi Zero 2 W, made so the first measurement can start the day the
board arrives. **There are no performance numbers here.** Nothing ran on an A53, and nothing below says
how fast one is.

| | |
|---|---|
| Command | `scripts/measure-core --host zap --build-only --out build/zap/measure/bench` |
| namchain | `ae6f8531e51bc9c7e032533397134e00ca612dc0`, clean |
| Container | `pedal-build:20260929T000000Z`, vip's (`devices/zap/image.lock`) |
| Flags | `-march=armv8-a+crc -mtune=cortex-a53 -static` (`devices/zap/image.env`) |
| Configure | `A2 planar NEON: ON` (`build-bench` refuses otherwise) |
| Result | ELF aarch64, statically linked, 6.2 MB |
| sha256 | `41558ac4d8ca8a37fddb8bf8812ac0b167fd794d77baaf2c261ea134ba0696e4` |

The binary is not kept here: `build/` is ignored, and the command above makes it again.

## What was checked

- **It can run on an A53's instruction set.** It was run under `qemu-aarch64 -cpu cortex-a53` (10.2.1)
  through the `measure` mode for a NAM Full unit, a NAM Lite unit and a node unit, against the vendored
  core's `A2.nam`, without an illegal instruction. The kernels in the NAM units are what this is for.
  **qemu's timings are meaningless and are not recorded.** The Full run's "misses the deadline" and exit
  status 1 are qemu being slow.
- **It starts on other userlands:** Ubuntu 26.04 and Debian 12, which has a much older glibc. That is
  what `-static` is for.
- **It fits.** Peak RSS was about 24 MB for each of: NAM Full at `--max` 1, 2 and 4, NAM Lite at 1 and 4,
  and an 8192-tap IR, with the library's 294 kB VT-40 model and the DI, native in the arm64 container.
  So the bench will not run zap out of memory. This says nothing about the engine, or about
  warm rigs.

## What was not checked

Anything on a real A53: speed, thermals, `measure-core`'s host side on a Zero 2 W, or `pedal-bench.slice`
on a stock OS. qemu models the instruction set, not the cache or the pipeline, so this is no evidence of
how the planar kernels will perform on an in-order core.

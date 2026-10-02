# Where the two-amp Ambient Wash's peaks come from (vip, 2026-10-02)

The question (plan.md, vip soak item 3, "Measured steady"): the two-amp Ambient Wash fails the
gate by itself on vip at q64, with a median block of 15% and a worst of 98.9%. Is the tail in the
rig's work, in the engine, or in the host?

**Answer: memory.** The rig's two A2-Full amps don't fit in a core's L2 together, so every block
depends on the L3 and DRAM that the other cores share, and the tail is whatever else touches memory
while it plays. Not the cab IR, not the delay, not the block size, not the daemon.

## Method

`namchain-soak --graph` (namchain 2e1a63a, as deployed in `/opt/namchain/current`), null backend,
paced to the wall clock like the device (unless `--no-pacing`), on core 2 at SCHED_FIFO 80, in a
scope under `pedal.slice` (`run.sh`; `system.slice` and `user.slice` are confined to cores 0-1).
namchaind kept running on core 3 with no rig. The host lock was held throughout. Input: `pluck.wav`,
20 s of decaying plucked notes at about -12 dBFS plus -60 dBFS noise, generated for this run. The
graphs are the steady session's Guitar chain (`two-amp.json`) with nodes removed or swapped. The
model files came from the library. `gvt/` and `svt/` were each amp's two submodels, extracted
with namchain's `tools/extract_a2_submodels.py`; they're not kept here. `out-*.json` is the
last run of each graph and input.

Core 2 also takes the codec's DMA interrupt, so offline numbers here run harsher than the live
engine's on core 3. For example, the two-amp rig gave p99 59-76% across three runs here, against
46% live. Compare rows with each other, not with the live soak.

## Results (% of the block deadline: 1,333 µs at q64, 2,667 µs at q128)

| graph | p50 | p99 | worst | over deadline |
|---|---|---|---|---|
| two-amp (the rig), paced | 14.6-15.0 | 59-76 | 107-144 | 4-84 |
| two-amp, silence in | 14.9 | 71.1 | 110.3 | 7 |
| two-amp, **flat out** (`--no-pacing`) | 14.0 | 26.0 | 107.5 | 1 |
| two-amp, an idle-priority spinner on core 2 | 15.8 | 61.7 | 118.8 | 6 |
| two-amp, **`dd bs=4M` on core 0**, paced | **32.0** | 75.9 | 125.6 | 24 |
| two-amp, `dd` on core 0, flat out | **28.0** | 67.9 | 116.9 | 11 |
| two-amp, q128 | 15.2 | 51.9 | 91.7 | 0 |
| two-amp, IR cut to 4096 taps (44.1 kHz) | 14.7 | 63.4 | 127.7 | 13 |
| two-amp, IR cut to 2048 taps | 15.0 | 72.8 | 115.2 | 10 |
| GVT amp alone | 6.0 | 22.1 | 38.2 | 0 |
| SVT amp alone | 5.9 | 19.0 | 41.0 | 0 |
| both amps, nothing else | 12.6 | 53.0 | 83.5 | 0 |
| one amp + cab + delay | 7.9 | 31.3 | 62.2 | 0 |
| cab + delay, no amps | 1.3 | 9.3 | 26.3 | 0 |
| two-amp, both as the extracted A2-Full (control) | 15.0 | 74.0 | 122.9 | 24 |
| two-amp, **GVT Full + SVT Lite** | 9.6 | 42.9 | 98.3 | 0 |
| two-amp, **both Lite** | 4.1 | 23.0 | 55.2 | 0 |

## Reading it

- **Memory-bound.** A `dd` streaming through 4 MB buffers on core 0 doubles the rig's median on
  core 2, both paced and flat out. Work that fits in a core's own L2 wouldn't notice.
- **The tail grows faster than the work.** Each amp alone has p99 about 20%; the two together have
  53%, and adding the cab and delay (2% of median) takes it to 59-76%. That is a capacity cliff,
  not a sum of costs.
- **Why it's the amps.** Both are `SlimmableContainer`s whose full submodel is A2-Full: 8 channels,
  23 dilated layers, dilations to 239 at kernel 6. Each layer's ring buffer is
  `2 × lookback + 64` columns × 8 channels, about 450 KB per model. A block reads 6 taps × 64
  frames per layer, from up to 1,195 samples back (19 blocks). So each block walks a few hundred KB
  per model, written up to 25 ms earlier. Two models don't fit in the Cortex-A76's 512 KB L2.
  This is an estimate from the code (`vendor/NeuralAmpModelerCore/NAM/ring_buffer.cpp`, the
  model's config), not a counter measurement: vip has no `perf`.
- **Pacing exposes it.** Flat out, the rig's own data stays hot and p99 is 26%. Paced, the core
  waits about 1.1 ms per block, while the other cores' traffic evicts the rig's data from the
  shared L3. vip has no cpuidle states (driver `none`), so it isn't idle-state exit. Keeping the
  core busy with a spinner barely helps (p99 76 → 62%).
- **Not the IR, not the block size.** Cutting the IR to 2048 taps changes nothing. q128 leaves the
  median at the same 15% of its doubled deadline, and its worst block still reaches 92%.
- **What fits.** A2-Lite has 3 channels, so its buffers are 3/8 the size. Two Lites peak at 55%
  here. Full + Lite peaks at 98% here, on the harsher core; it needs a live soak on core 3 before
  it counts.

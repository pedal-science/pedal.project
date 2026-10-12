# The codec's input noise — 2026-10-12

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **repeat of the run above: LIN1 shorted to the codec's own GND, only vip and the codec connected**.

The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -86.93 dBFS | **-88.94 dBFS(A)** | -86.10 dBFS | -72.53 | 45.0 µV | 35.7 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -87.25 dBFS | **-89.30 dBFS(A)** | -86.40 dBFS | -72.61 | 43.4 µV | 34.3 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -93.42 dBFS | **-95.72 dBFS(A)** | -85.20 dBFS | -59.85 | 21.3 µV | 16.4 µV |

The quietest arm reads **-93.42 dBFS** unweighted, inside the bench test's codec-only bar of -75 ± 3 dBFS.

**`capture-only` is not as quiet as its band-limited figure says.** Raw -85.20 dBFS against -93.42 dBFS in the 20 Hz–20 kHz band: 8.2 dB, so roughly 85% of this arm's power is outside the audio band — it drifts or settles rather than hisses, and the unweighted, A-weighted and µV columns, band-limited as every earlier reading of this converter is, cannot see it. By the raw figure it is the loudest of the arms measured here.

## What it is compared with

| when | state | unweighted | A-weighted |
|---|---|---|---|
| 2026-10-11 | engine, 64-frame periods, muted | -75.72 dBFS | -75.29 dBFS(A) |
| 2026-10-11 | engine, 1024-frame periods, muted | -79.09 dBFS | -79.73 dBFS(A) |
| 2026-10-11 | arecord alone | -75.83 dBFS | -75.75 dBFS(A) |
| 2026-10-11 | arecord + silent playback | -79.74 dBFS | -79.86 dBFS(A) |
| 2026-09-27 | 2a's bench record, LIN1 shorted | -90.60 dBFS | -93.50 dBFS(A) |

The 2026-10-11 rows are the codec-only captures in [../2026-10-11-codec-noise-spectra/README.md](../2026-10-11-codec-noise-spectra/README.md); the 2a row is that bench's own record. The bench test's “Codec input on its own” check reads the same measurement against a bar of -75 dBFS ± 3, and paints the codec block when it fails (`devices/common/rootfs/usr/local/lib/benchtest/catalog.py`).

## The run

- The engine: `active` before, `active` after; mute `False` → `False`; xruns `0` → `0`.
- Card `hw:wm8960`, format `S32_LE`, 20 s per arm, channel 0 = LIN1.
- Arms run: engine, playback, alone.

## Running it again

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it again afterwards and puts the mute back as it found it. `--arms engine` alone needs no interruption at all: the engine records its own capture while it runs.

# The codec's input noise — 2026-10-12

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **LIN 1 wired to Codec GND, input board not connected to anything**.


The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -89.33 dBFS | **-91.39 dBFS(A)** | -127.9 dBFS | -88.44 dBFS | -74.91 | 34.2 µV | 26.9 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -89.98 dBFS | **-92.07 dBFS(A)** | -129.3 dBFS | -88.98 dBFS | -75.06 | 31.7 µV | 24.9 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -91.10 dBFS | **-94.12 dBFS(A)** | -121.1 dBFS | -83.58 dBFS | -58.31 | 27.9 µV | 19.7 µV |

The quietest arm reads **-91.10 dBFS** unweighted, inside the bench test's codec-only bar of -75 ± 3 dBFS.

**`capture-only` is not as quiet as its band-limited figure says.** Raw -83.58 dBFS against -91.10 dBFS in the 20 Hz–20 kHz band: 7.5 dB, so roughly 82% of this arm's power is outside the audio band — it drifts or settles rather than hisses, and the unweighted, A-weighted and µV columns, band-limited as every earlier reading of this converter is, cannot see it. By the raw figure it is the loudest of the arms measured here.

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
- Kernel `7.0.0-1017-raspi-realtime-numaemu3-dmaidle1-trimmed`.
- Arms run: engine, playback, alone.
- Attempts: engine 1, playback 1, alone 1.
- Kernel messages during the `arecord` arms: none.

## Running it again

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it again afterwards and puts the mute back as it found it. `--arms engine` alone needs no interruption at all: the engine records its own capture while it runs.

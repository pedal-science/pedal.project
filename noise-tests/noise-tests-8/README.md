# The codec's input noise — 2026-10-13

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **LIN 1 wired to input board LIN1, input board GND connected to Codec GND. input board V9 connected to 9V battery +, input board GND connected to battery -. input board IN to jack tip. input board GND connected to jack sleeve. 20cm TRS cable plugged into jack, other end connected to guitar, player not touching the guitar strings. input board SW-C jumpered to SW-L. U1 pin 3 shorted to board ground.**.


The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -85.21 dBFS | **-87.18 dBFS(A)** | -117.5 dBFS | -84.45 dBFS | -70.17 | 54.9 µV | 43.8 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -87.64 dBFS | **-89.74 dBFS(A)** | -118.5 dBFS | -86.79 dBFS | -72.92 | 41.5 µV | 32.6 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -91.57 dBFS | **-93.70 dBFS(A)** | -119.2 dBFS | -83.50 dBFS | -58.28 | 26.4 µV | 20.6 µV |

The quietest arm reads **-91.57 dBFS** unweighted, inside the bench test's codec-only bar of -75 ± 3 dBFS.

**`capture-only` is not as quiet as its band-limited figure says.** Raw -83.50 dBFS against -91.57 dBFS in the 20 Hz–20 kHz band: 8.1 dB, so roughly 84% of this arm's power is outside the audio band — it drifts or settles rather than hisses, and the unweighted, A-weighted and µV columns, band-limited as every earlier reading of this converter is, cannot see it. By the raw figure it is the loudest of the arms measured here.

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
- Kernel messages during the `arecord` arms: in `dmesg-playback-open.txt`.

## Running it again

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it again afterwards and puts the mute back as it found it. `--arms engine` alone needs no interruption at all: the engine records its own capture while it runs.

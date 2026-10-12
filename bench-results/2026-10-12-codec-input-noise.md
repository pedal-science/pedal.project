# 2026-10-12 — the codec's input noise, after the wiring was re-seated

The owner re-checked and re-seated the codec's wiring and left the pedal with **only vip and the
codec in it** — no board 1, no jacks, no output fixture, no Pico, no interface, nothing but the
host's own USB-C supply — and asked for the input noise to be measured again and graphed against
the October baseline. Two runs, back to back, both with LIN1 shorted to the codec's own GND.

**Result: the codec's input floor is now −89.3 dBFS(A) in the pedal's normal state, 14.0 dB below
the 2026-10-11 codec-only reading of −75.3 dBFS(A), and there is no mains hum anywhere in it.**

| arm | run 1, 18:44 | run 2, 18:50 | 2026-10-11 |
|---|---|---|---|
| engine running, muted (64-frame periods) — the normal state | **−87.31 dBFS / −89.34 dB(A)** | −86.93 / −88.94 | −75.72 / −75.29 |
| engine stopped, a silent playback stream open | −87.51 / **−89.58 dB(A)** | −87.25 / −89.30 | −79.74 / −79.86 |
| engine stopped, capture only | −92.43 / −94.63 † | −93.42 / −95.72 † | −75.83 / −75.75 |
| *(reference)* 2a's bench, LIN1 shorted, 2026-09-27 | — | — | −90.60 / −93.50 |

† **Not as quiet as it looks.** 8–9 dB of that arm's power is *outside* the 20 Hz–20 kHz band the
figures use (raw −83.0 and −85.2 dBFS against −92.4 and −93.4 in band), and its loudest lines are
all below 25 Hz: with no playback stream open the converter drifts at sub-audio frequencies, and
the band-limited convention — which every earlier reading of this converter uses — cannot see it.
The two arms that matter are the first two, and they agree with each other to 0.2–0.4 dB.

The pages, with a spectrum and an octave-band chart per arm and the audio to listen to:
[run 1](2026-10-12-codec-input-noise/index.html) and [run 2](2026-10-12-codec-input-noise-repeat/index.html).

## What the graphs show

- **No hum at all.** No 50 Hz line appears in any of the six captures. On 2026-10-11 the codec-only
  set had none either, but that session's *input* row — board 1 at node B, everything on mains —
  read 50 Hz at −58 dBFS. Whatever carried it then is not carrying it now.
- **The broadband floor is the whole story**: about −125 dBFS per 0.73 Hz bin, flat to 20 kHz, with
  nothing above it except the engine's own period-rate family.
- **The engine's 750 Hz family is unchanged, and is the engine's.** At 64-frame periods there are
  lines at 750, 1500, 2250 and 3000 Hz, ±0.7 Hz sidebands included, the loudest at −109 to −110
  dBFS — about 15 dB above the per-bin floor and 22 dB under the arm's total. The same family was
  there on 2026-10-11 and in the engine's interface captures; it is the render loop's period rate,
  not the wiring, and moving the engine to 1024-frame periods is what removes it (2026-10-11
  measured that as worth 4.4 dB(A) *when the floor was 14 dB higher*).
- **The pedal is now within 4 dB of the best number the bench has** for this converter: 2a's
  −93.5 dB(A), measured on a bare board on `piv` with no case, no supply and no USB.

## The two runs agree

Engine and playback arms: 0.38 and 0.26 dB apart. Capture-only: 0.99 dB on the band-limited figure
and 2.2 dB on the raw one — that arm's drift is what moves, which is the same instability the
2026-10-11 log recorded for it ("the least trustworthy of the five"). The engine's own recording
reported 0 xruns, 0 dropped and 0 inserted periods in both runs, and the host came out of each run
as it went in: namchaind active, unmuted, 0 xruns, no `arecord` or `aplay` left behind.

## How it was measured

`scripts/codec-input-noise.py` — written for this, because the recipe in
[docs/codec-bringup-2c.md](../docs/codec-bringup-2c.md) was a list of commands to type and the
graphs were a one-off script tied to the captures of one session:

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, records the engine's own capture while it runs (the arm that needs
no interruption), stops `namchaind` for the two `arecord` arms, starts it again afterwards and puts
the mute back as it found it. `scripts/noise-document.py` draws the page from a manifest of
captures, and is what the 2026-10-11 page's `make-document.py` became: it checks its own RMS
against `scripts/codec-noise.py` for every capture (0.00 dB on all six here) and refuses to write
the page if it disagrees by more than 0.05 dB. `--rebuild DIR` re-analyses and re-draws a results
directory without touching the pedal. 18 tests in `scripts/tests/test_codec_input_noise.py`, which
is where the format dump, the silence file, `--dry-run` and `--rebuild` are checked; the captures
themselves need the pedal and are not tested.

The raw captures (7.7 MB each) and the playable copies are in each results directory's `captures/`
and `audio/`, untracked by a `.gitignore` in that directory; the numbers, the graphs, the pages and
the state of the host around each run are tracked. The engine's own recordings are left on vip in
`/var/lib/namchain/recordings/codec-input-noise-20261012-*`.

## Open

- **The bench test's bar for this is stale.** Its "Codec input on its own" check passes at
  `codec_only_rms_dbfs = -75.0 ± 3` from the 2026-10-11 log and paints the codec block when it
  fails. This pedal now reads −87 to −93 dBFS unweighted, so the check would pass a pedal 15 dB
  worse than this one. Tightening it is a decision about what the pedal should achieve, not a
  measurement, and it is the owner's.
- **This says nothing about the input stage.** LIN1 is shorted at the pin, so what was measured is
  the converter and the wiring to it. The guitar input's own noise is the other row, and it needs
  board 1 wired to LIN1 — plan.md's stage 7 — before it can be measured at all.
- **The 14 dB is not a controlled experiment.** The bench changed between 2026-10-11 and now by the
  owner's re-seating, which is the obvious candidate and the only one anybody named; nothing here
  separates one wire from another.

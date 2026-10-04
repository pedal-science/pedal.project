# No audio from the codec: it is processing, but nothing is arriving

**Date:** 2026-10-04 (host up 10 minutes — the fault started at this boot)
**Question:** the codec is giving no output. Is it receiving audio, and is it processing it?

## Findings

| Check | Result |
|---|---|
| Engine | `running`, `ok`, `mute false`, rig "Crunch Lead" applied, no failed nodes, `render_errors 0`, no queue drops; blocks advance at ~810/s |
| Mixer vs the recorded state | all 28 controls match `devices/common/rootfs/etc/pedal/codec/wm8960.mixer`; DAC 'Playback' 255 (0 dB); card running S32_LE, 48 kHz, period 64 |
| `namchainctl record` capture | **all zeros** (−inf dBFS, 0 µV, both channels) |
| `arecord` with the engine stopped | **all zeros**, both channels — the same, so it is not the engine's recorder |
| `recordings/guitar2/` (2026-10-02, working) | capture −86.69 dBFS (46.3 µV), A-weighted −89.45, 50/100 Hz lines: a plugged-in guitar at rest |
| `recordings/guitar2/playback.wav` | channel 0 −51.66 dBFS (the rig), channel 1 −102.23 dBFS (the engine's floor) |

So: the engine renders the rig to **output channel 0 = HPL**. Channel 1 carried only the floor when it
worked, and the engine does not yet bind a chain's `output_channel` (namchain's `docs/rig-pipeline.md`:
"parsed and validated but not yet bound"). A fixture fed from **HPR** therefore stays silent.

The capture being all zeros means the codec's ADC is delivering no data at all — not even a quiet
analogue floor, which a connected guitar produces. The chip is alive (the mixer reads and writes over
I2C at 0x1a), the card is running, and the mixer is exactly as recorded, so this is the digital audio
data path, not a configuration problem.

2a's own row for this symptom: **"Clocks present but the recording is all zeros → the ADAT lead, or
the ADC not following DACLRC (`wlf,gpio-cfg`)"** — see
[docs/codec-bringup-2a.md](../docs/codec-bringup-2a.md) stage 4's wiring table and its troubleshooting
table.

## What to check

1. **The I2S leads on the codec board**, which the bench work may have disturbed: ADAT (ADCDAT) to
   GPIO20 (header pin 38), DDAT (DACDAT) to GPIO21 (pin 40), BCLK to GPIO18 (pin 12), DLRC to GPIO19
   (pin 35). ADCLRC (ALRC) is deliberately not connected — the overlay runs the ADC from DACLRC.
2. **Use the left output.** HPL → its 10 µF → 100 Ω → OUT L tip, with the 1 MΩ to the star, is the
   path that carries the rig, and it is the one already checked out as correct. Put the interface's
   cable in the OUT L jack. Setting the chain's output channel to 1 in ljoss will not help yet.

## How it was measured

`scripts/codec-noise.py` (see [docs/codec-bringup-2c.md](../docs/codec-bringup-2c.md)), full scale
1.0 V rms, so the µV figures compare with 2a's. The direct capture needed the engine stopped: it was
done under `scripts/host-lock`, `namchaind` was restarted straight after, came back `active` with
"Crunch Lead" reseeded by `pedal-resume`, and left no recording running. The engine's own recordings
stay on the host under `/var/lib/namchain/recordings/` (`diag1`, and the 2026-10-02 `guitar*` used as
the reference).

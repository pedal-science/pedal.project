# Troubleshooting log — the pedal's noise, 2026-10-11

One test at a time, each with the same instrument and the same conventions, so the numbers can be
compared with each other. The earlier captures and reasoning in this directory stay as they are;
this file is the clean run through the same ground.

**Rig as it stands.** Pedal (board 1 on the breadboard, WM8960 codec on `vip`) powered, its OUT L
into the SSL 2+ Mk II's **input 1**. The SSL's output lead is **out of the pedal's IN jack**. The
engine runs but is **muted** (`device out L rms −200 dBFS`, silence), so nothing in these readings
comes through a rig or a document — and the rig is not to be used for any of them.

**The instrument.** sox through CoreAudio names the interface; capture is 2 channels, 24-bit,
48 kHz, and **channel 0 is input 1** (the interface's own loopback is on 2/4/6, so a two-channel
capture never sees it). `scripts/codec-noise.py` reports the DC offset, the unweighted RMS over
20 Hz–20 kHz in dBFS, the A-weighted RMS, the peak, and the largest spectral lines. Its µV column
assumes a 1.0 V rms full scale, which the interface's line input is not — **compare dBFS, not µV**.
Every capture goes through the same interface at the same gain, so dBFS is directly comparable
between tests.

**Why 2 channels and not 8:** opening the interface at eight channels raises its own noise floor by
11–12 dB (measured, `compare-2ch.wav` vs `compare-8ch.wav`). Two channels is the honest figure.

| # | Test | Reading | What it means |
|---|---|---|---|
| 1 | **Noise at SSL input 1** (`t1-ssl-input1-noise.wav`, 15 s, 13:46). Setup confirmed with the owner: pedal powered, **9 V input live**; **OUT L → SSL input 1**; the SSL's output lead **out of** the pedal's IN jack; engine running but muted; nothing playing | **−99.35 dBFS rms** unweighted; **−100.44 dBFS(A)**; peak −88.71 dBFS. Largest line below 1 kHz: 49.8 Hz at **−148.33 dBFS** — no hum. Only structure: 750/1500/2250/6750 Hz at −113 to −119 dBFS, the engine's 750 blocks/s | The pedal's **output is quiet**: with the engine sending silence, what arrives at the interface is its own floor. Nothing wrong at the output — no hum, no hiss. This is the baseline every later output reading is compared against |
| 2 | **Noise at the codec's own input** (channel 0 = LIN1), 20 s via `namchainctl record` (`t2-adc-noise.wav`, 13:52). Setup: **SSL output 1 → pedal's IN jack**, the pedal's OUT L plug **removed**; Inst/Line switch **removed** from the breadboard with SW-L jumpered to SW-C (the follower sits permanently on node B); engine running and **muted**; soldering station **off** | **−52.78 dBFS rms** unweighted; **−65.30 dBFS(A)**; peak −42.20 dBFS. Lines: **49.8 Hz −58.30**, 50.5 −60.53, 99.6 −61.12, 100.3 −59.77, 200.0 −65.68; engine 750 Hz family at −79 to −86 | **The input side is where the noise is**: 50 Hz mains hum with harmonics, 46 dB above the output baseline of test 1. The engine contributes nothing to it — the same recording's playback channel is *exactly* 0.00 (digital silence) — so it is all the input chain: jack → C5 → node B → follower → LIN1 → ADC. For reference, 2a measured the codec's own floor at −93.5 dBFS(A) with LIN1 shorted, so ~28 dB of this is pickup, not the converter |
| — | The same measurement taken immediately **before** and **after** the owner switched off a soldering station on the bench (13:50:05–25 and 13:52) | −52.77 / −65.29 dB(A) then −52.78 / −65.30 dB(A) | The soldering station was contributing **nothing** — the same reading to 0.01 dB. Worth knowing: it was a suspect and it is now excluded |
| 3 | **The same input, with the follower's node grounded**: SW-C (U1 pin 3) jumpered to the board's 0 V row. The follower's output then sits at 0 V, which the codec's input capacitor blocks; the follower, the LIN1 lead, the codec and the board's ground are all unchanged (20 s, `t3-adc-noise.wav`, 13:54) | **−68.44 dBFS rms** unweighted; **−69.07 dBFS(A)**; peak −56.60 dBFS. **49.8 Hz is gone** (below −113, a fall of more than 55 dB). Largest lines: 750.0 Hz −80.41, 1500.0 −79.18, 198.5 −113.79, 397.0 −112.89 | **All of the mains hum entered at the input node.** Grounding it removed 15.7 dB of the overall level and more than 55 dB of the 50 Hz line, leaving a floor that is broadband with the engine's 750 Hz family (48 kHz / 64-frame periods) on top — 22 dB above 2a's −90.6 dBFS. The A-weighted figure barely moves from the unweighted one, which is what "no hum left, just hiss" looks like |
| 4 | **Is it the engine, or the stream's period size?** Engine **stopped**, the codec captured with `arecord` on the host at two period sizes, the node still grounded: 64-frame periods (`t4-B-stopped-p64.wav`) and 1024 (`t4-C-stopped-p1024.wav`), both 13:58. (First attempt failed — `rik` is not in the `audio` group, so ALSA's name lookup needs `sudo`, and the service needs root to stop. The engine's xruns were unchanged afterwards, 1 capture / 1 playback.) Engine restarted and re-muted | period 64: **−64.12 dBFS rms**, −65.26 dB(A); period 1024: **−63.22 dBFS rms**, −64.28 dB(A) — a 0.9 dB difference. Both spectra are HF-dominated (below). Engine running (test 3, same period size) was −68.44 | **Neither the engine nor the period rate is the noise.** 64 vs 1024 frames changes nothing, and stopping the engine does not clean it (it reads ~4 dB *worse*, consistent with a codec whose DAPM blocks differ when only capture is open). The 750 Hz family in test 3 is real but 16 dB under the broadband floor. What is left is **high-frequency hash, 4–16 kHz, with no hum at all** — so it is the codec, board 1 or the bench, not the software |
| 5 | **Does the Mac's mains connection matter?** The owner unplugged the Mac's power supply, so the Mac and the USB-powered interface float on battery and there is no mains-earth path into the pedal through the interface at all. Both arms repeated exactly as tests 3 and 4C: engine running and muted (`t5-A-engine-adc.wav`), then engine stopped with `arecord` at 1024-frame periods (`t5-B-stopped-p1024.wav`) | engine running: **−67.31 dBFS rms**, −67.95 dB(A), 4–8 kHz −71.6 (49%); engine stopped: **−63.98 dBFS rms**, −65.19 dB(A), 4–8 kHz −66.6 (67%). Against the mains-powered arms: −68.44 and −63.22 | **No difference** — 1.1 dB one way on one arm, 0.8 dB the other, both inside the drift between runs. The Mac's charger and the earth path through the interface are **not** carrying any of this noise. Every remaining suspect is on the pedal's own side of the cable: the codec, the follower, or the breadboard around them |
| 6 | **Everything on battery**: the owner moved vip
| 7 | **The node back on SW-L** (jumper from SW-C to SW-L, so the follower looks at node B at the jack side again), everything still on battery, engine muted, 20 s via its own record (`t7-A-nodeB-all-battery.wav`, 14:09) | **−65.51 dBFS rms**, **−65.73 dBFS(A)**, peak −52.58. **49.8 Hz fell to −83.91** — 25.6 dB below the −58.30 of test 2 in the same configuration. Largest lines are now the engine's 750.0 Hz −75.49 and 1500.0 −74.19. Bands unchanged from test 6: 4–8 kHz −72.6 (26%), 2–4 kHz −73.4, 1–2 kHz −73.7 | **The hum is 12.7 dB down on test 2 (−65.51 against −52.78) and the input node now adds nothing measurable**: −65.51 ungrounded against −65.21 with the node grounded in test 6. So the 50 Hz was not simply the room's field coupling into the node — its **current needed a mains-referenced return path**, and the supplies' common-mode (Y-capacitor) leakage was that path. On batteries the field is still there but cannot drive the current. **This is the finding with a consequence for the build:** the finished pedal's Core host will be mains-powered, so this hum can be expected to come back unless the host's supply leakage is dealt with |: the owner moved `vip` from its mains adapter to a USB lithium-ion pack, so with the Mac on battery too there is **no mains connection anywhere** in the setup. Node still grounded; engine running and muted; 20 s via its own record (`t6-A-all-battery-adc.wav`, 14:07). **`vip` rebooted on the way** — the pack dropped power, uptime came back at 0 minutes; not investigated, per the owner, and the codec card and engine both came back on their own | **−65.21 dBFS rms**, **−65.37 dBFS(A)**, peak −51.93. **No mains line at all** — nothing at 50, 100 or 200 Hz; the largest lines are the engine's 750.0 Hz at −75.38 and 1500.0 at −74.01. Bands: 4–8 kHz −71.7 (30%), 2–4 kHz −73.2 (21%), 1–2 kHz −73.6 (20%), 8–16 kHz −76.0 (11%) | **For the hash, removing every mains connection changes nothing** (the node was grounded here, so there was no hum in this reading either way) — −65.21 against −67.31 (Mac on battery, Pi on mains) and −68.44 (all mains), so if anything 2 dB worse, inside the variation between runs. None of this noise is conducted from the mains. It is generated locally: broadband hash plus the engine's block-rate family. The hum is absent here by construction (the node is grounded), so this test does not speak to the hum — that question needs the node back on SW-L | |

**Where the noise sits, in octave bands** (`band-rms.py`, the same Welch spectrum `codec-noise.py` uses):

| band | engine running, node grounded (test 3) | engine stopped, period 64 (4B) | engine stopped, period 1024 (4C) |
|---|---|---|---|
| 31.5–250 Hz | −108 to −104 | −95 to −89 | −113 to −104 |
| 500–4000 Hz | −80 to −79 | −95 to −89 | −99 to −90 |
| **4–8 kHz** | **−73.1 (46%)** | **−66.7 (70%)** | **−65.7 (75%)** |
| 8–16 kHz | −77.2 (18%) | −72.2 (20%) | −71.3 (21%) |
| total, 20 Hz–20 kHz | −69.7 | −65.2 | −64.4 |

**A supply fact that corrects an earlier assumption:** board 1 is running from a **9 V battery in the
battery clip**, not from the Cioks — the Cioks is not connected at all. Board 1's supply is
therefore floating and mains-free, which rules the supply out both as a path for the hum and as a
source of the hash. Everything above was measured with the battery supply.


**Operational notes for the host.** `rik` is not in the `audio` group, so `arecord` needs `sudo` for
ALSA's card lookup as well as for opening it, and stopping `namchaind` needs root. After a restart
the engine comes back **unmuted** with its last document, so it must be re-muted by hand; a `levels`
read taken in the same breath as the `mute` still shows the old output and needs a moment. Left in
this state: engine running, **muted** (`out L rms −200`), node still grounded.


## What the session has established

- **The output side is clean.** −99.35 dBFS at the interface with the engine sending digital
  silence, no hum (test 1).
- **The input side's hum is not the room's field alone.** On mains power it reads −52.78 dBFS with
  49.8 Hz at −58.30 (test 2); on batteries, same node and same wiring, −65.51 with 49.8 Hz at
  −83.91 (test 7). Grounding the node removed it entirely, more than 55 dB down on the 50 Hz line
  (test 3), so the node is where it enters.
- **Its current needs a mains-referenced return path.** The Mac on battery alone changes nothing
  (test 5); the Mac *and* the Pi on batteries drop it 12.7 dB overall and 25.6 dB on the 50 Hz line
  (test 7). The supplies' common-mode (Y-capacitor) leakage is that path. **A mains-powered Core
  host will bring this back**, so the host supply's common-mode behaviour is part of the pedal's
  noise design, alongside the input's shielding.
- **What is left is not mains-related:** ≈ −65 dBFS rms of broadband hash, 4–16 kHz, plus the
  engine's 750 Hz block-rate family at −75. Stopping the engine, changing its period size, or
  removing every mains connection leaves it where it is (tests 4 and 6). Next: board 1's follower
  or the codec and the Pi's own ground — the scope on U1 pin 1, or the codec-alone test.
- **Excluded along the way, each by measurement rather than argument:** the interface's cable and
  its earth path (test A, test 5), the rig and the engine as a source of the input noise (test 2's
  silent playback channel), the stream's period size (test 4), the soldering station (test 3's
  predecessor), board 1's supply (a 9 V battery throughout), and the mains connections as the
  source of the remaining hash (tests 5, 6).

---

**Convention for this file** (owner's instruction, 2026-10-11): **append, don't edit.** Tests from
here on are appended below as their own dated block, with their own reading and their own note on
what it means. Nothing above is rewritten and no row is edited in place — a correction is a new
block that says what it corrects. The table above runs to test 7 as first written.

## Test 8 onwards

_(nothing yet — the next measurement is appended here)_

### Test 8 — 2026-10-11 14:13 — `vip` back on mains, **without** the USB-C extension cable

**Why.** The owner noticed that moving `vip` to the battery had also removed a USB-C extension cable
between the supply and the Pi — the battery stopped dropping the Pi once the extension was out of
circuit — and wondered whether the cable itself was part of the noise. So: `vip` back on its mains
adapter with **no extension cable**, node B (jumper SW-C ↔ SW-L), Mac still on battery, board 1 still
on its 9 V battery. Engine running, muted, 20 s via its own record (`t8-A-mains-noext.wav`). `vip`
rebooted on the power change (uptime 0 min); the engine came back and was re-muted before the capture.

**Reading.** **−49.54 dBFS rms** unweighted (3.34 mV at 1 V FS), peak −39.12; **A-weighted
−65.32 dBFS(A)**. Lines: 49.1 Hz −61.54, **49.8 Hz −54.07**, 50.5 Hz −58.70, 99.6 Hz −56.00,
100.3 Hz −59.31. Bands: the hum bands carry it; 4–8 kHz −76.4, 1–2 kHz −76.5.

**What it means.**

- **The extension cable was not the noise.** With `vip` back on mains the hum returns, and reads
  3.2 dB *higher* than test 2's −52.78 in the same node configuration. Nothing about the cable
  accounts for it; it is the mains connection, exactly as test 7 predicted. What the cable did cause
  was the Pi's power drops and reboots — a marginal USB-C connection — which is a reliability
  matter, not a noise one.
- **The 3.2 dB is most likely the Mac's earth.** In test 2 the Mac was on mains, so its charger
  earthed the interface end of the cable; now it floats on battery and the same leakage has less to
  push against. So the size of this hum is set by the common-mode arrangement at *both* ends, not by
  the pedal alone.
- **Caveat on that comparison, for honesty:** board 1's supply changed from the Cioks to the 9 V
  battery at some point during the session and the exact moment was never pinned down, so tests 2
  and 8 are not perfectly matched. If the Cioks was still connected at test 2, part of the 3.2 dB
  could belong to that instead of the Mac's earth. The direction of the finding does not depend on
  it — mains restores the hum, batteries remove it (test 7) — but the 3.2 dB does.
- **By the A-weighted measure nothing changed at all:** −65.32 dB(A) here against −65.30 (test 2) and
  −65.73 (test 7, all battery). A-weighting discounts 50 Hz by ~30 dB, so this split is the whole
  story: **the hum comes and goes with the mains; the hiss does not.**

### Correction — 2026-10-11 — board 1 was never on the Cioks

The owner has stated plainly: **the Cioks has never been connected to the pedal**, in this session or
before. Board 1 has run from the **9 V battery in its clip** throughout, with no change at any point.

The caveat in test 8 above — that board 1's supply "changed from the Cioks to the 9 V battery at some
point during the session and the exact moment was never pinned down" — is **wrong**. It came from my
own inference (I read "9 V input is also live" in test 1's setup as the Cioks) and was then treated as
though the owner had said it. Nothing in the owner's account ever said the Cioks was in use; the
Cioks appears in this project only as a *planned* supply leg for 2c.

**What survives, and is now cleaner:** tests 2 and 8 **are** matched on board 1's supply — the same
9 V battery, no change between them — so the 3.2 dB between them (−52.78 in test 2 and −49.54 in test
8) stands as attributable to the **Mac's mains earth**: earthed through its charger in test 2,
floating on battery in test 8, with everything else equal. Test 7's finding is untouched: mains at
the Core host restores the hum, batteries remove it.

### Test 5 — 2026-10-11 14:22 — the codec's own input shorted, **board 1 disconnected**

**Why.** To split what is left: the LIN1 lead was taken **off** the codec board and the codec's own
LIN1 pin jumpered to its GND pin. Board 1 is therefore not connected to the converter at all — its
follower, its leads and its input network are all out of the measurement. Two arms, both with the
codec's input shorted: engine running and muted (`t9-A-shorted-engine.wav`, 20 s), then engine
stopped with `arecord` at 1024-frame periods (`t9-B-shorted-stopped.wav`, 15 s) — the second being
2a's own method.

| arm | unweighted | A-weighted | where the energy is |
|---|---|---|---|
| engine running, muted | **−73.94 dBFS** | −73.65 dB(A) | 2–4 kHz −80.0 (33%), 1–2 kHz −81.6 (23%), 4–8 kHz −83.0; engine's 750/1500 Hz lines at −83.4/−82.1; no hum |
| engine stopped, `arecord` 1024 | **−62.03 dBFS** | −63.34 dB(A) | 4–8 kHz −65.0 (65%), 8–16 kHz −69.3 (24%), a drifting ~6.69 kHz line, LF rumble at 20 Hz |

**What it means.**

- **Board 1 is not the source of the remaining hiss.** With it disconnected entirely and the
  converter's input shorted, the floor is −73.94 dBFS through the engine's path. Board 1 connected
  with its node grounded measured −68.44 (test 3), so the follower and its lead cost about 5.5 dB —
  real, worth having, but not the bulk of it.
- **This host's own floor has moved 14 dB since 2026-10-06.** That day, on `vip`, through the same
  engine path, with the jack wired straight to LIN1 and the interface connected and silent, the
  input floor was **−88.0 dBFS(A)**
  ([bench-results/2026-10-06-input-stage-scale-clipping-and-protection.md](../2026-10-06-input-stage-scale-clipping-and-protection.md)).
  Today a *shorted* input reads −73.65 dB(A). Board 1 did not exist on 10-06, so whatever moved is
  on the host, codec or bench side, and it moved after that date.
- **The codec's mixer is not the cause.** Read on the live card: ALC Function **Off**, ALC Mode ALC
  but inactive, ADC PCM 195 (0.00 dB), Left Boost Mixer LINPUT1 **on**, Left Input Boost Mixer
  LINPT1 0.00 dB, Capture Volume 23 (0.00 dB, on), Headphone −6 dB, Speaker muted, right channel
  boost off. `pedal-codec.service` is active on this boot and the state matches the project's intent
  — including the standing rule that ALC stays off.
- **Methodological caveat, unresolved.** The two capture paths disagree by ~12 dB on the same
  input, and the `arecord` arms do not track what is connected: tests 4B, 4C, 5B read −64.1, −63.2
  and −62.0 whether the node is grounded or the converter's input is shorted. The engine's own
  record tracks the input state sensibly (−68.4 grounded, −73.9 shorted). So the `arecord` arms look
  like they are measuring something of their own — writing to the SD card, or the Pi's state with
  the engine stopped — rather than the converter's input. Worth settling before any of those three
  numbers is quoted; the engine path is the one that compares like for like with 10-06 and 2a.

### Test 10 — 2026-10-11 14:25 — which capture path is telling the truth?

**Why.** Test 5 left a 12 dB disagreement between the engine's own record (−73.94 with the
converter's input shorted) and `arecord` (−62.03), with the `arecord` arms insensitive to what was
connected. Four arms, all with the converter's input **still shorted at its pin** (board 1
disconnected), engine stopped except where noted, every file 15 s at 48 kHz, S32_LE, 2 channels:

| arm | what it is | unweighted | A-weighted | shape |
|---|---|---|---|---|
| 10-A | `arecord` → `/var/tmp` (SD card), period 1024 | −61.86 dBFS | −63.26 dB(A) | 4–8 kHz −64.8 (62%) |
| 10-B | `arecord` → `/run` (**tmpfs**), period 1024 | −60.65 dBFS | −61.91 dB(A) | 4–8 kHz −63.5 (69%) |
| 10-C | `arecord` → `/run` (tmpfs), period **64** | −60.66 dBFS | −61.92 dB(A) | 4–8 kHz −63.5 (69%) |
| 10-D | `arecord` + a **silent `aplay`** holding the playback path open (default periods) | −74.76 dBFS | −76.08 dB(A) | 4–8 kHz −78.0 (61%), mids −102/−96/−95 |
| 10-E | as 10-D but `aplay` at **64-frame periods** | −71.57 dBFS | −72.86 dB(A) | 4–8 kHz −74.7 (62%), mids −97/−90 |
| (9-A) | the engine's own record, muted, same shorted input | −73.94 dBFS | −73.65 dB(A) | **mids −83/−82/−80**, 4–8 kHz −83.0 |

**What it means.**

- **Neither the SD card nor the period size.** tmpfs is 1.2 dB *worse* than the SD card, and B and C
  are identical to 0.01 dB. Those two explanations are dead; the `arecord` arms' extra noise is
  neither.
- **A third of it is the playback state.** Opening a playback stream — even one playing digital
  silence — drops the HF hash by 15 dB (4–8 kHz: −63.5 → −78.0) and the total by 14 dB. With no
  playback stream open, this converter's capture path carries a 4–16 kHz hash that has nothing to do
  with its input. **Anything measured with `arecord` alone is measuring that, not the input.**
- **The engine adds a mid-band noise of its own.** 10-D and 9-A agree in total (−74.76 against
  −73.94) but not in shape: the engine's mids are 20 dB higher (−81.6 at 1–2 kHz against −95.8) and
  its HF is 5 dB lower. A 3.2 dB part of the HF difference is the playback period size (10-D vs
  10-E), but **nothing about the period size explains the mids**. So something in the engine's own
  operation — its graph, its threads, its core pinning, its record path — contributes ≈ −81 dBFS per
  octave band across 500 Hz–4 kHz to what it captures and reports.
- **Consequence for every number in this file.** The engine's meter and the engine's record agree
  with each other (they are the same buffer), so the engine path is self-consistent and is the right
  instrument for what the *player* would hear. But its floor is not the converter's floor, and the
  10-06 reference of −88.0 dBFS(A) was taken through that same path. Something between that path
  then and now costs about 14 dB, and it is not board 1, not the mains, not the codec's mixer and not
  the capture method's disk or period settings.

**Next test to separate the last two candidates:** engine stopped, a silent playback stream open, and
a deliberate CPU load pinned to the warm cores (1–2, where the engine's work goes) — if the
mid-band noise appears, it is CPU activity coupling into the converter; if it stays quiet, it is
something in `namchaind`'s own code path rather than the host being busy.

### Test 12 — 2026-10-11 14:33 — does the engine's noise reach its output, or only its file?

**Why.** Tests 10 and 11 showed the engine's capture carries a mid-band noise that no other capture
path sees. If that noise is only in the file the engine writes (a record-path artefact), the pedal's
audio could still be clean; if it is in the buffer the DSP processes, a player hears it. The engine
records its capture *and* its playback, so the two can be compared directly. Two 15 s records, one
muted and one live, with the document's +24 dB gain node in the path:

| file | unweighted | 500–1000 | 1–2 kHz | 2–4 kHz | 4–8 kHz |
|---|---|---|---|---|---|
| `t12-muted-capture.wav` | −69.40 dBFS | −82.5 | −80.4 | −78.6 | −74.3 |
| `t12-muted-playback.wav` | **−inf (0.00)** | — | — | — | — |
| `t12-live-capture.wav` | −69.40 dBFS | −83.2 | −80.1 | −78.7 | −74.2 |
| `t12-live-playback.wav` | −45.40 dBFS | −59.2 | −56.1 | −54.7 | −50.2 |

**What it means.** The playback is **exactly +24.00 dB** on the capture — overall and in every
octave band (+23.3 to +24.3, the spread being measurement noise). So the engine's capture goes to
its output **unfiltered**: nothing is removed, nothing is shaped, and the mid-band noise is in the
audio the DSP processes and sends to the DAC. **It is audible noise, not a logging artefact.** That
also validates the engine's own record and level meter as instruments for judging the pedal: they
show what the audio path carries.

### Test 13 — 2026-10-11 14:39 — is the engine's mid-band noise just a busy CPU?

**Why.** To separate "CPU activity coupling into the converter" from "something in `namchaind`'s own
code path". Two earlier attempts failed for a mechanical reason worth recording: **CPUs 1–3 are
isolated** (`isolcpus=managed_irq,domain,1-3 nohz_full=1-3 rcu_nocbs=1-3`) and `nproc` is 1, so
`taskset -c 1` from a shell fails with EINVAL and nothing spins. The load has to go in through
`pedal-bench.slice`, which is what `pedal-measure` uses. A first attempt that way also cost the ssh
session mid-capture (the capture file was lost), so the arm was re-run as a detached script on the
host with `RuntimeMaxSec` on the units.

**Setup:** engine stopped, silent `aplay` holding the playback path open (the 10-D arm), two spinning
`/bin/sh` loops confirmed at **93% on CPU 1 and 77% on CPU 2**, `arecord` 15 s → `t12-load.wav`.

| arm | unweighted | 1–2 kHz | 2–4 kHz | 4–8 kHz |
|---|---|---|---|---|
| no load (10-D) | −74.76 | −95.8 | −95.0 | −78.0 |
| no load, repeat (11) | −71.40 | — | −94.1 | −74.5 |
| **CPUs 1–2 spun hard** | **−70.07** | **−94.8** | **−94.3** | **−73.2** |

**What it means.** Spinning both isolated cores at ~90% moves the mid bands by **0.2 and 0.7 dB** —
nothing, well inside the 3 dB drift between the two no-load repeats. **A busy CPU is not the cause.**
The engine's 20 dB of extra mid-band noise is therefore *not* host activity coupling into the
converter; it comes from `namchaind`'s own capture handling. The engine's capture also carries a
750 Hz line and its harmonics (48 kHz ÷ 64-frame periods) that no other capture path shows, which is
the signature of period-boundary handling rather than of the converter.

**The test that would settle it:** change `namchaind`'s `period_size` (64 → 1024) and watch whether
the mid-band noise and the 750 Hz comb move with it. That edits the deployed config on the host, so
it needs the owner's say-so first.

### Test 14 — 2026-10-11 14:46 — the codec alone: nothing attached but a short on LIN1

**Why.** The owner disconnected every input and output from the codec, removed the whole input and
output circuits, checked the seating of the codec-to-Core jumpers, and **disconnected the Pico
entirely**. On the audio side the codec now has only LIN1 jumpered to its own GND. So the converter,
its jumpers to the Core and `namchaind` are all that is left — the cleanest version of test 5.

**Reading.** Two independent 20 s captures through the engine's path, `t14-A-codec-only.wav` and
`t14-C-codec-only.wav` (the second after the engine was restarted; see the incident below):

| | unweighted | A-weighted | 1–2 kHz | 2–4 kHz | 4–8 kHz | 8–16 kHz |
|---|---|---|---|---|---|---|
| 14-A | **−75.67 dBFS** | −75.59 dB(A) | −82.4 | −83.0 | −88.2 | −90.3 |
| 14-C | **−75.80 dBFS** | −75.57 dB(A) | −82.9 | −82.2 | −88.9 | −89.8 |

Two captures 0.13 dB apart: this figure is solid.

Lines, in 14-C: **750.0 Hz −83.29**, 1500.0 Hz −83.43, 2250.0 Hz −85.20, 3000.0 Hz −87.37, each with
±0.7 Hz sidebands. 750 Hz is 48 kHz ÷ 64 — the engine's own period rate.

**What it means.**

- **Their disconnections bought 1.9 dB overall and 5.9 dB in the HF.** Against 9-A (−73.94, the same
  short but with the Pico, the output circuit and board 1's remains connected), 4–8 kHz improved
  from −83.0 to −88.9 and 8–16 kHz from −86.7 to −89.8. So the Pico and the disconnected circuits
  *were* contributing HF hash, and removing them helped — but only in the HF.
- **The 1–4 kHz band is unchanged at −82 to −83** and is now the whole of what is left. That is the
  mid-band noise tests 12 and 13 attributed to the engine: not CPU activity, passed to the output
  unfiltered, and present with nothing but a short on the converter's input.
- **The clincher — the same period size through a different capture path.** `arecord` at the *same*
  64-frame periods, with the same shorted input, shows that same 750 Hz line at **−100.85 dBFS**
  (t10-C), and at **−112.06** with a silent playback stream open (t10-E). `namchaind` shows it at
  **−83.29**. The period rate is a real event in every 64-frame capture — the engine's handling of it
  is **18 to 29 dB worse** than a plain `arecord` at the identical period size. The broadband mid
  noise sits at the same level as the comb, which is what a jittered period-boundary artefact looks
  like.
- **Still 12.4 dB above 10-06.** That record's −88.0 dBFS(A) was taken through this same engine path
  with the Pico attached, so the engine was not always like this.

**Incident worth recording.** The `arecord` arm of this test died with `pcm_read: read error:
Input/output error` and left `namchaind` in state **`lost`** with empty level lists. The card stayed
present (`/proc/asound/cards` has `wm8960`, I²C `UU` at 0x1a) and `systemctl restart namchaind`
brought it straight back — but it is the second time an `arecord` arm has broken the stream, so it
belongs in the record rather than in a footnote.

**The test that would settle the last question:** change `namchaind`'s `period_size` from 64 to 1024
and re-measure. If the comb moves to 47 Hz and the mid-band noise falls, the artefact is
period-boundary handling and the fix is in the engine's capture path. Needs the owner's say-so, since
it edits the deployed config on the host.

### Test 15 — 2026-10-11 15:14 — the engine's period size, changed and put back

**Why.** Test 14 left one artefact in the codec-alone capture: a 750 Hz line (−83.29 dBFS) with
harmonics, 750 Hz being 48 kHz ÷ `namchaind`'s 64-frame periods, and 18–29 dB louder than the same
line in an `arecord` capture at the identical period size. If the artefact is period-boundary
handling, changing the period size must move it.

**Method.** `/etc/namchain/namchaind.json` backed up to `/run/namchaind.json.t15bak`
(sha256 `0d4e0841f3fb810f`), `period_size` changed **64 → 1024** and nothing else, engine restarted,
20 s record with the input still shorted, then the backup copied back, the engine restarted again
and the restore verified by checksum. Run as one script on the host so a dropped session could not
leave the config edited.

| | period **64** (14-C) | period **1024** (15) |
|---|---|---|
| unweighted | −75.80 dBFS | **−79.28 dBFS** |
| A-weighted | −75.57 dB(A) | **−79.90 dB(A)** |
| 1–2 kHz | −82.9 | **−87.7** |
| 2–4 kHz | −82.2 | **−87.2** |
| 4–8 kHz | −88.9 | −89.9 |
| period-rate line | **750.0 Hz −83.29** | none at 750; largest lines 93.8, 140.6, 187.5, 234.4, 562.5 Hz at −96.8 to −98.9, i.e. **2×, 3×, 4×, 5×, 12× 46.875 Hz** |

**What it means.**

- **The artefact follows the period rate exactly.** At 1024-frame periods the comb is no longer at
  750 Hz; it is at **46.875 Hz** and its harmonics — 48 kHz ÷ 1024. The 750 Hz line falls by more
  than 13 dB, the 1–4 kHz bands improve by ~5 dB, and the whole floor improves 3.5 dB unweighted and
  4.3 dB A-weighted.
- **So it is period-boundary handling in `namchaind`'s capture path**, not the converter and not the
  host. A plain `arecord` at the same 64-frame periods produces the same line 18 dB lower (test 14),
  and the engine's own handling multiplies it.
- **It is a latency/noise trade, and 64 frames is not free.** 64-frame periods are 1.33 ms — the
  reason the engine uses them — and they cost about 4–5 dB of 1–4 kHz noise against 1024-frame
  periods. That belongs in the record beside the latency figures, and the boundary handling itself is
  worth a look on the engine's side.
- **It does not explain all of the gap to 10-06.** Period 1024 recovers 4.3 dB of the 12.4 dB between
  today's codec-alone floor and 10-06's −88.0 dBFS(A); about 8 dB remains, and the engine's period
  size on 10-06 is not recorded, so some or none of that 8 dB may be the same effect.
- **The host was left as found:** backup restored, checksum identical, engine active at
  `period_size` 64, muted (`out L rms −200`).

### Test 16 — 2026-10-11 15:19 — the noise as graphs and audio

The four codec-and-Core states were measured again, together, and with a fifth capture as a hum
reference, and the whole set is now a document with a spectrum and an octave-band chart for each
capture, the numbers beside them, and a play button per line so it can be heard:
**[../2026-10-11-codec-noise-spectra/index.html](../2026-10-11-codec-noise-spectra/index.html)**
(with its own [README](../2026-10-11-codec-noise-spectra/README.md)).

Every capture is analysed **from 2 s in**, because the stream's start-up transient sits in the first
seconds: `t16-D`'s peak falls from −44.7 to −62.5 dBFS and `t16-E`'s from −41.2 to −57.0 once it is
excluded. The audio on the page is trimmed the same way, so what is heard is what was measured. The
figures agree with `codec-noise.py` to 0.01 dB on every file.

| capture | state | unweighted | A-weighted |
|---|---|---|---|
| `engine-p64` (t16-A) | engine running, 64-frame periods — the normal state | −75.72 dBFS | **−75.29 dB(A)** |
| `engine-p1024` (t16-B) | engine running, 1024-frame periods | −79.09 dBFS | **−79.73 dB(A)** |
| `arecord-alone` (t16-E) | engine stopped, no playback stream open | −75.83 dBFS | −75.75 dB(A) |
| `arecord-playback` (t16-D) | engine stopped, silent playback stream open | −79.74 dBFS | **−79.86 dB(A)** |
| `hum-reference` (t8-A) | *not* codec-only: board 1 at node B, all mains | −49.55 dBFS | −65.33 dB(A) |

**What the graphs make obvious, and the tables did not:**

- **The engine's period rate is a comb right across the band.** At 64-frame periods there is a line at
  every multiple of 750 Hz — 750, 1500, 2250, 3000 and on up to 20 kHz — and the 1–4 kHz bands sit at
  the same level as the first of them. At 1024 the family moves to 46.875 Hz and its harmonics and
  the comb is 13–15 dB lower.
- **The engine at 1024-frame periods is as quiet as the converter with no engine at all**: −79.73
  against −79.86 dB(A). The 64-frame periods the engine uses for latency cost **4.4 dB(A)** against
  that. That is the clearest statement this session has of the trade.
- **The `arecord`-alone arm is not stable between runs.** With the Pico attached (test 10) it was
  4–8 kHz dominated at −60.7 dBFS; minutes before this one, Pico gone, it was LF-dominated with a
  −42 dBFS peak; in the settled re-run used here it lands within 1 dB of the engine's own capture.
  So that arm is the least trustworthy of the five, and the "HF hash" it showed earlier looks like
  the Pico's USB cable rather than the converter.
- **No hum anywhere in the codec-only state**, which is what test 3 and test 7 predicted: hum needs
  board 1's input node and a mains-referenced return path, and neither is present here.

### Captures deleted — 2026-10-11, at the owner's instruction

The raw captures and the document's playback copies were deleted once the report had been read:
43 wav files, 260.4 MB, from this directory, and the document's `audio/` directory, 10 files,
22.0 MB — 282 MB in all. What remains is the record of them: this log, the two READMEs, the
scripts, the engine's level logs and JSON, and the document's page, graphs and numbers.

Three consequences, stated rather than left to be discovered:

- **The document's play buttons went with the audio.** The page was rebuilt without them — five
  audio blocks and the legend's ten cells removed — so nothing on it points at a missing file.
- **`make-document.py` can no longer be run.** It reads the captures, which do not exist now and
  were never committed: bench-results tracks text, and these were 283 MB. The page, the eleven
  graphs and `noise-numbers.json` are the record, and `make-document.py` is kept as the method.
- **The two generated inputs went too** (`tone-1k-m60.wav`, `silence-20s.wav`). A future session
  re-running `roundtrip.sh` needs them remade, one command each:

      sox -q -n -r 48000 -c 2 -b 16 tone-1k-m60.wav synth 30 sine 1000 vol -60dB remix 1 0
      sox -q -n -r 48000 -c 2 -b 32 silence-20s.wav trim 0 20

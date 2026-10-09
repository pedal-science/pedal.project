# The audio DMA interrupt thread (`irq/N-dw_axi_dmac_platform`)

Written 2026-10-03, from a question while watching `top` on vip: with `namchaind` running,
the top CPU user is `irq/138-dw_axi_dmac_platform` at ~5% CPU and "niced to -86". This page
explains what that process is, why it costs what it costs, and why it is prioritized the way
it is. The facts are measured, not inferred; the commands to re-measure them are at the end.

## What it is

The pedal's audio path on the Core host is: `namchaind` → ALSA (`snd-soc-simple-card`) →
`designware_i2s` (the RP1's I2S controller) → the WM8960 codec. The RP1's **DesignWare AXI
DMA controller** (`dw-axi-dmac`) is what actually moves the audio between RAM and the I2S
FIFO, and `irq/138-dw_axi_dmac_platform` is the **threaded handler for that controller's
interrupt** (threaded because the pedal runs PREEMPT_RT, where interrupts are force-threaded).
It is the audio engine's data mover made visible in the process list — one interrupt line,
shared by both directions of the stream.

## The measured numbers (vip, 2026-10-03, `namchaind` running)

- Both streams are open: playback `pcm0p` and capture `pcm0c` are `RUNNING`
  (`/proc/asound/card0/pcm0{p,c}/sub0/status`).
- Interrupt rate: `/proc/interrupts` advanced by **15,016 in 5 s ≈ 3,000 IRQs/s** on line 138.
  That is exactly duplex at the pedal's chosen period: 48 kHz ÷ 32 frames = 1,500 periods/s
  per direction, × 2 directions = 3,000/s.
- Cost: ~4–5% of one core ≈ 40–50 ms/s over 3,000 interrupts ≈ **13–15 µs per interrupt** —
  the threaded handler, descriptor bookkeeping, `snd_pcm_period_elapsed`, and waking
  namchaind's render thread. Tiny per interrupt; it is the *volume* that adds up.
- The thread was on a **housekeeping core** (PSR 1; `irqaffinity=0-1`) when this was measured,
  never on the render core, so it costs housekeeping capacity, not render headroom. What the tree
  *asked* for at the time was core 2 (`AUDIO_IRQ_CPU="2"` in `tune.conf`), which is not where the
  sample caught the thread running; **P7 pinned the delivery to core 0**, a housekeeping core, so
  the request and the intent agree (below).

## Why the priority (the "-86" in `top`)

`top`'s "niced to -86" is its way of showing a realtime priority: the thread runs **SCHED_FIFO
at priority 85** (top's PR column shows 125 = 85 + 40). This is deliberate:
`pedal-tune` (pedal.project, `devices/common/rootfs/usr/local/sbin/pedal-tune`) sets
`AUDIO_IRQ_PRIO=85`, **above namchaind's render thread at priority 80**
(`devices/vip/rootfs/etc/namchain/namchaind.json`, `rt_priority`). The interrupt must always
preempt the renderer: it is what tells the engine a buffer needs refilling, and delaying it is
exactly what produces xruns. The audio DMA interrupt is the highest-priority realtime thing
on the box, by design.

## Which core it lands on (2026-10-09; P7's core 0 reversed)

It must not land on the **active** render core. The interrupt preempts whatever it lands on, and the
active render thread being preempted is a missed deadline; on an *inactive* render core the only
thing it can preempt is a warm rig, which falls a block behind and catches up. That is the rule now —
all but one core renders, so the interrupt's home is a render core, and the one it must not touch is
the one playing what the player hears. The tree pins its delivery to **core 1**:
`AUDIO_IRQ_CPU="1"` in `devices/vip/rootfs/etc/pedal/tune.conf`, and `pedal-tune check` asserts that
the core is *inside* `ISOLATED_CPUS` and *not* `RT_CPUS`. Every interrupt that is not the audio one
goes to the single housekeeping core (`irqaffinity=0` in `rtpi/devices/vip/device.env`).

P7 pinned the same interrupt to core 0 on the reading that no render core may carry it, and **T6
then measured both placements**: 7.4 ns of wait-to-run per wake on a render core against 7.7 ns on
the housekeeping core (2026-10-08), and 16.8 against 17.0 ns on 2026-10-09 with identical render
distributions and zero xruns in either arm. So this decision does not rest on the interrupt's
latency, which does not care; it rests on where the preemption lands, which T6 does not measure and
P6's warm set does — 0 to 1 block of lag and no dropped blocks with a warm rig beside it.

Only the interrupt's **delivery** can be pinned. Its handler thread carries `0-3` on this kernel
(`PF_NO_SETAFFINITY`, and it does not follow the IRQ's affinity here), so `isolcpus=domain`, not the
mask, is what keeps it off the other render cores; `pedal-tune check` reports the core it is on and
fails if it is ever the active one.

## The tradeoff this represents

The period is what sets the interrupt rate, and the pedal runs a **64-frame** period
(`period_size` in `devices/vip/rootfs/etc/namchain/namchaind.json`), so the figures below are the
2.5% row, not the 5% one — the 32-frame rates are what was measured on 2026-10-03, before the
period moved:

- 32-frame period → 1,500 IRQs/s per direction → ~5% of one core.
- 64-frame → 750/s → ~2.5%. 128-frame → 375/s → ~1.3%.
- And latency grows the same amount the CPU shrinks.

So the process is healthy and expected: it is the cost of moving audio at low latency, not a
leak or a runaway. If it ever seems worth reclaiming, the lever is the period size, not the
priority.

## How to look at it again

```sh
# The thread and its realtime class/priority (chrt reports the SCHED_FIFO 85):
ps -e -o pid,comm,pcpu,pri,rtprio,cls,psr | grep 'irq/.*dw_axi'
chrt -p "$(pgrep -f 'irq/.*dw_axi' | head -1)"

# The interrupt rate (two reads, ~5 s apart; difference / seconds):
grep -i dw_axi /proc/interrupts; sleep 5; grep -i dw_axi /proc/interrupts

# Both directions of the stream:
cat /proc/asound/card0/pcm0p/sub0/status /proc/asound/card0/pcm0c/sub0/status
```

The priority comes from `pedal-tune` (AUDIO_IRQ_PRIO), applied at boot by `pedal-device`; the
render thread's 80 comes from namchaind's config (`rt_priority` in namchaind.json).

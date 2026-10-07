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

## Which core it lands on (P7)

It must not land on a render core. The interrupt preempts whatever it lands on, and a render
thread that is preempted is a render thread that can miss its deadline; the whole point of
isolating cores 2–3 is that nothing else does that to them. So the tree pins the IRQ's delivery
to **core 0**, a housekeeping core: `AUDIO_IRQ_CPU="0"` in
`devices/vip/rootfs/etc/pedal/tune.conf`, and `pedal-tune check` fails if the core it finds is
inside `ISOLATED_CPUS`. Core 0 is also what the kernel's own `irqaffinity=0-1` names
(`rtpi/devices/vip/device.env`), so nothing here asks for anything the command line does not
already allow. The interrupt's ~5% of a core comes out of housekeeping capacity either way.

Moving it off a render core is not free — it parks the interrupt's wake-to-completion tail on
the same core as WiFi, the SD card and every service, and the reason a render core looked
attractive is that it is quiet. That trade is what **T6** measures (both placements, with WiFi
and the SD card busy); the decision in
[managing-processing-power-and-optimising-for-fast-switching.md](managing-processing-power-and-optimising-for-fast-switching.md)
(D5) is recorded from that measurement, and D5 carries the result.

## The tradeoff this represents

The 32-frame period was chosen in the latency budget (plan.md, "real-time scheduling and a
32-frame device buffer"). The interrupt rate — and this ~5% — is the direct price of it:

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

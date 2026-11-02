# pro: the hour that failed, run again on the RT kernel with isolation

**Date:** 2026-11-01
**Question:** on 2026-10-31 an hour-long soak on pro failed — a burst at about 22 min 51 s took up to
**2.0 ms of CPU time** per block against a 1,333 µs deadline, giving 4 deadline overruns and 1
playback underrun ([2026-10-31-soak-pro](../2026-10-31-soak-pro/README.md)). Wall time equalled CPU
time, so the thread was not preempted: something made the same work slow. That was on a stock
`PREEMPT_DYNAMIC` kernel with no isolation, no interrupt placement, deep C-states enabled on every
core and two dozen daemons running. Does it still happen once none of that is true?

**In one line:** **the hour passes now** — 2.7 million blocks, p99 at 18.47% of the deadline, **0
deadline overruns, 0 xruns**, and a slowest block of 290 µs of CPU time against the 2.0 ms burst
that failed it before (the worst *block time*, which includes waiting on the device, was 346 µs). Getting there turned up the likely mechanism: the first attempt measured **726
system-management interrupts in a single 10-second window** as **`fwupd`** woke up and enumerated
the machine's firmware — a daemon this host's own `masked-units` named in its prose and had left out
of the list. With fwupd masked, the rerun recorded **no SMIs at all**.

## What changed, and what deliberately did not

Deliberately the same, so the two runs are comparable: `namchain-soak` against the UMC202HD through
`alsa_raw`, two A2-Full instances of `ORNG-V30-421-Center.nam`, `guitar-di.wav` as input, 64-frame
period × 6, render thread SCHED_FIFO 80 on core 5, `namchaind` stopped, one hour. **No signal was
injected and no live rig ran through `namchaind`**, so this is T10's load and not T10.

Changed — the whole point:

| | 2026-10-31 | 2026-11-01 |
|---|---|---|
| Kernel | `7.0.0-42-generic`, `PREEMPT_DYNAMIC` | `7.0.0-38-realtime`, **`PREEMPT_RT`** (Ubuntu's signed amd64 flavour) |
| `isolcpus` / `nohz_full` / `rcu_nocbs` | none | **1-5**, with `irqaffinity=0 skew_tick=1 drm_kms_helper.poll=0` |
| The audio interrupt | xHCI delivered on **core 5, the render core** | core 1, and its handler thread `irq/124-xhci_hcd` at **SCHED_FIFO 85** |
| Deep idle on render cores | C1..C10, C10 exit latency **890 µs** | everything over 50 µs disabled on cores 1-5 |
| Services, logins | unconfined | cpuset **0**; the soak runs in `pedal-rt.slice`, the only one that reaches core 5 |
| Daemons | snapd, cloud-init, thermald, unattended-upgrades, fwupd, … | **72 units masked** |
| Unbound workqueues | mask `3f` | mask `01` |

`before.txt` in each run directory records all of that from the host itself, plus `pedal-tune check`,
rather than relying on this table.

## How it was run

```sh
bench-results/2026-11-01-soak-pro-rt/soak.sh 3600
```

Under `scripts/host-lock --host pro`, and through `sudo pedal-rt` — because `user.slice`'s cpuset is
core 0 now, so `--cpu 5` from an ssh session is refused unless it goes through the one slice that
allows it. That refusal is the isolation working, not a problem to route around.

`turbostat` runs alongside at 10 s intervals recording **SMI count**, the real clock, package power
and temperature. The SMI count is the one candidate for the earlier stall that nothing else would
show: a system-management interrupt steals the core in firmware, invisible to the kernel, and would
look exactly like "the same work took longer" with wall equal to CPU.

## Attempt 1: the host was fine, the runner was not

```
01:31:40  soak started (3600 s requested)
01:31:40  before.txt: PREEMPT_RT, isolated=1-5, audio IRQ on core 1 at FIFO 85, pedal-tune check clean
02:26:14  wpa_supplicant: CTRL-EVENT-BEACON-LOSS, then "Lost carrier" and "DHCP lease lost"
02:26:16  reassociated with the OTHER access point of the same SSID — but no address yet
02:28:24  DHCPv4 address re-acquired. pro had been unreachable for about two minutes
02:31     the soak ran to its full 3600 s and wrote its report into a dead ssh channel
```

**pro never faltered.** Its uptime was continuous across the whole episode — no reboot, no hang, no
reset — and `namchain-soak` and `turbostat` were still running afterwards, at 58 minutes elapsed,
exactly as asked. The two minutes of silence were a WiFi roam between the two access points in the
house, with the gap being how long it took to get a DHCP address back.

**I misread it at the time.** Seeing no ssh and no ping, I concluded the machine had hung and wrote
that down, including a line about it needing a power cycle. It did not. Checking `uptime` and
`journalctl -u wpa_supplicant` is what settled it, and both were available the moment pro answered
again. The lesson is the obvious one: *unreachable* and *dead* are different claims, and the second
needs evidence the first does not provide.

**What was actually lost, and why it was my fault**

`namchain-soak` prints its entire summary — p99, overruns, xruns, the slowest blocks — at the very
end of the run. The runner let that come back over the ssh channel, so when the channel died at 55
minutes the verdict went with it: `soak.txt` is zero bytes. An hour of good data, discarded by a
redirect. An unattended hour-long run over WiFi has to assume the link will blink, so `soak.sh` now
runs the work under `setsid` with its output going to a **file on the host**, polls for a
`soak-done` marker rather than for reachability, and reconnects as often as it takes.

**What survived, and found more than the verdict would have**

`turbostat` wrote to a file on the host from the start, so all 356 samples of it are here.

| | Over the full hour |
|---|---|
| Clock | **3400-3410 MHz**, a 10 MHz spread over 59 minutes; the earlier run blamed part of its trouble on frequency, and there is nothing here to blame |
| Package power | **12.89 W peak** against a PL1 of 35 W and PL2 of 69 W, so nowhere near a limit |
| Package temperature | 52-58 °C |
| Throttle counters | 0 on every core, before and after |
| **SMI count** | **726 — all of them in one single 10-second sample** (t+3390 s), and **0** in the other 355 |

### The SMI burst, and what caused it

Three of the four suspects behind the 2026-10-31 stall are cleared outright: no frequency excursion,
no power limit, no thermal event, for an hour. The fourth is not cleared — it *fired*.

726 SMIs arrived in one 10-second window and none in any other. pro's journal for that window:

```
Nov 01 02:28:12 pro systemd[1]: Starting fwupd-refresh.service - Refresh fwupd metadata and update motd...
Nov 01 02:28:12 pro dbus-daemon[1025]: Activating via systemd: service name='org.freedesktop.fwupd' unit='fwupd.service'
Nov 01 02:28:12 pro systemd[1]: Starting fwupd.service - Firmware update daemon...
```

**fwupd**, enumerating firmware: the UEFI capsule interface, the TPM, SPI flash, NVMe, USB. Reading
those traps into system-management mode, and an SMI is the one kind of interruption the kernel can
neither see, schedule around, nor account for — the core simply stops being the kernel's for a while.
That is exactly the signature of the failure this whole exercise set out to explain: on 2026-10-31 a
block took **2.0 ms of CPU time** against a 1,333 µs deadline, with wall time equal to CPU time, so
the thread was never preempted — *something made the same work slow*.

Two things to be careful about before calling it solved:

- **This is a correlation in one window of one run,** and the audio verdict for that run is the thing
  that got lost, so there is no block-time spike here to line up against the burst. The 2026-10-31
  stall was at 22 min 51 s and this burst at 56 min 30 s, so if fwupd is the cause its schedule is
  not fixed relative to the soak — which a timer with a randomised delay would explain.
- **fwupd was supposed to be off already.** `devices/pro/rootfs/etc/pedal/masked-units` listed it in
  its prose from the first version and never in the list, so the timer went on firing. The prose was
  wrong and the measurement found it. It is masked now (`fwupd.service`,
  `fwupd-refresh.service`, `fwupd-refresh.timer`; the service is dbus-activated, so the timer alone
  would not have been enough).

The clean test is the rerun below: same load, same hour, fwupd masked. If the burst does not recur,
that is a cause identified rather than a suspect listed. `turbostat` now records
`Time_Of_Day_Seconds` so the next one can be put against the journal to the second instead of by
counting samples.

**One incidental result worth keeping:** the NVMe completion interrupt that `isolcpus` cannot move
off core 5 fired **once** in the whole hour (31 → 32). The argument that it does not matter because
the render thread does no I/O now has a number behind it.

## Attempt 2: a clean hour, and no SMIs at all

Same load, same hour, the runner writing on the host — and **fwupd masked**. `run-20261101T023421Z/`.

```
result:            PASS
blocks:            2700000     (3600.000 s of audio in 3599.965 s wall, RTF 1.0000)
p99/deadline:      18.47%      (gate <= 80.00%)
deadline overruns: 0
driver xruns:      0           (0 capture overruns, 0 playback underruns)
max lateness:      0.000 ms
block time:        p50 219532 ns, p99 246216 ns, max 345600 ns
slowest block:     290447 ns of CPU (wall 290246 ns)
render-path alloc: 0 allocations, 0 frees
bring-up xruns:    1           (before the measured loop, as every run on this host reports)
```

And alongside it, over 360 samples:

| | Attempt 2 |
|---|---|
| **SMI count** | **0.** Not one, in the whole hour |
| Render core (cpu5) | busy 18.3%, clock **3110-3309 MHz** — a 199 MHz spread over 60 minutes |
| cpu1 (the audio interrupt and a warm thread) | busy 7.9% |
| cpu0 (everything else) | busy 2.2% |
| Throttle counters | **0 on every core, before and after** |
| Package power / temperature | 11.6 W peak against a 35 W limit; 64 °C peak |

### What the three runs say together

| | 2026-10-31<br>stock kernel, untuned | 2026-11-01 #1<br>RT, tuned, fwupd live | 2026-11-01 #2<br>RT, tuned, fwupd masked |
|---|---|---|---|
| Result | **FAIL** | verdict lost (runner) | **PASS** |
| p99 / deadline | 20.61% | — | 18.47% |
| Deadline overruns | **4** | — | **0** |
| Playback underruns | **1** | — | **0** |
| Worst block, CPU time | **2,026,954 ns** | — | **290,447 ns** |
| SMI count | not measured | **726**, all in one 10 s window | **0** |

The middle column is the one that explains the first. The 2026-10-31 failure was a block taking
**2.0 ms of CPU time** with wall equal to CPU — work that was never preempted and simply took
longer, which is what an SMI looks like from inside Linux. Attempt 1 caught 726 of them in one
window, arriving as fwupd enumerated the machine's firmware. Attempt 2, with fwupd masked, recorded
**none**, and the slowest block in 2.7 million took **290 µs of CPU** — a seventh of the failing
burst. Like for like: both figures are CPU time, which is what the table's row compares. The worst
*block time* was 346 µs, a little over a quarter of the deadline.

**What this is fair to claim.** On the tuned host with fwupd masked, pro renders two A2-Full models
at a 64-frame period for an hour with no overrun and no xrun, and nothing in the machine's power,
clock, thermal or SMI behaviour moves while it does. The 2026-10-31 stall has a mechanism that fits
it and a fix that removes it.

**What is not fair to claim.** This does not prove fwupd caused *that specific* stall: nobody
measured SMIs on 2026-10-31, and the two events were at different offsets (22 min 51 s against
56 min 30 s), so the most that can be said is that the only run which stalled had fwupd live and an
unmeasured SMI count, and the only run with a measured SMI burst had fwupd live. It is also still
true that **no signal went through the interface** — this is T10's load, not T10 — and that the
isolation, the masking and the RT kernel all changed at once, so the hour cannot apportion credit
between them.

## Files

Two run directories, the failed attempt and the good one.

| | |
|---|---|
| `run-20261101T013140Z/` | **attempt 1.** `before.txt` and `turbostat.txt` (the whole hour, including the 726-SMI sample); `soak.txt` is zero bytes — that is the lost verdict |
| `run-20261101T023421Z/` | **attempt 2, the PASS.** `before.txt`, `soak.txt`, `turbostat.txt` (now with `Time_Of_Day_Seconds`), `after.txt` |

`before.txt` is the host's state going in, read from the host rather than asserted here, and it ends
with `pedal-tune check`. `after.txt` has the throttle counters afterwards and the boot's kernel log,
filtered. `soak.sh` is the runner: it writes everything on the host under `setsid` and polls for a
`soak-done` marker, so neither a WiFi roam nor a closed laptop can cost another hour.

## The runner grew a second arm (2026-11-01, after these runs)

Both runs above, and the nine arms across this directory and `2026-10-31-soak-pro`, were run with
**no output-queue options** — and that is not the stream the pedal plays. `prime_playback` primes
one period when no target is set and the target's worth when one is, and every host configures four
(`devices/{vip,piv,pro}/rootfs/etc/namchain/namchaind.json`). So the harness had been characterising
a one-period prime while the engine ran a four-period one, which is also the whole reason these runs
report `bring-up xruns: 1` and a run with the target does not.

`soak.sh` therefore takes `--arms`, and runs **both** by default:

| Arm | Flags | What it is for |
|---|---|---|
| `bare` | none | The RT baseline. **Its flags must not change** — the nine committed arms are measured against it, and re-flagging them would make every future run incomparable |
| `queue` | `--output-queue-periods 4 --output-queue-floor-periods 2` | The stream the engine actually runs |

Neither subsumes the other: the target brings the cap's refusals and the floor's insertions with it
(namchain plan §9.5 item 8 — 8 playback underruns at a 4-period target against 92 for the bare
4-period ring). `--arms bare` reproduces exactly what produced the runs above.

Two consequences for reading this directory. The default is now **two hours**, one per arm. And a
future run's files are named per arm — `bare-soak.txt`, `queue-turbostat.txt` and so on — while the
two directories above keep the single-arm names they were written with; `before.txt` stays once per
run, since the host's state does not change between arms.

`before.txt` and each arm's `after.txt` also now record `/proc/loadavg` and the busiest processes.
pro is used for compilations (the owner, 2026-11-01), and the host's lock keeps other *measurements*
away but cannot stop a build. A soak that shared the machine with one is not a measurement of a
quiet host, and without that snapshot nobody could tell afterwards which kind of run they were
reading. None of the runs above has it, so take their quietness as unverified rather than established.

## Both arms, an hour each (2026-11-02)

`run-20261101T215947Z/`. The first run of the two-arm harness, and the first back-to-back A/B of the
prime on one host: 21:59:47Z to 00:00:48Z, `bare` then `queue`, **both PASS**.

| | `bare`<br>no queue options | `queue`<br>target 4, floor 2 |
|---|---|---|
| Result | **PASS** | **PASS** |
| p99 / deadline | 19.17% | 18.80% |
| Deadline overruns | 0 | 0 |
| Driver xruns | 0 | 0 |
| — capture overruns / playback underruns | 0 / 0 | 0 / 0 |
| **bring-up xruns** | **1** | **none** |
| Max lateness | 0.000 ms | 0.000 ms |
| Worst block, CPU time | 304,495 ns | 301,662 ns |
| Block time p50 / p99 / max | 243,134 / 255,647 / 336,202 ns | 238,388 / 250,631 / 351,285 ns |
| Chain p99 | 212,656 ns | 200,193 ns |
| Render-path allocations | 0 | 0 |
| **SMI count**, 360 samples | **0** | **0** |
| Throttle counters, after | 0 on every core | 0 on every core |
| Package peak temp / mean power | 63 °C / 11.48 W | 62 °C / 10.84 W |

### What the A/B settles: the bring-up xrun

`bare` reports `bring-up xruns: 1`. `queue` reports none — and that is a real zero, not a dropped
line: `tools/soak/namchain-soak.cpp:805` guards the print with `startup_driver_xruns > 0`.

Same host, same kernel, same load, same hour, one after the other, with **one flag set the only
difference**. That makes the ring prime the discriminator by measurement rather than by argument,
which is what the earlier runs could not do — they differed in configuration *and* in host, model
count and date. The mechanism read from the source holds: `queue_prime_frames` primes one period
when no target is set and the target's worth when one is, so `bare`'s untimed bring-up cycle empties
a single period and `queue` starts with four.

So the startup xrun is **not** a property of pro, of the model, of the instance count or of the RT
kernel. It is a property of running with no output-queue target — which no pedal host does.

### What the target costs and buys

The two arms' rings are the interesting part, and neither number was available before:

| | `bare` | `queue` |
|---|---|---|
| Playback ring, frames | 128..168 | 176..200 |
| Playback queue, periods | 2.00..2.62 (p50 2.45) | 2.75..3.12 (p50 2.95) |
| **Floor** — the stall the device absorbs without starving | **2.00 periods = 2.667 ms** | **2.75 periods = 3.667 ms** |
| Blocks holding less than one period | 0 of 2,700,000 | 0 of 2,700,000 |
| Target refusals (the cap declining a period) | n/a, no gate | **0** |
| Floor insertions | n/a | **0 times, 0 frames** |
| Prefill | — | 8 frames, 0.167 ms, paid once |

The trade, measured: the target holds about half a period more audio (p50 2.95 against 2.45, so
**+0.667 ms of output latency**) and in exchange the worst instant has **+1.0 ms more cushion**
(2.75 periods against 2.00). Over 2.7 million blocks the cap never once refused a period and the
floor never once inserted silence, so on this host that millisecond is bought with latency alone and
nothing else.

**What did not reproduce.** The second arm was justified by namchain plan §9.5 item 8 — 8 playback
underruns at a 4-period target against 92 for the bare 4-period ring — and that comparison **could
not be exercised here**: both arms underran zero times. The arms still answer different questions,
but this hour gave neither of them any trouble to handle, so it says nothing about how they differ
when there is some.

### The host really was quiet, and this is the first run that can say so

| | `before.txt` | after `bare` | after `queue` |
|---|---|---|---|
| Load average, 15 min | 0.35 | 0.36 | 0.46 |
| Compiler in the busiest eight | no | no | no |

The busiest processes at every sample were `namchaind` (before only), `irq/124-xhci_hcd` and
systemd. And the filtered kernel log in both `after.txt` files is byte-identical, ending at
`Nov 01 14:58` — **nothing was logged by the kernel during either hour**.

One thing did go wrong, in the harness rather than on the host: the Mac's wait on the `queue` arm
printed `Timeout, server pro not responding`. The host-side run continued under `setsid` and the
runner picked the result up from the `soak-done` marker, which is the path the runner was built for
after attempt 1 lost an hour's verdict. This is the first time it has actually been exercised rather
than argued for.

### The production engine, restarted by the trap

`namchaind` came back at 00:00:48 UTC and reports `xruns 0`, `startup_xruns 0`,
`playback_underruns 0`, `health ok`. It is configured with `output_queue_periods: 4`, which is the
`queue` arm — so on a pedal host **nothing is banked at bring-up at all**, and the explicit-ignore
machinery added for it (namchain `e2cf95b`) is a belt-and-braces for configurations no host uses.

**Noticed, not chased.** `occupancy_mismatches` — the soaks' `samples where delay disagreed with the
pointer pair` — is large and steady: 4,860,075 over 2.7 M blocks in `bare` (1.8 per block),
8,100,002 in `queue` (3.0 per block), and about 2.0 per block in `namchaind` in production. A couple
of frames of disagreement between `snd_pcm_delay()` and the pointer arithmetic on every block, with
zero underruns and zero drops alongside it. Nobody has checked whether that is the USB driver's
delay granularity or something the floor logic should care about, and it is recorded here as an
observation rather than a finding.

### Files

| | |
|---|---|
| `run-20261101T215947Z/` | `before.txt` once; then `bare-soak.txt`, `bare-turbostat.txt`, `bare-after.txt` and the same three for `queue` |

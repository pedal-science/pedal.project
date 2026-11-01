# pro: the hour that failed, run again on the RT kernel with isolation

**Date:** 2026-11-01
**Question:** on 2026-10-31 an hour-long soak on pro failed — a burst at about 22 min 51 s took up to
**2.0 ms of CPU time** per block against a 1,333 µs deadline, giving 4 deadline overruns and 1
playback underrun ([2026-10-31-soak-pro](../2026-10-31-soak-pro/README.md)). Wall time equalled CPU
time, so the thread was not preempted: something made the same work slow. That was on a stock
`PREEMPT_DYNAMIC` kernel with no isolation, no interrupt placement, deep C-states enabled on every
core and two dozen daemons running. Does it still happen once none of that is true?

**In one line:** **the hour passes now** — 2.7 million blocks, p99 at 18.47% of the deadline, **0
deadline overruns, 0 xruns**, and a worst block of 290 µs against the 2.0 ms burst that failed it
before. Getting there turned up the likely mechanism: the first attempt measured **726
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
**none** and the worst block in 2.7 million was **290 µs** — a seventh of the failing burst, and
under a quarter of the deadline.

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

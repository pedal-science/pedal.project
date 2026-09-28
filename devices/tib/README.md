# tib — appliance configuration

## Status: retired; worked again briefly on 2026-09-28, then failed again

`tib` was retired on 2026-09-26 after it stopped working on 2026-09-25. It showed nothing on HDMI,
and in maskrom mode it accepted Rockchip's loader over USB, then stopped responding before the
loader got as far as reading the card: the RAM setup stage. RAM or power were the suspects.

On 2026-09-28 it booted again while its 5 V was being measured: about 4 V at switch-on, rising
quickly to 5 V. Around 20 cold boots followed, 10 s apart, and it came up every time. The three
captured on the serial console ([logs/20260928-console.log](logs/20260928-console.log)) are
identical to within milliseconds:

| Stage | After the first console line |
|---|---|
| U-Boot TPL (RAM set up), `Reset cause: POR`, `DRAM: 2 GiB`, `PMIC: RK808` | 0 s |
| `rtpi: booting slot: known-good` | 3.1 s |
| `Starting kernel ...` | 4.7 s |
| `tinkerboard login:` | 31.7 s |

**The cause is unknown.** It recovered without a repair, which points at power rather than the
RAM, but nothing so far has made it fail again. It stays retired: the Core host is piv, then vip.

**Soak under load**, started 12:36 BST, 4 h: `memtester 1200M` plus `stress-ng` on all four cores
(core 3's worker in `pedal-rt.slice`), as transient units `soak-mem`, `soak-cpu` and `soak-cpu3`
logging to `/var/tmp/soak/`. Watcher log: [logs/20260928-soak-watch.log](logs/20260928-soak-watch.log).

**Result: thermal shutdown after 23 min, then dead again.** memtester found no errors. The CPU
climbed from 68 °C to 88 °C (the clock throttling between 1008 and 1704 MHz), and at 12:59:43
the kernel hit the 90 °C critical trip: `HARDWARE PROTECTION shutdown (Temperature too high)`.
It came back at 13:00 (`Reset cause: WDOG`) and answered ssh for five minutes, idle, at 1800 MHz:
the 1416 MHz cap wasn't in force after that boot. At 13:06 it went through a power-on reset,
reached `Starting kernel ...`, and never got to a login or answered ssh again. Later power
cycles didn't bring it back, and work on it has stopped, possibly for good.

What this does and doesn't show: with no heatsink or fan worth the name, this board can't hold
four cores under load, so thermal shutdown is expected, not a fault. The failure after it fits
the earlier pattern (heat or power, not RAM contents), but nothing here names the part.

**Serial console with the Raspberry Pi Debug Probe.** Its UART port on the header: probe RX to
pin 32 (tib's TX), GND to pin 34, and probe TX left off, because reading is all that's needed
and an unpowered `tib` shouldn't be fed through its RX pin. 115200 8N1, `/dev/cu.usbmodem*` on
the Mac. **The probe needs firmware 2.3.1 or later**: with 1.01, as shipped, its UART stopped
passing data each time `tib` lost power, until the probe was unplugged.

**Seen in passing:** booting the known-good slot, U-Boot can't find `/boot/dtb-good/overlay/`,
so the `i2c1 i2c4 spi2 spidev2 uart1 uart2` overlays in `armbianEnv.txt` aren't applied. That's
rtpi's slot layout, and doesn't matter while `tib` is retired.

Everything on `tib` above the kernel that makes it a pedal rather than a general-purpose
Armbian box (rule 7 in [working-across-repos](../../docs/working-across-repos.md)). The kernel,
its command line and the boot slots are `rtpi`'s; the engine and its protocol are `namchain`'s.

| Layer | Owner | What it does for core 3 |
|---|---|---|
| Kernel | `rtpi` (`7.2.6-tib1`) | PREEMPT_RT; `isolcpus=managed_irq,domain,3 nohz_full=3 rcu_nocbs=3`: no load balancing, no tick, no RCU callbacks, no managed interrupts on core 3 |
| Userspace | here | Services and logins confined to 0–2, the clock capped, the audio interrupt raised above the others, background jobs masked, logs kept in RAM |
| Engine | `namchain` | Pins its render thread to core 3 at SCHED_FIFO 80 |

## Using it

```bash
devices/tib/apply --dry-run   # show what would change
devices/tib/apply             # back up, install, bring into force, check
devices/tib/check             # read-only: tib matches this tree and it is all in force
devices/tib/backup            # pull the current state into backups/<stamp>/
ssh tib sudo pedal-device revert   # undo exactly what apply recorded
```

`apply` refuses while a soak or the engine is running, takes `/run/lock/tib.lock` on the board,
and records the commit it came from in `/etc/pedal/applied` (with `-dirty` if this directory had
uncommitted changes). Each run's backup, apply log and post-apply check land in `backups/<stamp>/`
and are committed.

**Measurements now need `pedal-rt`.** Once the login slice is confined, a process started from
ssh cannot pin itself to core 3: `taskset -c 3` fails with EINVAL, and `namchain-soak --cpu 3`
reports the failure and carries on unpinned. Run them in the slice that is allowed there:

```bash
sudo pedal-rt ./namchain-soak --cpu 3 ...
```

`namchaind`'s unit (Phase 1 step 3) needs `Slice=pedal-rt.slice`, and `LimitRTPRIO=95` and
`LimitMEMLOCK=infinity`, because a service does not get `limits.d`.

## What is in `rootfs/`

Every file is installed at the same path on `tib`.

| File | Why |
|---|---|
| `etc/pedal/tune.conf` | The one place the CPU split, clock cap and audio interrupt are declared |
| `usr/local/sbin/pedal-tune` + `pedal-tune.service` | At boot: governor and 1416 MHz cap, `init.scope`'s cpuset (it is transient, so a drop-in is ignored), the audio interrupt's affinity and priority. `pedal-tune check` verifies all of it, plus the kernel isolation, temperature, throttle state, and that no user task is allowed on core 3 |
| `etc/systemd/system/{system,user}.slice.d/` | Services and logins on 0–2. cgroup v2 resets a task's affinity to its cpuset, which is 0–3 without these, so `isolcpus` alone leaves ~20 daemons *allowed* on core 3 |
| `etc/systemd/system/pedal-rt.slice` + `usr/local/bin/pedal-rt` | The one slice allowed on core 3 |
| `etc/pedal/masked-units` | Background jobs masked, and the ones deliberately kept, with reasons |
| `etc/systemd/journald.conf.d/10-pedal.conf` | Logs in RAM |
| `etc/sysctl.d/90-pedal.conf` | vmstat timer at 10 s |
| `etc/security/limits.d/90-pedal-rt.conf` | rtprio, memlock and an rttime backstop for `@audio` |
| `usr/local/sbin/pedal-device` | The on-board installer: `apply`, `revert`, `status` |

It replaces namchain's `tools/soak/host-slim.sh`, which configured `tib` on 17 Sep for the
isolation experiments. The first `apply` takes host-slim's masks over, removes its files (kept in
`/var/lib/pedal/adopted/`) and moves the hand-written `limits.d/audio.conf` into
`90-pedal-rt.conf`.

Changed from host-slim: housekeeping is 0–2 rather than 0–1, matching the kernel's isolation
of core 3 alone, and the `cpu_dma_latency` rule is gone because this board has no cpuidle states
for it to hold off.

## What it cannot do

Core 3 shares the 1 MB L2 cache and the memory bus with the other three cores. namchain measured a
memory-bandwidth load on the housekeeping cores pushing the render p99 past the deadline with
isolation in force (`namchain/bench-results/tib-nohzfull-summary.txt` §2). Configuration can only
keep such loads off the board; it cannot partition the cache or the bus.

## Next

- **The network stack.** systemd-networkd and netplan's `wpa_supplicant` run the WiFi, but iwd,
  NetworkManager and a second `wpa_supplicant` are running too, and iwd lists `wlan0` as one of its own
  stations. They should be masked. WiFi is the only way into `tib`, so this waits for a boot-time
  fallback: a unit that, a few minutes after boot, unmasks them and reboots if there is no route
  to the gateway.
- **Writeback.** `vm.dirty_ratio` 20 lets ~400 MB of dirty pages build up and then flush to the SD
  card in one burst. Smaller `vm.dirty_bytes` / `dirty_background_bytes` should smooth the step 8
  library rsync. It is a candidate to measure there, not a setting to apply blind.
- **The audio interrupt move** to core 2 is unmeasured on `tib`. The step 8 soak measures it;
  `AUDIO_IRQ_CPU=""` in `tune.conf` turns it off.

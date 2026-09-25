# tib — appliance configuration

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

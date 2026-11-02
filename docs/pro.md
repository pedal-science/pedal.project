# pro: the big-case host

**pro** is an HP ProDesk 600 G5 Mini that runs the pedal's DSP in the bigger case, the way **vip**
runs it in the original, smaller one. Recorded 2026-10-31, from the machine itself. This page says why it exists, what it is, what its
first measurement found and what is not yet done; it grows as the machine is set up.

---

## Why a second Core host

Several NAM A2-Full (WaveNet) instances in parallel do not scale on a Pi 5: they seem to fight over
cache, not CPU time, so the sum of the instances costs more than the instances measured alone (the
crowding is already in vip's per-model figure, see
[managing-processing-power-and-optimising-for-fast-switching.md](managing-processing-power-and-optimising-for-fast-switching.md)).
**This is the owner's reading of the symptom and has not been confirmed with a cache measurement.**
The bigger case has room for a small PC, and a desktop-class part has far more L3 than the Pi 5's
2 MB shared between four cores, so pro is the attempt to buy headroom with cache.

vip stays the Core host of the original case. pro does not replace it; it is a second target
for the same engine and the same rigs, in a case that can hold it.

## What it is

Read from the machine on 2026-10-31.

| Part | Detail |
|---|---|
| Computer | HP ProDesk 600 G5 Mini, x86-64 |
| CPU | Intel Core i5-9500T, 6 cores, no SMT, 2.2 GHz base / 3.7 GHz turbo. L1d 32 KiB and L2 256 KiB per core (192 KiB and 1.5 MiB in all), **L3 9 MiB** shared (the Pi 5's is 2 MiB) |
| RAM | 16 GB (14 GiB usable), 4 GiB swap; vip has 1 GB, so memory stops being a constraint |
| Storage | 2 TB ADATA SX8200PNP NVMe in one LVM volume group, `ubuntu-vg`: `ubuntu-lv` 100 GB for `/` (what the installer made), and **`pedal-data` 200 GB**, ext4 labelled `pedal-data`, mounted at `/var/lib/pedal` as on vip (library, rigs, evidence; made 2026-10-31 by hand, and now made-if-missing by `devices/pro/apply`, which never re-makes or formats an existing one). About 1.57 TB of the group is deliberately unallocated, to grow either from with `lvextend -r` |
| OS | Ubuntu Server 26.04.1 LTS, kernel 7.0.0-42-generic (`PREEMPT_DYNAMIC`, stock; not RT) |
| Network | Wi-Fi `wlp0s20f3` is up (192.168.178.183 by DHCP, so it may move); wired `eno1` is down. Hostname `pro`; `ssh pro` works as `rik` with a key and passwordless `sudo` |
| Audio interface | Behringer UMC202HD 192k, USB 2.0 high speed, ID 1397:0507, ALSA card 0 `U192k`. 2 channels in and out, `S32_LE` (24 bits in it), 44.1/48/88.2/96/176.4/192 kHz, asynchronous endpoints with implicit feedback, 125 us packets. Card 1 is the board's own HDA audio (HDMI/headphone) |
| Also present | Intel Bluetooth 9460/9560 on USB |

**`/tmp` is a RAM disk here too** (tmpfs, 7.5 GB, half the RAM), as on vip. Anything large or
long-lived (captures, builds, bench output, model copies) goes on disk instead: `/var/tmp` (on `/`,
86 GB free) or `/var/lib/pedal/scratch` (on `pedal-data`). Bench evidence goes into a repo's
`bench-results/`, never `/tmp` (working rule).

What was added to the stock install by hand (2026-10-31): apt packages `build-essential cmake
ninja-build alsa-utils rsync pkg-config libasound2-dev linux-tools-common sysstat`. A namchain build
tree is in `~/pedal-build` and the bench inputs in `~/pedal-bench`. Everything else is `devices/pro/`'s
(next section).

## Configuration as code: `devices/pro/`

**pro runs the Pi hosts' own tooling** (2026-11-01). `devices/pro/{apply,check,backup}` are the same
symlinks into `devices/common/` that vip and piv use, and the host-side script is `pedal-device` —
the same one, not a cousin. Until 2026-11-01 pro had its own `pro-device` and `pedal-governor`, which
had drifted into a second implementation of the same job with none of the isolation; they are
retired, and `pedal-device` learned the two things pro genuinely needs that no Pi host does:

- **a storage stage**, from `/etc/pedal/storage.conf`: the `pedal-data` logical volume, made once if
  it is missing and never re-made or re-formatted. vip receives its partition from its card build,
  so it has no such file and no such stage.
- **seeding the first rig** where there is no pedald to save one.

Everything else that differs is a *file* rather than a code path: `devices/pro/rootfs` holds pro's
own copy wherever the Pi hosts' version would be wrong, and `devices/pro/common-files` names the
handful it takes from `devices/common/rootfs`, so none of the codec, UART, pedald or rigpa units land
on it. 21 files in all. `pedal-device`'s Pi-specific steps are now guarded on whether the unit is
actually installed, which is what made one tool serve both.

| What | Where | Notes |
|---|---|---|
| core split | `/etc/pedal/tune.conf` | **the one place pro's core map is written down**, and `pedal-tune` checks it against the kernel command line and the slice drop-ins at every boot. Core 0 housekeeping; 1-5 render; **5 active**, 1-4 warm; the audio interrupt on core 1 at SCHED_FIFO 85 |
| runtime tuning | `pedal-tune.service` | the clock (performance, 3.7 GHz), `init.scope`'s cpuset, the audio interrupt, and three things only pro asks for: every other interrupt onto core 0, deep C-states off cores 1-5, unbound workqueues onto core 0 |
| slice cpusets | `system.slice.d`, `user.slice.d` (`AllowedCPUs=0`), `pedal-rt.slice` (`0-5`) | services and logins cannot touch a render core; `sudo pedal-rt <command>` is the only way in, which is how a soak gets `--cpu 5` |
| services off | `/etc/pedal/masked-units` | **72 units masked.** vip gets this by omission (its root is built from a package list); pro is a hand-installed Ubuntu Server, so each one is named. snapd, cloud-init, unattended-upgrades, thermald, ModemManager, multipathd, udisks2, fwupd, rsyslog, sysstat, apport, kdump, open-vm-tools, upower, cron and the maintenance timers |
| `namchaind.json` | `/etc/namchain/` | `hw:CARD=U192k,DEV=0`, 48 kHz, 64-frame period × 6, 2 in / 2 out (the same engine settings as vip). `cpu: 5`, `warm_cpus: [1,2,3,4]` |
| unit drop-in | `namchaind.service.d/10-pedal.conf` | `Slice=pedal-rt.slice`, `ExecStart` at `/opt/namchain/current`, after `pedal-tune`, after `/var/lib/pedal` is mounted, control thread on core 0 at normal priority |
| realtime limits | `limits.d/90-pedal-rt.conf` (shared) | `@audio` rtprio 95, memlock unlimited, rttime 200 ms. The unit sets its own `LimitRTPRIO`/`LimitMEMLOCK` (services get no pam_limits) |
| the library's owner | `/etc/pedal/storage.conf` | the `pedal` service user, **by name and the same user as vip's**, because the scripts that write rigs `chown pedal:pedal`. The owner's login `rik` is in group `audio` instead |
| data volume | `pedal-device`'s storage stage | `pedal-data`, 200 GB, `/var/lib/pedal`, with `library/{models,irs,rigs}` and `scratch/` |
| first rig | `library/rigs/last.json` | seeded once from `/etc/pedal/default-rig.json`, since namchaind starts silent without one and pro has no pedald |
| WiFi | `pedal-wifi.service` (pro's own) | power saving off on `wlp0s20f3`; the Pi hosts' unit follows `wlan0` |
| journal | `journald.conf.d/10-pedal.conf` (pro's own) | persistent, 200 MB. The common file is `Storage=volatile` because the Pi hosts log to an SD card |
| loose profile | `pedal-maint.target` | reachable, not playing: no engine and no tuning, for answering "did the tuning do this?". Booted and checked 2026-11-01 — ssh up, `pedal-maint.target` active, the library mounted, `namchaind` and `pedal-tune` inactive, `isolated` empty |
| default sound card | `/etc/asound.conf` | the UMC202HD, so `aplay`/`arecord` need no `-D` |

Verified 2026-11-01, applied and checked: 72 units masked, the cpusets in force, `/var/lib/pedal`
mounted and owned by `pedal`, WiFi power saving off, the build flags matching `build.env`, and the
engine running with its render thread SCHED_FIFO 80 on core 5, one warm thread SCHED_FIFO 70 on core
1 and the control thread SCHED_OTHER on core 0.

**The audio interrupt was on the active render core.** Before this, the xHCI controller carrying the
UMC202HD was delivering its interrupt to **core 5** — the core the render thread runs on, which is
the pedal's R4 (D5) breaking: the one core whose preemption is a missed deadline. `irqaffinity=0` on
the command line would not have fixed it on its own, because that sets only the default mask and only
for interrupts allocated after it is parsed. `pedal-tune` moves it, and `pedal-tune check` now fails
if it is ever delivered there again.

Still not done here: pedald. (A cost table **was** measured and installed on 2026-11-02 — 14 rows,
one A2-Full at 0.04 of a core — so the unknown cost of 0.25 no longer applies; see below.)

## The kernel and the boot: `rtpi/devices/pro/`

rtpi owns pro's kernel and its boot, as it owns vip's. `rtpi/devices/pro/device.env` is the single
place the kernel releases and the boot arguments are written down, and it carries the reasons.

**pro takes Ubuntu's own signed realtime kernel and does not rebuild it.** Three reasons, in the
order that settles the question:

1. **Secure Boot is enabled** on this machine, with Canonical's shim and a signed GRUB.
   `linux-image-7.0.0-38-realtime` is a signed image; a kernel built the way vip's is would not load
   without enrolling a Machine Owner Key, which is a larger change to the machine's trust than the
   pedal needs.
2. **There is nothing to change.** Every RT-relevant symbol in rtpi's `config/audio-rt-common.fragment`
   — PREEMPT_RT, HZ 1000, NO_HZ_FULL, RCU_NOCB_CPU, RT_GROUP_SCHED off, the osnoise/timerlat/hwlat
   tracers — is already set in Ubuntu's flavour. vip's rebuild exists for `CONFIG_NUMA_EMU`, which
   the Pi firmware's `numa=fake=4` needs, and for an RP1 DMA patch: a Pi I/O chip pro does not have.
3. It is in **main**, not behind Ubuntu Pro, so it updates like any other package. This is piv's
   route (`linux-raspi-realtime` through apt) on a machine whose one-shot boot is GRUB's.

The flavour lags generic (38 against 42) because it is a separate source package. Both kernels are
held, so they move when we move them.

### `pro-boot`: the same policy as vip, about half the code (550 lines against 1035)

GRUB already provides the mechanism vip's two FAT kernel slots exist to provide, which is why
`rtpi/devices/pro/usr/local/sbin/pro-boot` is small:

- **`grub-reboot <id>`** writes `next_entry` into `grubenv`, and the generated `grub.cfg` boots that
  entry **once** — it clears `next_entry` and saves the environment before loading the kernel. A
  panic, a hang or a reset during that boot therefore lands on the saved default at the next boot,
  with no action from anyone. That is the whole safety net.
- **`GRUB_DEFAULT=saved`** plus `saved_entry` is the promotion mechanism.

This works here only because **`/boot` is its own ext4 partition**: on an LVM or RAID `/boot`, GRUB
cannot write `grubenv`, `grub-reboot` would succeed and change nothing, and a trial would become a
permanent boot. That is the one assumption the design rests on, so `pro-boot` reads `next_entry` back
after arming, and `preflight.sh pro` checks it independently.

`/etc/grub.d/42_pedal` writes three entries from `/var/lib/rtpi/pro-boot/`; Ubuntu's own entries stay
above them, keep their ids, and are the fallback.

| Entry | What it boots |
|---|---|
| `pedal-tuned` | the pedal kernel with the isolation arguments — what pro boots once a trial has been validated |
| `pedal-loose` | the same kernel, `systemd.unit=pedal-maint.target`: no isolation, no engine |
| `pedal-trial` | only while a trial is armed and untested; it is removed the moment one fails |
| *(Ubuntu's own)* | the stock kernel. `GRUB_TOP_LEVEL` pins it there so installing a newer kernel cannot quietly take its place |

That last line is the trap worth naming: with Ubuntu's stock `GRUB_DEFAULT=0`, **installing** the
realtime kernel would have changed what pro boots, because `10_linux` writes its "Ubuntu" entry for
the newest kernel it finds. `rtpi/devices/pro/etc/default/grub.d/90-rtpi.cfg` fixes that in two
lines, and `pro-rt.sh` refuses to install a kernel on a host that has not had them.

**Trying a kernel**, `pro-boot try --kernel <release> --args '<args>'`: write the trial, regenerate
the menu, arm the one-shot, reboot. On the trial's own boot (`pedalboot.profile=trial` on the command
line) `pro-boot-validate.service` runs the hook, which requires **sshd listening, a real network
address, the expected release, PREEMPT_RT where the name says realtime, the isolation actually in
force, and namchaind active and reporting `running`**. It is promoted only if all of those pass.

What covers each way a trial can fail:

| Failure | What recovers it |
|---|---|
| Fails validation | the hook marks the trial bad, removes its entry and reboots |
| Kernel panic | `panic=10` |
| Root never appears | `rd.shell=0 rd.emergency=reboot rd.retry=60 rd.timeout=90` — all four are needed, none is sufficient alone |
| Emergency or rescue mode | drop-ins that reboot after 10 s, **on a trial boot only** (a normal boot keeps Ubuntu's behaviour, because then it is a machine to debug rather than a test to abandon) |
| Boots, then hangs short of validating | `pro-boot-deadline.service`: sleeps 600 s, then marks it bad and reboots |
| Never validated, machine reset | `pro-boot settle` on the next boot marks it bad |
| Wedges before systemd starts | **nothing automatic.** pro has no armed watchdog by default; it needs a power cycle. See below |

**The watchdog is off, deliberately, and this differs from vip.** vip is unreachable without one.
pro is on the bench, in the room, and its BIOS restores power state after a loss. Against that:
Ubuntu blacklists every watchdog module here, the BIOS's own "Watchdog Timer" is Disable, and a
watchdog that fires during a deliberate hour-long soak destroys the measurement it fired during.
`make harden-pro-watchdog` opts in (loading `iTCO_wdt` by name, 60 s rather than vip's 14) and says
whether the chipset actually gave us a device.

### The fallback was rehearsed, not assumed

2026-11-01, `make rehearse-pro-failure`: a trial carrying `modprobe.blacklist=iwlwifi,iwlmvm` — the
running kernel, nothing else changed, so the only variable is the machinery. It booted, found no
network, and **came back on its own in about three minutes**:

```
01:11:13  trial armed (kernel 7.0.0-42-generic, args modprobe.blacklist=iwlwifi,iwlmvm)
01:13:00  pro-boot-validate: FAIL: no PHYSICAL interface has a global IPv4 address after 60s
01:13:01  trial marked bad, its menu entry removed, rebooting
          → back on Ubuntu's own entry, next_entry empty, namchaind active
```

Every check afterwards held: back on the saved default, not a trial boot, trial marked `bad`, no
trial entry left in the menu, the one-shot consumed, the engine running. A safety net nobody has
dropped something into is a hypothesis; this one has been.

Four bugs in the new tooling surfaced by being exercised rather than by being read, all worth
keeping written down because each would have been invisible until it mattered:

- **The rehearsal's own `one-shot was consumed` check was wrong.** GRUB clears `next_entry` by
  setting it to the *empty string*, not by removing the variable, so `grub-editenv list` still
  prints the name. Asserting the variable's absence reported a failure on a rehearsal that had
  worked perfectly.
- **The first real trial of the RT kernel was rolled back by a bug in the validation hook, not by
  anything wrong with the kernel.** Its engine check read the state with
  `sed -n 's/.*"state":"\([a-z]*\)".*/\1/p'`, and `.*` is greedy, so on a one-line status document
  it matched the *last* `"state"` of four — a warm-set document's, which reads `audible`. The engine
  was `running`, health `ok`. The hook parses the JSON with `python3` now. The rollback itself was
  correct behaviour: a check said no, so the machine came back. It is just that the check was ours.
- **`pedal-tune` failed a boot over an unreadable thermometer.** pro's `thermal_zone1` is the WiFi
  radio, and it answers "No data available" whenever the radio is not up — which left
  `$(( / 1000 ))`, and an arithmetic expansion with nothing in it is a *fatal* expansion error in a
  non-interactive shell. One transient read on a boot where the radio was still associating took the
  whole unit down and left the host untuned. The read is guarded now, and `apply` calls `check` in a
  subshell as well, so this unit's first promise — that it never fails the boot — holds structurally
  rather than depending on `check` being faultless. This one was latent in the shared tree and would
  have reached vip eventually.
- **The soak runner threw away an hour** by letting the result come back over ssh; see the soak
  below.

## Differences from vip that matter

- **x86-64, not aarch64.** This used to mean A2 took the Eigen path here, because the planar kernels
  in the vendored NeuralAmpModelerCore fork were Arm-only. **Not true since 2026-11-02:** core
  `97d7cd4` widened the gate to x86-64 AVX2+FMA (`NAM_A2_PLANAR_AVX2`), so pro runs planar kernels
  too, and the parity test now asserts bit-identity on Arm and a −120 dB error floor on AVX2, because
  the core only claims the weaker property there. Every number in vip's cost table is still a Pi 5
  number; [pro's own](../bench-results/2026-11-02-cost-table-pro/README.md) is below.
- **pro builds its own engine.** vip has no compiler and receives built artefacts; pro has gcc 15.2
  and namchain builds in about two minutes, so `scripts/deploy-engine --host pro` exports the commit
  from the Mac (it need not be pushed), builds it clean on pro in `~/pedal-build`, runs the tests, and
  installs it in `/opt/namchain/<commit>/` with `current` swapped, as on the other hosts (decided
  2026-10-31, for the development phase; when pro is treated as a throwaway device the way
  Core builds are made consistent and optimised may change, and vip and pro should then share one
  route). Flags are in `devices/pro/build.env` (`-march=skylake -mtune=skylake`, not `native`, so
  they are in git). It refuses to build while `namchaind` is running (rule 8). It leaves the service
  alone on a host without `devices/pro/`'s configuration.
- **No WM8960, no Pico link, no I2S.** The codec's device tree, the I2C mixer state and the header UART
  in the Pi docs do not apply. Audio is USB class-compliant, through ALSA, opened by card id like
  everything else `namchaind` opens. The footswitch/MIDI/Pico path ([uart-protocol.md](uart-protocol.md))
  has no host-side transport on pro yet; how the controls reach it is open.
- **The UMC202HD is not the WM8960.** Its input stage, gain and noise floor are its own, and the
  hum and noise work in [codec-bringup-2c.md](codec-bringup-2c.md) was done on the codec. Its USB
  clocking is asynchronous to the host, which is a different story from the codec being I2S master.
- **The configuration is the Pi's tooling with pro's files.** Since 2026-11-01 `devices/pro/` runs
  the same `apply`, `check`, `backup` and `pedal-device` as vip and piv; what differs is which files
  the tree holds, not which code runs. `scripts/host-lock`, `scripts/deploy-engine`,
  `scripts/components-lock`, `scripts/sync-library` and `scripts/status` all work with `--host pro`.
- **Boot is GRUB's, not the Pi firmware's**, so there are no kernel slots, no `config.txt`, no
  EEPROM and no rescue root — and no `tryboot`, because `grub-reboot` is the same one-shot by another
  name. What pro has instead of vip's `eeprom.lock` is a committed record of the BIOS settings that
  affect latency, read through HP's `hp-bioscfg` interface by `rtpi`'s `backup-boot.sh` and never
  written by any tool.

## What it costs: the first measurement

[bench-results/2026-10-31-cost-pro/README.md](../bench-results/2026-10-31-cost-pro/README.md),
vip's bench (`namchain-warm-bench measure`) on stock Ubuntu with no core isolation:

| | Full models per core | cost per model | five cores loaded at once |
|---|---|---|---|
| vip (Pi 5, planar NEON) | 9 | 0.111 | not measured here |
| pro, engine as vip builds it | 9 | 0.111 | 8 per core (+13% time per model) |
| pro, `-march=native` | 14 | 0.0714 | 12 per core (+21% time per model), 14 fails |

So pro's single core is no better than vip's with the stock build, and with AVX2 it is 1.5 times
better; what the bigger L3 was bought for, **the cost of running many instances at once, is not
solved**: the same work takes 13-21% longer when five cores run it than when one does. Part of that
is the clock (3.43 GHz against 3.65), and the rest is not yet attributed to the L3 rather than memory
bandwidth or power limits. The cache explanation remains a hypothesis.

### The table, measured and installed, 2026-11-02

[bench-results/2026-11-02-cost-table-pro/README.md](../bench-results/2026-11-02-cost-table-pro/README.md).
pro now has a real cost table — 14 rows in
[devices/pro/rootfs/etc/namchain/cost.json](../devices/pro/rootfs/etc/namchain/cost.json), measured
with `scripts/measure-core --host pro --seconds 30` on an isolated render core of the tuned RT host,
with the engine at namchain `ae6f853` (`-march=skylake`, vendored core `97d7cd4`, parity gate green).
`namchaind` no longer reports `cost_table_missing`.

| unit | vip | pro | vip/pro |
|---|---|---|---|
| `NAM.WaveNet.full` | 0.111 (9/core) | **0.04 (25/core)** | 2.77× |
| `NAM.WaveNet.lite` | 0.0333 (30) | **0.0105 (95)** | 3.17× |
| `IR.8192` / `IR.4096` | 0.0222 (45) | **0.0182 (55)** | 1.22× |
| `IR.2048` | 0.01 (100) | 0.00781 (≥128) | ≥1.28× |
| `IR.1024`, `IR.512`, all seven node types | 0.00781 (≥128) | 0.00781 (≥128) | — |

**Three things this changes and one it does not.** It changes the 9-per-core figure in the table
above: with the planar AVX2 kernels one core fits **25**, where the same host with AVX2 but Eigen fit
14 and the x86-64 baseline fit 9. It changes rig sizing, which was a guess at 0.25 per unit. And it
makes pro, for NAM work, about 2.8 times a Pi 5 per core rather than equal to one. What it does
**not** change is the five-core question above: every row is a one-core-busy row, the 13-21%
multi-core penalty has not been re-measured with the planar kernels, and pro's table carries no
`coexistence` block where vip's does, so nothing corrects for it. The win is also narrower than the
headline: the IR ladder improves only 1.22×, so most of the 2.77× is the A2 kernels, not the box.

### What the RT kernel and the isolation actually changed

Measured on the trial boot, 2026-11-01, with `devices/pro/check` fully green
(`pro matches devices/pro and it is in force`):

| | Stock 7.0.0-42-generic, untuned | RT 7.0.0-38-realtime, tuned |
|---|---|---|
| Preemption | `PREEMPT_DYNAMIC` | **`PREEMPT_RT`** |
| `isolated` / `nohz_full` | empty | **1-5** |
| The audio interrupt | delivered on **core 5, the active render core** | core 1, a warm core — **331,665 deliveries, every one on core 1** |
| Its handler | no thread (not a threaded-IRQ kernel) | `irq/124-xhci_hcd`, **SCHED_FIFO 85**, on core 1 |
| Services and logins | everywhere | `system.slice`, `user.slice`, `init.scope` cpuset **0** |
| Deep idle on render cores | C1..C10 enabled, **C10 exit 890 µs** against a 1,333 µs deadline | everything over 50 µs disabled on cores 1-5; core 0 keeps all of it |
| Unbound workqueues | mask `3f` (every core) | mask `01` |
| Units running on their own | snapd, cloud-init, thermald, unattended-upgrades, fwupd, ModemManager, … | **72 masked** |

**The NVMe queue interrupts are the one thing isolation could not move**, and the reason is worth
writing down rather than filing as a failure. The driver gives every CPU its own completion queue,
so each queue's interrupt is masked to exactly one CPU — and the kernel documents
`isolcpus=managed_irq` as having *no effect* when the mask contains only isolated CPUs. Five of
pro's six sit on cores 1-5 and cannot be moved from userspace.

What makes that acceptable is which number matters. A completion interrupt is delivered to the core
that *submitted* the I/O, and the render thread never does I/O (namchain's rule: nothing on the
render path allocates, locks or blocks). Measured one minute into the tuned boot: four of the five
had fired **zero** times, and the one on core 5 had fired **31** times — boot-time I/O from before
the cpusets took effect. `pedal-tune check` now reports that count and says it must not grow while
playing, which is the thing to read after a soak rather than a mask to argue about.

## Period and soak

[bench-results/2026-10-31-soak-pro/](../bench-results/2026-10-31-soak-pro/README.md), `namchain-soak`
against the UMC202HD (`alsa_raw`, two A2-Full instances, render on core 5 at SCHED_FIFO 80, `namchaind`
stopped; **no signal was injected and no live rig ran through `namchaind`**, so this is T10's load, not
T10).

- **Period sweep, 45 s each:** 128, 64, 48 and 32 frames pass with no driver xruns; 24 and 16 fail with
  a playback underrun (16 also with deadline overruns). p99 block time was 16-22% of the deadline down
  to 32 frames, so the limit is the USB/driver path, not CPU. 64 stays configured; 32 is provisional
  (one 45 s run).
- **One hour at 64 frames: FAIL.** Block p99 was 20.6% of the deadline and the render thread was on
  CPU 99.8% of the time, but a burst at block 1028378-1029028 (about 22 min 51 s in) took up to 2.0 ms
  of *CPU time* per block, giving 4 deadline overruns and 1 playback underrun. Three isolated 0.7 ms
  spikes happened elsewhere. Because wall time equals CPU time, the thread was not preempted: something
  made the same work slow (an SMI, a frequency or power-limit change, or a stall in memory or USB), on a
  stock kernel with no isolation. Cause not found.
- Every run also reports one xrun at bring-up, before the measured loop. Explained on 2026-11-02:
  it is the output-queue prime, not the host — see below.

### A clean hour, and the cause of the stall, 2026-11-01

[bench-results/2026-11-01-soak-pro-rt/](../bench-results/2026-11-01-soak-pro-rt/README.md). Rerunning
the hour on the tuned RT host with `turbostat` alongside found **726 system-management interrupts in
a single 10-second window and none in the other 355 samples** — arriving exactly as `fwupd`, the
firmware update daemon, woke up and enumerated the machine's firmware (UEFI capsule, TPM, SPI flash,
NVMe, USB).

Why that is the right suspect: an SMI takes the core in firmware, and the kernel can neither see it,
schedule around it, nor account for it. The 2026-10-31 failure was a block taking **2.0 ms of CPU
time** with wall time equal to CPU time — the thread was never preempted, so *the same work simply
took longer*. That is what an SMI looks like from inside Linux, and nothing else on the suspect list
survived the same hour: the clock held 3400-3410 MHz, package power peaked at 12.9 W against a 35 W
limit, and every throttle counter stayed at zero.

**fwupd was supposed to be masked already.** It was named in `masked-units`'s prose from the first
version and never put in the list, so its timer kept firing. The measurement found the gap.

**With fwupd masked, the hour passes.** The rerun — same load, same period, same hour:

| | 2026-10-31 stock, untuned | 2026-11-01 RT, tuned, fwupd masked |
|---|---|---|
| Result | **FAIL** | **PASS** |
| p99 / deadline | 20.61% | 18.47% |
| Deadline overruns | 4 | **0** |
| Playback underruns | 1 | **0** |
| Worst block, CPU time | **2,026,954 ns** | **290,447 ns** |
| SMI count over the hour | not measured | **0** |
| Render core clock | — | 3110-3309 MHz, a 199 MHz spread |
| Throttle counters | — | 0 on every core, before and after |

2.7 million blocks, 3600.000 s of audio in 3599.965 s of wall clock, no allocation on the render
path, and the NVMe completion interrupt that `isolcpus` cannot move off core 5 did not fire once in
the whole hour. The one xrun at bring-up is still there; it was explained the next day, below.

**What this does not prove.** Nobody measured SMIs on 2026-10-31, and the two events sat at
different offsets (22 min 51 s against 56 min 30 s), so fwupd is the mechanism that fits rather than
the one caught in the act. The RT kernel, the isolation and the masking all changed together, so the
hour cannot apportion credit between them. And **no signal has been through the interface** — this
is T10's load, not T10.

### Two arms, and the bring-up xrun explained, 2026-11-02

[run-20261101T215947Z](../bench-results/2026-11-01-soak-pro-rt/README.md#both-arms-an-hour-each-2026-11-02).
Two hours back to back on the same host, the only difference between them one flag set: `bare` with
no output-queue options, `queue` with `--output-queue-periods 4 --output-queue-floor-periods 2`,
which is what every host's `namchaind.json` configures. **Both PASS** — 0 deadline overruns, 0
driver xruns, 0 playback underruns, 0 SMIs and 0 throttle events in either hour, p99 at 19.17% and
18.80% of the deadline.

**The bring-up xrun is the prime, not the host.** `bare` reports one, `queue` reports none, and the
soak prints that line only when the count is non-zero (`tools/soak/namchain-soak.cpp:805`). Same
kernel, same load, same hour, one flag apart — so it is a property of running with no output-queue
target, which no pedal host does. `namchaind` on pro, restarted after the run, reports
`startup_xruns 0` and `xruns 0`: with a 4-period target nothing is banked at bring-up at all.

**What the target costs.** The ring's floor — the stall the device absorbs without starving — was
2.00 periods (2.667 ms) bare against **2.75 periods (3.667 ms)** with the target, for about half a
period more audio held (+0.667 ms of output latency). In 2.7 million blocks the cap never refused a
period and the floor never inserted silence, so the extra millisecond of cushion cost latency and
nothing else. The underrun difference that justified keeping both arms (namchain plan §9.5 item 8)
could not be exercised: both arms underran zero times.

**And the host was verifiably quiet** — 15-minute load 0.35 going in, 0.36 and 0.46 after each arm,
no compiler in the busiest eight at any sample, and no kernel messages at all during either hour.
pro is used for compilations, so earlier runs' quietness was assumed; this is the first one where it
is recorded.

## Status

Done, and checked rather than assumed:

- hardware assembled in the case; Ubuntu Server installed; the hardware, the UMC202HD and the OS
  recorded above;
- `scripts/deploy-engine --host pro` builds namchain with the committed flags, tests it and installs
  it; the cost of a Full model measured on one core and on five;
- **the same `devices/` tooling as the Pi hosts**: `pedal-device`, `pedal-tune`, `apply`, `check`,
  `backup`, with pro's own files for the 21 paths that differ. `pro-device` and `pedal-governor`
  retired;
- **the isolation in force**: cores 0 / 1-5, the active render core 5, the audio interrupt on core 1
  at SCHED_FIFO 85, deep C-states off the render cores, the cpusets, 72 units masked;
- **Ubuntu's signed amd64 PREEMPT_RT kernel** installed, held, tried once and promoted by validation;
- **the fallback rehearsed**, with a trial that was meant to fail and came back by itself;
- `devices/pro/check` reporting `pro matches devices/pro and it is in force`;
- **an hour at 64 frames with 0 deadline overruns and 0 xruns** (above), which is the thing the
  stock, untuned host could not do.

Not done, and not claimed:

- **A live-rig hour.** The hour above is `namchain-soak`'s load, not `namchaind` serving a rig with
  switching, which is what vip's T10 is. That is the soak that would make pro a pedal rather than a
  host that can render.
- 32/24-frame reruns on the tuned host. 32 frames is still the smallest period seen to pass, in one
  45 s run on the old kernel. (The bring-up xrun that used to sit in this list was explained on
  2026-11-02: it is the output-queue prime, above.)
- **No audio has been through the interface.** Nothing was plugged in for any of this.
- The cost table's **multi-core correction**. The 14 rows are measured and installed (2026-11-02,
  above), but each on one busy core; the 13-21% five-core penalty has not been re-measured with the
  planar kernels, and pro has no `coexistence` block where vip has one. Admission is no longer a
  guess, but it is still a one-core guess about a five-core machine.
- The cost table **confirmed against a live rig**: vip's T2 (16 heterogeneous rigs against the table)
  and T10 (an hour of real playing) have no pro equivalent.
- The L3 hypothesis tested: `perf stat` counters, a pinned-clock rerun, the five-core arm on vip.
- Wired networking, and how ljoss finds pro (Wi-Fi at a DHCP address).
- The watchdog: off by default, and whether this chipset will even give us one is unknown
  (`harden-pro --watchdog` reports it).
- A parity or soak run of the Skylake build specifically; its golden tests pass (5/5).
- pedald, and so the footswitch and MIDI path has no host-side transport on pro.

## Next steps

1. **A live-rig hour through `namchaind`**, as vip's T10: rig switching, the warm set, the control
   path, and a signal actually through the interface. That is what would make this a pedal rather
   than a host that renders.
2. ~~Measure and install pro's cost table.~~ **Done 2026-11-02** (above). `scripts/measure-core` runs
   against pro with `--no-build` plus the host's own deployed bench; its build step still assumes the
   aarch64 container and `devices/<host>/image.env`, which pro has not got, so an x86 build path in
   that script is the remaining tidy-up. What is left of the question is the multi-core correction and
   a live-rig confirmation, both listed above.
3. **Confirm fwupd was the 2026-10-31 stall**, if it is worth the time: the `hwlat` tracer in this
   kernel measures SMI stalls directly, so an hour with fwupd deliberately unmasked and `hwlat`
   running would catch one in the act instead of inferring it.
4. **Decide the watchdog.** The argument for leaving it off (`rtpi/devices/pro/device.env`) rests on
   pro being attended, and an unattended hour is when it would earn its keep.
   `make harden-pro-watchdog` says whether this chipset will even provide one — the BIOS's own
   "Watchdog Timer" is `Disable`.
5. Rerun 32 and 24 frames for longer than 45 s, now that 64 is proven for an hour.
6. Find what the five-core slowdown is (counters, pinned clock, vip's arm) before trusting the cache
   story or sizing rigs from the 12-per-core figure.
7. Wired networking. The WiFi roam that cost attempt 1 its verdict is a reason of its own: a cable
   would have avoided it, and ljoss has to find pro at a DHCP address as things stand.

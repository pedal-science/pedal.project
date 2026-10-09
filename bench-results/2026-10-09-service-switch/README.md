# T7's service half, and a reboot during T8's storm (2026-10-09)

A press has no path into the service without the Pico, which is why T7's service half and T8's storm
have been waiting. `pedald` now takes one event over HTTP — `POST /event`, the link's own vocabulary
`{"kind": 1, "a": 0, "b": 0}` (= rig_up) — and hands it to the same `on_event` the UART reader
calls, so the mapping tables decide exactly as they do for a press. `scripts/measure-switch` drives
it from the Mac over WiFi, with a bank of two rigs built from the rig the pedal plays.

## T7's service half: PASS

Eight presses, one a second, each one stepping the bank, engine `9f3cbb6` (the charge in place),
`vip`, in `pedal-bench.slice` conditions (nothing else on the machine):

```
bank:        t7-a.json, t7-b.json (both the document the pedal plays)
before:      switches 0, xruns 0, issues 0; warm: t7-a.json on core 1, state warm, behind 0, dropped 0
press 1..8:  warm 1 cold 0 xruns 0      (every press)
after:       switches 8 (warm 8, cold 0), xruns 0, issues 0
             warm: t7-a.json on core 1, state warm, behind 0 (worst 1), dropped 0
```

**8 of 8 presses were handovers.** No press was a cold switch, no block was dropped, the warm
document stayed within a block of the device thread, and the warm set slid to the new neighbour after
every step (the rig left behind is what the next press reaches, and it is warm again by the time the
next press comes). That is T7's service half, and it is D10's promise — a press costs a fade, not a
compile — measured end to end through the service rather than at the engine.

## T8's storm: NOT MEASURED — the pedal rebooted

The storm run is void, and the reason is more interesting than the storm. At a requested 10 presses a
second the script managed 1.77/s (each `curl` took ~500 ms, and 9 of 106 presses did not answer 200 —
the service is slower when the engine is compiling neighbours cold, which is itself what a storm
does). Then, partway through, **the pedal rebooted**:

```
Oct 09 21:46:51 vip systemd[1]: Starting systemd-user-sessions.service...
Oct 09 21:46:52 vip systemd[1]: Starting namchaind.service...
Oct 09 21:47:03 vip systemd[1]: Startup finished in 2.215s (kernel) + 3.196s (initrd) + 14.706s (userspace)
```

The storm's `after` snapshot read the engine's counters as zero because it was reading a *new*
process. What the run did show before the reboot: switches 8 → 37, of which **9 were cold** (the storm
outruns the warming — the newest press wins and lands on a rig the engine has not finished compiling
and prewarming), `xruns` 0 and no guard trips, and the warm document current (behind 0, nothing
dropped). So the *shape* is D10's and T8's expected one; the numbers are not evidence.

**The cause is not known, and the log that would say was already gone.** vip's journal is volatile
(`Storage=auto` with no `/var/log/journal`), so the previous boot's tail — the kernel's
`Undervoltage detected!`, a thermal shutdown, a panic — does not survive the reboot it caused. The
firmware's own low-voltage flag (`hwmon rpi_volt in0_lcrit_alarm`, which `pedal-diag` reads) is
live-only and reads 0 now, after the reboot. Temperature now 63.9 °C, diagnostics 0 fails / 1 warn,
both slots `good`, `guard 0 of 3 unguarded boots`, no rollback.

The lead is power: the storm is the heaviest thing this pedal has been asked to do (a cold switch
compiles a document per press, on top of WiFi and the audio thread), and a Pi 5 whose rail sags
reboots exactly like this. **The next step is the owner's**: the supply and cable
(`docs/hardware-handoff.md`), and whether the codec board's feed shares the rail. What has been done
here is to make the next occurrence diagnosable: `devices/vip/rootfs/etc/systemd/journald.conf.d/
persistent.conf` turns the journal persistent on this device and a tmpfiles entry creates
`/var/log/journal` at boot, so the next reboot's last minute survives it.

T8's storm is therefore **unproven**, not failed: it needs a gentler rate first (2/s rather than 10/s)
and a board whose power is known, and the falsifier it is looking for — a storm that leaves the warm
set permanently behind — has not been demonstrated either way.

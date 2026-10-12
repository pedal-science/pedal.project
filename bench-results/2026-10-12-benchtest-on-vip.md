# 2026-10-12 — the bench test on vip

`pedal.benchtest` installed on vip with `devices/vip/apply` and run live from the Mac with
`scripts/benchtest --host vip --no-browser`, driving its API with curl. The raw records are in
[2026-10-12-benchtest-on-vip/](2026-10-12-benchtest-on-vip/): the read-only check before, both dry
runs, the engine's status at each step, and the page's state before and after the health run.

## What was installed

- First apply, devices tree 5c7a2e6 (backup `devices/vip/backups/20261012T160249Z`): the unit
  `/etc/systemd/system/pedal.benchtest.service`, `/usr/local/sbin/pedal-benchtest` and the 14 files
  of `/usr/local/lib/benchtest/`. The dry run named those 16 files and nothing else besides apply's
  usual daemon-reload and re-enable/restart of pedal-tune, pedal-uart, pedald, pedal-codec and
  pedal-wifi. The unit came up `static` and inactive: nothing starts it at boot.
- Second apply, 6a77997 (backup `20261012T160641Z`), after the fix below: `main.py` and
  `__init__.py` only, as its dry run said.

Both applies ended with rc 1, because apply's own check fails on the cost table's provenance
(`cost.json` names engine 894b67c and kernel numaemu1; vip runs the image's engine on numaemu3). That
was failing before this work and is unchanged by it; it stops apply before it writes
`components.lock`, so `scripts/components-lock --host vip` wrote it each time.

## What failed first, and the fix

The first start failed at once: `OSError: [Errno 98] Address already in use`. The bench test's
default port was 47820, which pedald has served its HTTP API on since 0.1. It now listens on 47830
(6a77997), and `test_benchtest_server.Port` holds its default against pedald's and namchaind's
ports in every host's configuration (it fails on 47820). The launcher's hint on a failed start now
says `sudo journalctl`; without sudo, vip shows "No entries". `devices/common/test-pedald`: 408 tests
OK (1 skipped, as before), scripts/tests 20 OK, the browser test 4 OK.

## The engine

| When | State | Mute | xruns | Health |
|---|---|---|---|---|
| Before (up since 2026-10-11 21:45) | running | off | 2 | warn: `cost_unknown` on one tone node |
| After the first apply's restart | running | off | 1 (a capture overrun as it started) | warn, the same |
| After the second apply's restart | running | off | 0 | warn, the same |
| After the health run | running | off | 0 | warn, the same |
| After the shutdown | running | off | 0 | warn, the same |

namchaind was stopped for each apply under the host's lock and started again in the same locked
session; it came back on the same rig (`last.json`), unmuted as it was. The health run did not touch
it: xruns 0 before and after.

## The health benchtests, live

One run of `codec`, `audio`, `link`, `core` and `probe`, 7.4 s from start to done:

- **Codec — pass.** It answers on I2C (the driver has it bound and its 47 registers read) and its
  clocks reach Core.
- **Sound device and engine — pass.** The engine has the WM8960 open and streaming in the right
  format, with no xrun issue.
- **Pico link — fail, and it is the bench.** "No frames have ever arrived on the Core→Pico UART
  link"; next: the lead in header pin 10, at both ends. pedald's own `/status` agrees: ttyAMA0 is
  open at 115200, 0 bytes in, 0 frames, no session, and no Pico on vip's USB. Nothing the bench test
  misread; the Pico is not talking to vip at the moment.
- **Core — pass.** 44.6 °C, below where it slows itself, and the low-voltage alarm is off.
- **Debug probe — fail, as expected.** Its USB is not on this Mac. That check runs on the Mac only.

The noise benchtests were not run: they need the interface's cables, which only the owner can plug
in.

## Stopping

`POST /api/shutdown` answered 200; the unit went inactive with `Result=success` and exit status 0,
`/run/pedal-benchtest/` (the URL file) was removed, `scripts/benchtest` said the service had stopped
and exited 0 on its own, and the lock was released. Nothing named benchtest or pedal-diag was left
running on vip or the Mac. The idle exit was not tried live (its tests cover it).

The run's results stay in vip's `/var/lib/pedal/benchtest/history.json`, so the page will show the
link's and the probe's fail as the previous results until "Forget previous results".

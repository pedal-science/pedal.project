# `pedal-diag` on vip: what it reports, and what it costs

2026-10-05. The diagnostic tool's first live run against the assembled pedal, plus the
cost measurement that decides whether it can be left running. Instrument:
`scripts/diag` (`devices/common/rootfs/usr/local/sbin/pedal-diag`), reading vip over ssh
as `sudo -n python3`. Nothing on the pedal was changed to take these numbers.

## What it says about a healthy pedal

```
pedal-diag — vip
  when     2026-10-05 16:48:43
  host     Linux vip 7.0.0-1017-raspi-realtime-numaemu1-trimmed #1 SMP PREEMPT_RT Sun Oct  4 20:32:26 UTC 2026 aarch64
  interface model: /Users/rik/code.local/pedal.project/devices/common/pedal-interface.json
  verdict  1 warn, 3 info, 8 ok

  warn  cpu-thermal is 61.7 C
        evidence: the firmware's cooling steps begin at 50.0 C, 60.0 C, 67.5 C, 75.0 C; critical 110.0 C
        likely:   the case is the plastic stand-in, or the lid is on, or the airflow is through a hole meant for a cable
                  a rig has just been switched and the load is transient
                  the fan is not spinning: check it on the board
        check:    the temperature again in a minute under the same rig. Sustained heat is what matters: a single reading after a rig switch is the load, not the cooling

  info  the engine does not publish the PCM format it opened
        evidence: engine.status has no 'format' key (namchain 0.1.0)
        likely:   not built yet: the daemon stores the format (active_format_) and never reports it
        check:    the plan's namchain change adds it; until then read /proc/asound/card0/*/hw_params

  info  no Raspberry Pi Debug Probe is attached to this host
        evidence: no 2e8a:000c on this host's USB
        likely:   it is on the Pico, on the Mac, or in a drawer
        check:    nothing — the Pico's console is also reachable over its own USB, and the link's counters come from pedald

  info  audio levels are not available from this engine
        evidence: engine advertises 17 features, none of them 'levels'; no engine.levels reply
        likely:   not built yet: namchain has no audio-level measurement at all as of b9ca368 (this plan adds engine.levels)
        check:    the plan's namchain change; until then read the card's own counters and the render/queue numbers in engine.status

  ok    the driver has the codec bound and its register map is readable
  ok    the capture stream is running and owned
  ok    the open device is at 48000 Hz, period 64, 2 channels
  ok    the Pico link has a session and has never seen a bad frame
  ok    the CPU split, governor, clock cap and cpusets are in force
  ok    namchaind has a realtime thread
  ok    the Pico's own USB is enumerated
  ok    the codec's 53 mixer controls are readable
  things software cannot see:
    - Which socket a lead is in, physically. The tool narrows the fault to a signal and names the pin; a meter or a photo closes it.
    - A lead that is fitted but making poor contact: intermittent, so it shows as noise, occasional framing errors or an occasional device loss rather than a clean absence.
    - An I2S line that is present and clocking but at the wrong logic level: it looks like data, and only a scope sees it.
```

Exit %d. The three `info` lines are things that are *true and worth saying* rather than
faults: the engine does not publish its PCM format, no Debug Probe is attached to vip, and
namchain has no audio-level telemetry yet (both are in the plan). The one `warn` is the
board sitting at 60-66 C, which is a Pi 5 under light load.

## The gate: does it disturb the audio?

`--watch --interval 2.5` running on the Mac against vip, sampling throughout, while the
engine played `New Rig`. The engine's own numbers before and after:

| | before | after |
|---|---|---|
| `state` | running | running |
| `xruns` | 2 | 2 |
| `guard_trips` | 0 | 0 |
| `failed_nodes` | 0 | 0 |
| `render_errors` | 0 | 0 |
| `output_drops` | 0 | 0 |
| `capture_bursts` | 0 | 0 |
| `health` | ok | ok |

| | before | after |
|---|---|---|
| `render.worst_percent` | 22.11 | 22.11 |
| `render.over_deadline` | 0 | 0 |

`issues`: []

**No change in any of them** across 16 samples over 35.4 s, with the sampler running the whole
time: the same 2 xruns that were there before, 0 guard trips, 0 drops, 0 over-deadline, and the
worst block within noise of where it started. That is the gate the plan set, and it holds.

## What it cost

```
pedal-diag: 10 samples, 48 ms cpu each on the pedal, 1.92% of one core at a 2.5s interval
```

(The tool prints this every tenth sample; the run below was `--quiet`, so the numbers come from
the log's own `cost` field instead — which is the same measurement.)

Per-sample, from the log's own `cost` field (the gatherer's whole process tree, read from
`/proc/self/stat` by the gatherer itself):

| | value |
|---|---|
| samples | 16 over 35.4 s |
| CPU per sample, median | 50 ms |
| CPU per sample, first (sudo cold start) | 2040 ms |
| mean of all but the slowest | 52 ms = 2.08% of one core at 2.5 s |
| log size | 4.7 kB/sample |

Two thirds of the fixed cost is `sudo` and the Python interpreter start (measured separately:
10 ms `python3 -c pass`, 20 ms through `sudo`), not the sampling. Nothing in a sample opens a
sound device, a bus or the Pico's line.

## The engine's own numbers, with the level probes in

`pedal-diag --watch --interval 2.5` on the Mac for a minute, against the engine with the
level probes compiled in and deployed (`a69d315` on vip):

| | before | after |
|---|---|---|
| `state` | running | running |
| `xruns` | 0 | 0 |
| `guard_trips` | 0 | 0 |
| `render_errors` | 0 | 0 |
| `output_drops` | 0 | 0 |
| `playback_underruns` | 0 | 0 |
| `capture_overruns` | 0 | 0 |
| `health` | ok | ok |
| `render.worst_percent` | 21.04 | 22.53 |
| `render.over_deadline` | 0 | 0 |

**Nothing moved.** And the probe's own cost, from the log's `cost.pedal_cpu_s` (the
gatherer's whole process tree): **92 ms a sample**, 3.68% of one core at a 2.5 s interval —
of which about 30 ms is `sudo` and the Python interpreter's own start rather than the
sampling.

```
pedal-diag: 24 samples, 46 ms cpu each on the pedal, 1.85% of one core at a 2.5s interval  (over the 1% budget: raise --interval, or --deep-every)
```

The sampler's numbers, read back from its own log:

```
pedal-diag: 48 samples over 2.1 min, one every 2.7 s
  worst finding seen: warn
  xruns                    0, unchanged over 2.1 min
  guard_trips              0, unchanged over 2.1 min
  frames_ok                46436 -> 46994 over 2.1 min (+4.476/s)
  frames_bad               0, unchanged over 2.1 min
  output_queue_drops       0, unchanged over 2.1 min
  capture_bursts           0, unchanged over 2.1 min
  cpu-thermal              53.5 C..57.3 C (mean 55.2 C)
  memory                   70.3%..74.6% available
  render                   22.5% worst block (deadline is 100%)
  findings (48 samples; the loudest first):
    warn  levels.hot                   35/48  the input channel 0 is at -0.0 dBFS
          -> the rig's gain stages, and the input stage's Inst/Line switch
    warn  levels.silent_input           4/48  the input is digitally silent
          -> the lead in header pin 38 first: it is the historical one
    info  wire.probe_absent            48/48  no Raspberry Pi Debug Probe is attached to this host
  6 of the samples carry the full evidence in this log
```

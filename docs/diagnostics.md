# Diagnostics

One command that reads everything the pedal will tell you about itself, and turns it into
"look at this wire" rather than a wall of numbers.

```sh
scripts/diag                      # from the Mac: one report, read-only, ~8 s
scripts/diag --host vip --watch   # continuously, one compact line per sample
scripts/diag --host vip --deltas scratch/diag/diag.jsonl   # what changed over a long run
sudo systemctl start pedal-diag   # on the host, logging to /var/log/pedal/diag.jsonl
sudo pedal-diag --probe           # the invasive checks, only while the engine is stopped
```

## Why it exists

Every fault this pedal has had so far has been one of four things: a lead out of its socket, a
device that would not open, a clock that was not arriving, or a thermal/CPU limit. Each of those
leaves a *different fingerprint in a different file*, and nobody remembers which — the last three
cost an evening or a day each
([2026-10-04-rewire-faults-and-the-pico-console.md](../bench-results/2026-10-04-rewire-faults-and-the-pico-console.md),
[2026-10-04-case-no-audio-diagnosis.md](../bench-results/2026-10-04-case-no-audio-diagnosis.md),
[2026-10-05-pico-power-test.md](../bench-results/2026-10-05-pico-power-test.md)).

So the fingerprints are written down instead of remembered. `pedal-interface.json` holds the
interface as data — every signal that has to be present, the header pin it lives on, and what a
fault in it looks like from software. The tool reads the files, compares them with that model,
and prints the three lines that matter: **what is wrong**, **the evidence**, and **the exact
measurement that closes it**.

```
  fail  the codec is not on the I2C bus at all (no 1-001a sysfs entry)
        evidence: i2c-1 devices: (none besides the bus itself)
        likely:   3V3 to the codec board is out (header pin 1): its DCVDD, DBVDD and the 24 MHz
                  oscillator are all on that rail, and the board's PWR LED would be dark
                  the SDA or SCL lead is out (header pins 3 and 5)
        check:    the board's supplies and its I2C are four adjacent header pins (1, 2, 3, 5).
                  Check those leads and the board's seating first, then dmesg for 'wm8960 1-001a'
        seen before: i2c-nack-vs-timeout
```

## The three modes, and why they are three

| Mode | What it does | What it must never do |
|---|---|---|
| a report (`scripts/diag`) | reads everything once, prints the findings | write anything, anywhere |
| `--watch` | samples continuously, one compact line per sample, plus a full sample every tenth | fork per sample, open a bus, talk to the codec |
| `--probe` | the invasive checks: the Pico's console, and anything else that changes what is measured | run while the engine is playing — it checks, and refuses |

The split is the design, not a convenience. A diagnostic that changed the thing it was measuring
would be worse than no diagnostic, so the passive reading and the active poking are separate
commands with separate costs, and the passive one is the one to leave running.

`--watch` **measures itself and prints the number**, because a cost claim nobody can check is not
much of a claim. Measured on vip (2026-10-05), the gatherer's whole process tree read from
`/proc/self/stat` by the gatherer itself:

```
pedal-diag: 10 samples, 48 ms cpu each on the pedal, 1.92% of one core at a 2.5s interval
```

Break that down and it is honest about where it goes: **10 ms** is the Python interpreter, **20 ms**
is `sudo`'s first invocation (a one-off, which is why the quoted mean drops the slowest sample),
and the rest is the reads and the few forking checks. Two things dominate the fixed cost, and
neither is the sampling: `sudo`, and the interpreter start. At 5 s the same run is under 1% of one
core; at 2.5 s it is about 2%. Nothing in the sample touches a bus, a sound device or the Pico's
line, and the audio-side gate (`xruns`, `render.worst_percent`, `queue.output_drops` unchanged over
a run) is what actually decides whether it is free enough — the CPU number is a proxy for that, not
the verdict.

A sample is about 1.7 kB of log, and every tenth (`--deep-every`) is a full ~60 kB sample with the
whole raw state in it: about 20 MB a day at the default interval, rotated hourly and bounded by
`--keep`. The forking checks — `systemctl` per unit, `amixer`, `dmesg` — ride with the deep sample,
and `pedal-tune check` (2 s of CPU on its own: it forks per masked unit) runs every tenth *minute*
(`--tune-every`). Between its runs the same facts are read from the files every sample, so a
disagreement shows up immediately and the authoritative answer follows.

## What it reads

Everything under `/proc`, `/sys` and `/sys/kernel/debug` that is relevant, plus the two local
sockets. The list is long because the point is breadth; these are the parts worth knowing:

- **the codec**: `/sys/kernel/debug/regmap/1-001a/registers` (root-only) with the register words
  decoded — clocking, the audio interface, the power domains — and the driver's access summary
- **the audio device**: card list, `/proc/asound/card0/pcm0{c,p}/sub0/status` and `hw_params`,
  who owns the PCM, and the state words explained
- **the engine**: `engine.status` over the TCP control protocol, with its issues, xruns, render
  histogram, queue drops and model budget; `engine.levels` once namchain publishes it (see below)
- **the link**: `pedald`'s `/status` — session, frame counters, byte counters, drops, and how long
  since anything arrived — plus the port's own line discipline from `termios`
- **the host**: thermal zone and its cooling steps, `rpi_volt`'s undervoltage alarm, cpufreq, the
  render thread's realtime policy *and* which core it is on, the audio interrupt's affinity,
  memory, storage, USB devices, the deployed engine's commit
- **the things that already answer part of this**: `pedal-tune check` and `pedal-device status` are
  run and *quoted* rather than reimplemented. Where an existing tool is the authority, this one
  repeats its answer and links to it.

## What it cannot see, and says so

Every report ends with the things software cannot decide, because the most expensive mistake in
this kind of tool is quiet confidence:

- which socket a lead is physically in — the tool narrows it to a signal and names the pin
- a lead that is fitted and making poor contact: intermittent, so it reads as noise or repeated
  drops rather than an absence
- an I2S line that is clocking at the wrong logic level: a scope's business
- anything not yet built (display, footswitches, MIDI, expression, relay) and anything analogue
  past the codec

## The one thing it cannot read, and why

A real reading of the codec's own registers over I2C was attempted and **did not work**; the
attempt is recorded in the tool's source so nobody repeats it. What was measured on vip
(Python 3.14.3, 2026-10-05):

- vip has no `i2cget` (`i2c-tools` is not in `devices/vip/packages`) and its `python3-minimal` has
  **no `ctypes`**, so a hand-packed ioctl is the only route that needs no packages.
- `/dev/i2c-1` cannot be claimed while the driver holds 0x1a: `I2C_SLAVE` returns `EBUSY`. The
  wm8960 driver owns it, which is correct and is not to be worked around.
- `I2C_SLAVE_FORCE` works, and then a plain write does reach the chip (a bad register number
  answers `-EREMOTEIO`, a real NAK) — but a plain read does not, because `i2c-dev` issues it as a
  read with no preceding write, which the WM8960's register protocol needs.
- `I2C_RDWR` is the ioctl that does exactly that, and with `array.buffer_info()`'s address packed
  into `i2c_rdwr_ioctl_data` it returns `EFAULT` even for a single write message. The adapter does
  advertise `I2C_FUNC_I2C` (`funcs=0xf7f0027`), so the capability is there; the Python side did not
  work out.
- The SMBus route is a dead end by design: the adapter has no `smbus_xfer`, so `I2C_SMBUS` returns
  `EINVAL`, and a 7-bit-register codec is not SMBus anyway.
- `regmap`'s `cache_bypass=Y` was also tried: the register file then answers `XXXX` for **every**
  register, so the driver cannot read the chip back on demand either (the codec is powered down
  between DAPM transitions). That is a reason *not* to make `--probe` flip it — it would report
  `XXXX` as though it were the chip's silence.

So the tool reports the driver's register map, and says in the finding that it is the driver's
cache rather than the chip. The two honest ways to get a real read are adding `i2c-tools` to
`devices/vip/packages` (an image change; `i2cget -y 1 0x1a 0x00 w`) or fixing the ioctl.

## The interface model

`devices/common/pedal-interface.json` is installed to `/etc/pedal/pedal-interface.json` and is the
one place that says what has to be true. It holds:

- the codec's bus, address, id register and expected value, and its register ranges
- every codec-to-header signal: the pin, what it carries, what a fault in it looks like, and how
  to check it — including the two rows that are *wrong to wire* (ALRC, and ADCDAT in the wrong
  socket)
- the Pico link's four signals and the firmware's console banners
- the expected audio device, `hw_params`, CPU split, thermal trips and engine/service endpoints
- `known_fault_seeds`: the historical symptom→cause pairs, quoted when their signature recurs
- `cannot_be_seen_from_software`

The prose stays where it is (`docs/codec-bringup-2a.md` stage 4, `docs/uart-protocol.md`); this
file is the same facts in the form a tool can check. **Change both together**, or a diagnostic
will confidently name the wrong wire.

## Levels: audio levels and every macro

The report has a `levels` section and it reads it from `engine.levels` (namchain `a69d315`), which
is also what the ljoss meters will poll. **Landed 2026-10-05**, in this shape:

1. **namchain** gains `engine.levels`, a read-only method with a small answer: device input and
   output peaks and RMS per channel, each chain's output, and every plan node's output keyed by
   its ljoss `element` — which is what "every macro in the running rig" means, since namchain
   lowers a macro into primitives that keep their `element`. Peaks are computed where the render
   loop already scans every output sample (`outputs_finite`), stored per plan as integer
   accumulators and float bit patterns (never a torn scalar), and read by the control thread. It
   also adds `format` and a real `backend_diagnostics` for ALSA, both of which the engine already
   knows and simply never publishes, and an `element_clip` issue, because `pcm_encode` clamps
   silently today.
2. **ljoss** polls `engine.levels` at 20 Hz and draws meters on the Input/Output tiles, a bar on
   every block tile, and a master in/out pair with a latching clip. Same method, same numbers,
   different cadence — ljoss talks to `namchaind` directly (D2), so no new credential surface and
   no `pedald` in the path.
3. **pedal-diag** reads the same `engine.levels` in its sample and reports the things only a level
   can show: a dead input, a hot channel, a saturating output, and *which* block is eating the
   level. It reads until a window has samples in it, because every read **empties** the probes and a
   read that lands between two blocks is a window of nothing — which is not the same as silence, and
   reporting it as `-200 dBFS` would be the tool inventing a fault out of its own timing. That trap
   is pinned by a test: a quiet guitar at −60 dBFS must be reported as a level, not as a dead input.

A client that does not see `levels` in `engine.hello`'s features gets the "unavailable" line instead,
because there is nothing to read rather than nothing to hear.

## Adding a check

A check is a finding, and a finding has four parts: a severity, a sentence saying what is wrong,
the evidence it came from (a file and a value), the ranked likely causes *each naming a physical
thing*, and the measurement that settles it. If a check cannot name what to measure next, it is
not finished — that is the bar the whole tool is built to.

1. Put the expectation in `pedal-interface.json` if it is a fact about the hardware.
2. Add the read to the gatherer (`GATHER_SOURCE`) — and to the read-only whitelist's keeping,
   because `test_diag.py` asserts the gatherer opens no sound device and writes to nothing.
3. Add the finding to `build_report`, with a fixture in your head: which mutation of a healthy
   sample should produce it?
4. Add that mutation to `devices/common/tests/test_diag.py`, using the real capture in
   `tests/fixtures/diag/healthy-vip.json`. The faults that have actually happened are the ones
   worth encoding — each one in the tests is a fault that cost somebody an evening.

# The pedal service

**Status:** design, 2026-09-28 (plan Phase 3.2). This decides what the service owns, where it
sits, how the library is stored and uploaded, how the footswitch and MIDI vocabulary is mapped,
and how it fails. It also settles the two questions [`uart-protocol.md`](uart-protocol.md)
deferred here: the relay-on-link-loss policy and the MIDI channel. The implementation is staged
at the end; [`pedal-resume`](../devices/common/rootfs/usr/local/sbin/pedal-resume) is the
service's v0.

## What it is, and what it is not

One process on the Core host (`piv` today, `vip` when it arrives), beside `namchaind`. It is the
pedal's control plane: the library and the bank on the device, resume, uploads, the mapping
tables, the Pico link, and — once namchain's M3 lands — the rigs one press away.

| Job | Owner |
|---|---|
| The rig document: library, editing, flattening into a graph | ljoss |
| The running plan, ramps, transitions, the device and its health | `namchaind` |
| The library on the pedal, the bank, resume, uploads, the mapping tables | **the service** |
| Keeping rigs ready and switching to one (`rig.ready_set`/`rig.switch`, M3) | `namchaind`, asked for by the service |
| The physical controls, the relay, the display | the Pico |
| Audio | nobody in this table: no part of the service is in the signal path |

It never:

- touches ALSA, the codec, I2C, the render core or an audio buffer (D4, `CLAUDE.md`'s hard
  constraints);
- becomes the only route to the engine: the app keeps its direct protocol-2 connection (D2), and
  the person at the pedal keeps playing when the service is down;
- writes a file the engine is reading, or a byte outside `/var/lib/pedal` and the journal;
- treats itself as critical. **The service being down must never mean audio is down** (D4).

## Beside the engine, not in front of it

Decided: **beside**. ljoss keeps talking to `namchaind` directly (D2), and the service is a
second client of the same engine, not a gateway.

- Knob streams decide it. ljoss sends a patch every 10 ms while a control moves; a proxy would
  add a hop to every one of them and, worse, an upgrade or a crash of the service would
  interrupt live editing that the engine is happily serving. That is exactly the failure
  separation the service exists to have.
- The contract decides it too. Protocol 2 lives in namchain and its consumers link to it
  ([working-across-repos.md](working-across-repos.md), rule 2). Fronting the engine would create
  a second contract — a service protocol that proxies the first — with two places to evolve.
- What "in front" would buy is not worth it: one endpoint instead of two, one host to discover
  instead of a name with two ports, one token to store. Two ports on one host, one credential
  and one mDNS name (a debt-register item either way) cover the same ground, and a browser UI is
  a new client of the two existing contracts rather than a reason to build a third.

So the Core host has two listeners:

| Endpoint | Default | Protocol | Clients |
|---|---|---|---|
| `namchaind` | TCP 47810, token from `/etc/namchain/token` | protocol 2 (namchain's) | ljoss, `namchainctl`, the service |
| the service | HTTP 47820, same token | this document | ljoss, scripts, a browser later |

**The service reaches the engine over TCP at `127.0.0.1:47810`, not the Unix socket.** On Linux
a Unix-socket reply is one datagram, about 208 KiB with the kernel default, and `engine.assets`
or `engine.schema` is about 1 MB for a library of 1,500 impulse responses — the exact case
`docs/daemon.md` warns about. TCP has no such limit. The tiny calls pay for a length prefix, and
one transport is worth more than the prefix costs. (`namchainctl` over the Unix socket stays the
operator's tool.)

A consequence of being a network client: a document the service applies may name models and IRs
by **library id only**, never by absolute path (`path_refused`). That is the portable-rigs rule
anyway (D3), and the service refuses to *store* a rig document that contains an absolute path for
the same reason.

## The process

- `pedald`, Python 3, standard library only. The service is control-plane I/O: a 1 Hz status
  poll, a 115200-baud link, a handful of HTTP requests. Python is what `pedal-resume` is written
  in, what the user reads when something is wrong, and small enough for `vip`'s 1 GB.
- `pedald.service`: `Wants=namchaind.service` and `After=namchaind.service` (it follows the
  engine and never holds it up), `Restart=always`, `RestartSec=2`, `Nice=10`,
  `IOSchedulingClass=idle`, `CPUAffinity=0-1` — housekeeping cores only. Core 3 renders, core 2
  is where a second chain would go (`devices/piv/rootfs/etc/pedal/tune.conf`).
- `/etc/pedal/pedald.json`, JSON like `namchaind.json` and with the same rule: an unknown key is
  an error, not a shrug. Keys: the engine's `tcp_address`/`tcp_port`/`token_file`, the UART
  device and baud, the HTTP bind/port, the roots under `/var/lib/pedal`, the size caps, the log
  level. `devices/<host>/` installs it like the rest of the appliance configuration.
- The resume job folds in. `pedald seed` stays namchaind's `ExecStartPre` (a one-shot that must
  run before the engine starts); `pedald run` is the service. `pedal-resume.service` retires
  when `pedald.service` lands, so there is one writer of `last.json`, not two.
- Logs go to the journal. **Nothing goes on the UART that is not a protocol frame** — the
  contract says so; the UART is not a debug port, and the Pico's USB console is where the
  firmware talks.

## Storage

```
/var/lib/pedal/                      # the roots namchaind.json already names
├── library/
│   ├── models/<id>.nam              # every .nam under the root is a model (namchain docs/assets.md)
│   ├── irs/<id>.wav | <id>.nam      # every .wav/.nam under the root is an IR
│   └── rigs/<name>.json             # saved documents; last.json, last.prev.json reserved
└── state/
    ├── bank.json                    # banks, their rigs in order, the last position
    └── midi-map.json                # PC → rig, CC → parameter, bank select, the assignable switch
```

- **Writers.** The service owns every write under `/var/lib/pedal` after this design, with one
  deliberate exception: `scripts/sync-library` rsyncs the operator's Mac library into `models/`
  and `irs/` (Phase 1, and it stays that way — it is how the library gets there with no app).
  The operator may drop files in by hand. Nothing watches the directories and nothing scans on a
  timer (the engine's rule): a file appears via `POST /library/refresh` or a reboot.
- **Uploads stage, then rename.** The bytes go to `.<name>.part` in the destination directory,
  are fsynced, and are renamed into place. The engine's scan skips dot-names, so a half-written
  file is invisible to `engine.assets` even before the rename, and the rename is atomic on one
  filesystem. After any rename: `engine.assets {"refresh": true}`.
- **Writes are atomic in the `pedal-resume` way** — temp, fsync, rename, fsync the directory —
  for the library and for `state/`. A power cut costs the upload or the last few seconds of
  edits, never a good file.
- Everything the service writes lives under `/var/lib/pedal`; `/etc/pedal` and `/etc/namchain`
  are configuration installed by `devices/`, and Phase 4's overlayroot is the reason.
- `devices/<host>/backup` gains `/var/lib/pedal/state`: the bank and the map are user data like
  rigs. The model and IR library is on the Mac and is not backed up from the pedal.

## Resume

The behaviour of v0, with one owner and one difference — the service also knows the bank:

- **Boot.** `pedald seed` (namchaind's `ExecStartPre`, prefixed `-` so it can never fail the
  start) copies `default-rig.json` to `rigs/last.json` if there is none. namchaind compiles and
  prewarms that before the clock starts, so the first block never pays a node's cold cost.
- **Saving.** The service polls `engine.status`; on a generation change it reads `rig.get` and,
  after 2 s of quiet, writes the running document to `last.json` and the previous one to
  `last.prev.json`. Documents are compared, not generations: a smoothed knob leaves the
  generation alone. The settle window is what makes a knob drag one write to the SD card rather
  than hundreds.
- **Position.** The running document is the truth. `state/bank.json` holds the last position as a
  hint, and at boot the service finds the rig's place by matching the running document against
  the library (canonical JSON, by content). A document the library does not have — an
  app-applied rig that has not been saved to the library — is a rig with no position:
  `rig_index` -1 in `STATE`.

## The upload API

HTTP/1.1 on 47820, JSON, `Authorization: Bearer <token>` on every request, `Content-Length`
required (no chunked bodies). This is the API the debt register's "no way to upload from the
app" and ljoss's "send to pedal" were waiting for.

| Method | Path | Body | Answer |
|---|---|---|---|
| `GET` | `/status` | — | service version and uptime; engine state, health and generations; the link; the bank and position; library counts; the ready set when M3 exists |
| `GET` | `/library/models`, `/library/irs` | — | the engine's `engine.assets` scan, ids and all — there is no second scan |
| `GET` | `/library/rigs` | — | the rig names, and which one is running |
| `PUT` | `/library/models/<id>` | the `.nam` bytes | 201 and whether it replaced; a declared rate other than 48000 is refused |
| `PUT` | `/library/irs/<id>` | the `.wav` or `.nam` bytes | 201; any rate is stored — `nc.cab.ir` resamples 44.1/96 kHz, and the engine refuses at compile time what it cannot use |
| `PUT` | `/library/rigs/<name>` | the document | 201, stored, **not applied**; absolute model/IR paths refused |
| `POST` | `/library/refresh` | — | the scan (the service does it after every upload anyway) |

- **Ids** are the path under the root with the extension removed (`assets.md`): UTF-8, `/`
  separates group from name, extension required — `.nam` for models, `.wav`/`.nam` for IRs.
  Refused: absolute paths, `..`, empty or dot-leading components, control characters, backslash,
  over 200 characters. Every write path is resolved and checked to be under its root before
  anything is created.
- **Overwrite is the default**, and the answer says whether it replaced: a "send to pedal"
  repeated after an edit should not need a delete first. Deletion is deliberately absent for now
  — a model the library lists may be named by rigs, and removing it is a library-management job
  with a UI that shows what would break. Over ssh is the escape hatch.
- **Caps** (configurable): a model 16 MiB, an IR 64 MiB, a rig 1 MiB (the engine's own TCP
  request cap). The cap is checked from `Content-Length` before the body is read. Free space is
  checked with `statvfs` and a full card is answered 507 rather than half-written.
- **A model's rate is the one thing the service refuses on.** The engine cannot resample NAM
  models (debt register), so a model that declares a rate other than 48 kHz is refused at the
  door, quoting the rate it declares; one that declares none is stored, and the engine's load is
  the final word. The service reads the same header sniff the engine's scanner reads; it never
  loads a model either.
- **Rig documents are stored, not applied.** The app owns the document and applies it to the
  engine itself (D2). The library entry is what the bank and the ready set can name, and what
  the resume snapshot is compared against.

## The event vocabulary, and the mapping tables

The UART contract fixes the vocabulary (`kind`, `a`, `b`) and says the service's tables key on
`kind`, never on `source`. This is the policy those tables implement.

A **bank** is 4–8 rigs the footswitches step through, in order (`bank.json`); the last position
is remembered. The **ready set** is the current bank plus every rig a PC can jump to (D10); the
service derives it, and it is not the same thing as a bank.

| Kind | Default action |
|---|---|
| `rig_up`, `rig_down` | step through the current bank, wrapping at the ends |
| `rig_select` | index within the current bank |
| `bank_up`, `bank_down` | the next/previous bank, landing on its first rig |
| `bank_select` | that bank, its first rig |
| `bypass_set`, `bypass_toggle` | mirror the relay's state for the panel and the app; no engine call |
| `cc` | the map: a parameter on the running rig; streamed only if `engine.schema` says it ramps, otherwise committed on release — one structural patch, not one per step |
| `pc` | the map: a rig **by name**; the jump may move the bank window, and the ready set follows |
| `expression` | reserved — mapped like `cc` if the expression jack survives the debt register |

- **Names, not indexes, in the map.** A PC entry names a rig; indexes are positions in a bank and
  a reordering must not silently repoint a MIDI pedal. `pc` may name a rig in another bank: the
  window moves to that bank and that position. A rig in no bank is legal — it joins the ready
  set, and the panel shows the name with `rig_index` -1.
- **The assignable footswitch is a `pc` sender.** The third switch's target is a program number
  in `midi-map.json`, and the same entry serves a MIDI pedal's PC. It needs no new kind and no
  protocol change; if it ever reads badly, a dedicated kind is a minor bump.
- **Bank select from MIDI** is CC0 (the convention: bank, then PC); CC32 is ignored — 128 banks is
  enough, and one rule beats two.
- **Unmapped `cc`** is acknowledged (the frame-level ACK is what the Pico needs) and counted;
  a learn UI can read the recent list later.
- **A CC's target** is an `element` (and optionally a `role`) plus a parameter, learned from the
  running document and checked against `engine.schema`. An entry that resolves to nothing is
  refused with what exists (logged, and in `/status`), never silently ignored.
- **MIDI channel: decided, ignored.** One controller today, and the vocabulary has no field for
  it. When a second controller on another channel matters, the cheap fix is the reserved `CFG`
  message: the service — which owns the map — tells the Pico which channel to keep, and the Pico
  filters in firmware. No event change, no version bump until it is needed.

## The relay, bypass, and what the panel shows

The relay is the Pico's, physically (Phase 3.6): de-energised is bypass. Its policy here is the
decision the contract deferred:

- **Link down: the Pico leaves the relay where it is.** The link is not in the audio path, and a
  broken link is not evidence that audio is broken; cutting a working audio path is the worse
  failure. The panel and the LED show the fault; a long press is a panic bypass and stays local
  to the Pico. The service's half of the same rule: log, reopen the port with backoff, keep
  polling the engine, and let the session come back on the next `HELLO`.
- **`audio_ready`** is `engine.status` with `state == "running"`, a document loaded and adopted
  (`audible_generation == generation`, `generation > 0`). A running engine with no rig is *not*
  ready: the relay stays in bypass and the amp hears the guitar, not silence. The flag tells the
  truth later too — a lost device clears it — and the flag is not the relay's rule.
- **Boot-only energise: decided.** The Pico energises on the first `audio_ready` after boot and
  does **not** de-energise when the flag goes false. namchaind retries a lost device every
  250 ms and systemd restarts it under `Restart=always`; a relay click mid-performance is a
  worse event than a moment of silence, and the panic bypass is under a foot. If the bench
  disagrees, this is one rule in the firmware.
- **`STATE.engine_bypass`** is the engine's mute (`engine.mute`), which the app may set. The
  service does not set it for a bypass: the relay has already disconnected the codec, and a mute
  on top would be a second, invisible state to explain.
- A switch that is not instant (the cold path, before M3) can leave the panel showing the
  requested rig name in a pending colour until `STATE` confirms it; the protocol's flags have
  free bits if a `switch_pending` bit is ever wanted, and this does not need one.

## The ready set, and the split with namchain (3.8)

- **The service owns** the bank, the MIDI map, and which rigs must be ready: the current bank
  plus every rig a PC can jump to (D10).
- **namchain owns** how: the tiers, the cost model, the memory and the threads
  ([rig-switch-strategies.md](rig-switch-strategies.md), E1/E2). The service does not measure RTF
  and does not guess what fits.
- **The calls the service needs** (a proposal for namchain's M3; the names are namchain's to
  choose, and they land engine-before-service per rule 4):
  - `rig.ready_set {"rigs": [names, in priority order]}` — hold these. The reply says what it
    granted, at which tier, and what it dropped, with the reason (budget, an all-on-infeasible
    rig, a missing model).
  - `rig.switch {"rig": name}` — crossfade to a ready rig now. Adoption is asynchronous as
    everywhere else: the reply is an acknowledgement and `audible_generation` is the truth.
  - `engine.status.ready` — per rig: tier, state (cold, loading, warm, catching up), and the
    same refusal reasons, so `/status` and the panel can show them.
- **One switch in flight, one pending.** A newer request replaces the pending target
  ([rig-switch-strategies.md](rig-switch-strategies.md)); the service implements it by keeping
  exactly one pending name. A bank change sends a new `ready_set`; the refill happens off the
  render core, in the engine.
- **Until M3 exists** the service switches with `rig.load`, which costs what the Phase 1 numbers
  cost (seconds), and the Pico's behaviour does not change. D10 is not met on that path and the
  plan already says so; the bank still works, and the first version can ship with it.

## Failure modes

The rule — the service down never means audio down — holds in every row because the service is
not in the audio path and the engine is a separate process with its own service manager.

| Failure | Audio | What the service does | What the player sees |
|---|---|---|---|
| The service is stopped, crashes or is upgraded | plays on | nothing; systemd restarts it in 2 s | link down after 1 s → panel/LED fault; presses do nothing; panic bypass still works |
| The service restarts | plays on | waits for `HELLO` (≤ 1 s), answers `WELCOME`, sends `STATE` | the fault clears; the display converges on the truth |
| `namchaind` is down or restarting | silent | status polls fail; `STATE` health fault, `audio_ready` 0; keeps retrying | fault on the panel; the relay is untouched (boot-only rule) |
| The engine's device is lost | silent until it returns | same; the issue is namchain's `device_lost` | fault; comes back when the device does (250 ms retries) |
| The UART device disappears on the Core host | plays on | reopens with backoff; logs once per state change, not per attempt | link fault on the panel |
| The SD card is full or read-only | plays on | uploads 507, the resume log says what failed, the last good `last.json` stands | nothing audible; uploads refused in the app |
| Power cut mid-write | off, then on | temp-file staging means the pedal comes back to the last good rig and library | the last upload or the last 2 s of edits are gone; nothing is corrupt |
| The token was rotated | plays on | re-reads the token file, logs `unauthorized`, retries both listeners' clients | uploads and switching limp until the files agree; the app says unauthorized |
| The service has a bug | plays on | worst case: switching, uploads and the library stop being updated | panel fault if it crashes; the engine, the app and the relay are unaffected |
| The app applies a rig while the service is switching | plays the last writer's rig | the engine is the only writer; the snapshot rule saves the outcome and the previous document | both writers are visible in the library and `last.prev.json` |
| Boot order: the service first, the engine later | silent until ready | retries `engine.hello` until answered | fault, then the boot sequence as normal |

## Security

The same token model as the engine, deliberately, and no second one:

- One pre-shared secret, at least 16 characters, plaintext on a trusted LAN, a tunnel if it ever
  leaves one. The service reads the engine's `/etc/namchain/token` rather than keeping a copy:
  one secret for one appliance, one credential for the app to store, and `deploy-engine` already
  generates it (it never enters git). The file is re-read when a connection is refused, so a
  rotation needs no restart of either process.
- Every HTTP request carries it (`Authorization: Bearer <token>`), compared in constant time. A
  failure is 401 and a journal line; three failures on one connection and the connection closes.
- The upload surface is the service's one new attack surface, so the rules above are enforced
  before anything is read or created: the size cap from `Content-Length`, the id rules, every
  resolved path under its root with `O_NOFOLLOW` on the final component, a dotfile staged in the
  destination directory, a `statvfs` check.
- No users, no roles, no audit log: a token holder can replace the library and the bank, exactly
  as they can rewrite the rig on the engine. That is namchain's stated threat model, and this
  design does not invent a second one.

## Testing

- The link: the frame codec, the session state machine, dedupe over eight sequence numbers and
  the `STATE`/`PONG` behaviour are a port of `firmware/tools/protocol-test.py`. Unit-tested
  against a pseudo-terminal, and run for real on the Mac against the Pico through the Debug
  Probe — the same wiring the firmware test uses — with a fake engine (`--engine dry`), so the
  bench loopback is the service's server side, not only a test script's.
- The engine client: against a real `namchaind` (`--backend null`) on the Mac, then on piv; the
  protocol 2 calls it answers are namchain's tests' subject already.
- The mapping tables and the writer's refusals (ids, escapes, sizes, rate, free space) are unit
  tests; the snapshot rule has one too.
- The ready set and switches: after M3, the plan's 3.8 switching soak (a switch every few
  seconds through a bank, glitch detector, render tail) is the acceptance test.
- Evidence goes in a `bench-results/`, never `/tmp` (rule 8).

## What is staged

- **v1** (the other half of Phase 3.4): `pedald` skeleton — config, engine client over TCP
  loopback, resume, the Pico link (`HELLO`/`WELCOME`, `EVENT`/`ACK` with dedupe, `PING`/`PONG`,
  `STATE` at 1 Hz and on change), `/status`, and switching via `rig.load`. This is what makes
  the footswitches real the day the firmware lands.
- **v2** (with Phase 3.5): the upload API and the refresh path; ljoss's "send to pedal" and the
  library listing.
- **v3** (with Phase 3.8): the ready set and `rig.switch`, once namchain's M2/M3 answer.

Each lands with the plan step that needs it, engine before service where the call is new
(`working-across-repos.md`, rule 4).

## What this leaves

- **The silent-input liveness check** (debt register, the I2S fault). It needs the capture
  stream, so it belongs in namchain; the service surfaces it as an issue and the Pico shows it
  when it exists.
- Deletion and replace policies for library files; resampling on upload; a second controller's
  channel; MIDI learn; authoring the CC → parameter map (it needs ljoss to name targets
  stably); mDNS; a browser UI.
- The exact `CFG` body the channel filter would use, and the baud rate, if step 4 measures that
  115200 is not enough (the contract says it will be).

# The pedal service

**Status:** design, 2026-09-28 (plan Phase 3.2). This decides what the service owns, where it
sits, how the library is stored and uploaded, how the footswitch and MIDI vocabulary is mapped,
and how it fails. It also answers the two questions [`uart-protocol.md`](uart-protocol.md)
deferred here: the MIDI channel, settled, and the relay's rule, proposed and yours to decide.
The service's v0 was [`pedal-resume`](../devices/common/rootfs/usr/local/sbin/pedal-resume), which
**retired on 2026-10-04**; **v1 is `pedald`**, landed the same day (783a8de, dcaf0e2), deployed on
vip, and running against a live Pico — see "What is staged" at the end.

**Reviewed by Claude, 2026-09-28.** The comments are at the end (R1–R15). The text already
carries the changes they propose, and where a choice is yours, it says so.

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
  is where a second chain would go (`devices/piv/rootfs/etc/pedal/tune.conf`). It runs as its
  own user, sandboxed: see Security (R11).
- `/etc/pedal/pedald.json`, JSON like `namchaind.json` and with the same rule: an unknown key is
  an error, not a shrug. Keys: the UART device and baud, the HTTP bind/port, the size caps, the
  log level. The engine's port and token file and the three roots are read from
  `namchaind.json`, as `pedal-resume` reads them, so each has one home (R12). `devices/<host>/`
  installs it like the rest of the appliance configuration.
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
    └── midi-map.json                # triggers (PC, CC, the footswitches) → actions
```

- **Writers.** The service owns every write under `/var/lib/pedal` after this design, with one
  exception for now: `scripts/sync-library` mirrors the operator's Mac library into `models/`
  and `irs/` (Phase 1: it is how the library gets there with no app). It mirrors with
  `rsync --delete --delete-excluded`, so it removes whatever the Mac doesn't have, an upload
  included. Until uploads exist (v3) it is the only writer of `models/` and `irs/`. With v3 it
  sends what changed through the upload API instead, and the service is the one writer (R10).
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
- `devices/<host>/backup` takes `/var/lib/pedal` less `library/models` and `library/irs`, so
  `state/` is covered as soon as it exists and **`library/rigs/` is covered too** (2026-10-05):
  `last.json`, `last.prev.json` and every stored rig have no other copy — `sync-library` carries
  models and IRs, not rigs — and it is small (12 KB for the two resume files, against 15 MB of
  models and 142 MB of IRs, which stay the Mac's, R13). `var/lib/pedal/soak` is excluded with
  them: soak results are evidence and belong in a repo's `bench-results/` (rule 8), not in a
  backup that is committed to git. Before the change the tar was 4.9 MB, of which the soak runs
  were 4.8 MB; it is 250 KB now.

## Resume

The behaviour of v0, with one owner and one difference — the service also knows the bank:

- **Boot.** `pedald seed` (namchaind's `ExecStartPre`, prefixed `-` so it can never fail the
  start) copies `default-rig.json` to `rigs/last.json` if there is none. namchaind compiles and
  prewarms that before the clock starts, so the first block never pays a node's cold cost.
- **Saving.** The service polls `engine.status` at 1 Hz anyway. When `generation` or
  `params_applied` moves, it reads `rig.get` and, after 2 s of quiet, writes the running
  document to `last.json` and the previous one to `last.prev.json`. Both counters, because a
  smoothed knob moves `params_applied` and leaves the generation alone; watching the generation
  alone would never save a knob (R2). Documents are compared before a write, as v0 compares
  them. The settle window is what makes a knob drag one write to the SD card rather than
  hundreds.
- **Position.** The running document is the truth, and `state/bank.json` holds the last position
  as a hint. At boot, and after any change the service didn't make, it finds the rig's place by
  the document's own name (`engine.status`'s `rig_name`) in the current bank, starting from the
  hint. A document whose content differs from the library's copy is the same rig, **modified**
  (the panel can mark it), not a rig with no position: matching by content would lose the bank
  the first time a knob moved after a save (R3). Names are unique in the library: the upload
  API refuses a second rig with a name it already has. A name the bank doesn't have — an
  app-applied rig not saved to the library — is `rig_index` -1 in `STATE`, and from there
  `rig_up` and `rig_down` step from the hint's position.

## The upload API

HTTP/1.1 on 47820, JSON, `Authorization: Bearer <token>` on every request, `Content-Length`
required (no chunked bodies). This is the API the debt register's "no way to upload from the
app" and ljoss's "send to pedal" were waiting for.

| Method | Path | Body | Answer |
|---|---|---|---|
| `GET` | `/status` | — | service version and uptime; engine state, health and generations; the link; the bank and position; library counts; the ready set when M3 exists |
| `GET` | `/library/models`, `/library/irs` | — | the engine's `engine.assets` scan, ids and all — there is no second scan |
| `GET` | `/library/rigs` | — | the rig names, and which one is running |
| `PUT` | `/library/models/<file>` | the `.nam` bytes | 201 and whether it replaced; a declared rate other than 48000 is refused |
| `PUT` | `/library/irs/<file>` | the `.wav` or `.nam` bytes | 201; any rate is stored — `nc.cab.ir` resamples 44.1/96 kHz, and the engine refuses at compile time what it cannot use |
| `PUT` | `/library/rigs/<name>` | the document | 201, stored, **not applied**; absolute model/IR paths refused, and a name another rig already has |
| `POST` | `/library/refresh` | — | the scan (the service does it after every upload anyway) |

- **A path names a file, and the id follows from it** (`assets.md`: the path under the root, less
  the extension). `PUT /library/irs/v30/57-cap.wav` stores the IR whose id is `v30/57-cap`.
  UTF-8, `/` separates group from name, and the extension is required: `.nam` for models,
  `.wav`/`.nam` for IRs. An upload that would give an id a second file (`cab.nam` beside
  `cab.wav`) is refused, because a document names the id and couldn't say which (R9). Refused
  too: absolute paths, `..`, empty or dot-leading components, control characters, backslash,
  over 200 characters. Every write path is resolved and checked to be under its root before
  anything is created. Rig names follow the same rules without the `/`; `last` and `last.prev`
  are reserved.
- **Overwrite is the default**, and the answer says whether it replaced: a "send to pedal"
  repeated after an edit should not need a delete first. Deletion is deliberately absent for now
  — a model the library lists may be named by rigs, and removing it is a library-management job
  with a UI that shows what would break. Over ssh is the escape hatch.
- **Caps** (configurable): a model 16 MiB, an IR 64 MiB, a rig 1 MiB (the engine's own TCP
  request cap). The cap is checked from `Content-Length` before the body is read. Free space is
  checked with `statvfs` and a full card is answered 507 rather than half-written.
- **A model's rate is the one thing the service refuses on.** The engine cannot resample NAM
  models (debt register), so a model that declares a rate other than 48 kHz is refused, quoting
  the rate it declares; one that declares none is stored, and the engine's load is the final
  word. The service reads the same header sniff the engine's scanner reads, and it never loads a
  model either. The rate follows the weights, at the end of the file (`assets.md`), so the check
  runs on the staged file, before the rename, not at the door.
- **Rig documents are stored, not applied.** The app owns the document and applies it to the
  engine itself (D2). The library entry is what the bank and the ready set can name, and what
  the resume snapshot is compared against.
- **Banks and the map have no endpoint yet.** Until v3 adds `GET` and `PUT` for `/bank` and
  `/midi-map`, `bank.json` and `midi-map.json` are written by hand. With no `bank.json`, the bank
  is the library's rigs by name, eight to a bank, so v1 works with nothing configured (R15).

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
| `cc` | the map: an action, or a parameter on the running rig (below) |
| `pc` | the map: an action, usually a rig **by name**; the jump may move the bank window, and the ready set follows |
| `expression` | reserved — mapped like `cc` if the expression jack survives the debt register |

- **The map goes from a trigger to an action** (R8). A trigger is `pc` *n* (with its bank) or
  `cc` *n*; an action is a rig by name, a bank, any kind in the table above (`rig_up`,
  `bypass_toggle`, …), or a parameter. A MIDI controller's "next" button arrives as a `cc` or a
  `pc`, and has to reach the same action as the footswitch: the service is the one place that
  knows the map, so this is where the two meet.
- **The footswitches are triggers too** (proposed in `uart-protocol.md` draft 2, U8; yours to
  choose). They send `cc` 80, 81 and 82, as a MIDI controller would, and the default map sends 80
  to `rig_down` and 81 to `rig_up`, with 82 the assignable one. Assigning it is a line in
  `midi-map.json`: a rig, a bank, a toggle. No new kind, no protocol change, and the same line
  serves a MIDI pedal sending the same controller. A switch acts on its press (127); the release
  (0) is there for a momentary action later.
- **Names, not indexes, in the map.** A PC entry names a rig; indexes are positions in a bank and
  a reordering must not silently repoint a MIDI pedal. `pc` may name a rig in another bank: the
  window moves to that bank and that position. A rig in no bank is legal — it joins the ready
  set, and the panel shows the name with `rig_index` -1.
- **A continuous controller drives only a rampable parameter** (R7): a MIDI knob or an expression
  pedal, streamed the way ljoss streams a knob (`rig-edits.md`, step 1): a `rig.patch`
  `set_param` at most every 10 ms, one in flight, the last value always sent. MIDI has no
  "release" to commit on, and a structural edit per CC step is how a heavy rig overruns
  (soak 1, plan 1.8). A parameter that isn't rampable takes a switch-type trigger — a `cc` read
  as on or off at 64, or a `pc` — and one structural patch per change.
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

The relay is the Pico's, physically (Phase 3.6): de-energised is bypass. Its rule is the
decision the contract deferred, and it is **yours to make** (R4). Proposed:

- **The relay passes the pedal only while audio is known to be flowing.** The Pico energises it
  once the session is up and `audio_ready` has held for 1 s. It drops to bypass when the link has
  been down for 5 s, or `audio_ready` has been false for 2 s, and engages again by the first rule
  when both recover. The three times are firmware constants, set on the bench in 3.6.
  - 5 s is longer than a service restart (1 s to notice, `RestartSec=2`, the next `HELLO`), so a
    crash or an upgrade of the service never clicks the relay. The engine plays on regardless.
  - 2 s is longer than `namchaind` restarting (`RestartSec=1`, then a compile and prewarm of
    ~20 ms a rig) or a device retry, so a blip is a moment of silence rather than two clicks.
  - What it covers that "leave it where it is" cannot: a Core host that hangs, or one that
    reboots while the Pico stays powered. Both run from the same 5 V, the Pico through its VSYS
    diode (`bom.md`), so a reboot is ~20 s of silence otherwise. 3.6 wants a booting `tib` to
    fall back to bypass, and Phase 3 is done when "the relay covers boot and failure".
    **Measured 2026-10-05** (`scripts/pico-power-test`, plan Phase 3.6): the assumption holds —
    on the header feed the Pico does not reset across a vip reboot or a shutdown (uptime 100 s →
    135 s and 190 s → 295 s), where on a USB-A port it does (48,930 s → 20 s). So link loss is the
    Pico's *only* cue during a Core host reboot, which is exactly what this rule reads.
  - What it costs: a click each way, and a service stuck in a crash loop leaves the pedal on dry
    guitar — audio, not silence, but not the rig either.
- **The alternative**, this document's first answer: leave the relay where it is on link loss,
  and energise it once, at boot. It never clicks after boot, but a hung or rebooting Core host is
  silence until the panic press.
- **The panic bypass** (a long press) is local to the Pico and holds until the player takes it
  off. It is sent as `bypass_set` so the panel and the app agree.
- **`audio_ready`** is `engine.status` with `state == "running"` and `audible_generation > 0`: a
  device open and a document adopted. Not `audible_generation == generation`: namchain reports
  the previous generation as audible while any chain is still moving, so that test is false for
  the length of every crossfade, and the flag would flicker on every switch and structural edit
  (R5). A running engine with no rig is not ready: the relay stays in bypass and the amp hears
  the guitar, not silence.
- The service's half of any rule: log, reopen the port with backoff, keep polling the engine,
  and let the session come back on the next `HELLO`.
- **`STATE`'s `engine_muted`** (draft 1 called it `engine_bypass`) is the engine's mute
  (`engine.mute`), which the app may set. The service does not mute for a bypass: the relay has
  already disconnected the codec, and a mute on top would be a second, invisible state to
  explain.
- A switch that is not instant (the cold path, before M3) can leave the panel showing the
  requested rig name in a pending colour until `STATE` confirms it; the protocol's flags have
  free bits if a `switch_pending` bit is ever wanted, and this does not need one.

## The ready set, and the split with namchain (3.8)

- **The service owns** the bank, the MIDI map, and which rigs must be ready: the current bank
  plus every rig a PC can jump to (D10).
- **namchain owns** how: the tiers, the cost model, the memory and the threads
  ([rig-switch-strategies.md](rig-switch-strategies.md), E1/E2). The service does not measure RTF
  and does not guess what fits.
  This moves the budget. `rig-switch-strategies.md` ("Limits") and plan 3.8 have the service
  working out each rig's cost and dropping candidates a tier when the budget is full. The engine
  is where costs are measured and where admission control (M2) will live, so this gives it to
  namchain, which D4's "keeping models loaded and ready" allows. **Yours to confirm**; if you do,
  those two places change to match (R14).
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
- **Until M3 exists** the service can only switch with `rig.load`. That is fast, ~25–35 ms to
  the new rig on piv (plan 1.7), but the rig starts from NAM's silence-state prewarm and sounds
  wrong for its first 170–340 ms, up to +15 dBFS from what it should be (E1). D10 rules that out
  on stage and puts 3.8 before the footswitches (3.5), so v1 switches this way on the bench only,
  to test the loop from a press to the engine (R1).

## Failure modes

The rule — the service down never means audio down — holds in every row because the service is
not in the audio path and the engine is a separate process with its own service manager.

| Failure | Audio | What the service does | What the player sees |
|---|---|---|---|
| The service is stopped, crashes or is upgraded | plays on | nothing; systemd restarts it in 2 s | link down after 1 s → panel/LED fault; presses do nothing; the relay stays (a restart is well inside 5 s); panic bypass still works |
| The service restarts | plays on | waits for `HELLO` (≤ 1 s), answers `WELCOME`, sends `STATE` | the fault clears; the display converges on the truth |
| `namchaind` is down or restarting | silent | status polls fail; `STATE` health fault, `audio_ready` 0; keeps retrying | fault on the panel; bypass after 2 s, under the proposed rule |
| The engine's device is lost | silent until it returns | same; the issue is namchain's `device_lost` | fault; bypass after 2 s, and back when the device is (250 ms retries) |
| The Core host hangs | silent (check in 3.6 whether a stalled output can repeat a buffer instead) | nothing: it isn't running | link down; bypass after 5 s |
| The Core host reboots while the Pico stays powered | silent for ~20 s | restarts with it | link down; bypass after 5 s; engages again on `audio_ready` |
| The Pico resets or crashes | plays on; the de-energised relay passes dry guitar meanwhile | sees the link drop; the session returns on `HELLO` | a moment of dry guitar, then the rig once `audio_ready` has held for 1 s |
| A rig in the bank won't load (`asset_missing`, `compile_failed`) | plays the rig it had: a failed load leaves the plan as it was | keeps the old position; reports the rig and the reason | the rig's name and the error on the panel; the next press moves on |
| The UART device disappears on the Core host | plays on | reopens with backoff; logs once per state change, not per attempt | link fault on the panel |
| The SD card is full or read-only | plays on | uploads 507, the resume log says what failed, the last good `last.json` stands | nothing audible; uploads refused in the app |
| Power cut mid-write | off, then on | temp-file staging means the pedal comes back to the last good rig and library | the last upload or the last 2 s of edits are gone; nothing is corrupt |
| The token was rotated | a gap: `namchaind` reads its token only at startup, so rotating it means restarting the engine | restarts with it (systemd copies the credential at start) | a moment of silence; the app says unauthorized until it has the new token |
| The service has a bug | plays on | worst case: switching, uploads and the library stop being updated | panel fault if it crashes; the engine and the app are unaffected; the relay drops to bypass only if it stays down past 5 s |
| ljoss applies a rig, or connects, while the pedal is on a rig the player chose | plays ljoss's rig | there are two writers, the service and ljoss, and the engine takes the last; the service sees the generation move, finds the position and saves as usual | today ljoss's rule on connect, "my document wins", undoes the player's choice (`rig-edits.md` C12; R6) |
| Boot order: the service first, the engine later | silent until ready | retries `engine.hello` until answered | fault, then the boot sequence as normal |

## Security

The same token model as the engine, deliberately, and no second one:

- One pre-shared secret, at least 16 characters, plaintext on a trusted LAN, a tunnel if it ever
  leaves one. The service uses the engine's `/etc/namchain/token` rather than keeping a copy of
  its own: one secret for one appliance, one credential for the app to store, and
  `deploy-engine` already generates it (root's, 0600, never in git). systemd hands it over
  (`LoadCredential=token:/etc/namchain/token`), so the file stays root's and the service never
  needs to read `/etc/namchain`. `namchaind` reads its token once, at startup
  (`src/daemon/config.cpp`), so rotating it means restarting the engine, a gap in the audio, and
  the service with it (R11).
- **The service runs unprivileged.** It is the one process with a port on the LAN that writes
  files, so it gets its own user and a sandbox: `User=pedal`, `NoNewPrivileges=yes`,
  `ProtectSystem=strict`, `ReadWritePaths=/var/lib/pedal`, `PrivateTmp=yes`, and
  `SupplementaryGroups=dialout` for the UART. A path-check bug is then a bug inside
  `/var/lib/pedal`, not a write as root. The tree under `/var/lib/pedal` belongs to that user,
  and `pedald seed`, still namchaind's `ExecStartPre`, keeps it so.
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

- The link: the frame codec, the session state machine, dedupe per session and the
  `STATE`/`PONG` behaviour are a port of `firmware/tools/protocol-test.py`. Unit-tested
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

Each version lands with the plan step that needs it, engine before service where the call is
new (`working-across-repos.md`, rule 4). D10 puts 3.8 before the footswitches (3.5), so the
pedal changes rigs for real only from v2 (R1):

- **v1** (the other half of Phase 3.4, the Core host's UART): the `pedald` skeleton — config, the
  engine client over TCP loopback, resume (`pedal-resume` retires), the Pico link
  (`HELLO`/`WELCOME`, `EVENT`/`ACK` with dedupe, `PING`/`PONG`, `STATE` at 1 Hz and on change),
  `/status`, and the mapping tables. It switches with `rig.load` on the bench only, to test the
  loop from a press to the engine; D10 keeps that path off the stage.
  **Landed 2026-10-04** (783a8de, dcaf0e2, in `devices/common/rootfs/usr/local/lib/pedald/`, 114
  tests under `devices/common/tests`, run by `devices/common/test-pedald` — on the Mac, which has
  `pty` and `http.client`, not on vip). Deployed on vip the
  same evening and running against a live Pico: `pedald 0.1 up: link /dev/ttyAMA0`, `Pico says
  hello: fw '0.1', protocol 1.0`, and the save rule wrote `last.json` for the app's rig. Three
  things the implementation settled that the design above does not say:
  - **The save rule (R2) needs a third input.** Watching `generation` and `params_applied` alone
    never saves a switch: a `rig.load` moves the rig's path and name and leaves both counters
    alone, measured on vip. `pedald` watches the rig the engine reports as well.
  - **The session is re-established by any valid frame, not only by `HELLO`.** Once its own
    session is up the firmware stops sending `HELLO`, so a Core that drops its half would wait
    for a message that cannot come while its own `PONG`s kept the Pico up. Found on the bench, not
    by the unit tests; the rule now lives in [`uart-protocol.md`](uart-protocol.md).
  - **The HTTP server is ours; the link is `termios`.** The server is written out rather than
    built on `http.server`, which gives request parsing and none of the rules below, and it is
    tested as such. The UART sets its own line discipline through `termios`. Both began as
    workarounds — the Core host's Python was `python3-minimal` that evening — but the image
    carries the full `python3` now (`libpython3-stdlib`; `devices/vip/packages` lists it), so the
    link no longer shells out to `stty`, and the server stays by choice. **The service requires
    the full standard library**, and the package list is where that requirement lives. It runs
    unprivileged (`User=pedal`, `ProtectSystem=strict`, the only writable path
    `/var/lib/pedal`, the token through `LoadCredential`), and the bearer is compared with
    `hmac.compare_digest` and fails closed.
- **v2** (with Phase 3.8, once namchain's M3 answers): the ready set and `rig.switch`. From here
  the footswitches and MIDI change rigs for real, and firmware v1 (3.5) has something to drive.
- **v3** (no plan step yet; it pays off the debt register's "no way to upload from the app"): the
  upload API and the refresh path, the `/bank` and `/midi-map` endpoints, ljoss's "send to
  pedal" and the library listing, and `sync-library` moving onto the API.

## Implementing what is left, in order

v1 is deployed and running (2026-10-04). This is the order for the rest, and each step is meant
to be green on its own: engine before service wherever the call is new (rule 4), and nothing
here changes the audio path.

**1. v1's loose ends** (no plan step; each is small and independently checkable)

- **`log_level` is read and ignored.** `pedal-device` enforces that every key in `pedald.json`
  is one the service knows, and then the service ignores this one. Either honour it (the `log()`
  every module takes already funnels every line) or drop the key — a key that does nothing is a
  lie in the same way a misspelling would be.
- **The event path on the board.** The bank is empty because `/var/lib/pedal/library/rigs/` holds
  only `last.json` and `last.prev.json`, so a press has nothing to load. Put one rig there, press
  `e` on the Pico's console, and watch the engine change rig and `STATE` go back: that is 3.2
  v1's bench loop, and it is the one acceptance D10 allows before 3.8.
- **`/status`'s `pico` is empty after a service restart.** The firmware stops sending `HELLO`
  once its session is up, so a restarted service never learns the version until the Pico resets.
  Decide: report "unknown" (today's behaviour, honest) or add a query to the reserved `CFG`
  message. Do not invent a `HELLO` from the Core — the direction is the Pico's.

**2. The relay rule's firmware half (R4, Phase 3.6).** The service's half is already on the
wire: `STATE`'s `audio_ready` is `state == running` and `audible_generation > 0`. **The three
times are the owner's to confirm** (bypass after 5 s without the link or 2 s without
`audio_ready`; engage after 1 s of both). Then it is firmware work in `firmware/`, and it is
Phase 3's "the relay covers boot and failure".

**3. v2: the ready set and `rig.switch`** (with Phase 3.8, once namchain's M3 answers).

- **Engine first** (rule 4): `rig.ready_set {"rigs": [... in priority order]}`, `rig.switch
  {"rig": name}`, and `engine.status.ready` per rig (tier, state, refusal reason). The names are
  namchain's to choose.
- **Service**: derive the ready set (the current bank plus every rig a PC can jump to, D10),
  keep one switch in flight and one pending, send a new `ready_set` on a bank change, and surface
  the per-rig state in `/status` so the panel and ljoss can show it.
- **Confirm R14 first**: this design gives "what fits" to namchain; `rig-switch-strategies.md`
  ("Limits") and plan 3.8 give it to the service. One of the two must change, and it changes
  before this step is written.
- **Acceptance**: the 3.8 switching soak — a switch every few seconds through a bank, the glitch
  detector, the render tail.

**4. v3: the upload API and the library** (no plan step; the debt register's "no way to upload
from the app"). Service only — no engine change.

- `PUT /library/{models,irs,rigs}/<path>`, `GET` the three listings, `POST /library/refresh`,
  and `GET`/`PUT` for `/bank` and `/midi-map`. The path names the file and the id follows from it
  (R9); stage by dot-name, fsync, rename, then `engine.assets {"refresh": true}`.
- **Build the listener with `max_body=cfg.max_ir_bytes`.** `httpd.Server`'s default is 1 MiB,
  which would answer a model or an IR with 413 before its route ever saw it — this is the one
  transport detail v3 must not forget.
- Refusals to keep asserted: a declared body over the cap (413, from `Content-Length`, before
  reading), free space (`statvfs`, 507), a model whose declared rate is not 48 kHz (checked on
  the staged file, after its weights, R9), a second file for an id that already has one, absolute
  paths, `..`, control characters, an over-long id, and a rig name that another rig has.
- **Then `sync-library` moves onto the API** (R10) and the service becomes the only writer of
  `models/` and `irs/`.
- **Acceptance**: upload one of each kind over the LAN from the Mac, watch the engine's scan pick
  it up, and play a rig that names the new id; then the refusals above.
- ljoss's "send to pedal" is the client of this, and lands in ljoss after it.

**5. What other repos owe this.** R6 (ljoss "my document wins" on connect) must be decided
*before* v2 puts switches under the player's feet. The MIDI channel wait for a second controller.
The map's learn UI waits for ljoss to name targets stably. The silent-input liveness check is
namchain's, and the service surfaces it as an issue once it exists.

**6. Housekeeping that keeps the above honest.** New routes arrive with tests, and the transport
rules (401, 404/405, 411, 413, the three-failures close, the `"GET /path"` key convention) stay
asserted. `devices/vip/components.lock` is re-stamped by the next apply on a clean tree (it reads
`-dirty` today). The service needs the full `python3`: keep it in `devices/vip/packages`, and
remember that an apply is what moves the running service to the tree — vip currently runs the
build from before the `termios`/`hmac` change.

## Threads: what owns one, and how to prove they come back

**Who has threads.** The HTTP server, and nothing else: one accept thread plus one per
connection, all daemons. The link, the engine client, resume and the mapping are single-threaded
and run on the main loop. That is also why there are no locks: the HTTP thread reads cached or
immutable state only (`self.status`, `link.open`, `session.session_up`, the counters) and never
calls the engine itself. **A v3 route that calls the engine from the HTTP thread** (refresh,
assets) breaks that argument, so it must either take a lock around the engine client or hand the
call to the main loop through a queue. Decide when the route is written, not after.

**What is already true**, measured against the module on the Mac (2026-10-04):

| | live `pedald-http-*` threads |
|---|---|
| after `start()` | 1 |
| 50 requests, each on a fresh connection, closed properly | 1 |
| 50 clients that connect and send nothing | **51** |
| those clients closed | 1 |
| `stop()` | 0 |

So the ordinary path and shutdown are clean. The defect is **unboundedness**: a connection that
never sends a request holds a thread until it goes away, with no cap and no read timeout. A LAN
client can open sockets until the service is a thread per socket (on a 1 GB Pi 5 that is a cheap
way to exhaust it), and a client that dies without a FIN — a Wi-Fi drop, which this box has —
leaves one held for as long as the kernel keeps the socket. namchaind caps its own TCP at
`tcp_max_connections` for the same reason; this listener caps nothing.

**What to fix, and how to check it:**

1. **Cap concurrent connections.** `Server(..., max_connections=N)`, default 8, with a
   `max_connections` key in `pedald.json` (and in the loader's known-keys map, or it is refused
   as unknown). Past the cap, accept and close at once with a log line — not a 500, which would
   claim the request was understood.
2. **Timeout a silent connection.** A deadline for the first request byte (5 s) and between
   keep-alive requests (30 s), after which the connection closes. `_Reader` needs a socket
   timeout it can act on.
3. **Make the threads attributable.** Name them per server (`pedald-http-<port>-conn`) or hand
   back the thread objects, so a test or `pedal-diag` can count *its own* server's threads.
4. **Fix the flaky assertion.** `test_httpd`'s `test_stop_is_safe_twice_and_leaves_no_thread_running`
   counts `pedald-http-*` process-wide while handlers from earlier tests are still unwinding — it
   failed four times and passed three across the seven runs done on 2026-10-04. With (3), assert
   on that server's threads and keep the deadline.
5. **Show it on the board.** Add `threads` (and a connections counter) to `/status`, or let
   `pedal-diag` sample `/proc/<pid>/status`; either way the number is visible over time.
6. **Churn gate.** Hold the host lock and hammer `/status` from the Mac for ten minutes — fresh
   connections, keep-alive, and sockets abandoned mid-request — sampling `Threads:` before and
   after. A flat line is the pass; it also covers the engine client's connection lifetime across
   an engine restart and the link's reconnects across a Pico reset. Evidence to `bench-results/`.

**What is not a leak, so nobody "fixes" it:** the per-connection thread while a request is being
served, a handler waiting on a slow client (bounded by (1) and (2)), and the accept thread —
one, by design.

## What this leaves

- **ljoss on connect** (`rig-edits.md` C12). Today ljoss applies its own document when it
  connects ("my document wins"), which would undo a rig the player chose on the pedal. ljoss
  should follow the device's rig, or ask; that is ljoss's change and your decision, and it is
  needed before v2 puts rig changes under the player's feet (R6).
- **The silent-input liveness check** (debt register, the I2S fault). It needs the capture
  stream, so it belongs in namchain; the service surfaces it as an issue and the Pico shows it
  when it exists. The relay rule can't see that fault either: the engine says it is running.
- Deletion and replace policies for library files; resampling on upload; a second controller's
  channel; MIDI learn; authoring the CC → parameter map (it needs ljoss to name targets
  stably); mDNS; a browser UI.
- The exact `CFG` body the channel filter would use, and the baud rate, if step 4 measures that
  115200 is not enough (the contract says it will be).

## Claude's review, 2026-09-28

The design is sound in its shape, and most of it stands: beside the engine, a second client over
TCP loopback, ids rather than paths, staging by dot-name, atomic writes, one scan (the engine's),
rigs stored but not applied, names rather than indexes in the map, one token, and the engine's
new calls proposed but left for namchain to name. Its engine facts check out against namchain
(`docs/daemon.md`, `docs/assets.md`, `src/daemon/config.cpp`) except where a comment says
otherwise. The text above already carries each change; **yours** marks a decision that is yours.

**R1. The staging contradicted D10, and 3.5 isn't uploads.** v1 switched rigs with `rig.load`
"the day the firmware lands", and uploads came "with Phase 3.5". D10 (yours, 2026-09-26) puts 3.8
before the footswitches, and 3.5 *is* the footswitches (firmware v1). The cold path isn't
"seconds" either: plan 1.7 measured 25–35 ms, but the first 170–340 ms sound wrong (E1).
Changed: v1 switches on the bench only, v2 is the ready set with 3.8, and uploads are v3, which
has no plan step yet.

**R2. Saving on a generation change would miss every knob.** A smoothed `set_param` leaves the
generation alone; `pedal-resume` says so in its own comment and polls `rig.get` instead.
Changed: watch `generation` and `params_applied`.

**R3. Matching by content lost the bank position.** The first knob moved after a save made the
running document match nothing, and nothing said what `rig_up` does from -1. Changed: match by
the document's name, "modified" when the content differs, unique names in the library; from no
position, step from the hint.

**R4. The relay rule — yours.** "Stay where it is on link loss, energise once at boot" leaves a
hung Core host, or one rebooting under a powered Pico, silent until the panic press. 3.6 wants
a booting `tib` to fall back to bypass, and Phase 3's "Done when" says "the relay covers boot
and failure"; the failure table had no row for either case. Proposed: bypass after 5 s without the
link or 2 s without `audio_ready`; engage again after 1 s of `audio_ready`. It costs a click
each way, and dry guitar if the service crash-loops. The first answer is kept as the
alternative.

**R5. `audio_ready` would flicker.** `audible_generation == generation` is false through every
crossfade. Changed: `audible_generation > 0` with the device running.

**R6. There are two writers — yours.** The service writes too (`rig.load`), and ljoss's "my
document wins" on connect would undo the player's choice (`rig-edits.md` C12). The failure table
said the engine was the only writer. Proposed: ljoss follows the device's rig on connect, or
asks, before v2.

**R7. MIDI has no "release".** "Committed on release" is a slider's rule (namchain's
`schema.md`). Changed: a continuous controller drives rampable parameters only, streamed as
ljoss streams (10 ms, one in flight, the last value sent); a non-rampable target needs a
switch-type trigger.

**R8. The map couldn't reach an action from MIDI.** It went PC → rig and CC → parameter, so a
MIDI "next" button couldn't reach `rig_up`, and the assignable switch, as a `pc` sender, could
only ever pick a rig. Changed: trigger → action. With the protocol's U8 (yours), the footswitches
send `cc` 80–82 and the map decides what each one does.

**R9. The upload path mixed ids and files.** An id has no extension while the path required one,
and `cab.wav` beside `cab.nam` would be one id with two files. A model's rate sits after its
weights, so it can't be refused "at the door". Changed: the path names the file, a second file
for an id is refused, and the rate is checked before the rename.

**R10. `sync-library` would delete uploads.** It mirrors with `rsync --delete --delete-excluded`,
so a model sent from ljoss that the Mac doesn't have would go at the next sync. Changed: it is
the only writer of `models/` and `irs/` until v3, and then goes through the API.

**R11. Token rotation, and running as root.** "A rotation needs no restart of either process" is
wrong for the engine, which reads its token once, at startup. And a root process with an upload
port on the LAN is the wrong default. Changed: `LoadCredential=`, its own user, and a sandbox
whose only writable path is `/var/lib/pedal`.

**R12. Configuration in two places.** `pedald.json` repeated the engine's port, token path and
roots. Changed: they're read from `namchaind.json`, as `pedal-resume` reads them (rule 1).

**R13. The backup's gap is rigs, not state.** `backup` already takes `state/`; it's
`library/rigs/` that it leaves out, and nothing else keeps a copy of those. Changed.

**R14. Who owns the switching budget — yours.** This document gives "what fits" to namchain;
`rig-switch-strategies.md` ("Limits") and plan 3.8 give it to the service. I'd keep this split:
the engine measures its own costs, and admission control is its M2. Neither of the other two is
changed yet.

**R15. Smaller things.** `engine_bypass` was the engine's mute: renamed `engine_muted` (protocol
U7). Banks and the map had no endpoint: with no `bank.json` the bank is the library by name, and
the endpoints come with v3. Rig names needed rules.

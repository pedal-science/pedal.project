# The pedal owns its state; ljoss and rigpa become views; rigpa gets a 4.3″ layout

**Status:** approved by Rik, 2026-11-07, and recorded as D17 in [`plan.md`](../plan.md). This is
the plan; where it stands is in `plan.md`'s "Next session starts with", not here.

## Context

Today ljoss owns the rig documents and the engine is "a sink, not a mirror". The decision record
behind that:

- [ljoss/docs/ENGINE.md](../../ljoss/docs/ENGINE.md), which says the app owns the document and nothing
  is rehydrated from the engine.
- [namchain/docs/daemon.md](../../namchain/docs/daemon.md), which calls `rig.get` "a diagnostic, not a
  document store".
- D2 and pedal-service.md's ownership table (row 1, "The rig document … | ljoss").

pedald sits beside the engine and owns the on-pedal library, the bank, resume and the mapping. Five
things follow from that split:

- **Nothing is pushed anywhere.** rigpa polls status at 2 Hz and the rig list every 5 s.
- **rigpa saves for itself.** It auto-saves its own edits and keeps its own undo.
- **ljoss overwrites the pedal.** ljoss applies "my document wins" on connect, undoing a rig the
  player chose with a footswitch (pedal-service R6, owed since 2026-10-09).
- **ljoss's library never reaches the pedal.** Files get there only through `scripts/sync-library`,
  which rsyncs with `--delete`.
- **The two apps offer different palettes.** ljoss shows about 100 block types of its own (27
  playable); rigpa shows the engine's raw types.

Separately, vip now sits in the **box** build (1590DD) with a Waveshare 4.3″ DSI QLED panel
(800×480, capacitive touch), and rigpa can't run on it:

- the layout is fixed at 1920×480;
- the unit starts only on an HDMI connector;
- `rotation: 270` is set for every host.

**Decision (Rik, 2026-11-07):** the pedal (pedald + namchaind) owns all data about its state and
about how that state can change: rigs, banks, the model/IR library and its files, and the catalogue
of blocks. Every UI is a view that sends commands and receives pushed updates. An update carries
both the cause and the result, e.g. "footswitch 2 pressed → rig switched to Clean", or "MIDI CC 11 →
Amp gain 6.2".

## Decisions (Rik, 2026-11-07, from the question rounds)

These are recorded as **D17** in `pedal.project/plan.md`'s Decisions table (M0). Superseded text gets
the usual "Superseded by D17" markers.

**The pedal and its protocol**

- **Two endpoints stay ("beside").** Edits still stream straight to namchaind. namchaind gains a
  subscription that pushes every change to every subscriber. pedald gains an event stream for
  pedal-level events: a trigger, the action it caused and the result; library, bank and
  saved-state changes.
- **The pedal auto-saves.** pedald writes the edited rig to its library entry once an edit settles,
  whoever made it. There is no Save button anywhere.
- **Performance changes are not edits.** Changes made by footswitches, MIDI and expression show in
  every UI, but they are not saved and do not mark the rig modified; reloading the rig restores its
  stored values. Edits come from ljoss, rigpa, and the encoder while it drives rigpa.
- **One shared undo history, kept by the pedal.** Undo in any UI steps back through the latest
  edits, whoever made them. Each rig has its own history, stored on the card beside the rig, so it
  survives switching away and restarts.
- **Resume brings back exactly what was playing,** performance changes included, as it does today.
  The pedal also remembers which values were performance changes, so they still aren't auto-saved
  after the restart.
- **The pedal serves the catalogue.** It is the engine's types plus named block templates made from
  ljoss's 27 playable blocks, with their names and 0–10 knobs, so ljoss and rigpa offer the same
  blocks. The ~75 unplayable ljoss blocks leave the palette.
- **What the engine can't play is hidden** until it can: lane pan, split modes other than a plain
  split, interface-only knobs. Visual-only data (layout, chain type, the template a block came from)
  lives in the engine document's `meta`.
- **Banks: view and reorder from both apps.** The footswitch/MIDI map stays a file for now, but
  every app sees what each press did.
- **The map file gains two actions now:** a switch that toggles a block, and a CC that moves a
  rampable parameter. Until the map editor and the MIDI firmware exist, these are the sources of
  performance changes.
- **Picking a rig plays it,** in both apps, so the rig you edit is always the one you hear.
- **Deleting the playing rig moves the pedal to its bank neighbour,** as a footswitch press would.
- **A new rig goes right after the running rig** in its bank if there is room (8 rigs). Otherwise it
  goes at the end of the last bank, starting a new bank if needed.
- **`scripts/sync-library` is retired.** pedald becomes the only writer of models and IRs.

**ljoss**

- **ljoss stops owning rigs.** Rig editing and rig management are disabled while it isn't connected.
  The offline state is empty: the pedal list and the Models & IRs library stay usable, and ljoss
  keeps no copy of any pedal's rigs.
- **Several connections, one view.** ljoss keeps a live connection to every known reachable pedal
  and shows one selected pedal.
- **The pedal list:** each pedal's name and whether it's connected, plus a "show disconnected"
  switch, off by default.
- **Recognising a pedal:** by an id generated once and stored with the pedal's data under
  `/var/lib/pedal`, carried in its backup. A restored card is the same pedal; a fresh card is a new
  one.
- **Finding pedals:** each pedal announces itself over Bonjour/mDNS, and ljoss also tries each known
  pedal's remembered address. A new pedal asks for its token once; BLE pairing stays a separate,
  later plan.
- **The first meeting with an unrecognised pedal** brings up a content-based comparison:
  - two boxes, "add to pedal" and "add to ljoss", both ticked by default, each expandable to
    per-file ticks;
  - identical content under another name counts as present;
  - a same-path clash keeps both, renaming the incoming file (e.g. `Twin (vip).nam`);
  - files coming into ljoss go to a folder chosen the first time (default: the first library
    folder), which ljoss remembers;
  - after the first meeting, a "Compare files…" action on each pedal runs the comparison on request;
  - **nothing is ever deleted, and no deletion is offered.**
- **ljoss's own rigs:** a one-off "Copy ljoss's rigs to this pedal…" offer, per rig, uploading the
  files each rig needs. Unplayable parts are reported and left out. The old files stay on disk,
  unused.
- **The model/IR picker lists the pedal's files only.** ljoss's own files reach a pedal through
  "Compare files…".
- **No "this computer" pedal.** Remove the run-locally controls from ljoss's UI, and stop the local
  start at launch. Leave the LocalEngine code in place, and build nothing new for running locally.
- **Mac only for now.** ljoss is built and checked on the Mac; iOS keeps compiling, with no device or
  simulator testing in this change.

**rigpa, 4.3″ (built first)**

- **Layout and choice:** landscape 800×480, selected at startup by a `rigpa.json` key with a
  command-line override. The bar layout stays the default.
- **Home is a big play view:** the rig name, its place in the bank and the next rig, the blocks as
  tap-to-toggle chips, and the cause of the last change. "Rigs" opens the rig list; "Edit" opens an
  ljoss-style chain editor.
- **First version:** switching rigs, editing blocks, building rigs, and the tuner. Every screen works
  by touch **and** by rotary/apply/back.

## Defaults (Claude's, approved with the plan)

- **Stale structural edits are refused.** A stale edit gets `if_seq` → `conflict`, and the app then
  adopts the pedal's document and says so. Knob streams stay last-writer-wins.
- **Adding a block that needs a file opens the picker first,** and cancelling adds nothing. So the
  pedal never holds a half-made block.
- **What counts as one undo step:** one gesture (tagged by the app), or a run of edits to the same
  control with gaps under 1.5 s.
- **Undo history limits:** 100 steps and 64 KiB per rig, 2 MiB in all. The limit is there because
  backups are committed to the public repo.
- **Edits from clients that don't name themselves** (old builds, scripts without `--client`) are
  shown but never saved.
- **After a crash, if `resume.json` doesn't match `last.json`,** value differences count as
  performance, so they are never baked into the stored rig.
- **A clashing incoming file is named after its source:** `Twin (vip).nam` into ljoss,
  `Twin (<computer name>).nam` onto a pedal.
- **Tokens:** a known pedal's token is tried only on a host whose Bonjour name or address matches
  that pedal. Anything else asks.
- **The panel:** its rotation (0 or 180) is set by looking at it in the box. If eglfs can't drive
  it, work stops and I report back.

## Who owns what, after D17

| What | Owner | How an app sees it |
|---|---|---|
| The running document, parameters, mute, health | namchaind | `engine.subscribe` events |
| Stored rigs, banks, saved state, undo history, the performance overlay, the pedal's id and name | pedald | `GET /events` (SSE) |
| Model/IR files and their hashes | pedald (the engine scans them) | `/library/…` and `library` events |
| The block catalogue | `engine.schema` + pedald's `templates.json` | `engine.schema`, `GET /catalogue` |
| A press, a CC → an action | Pico → pedald's map | `action` events: cause, action, result |

Edits go from the apps straight to namchaind: `rig.patch` streams, and `rig.apply` with `if_seq`,
each tagged with who made it. Commands go to pedald: switch rig, create/rename/delete rigs,
undo/redo, banks, files.

## Milestones

Two phases, in this order. A demo on the Mac, and Rik's review, follow every milestone.

### M0. Housekeeping (pedal.project, docs only)

- **Move this plan** here, out of the `plan/` folder that plan mode wrote it to at the workspace
  root, which `scripts/workspace check` refuses.
- **Record the decision.** Add D17 to `plan.md`'s Decisions table, and mark "Superseded by D17" on
  `docs/pedal-service.md`'s ownership row ("The rig document … | ljoss") and on R6, which this
  closes.

### Phase A: rigpa on the 4.3″ panel (first)

#### C1. Two layouts on one `rigpa_core`: compact Play, Rigs, Tuner and Settings (rigpa)

**Choosing the layout**
- A new key `display.layout` in `rigpa.json` takes `wide` (the default) or `compact`.
- A new flag `--layout` overrides it. An invalid value exits with code 2, as `rotation` does
  (`src/app/Config.cpp`, `src/main.cpp`).

**Sizes**
- A new `src/app/LayoutSpec.{h,cpp}`, exposed to QML as `App.layout`.
  - `wide` keeps today's numbers.
  - `compact` is:
    - 800×480, a 52 px top bar, a 40 px bottom bar, and no menu or info columns;
    - tiles of 132×72, a tuner bar of 560, a flowEQ curve of 280×188;
    - an 800 px keyboard and a 60 px title on the Play view.
- Make the sizes that are fixed in C++ settable:
  - `RigEditorModel`'s style gets a setter;
  - `TunerModel::kBarWidth` and `FlowEqModel`'s curve size become members;
  - the rig-list width setting applies to `wide` only.
- `qml/Theme.qml` reads every size from `App.layout`.
- `qml/Main.qml` takes its design size from `Theme`, picks `Shell.qml` or
  `qml/compact/CompactShell.qml` with a `Loader`, and sizes the keyboard from the layout.

**The compact views** (`qml/compact/`)
- **CompactShell:**
  - top bar: the title or rig name, a health dot and DSP %, and Undo/Redo where they apply;
  - bottom bar: the apply/back hints and messages.
- **PlayView:**
  - the rig's name, large;
  - "Bank 1 · 3 of 8" and "Next: Crunch";
  - the blocks as chips you tap to switch on or off;
  - a status line;
  - buttons for Rigs, Edit, Tuner and Settings.
- **RigsView:** the rig list, full screen, with New, Rename, Copy and Delete.
- **Tuner:** the existing `TunerView`, at compact sizes.
- **Settings:** today's settings, plus a Status page holding what `InfoPanel` shows.

**New in `rigpa_core`**
- `src/rig/PlayModel.{h,cpp}`:
  - its chips come from `RigDocument::flatten`;
  - a chip toggles through `RigSession::toggleBypass`;
  - it has its own `FocusRing` and a "last change" line.
- `src/pedald/PedaldStatus.{h,cpp}`: polls `/status` once a second for the bank position and the
  next rig. It is a stopgap, replaced by events in O5.

**Navigation and the encoder**
- `Navigator`'s `MainView` gains Play and Rigs, and `--view` accepts `play`, `rigs` and `edit`.
- The encoder rows for the compact views go into `docs/spec.md`:
  - **Play:** the chips, then the buttons.
  - **Rigs:** the rows, then the buttons.
  - **Edit:** the blocks in signal order.
  - **Deeper views:** as in `wide`.
- The Mac's key stand-ins and `--input` work unchanged.

**Checks**
- New `tst_layout`: both presets, config against flag, an invalid value.
- Compact rows in `tst_navigator`, `tst_tuner` at bar width 600, and the editor wrapping at 800.
- `PlayModel`: a unit test, plus a live test where `POST /event` moves the rig and the model follows.
- Screenshots at exactly 800×480: a `.dev/rigpa-compact.json` with scale 1, then
  `QT_QPA_PLATFORM=offscreen … --view play|rigs|tuner|settings --screenshot`.
- The wide screenshots taken again, to show they haven't changed.

#### C2. Compact editing (rigpa)

- New views in `qml/compact/`:
  - `ChainView.qml`: `RigEditorPanel`'s drag, trash and auto-scroll, with the compact style, and +,
    Undo, Redo and Back;
  - `KnobsView.qml`: the node editor's grid filling 800×388, with `FlowEqPanel` at its compact size;
  - `PickerView.qml` and `AddView.qml`;
  - the rig dialog, laid out above the 800 px keyboard.
- No model changes: `NodeEditorModel`, `PickerModel`, `PaletteModel`, `RigManager` and `EditStream`
  are reused as they are.
- **Checks:** `--input` scripts that open every overlay, with a screenshot of each; the existing
  live tests still pass.
- **Demo:** build a whole rig in the compact layout, rename it on the keyboard, and use the tuner.

#### C3. vip and the panel (pedal.project, rigpa's deploy)

1. **Read-only first,** under the host lock:
   - find which DRM card publishes the DSI connector: `/sys/class/drm/card*-*/status`, each card's
     driver, and `/dev/dri/by-path/`;
   - make one eglfs run with `QT_LOGGING_RULES=qt.qpa.*=true`.

   `drm_rp1_dsi` publishes the connector, not vc4, so `devices/vip/rootfs/etc/rigpa/kms.json` (which
   names vc4) has to change.
2. **The configuration:**
   - `devices/vip/rootfs/etc/rigpa/rigpa.json` gets `"display":{"layout":"compact","rotation":0}`,
     or 180 if the panel sits upside down. The common file stays the bar's.
   - `devices/common/rootfs/etc/systemd/system/rigpa.service.d/10-pedal.conf`: `ExecCondition`
     accepts a connected DSI connector as well as HDMI.
   - Update the comment in `20-vip.conf`.
   - `rigpa/dev/vip-vnc` runs at 800×480 for the compact layout.
3. **Deploy:** back up, apply, run `scripts/deploy-rigpa` (vip still runs 179e202), then
   `scripts/components-lock`.
4. **On the panel:** taps at the corners and on keyboard keys land where touched, and the rig name
   reads from standing height.
5. **Soak:** 10-minute legs (meters off, meters on, idle, `--demo-animate`) beside a heavy rig with
   its neighbour warm. 0 xruns. Evidence to `pedal.project/bench-results/<date>-rigpa-compact-vip/`.
6. **Records:**
   - `fleet/parts/rigpa-compact.json` and `fleet/builds/box.json`;
   - the rigpa-compact row in `docs/operations-plan.md`;
   - rigpa's `docs/spec.md` and `docs/plan.md`.

### Phase B: the pedal owns its data (engine, then service, then apps)

#### O1. namchain: events (the contract first, in `docs/daemon.md`)

**Protocol**
- `engine.hello` may carry `client: {name, version, instance}`, and the reply adds `connection`.
- New methods:
  - `engine.subscribe {events: [rig, params, state, assets], min_interval_ms, echo, documents}`;
  - `engine.unsubscribe`.
- Mutating requests may carry:
  - `tag`, which is echoed in the events;
  - `if_seq`, refused with `conflict` if the document has moved on.
- Replies and `rig.get` carry `seq`.
- New features: `events`, `client_name`, `op_tag`, `if_seq`.

**Event frames** carry `event` and no `id`:
- `rig.replaced`: why (load, apply, switch, reload or startup), the origin and the document.
- `rig.params`: coalesced values with their origins, each naming the document node it resolved to,
  from `ResolvedEdit`.
- `rig.patched`: a structural or bypass change, its ops and the document.
- `engine.mute`.
- `engine.state`: state, health, issues, rig, generation, warm and cost. It is compared at most every
  100 ms; DSP load and levels stay polled.
- `engine.assets`.
- `resync`.

**Implementation** (`src/daemon/daemon.cpp`, `include/namchain/daemon/daemon.h`)
- Each session gets an id, a name and a subscription.
- Events are sent on the control thread after every successful change, and also from
  `sync_warm_switch()`, SIGHUP and startup.
- `flush_subscriptions()` runs in the loop. Pending parameter values are flushed before a
  structural event, so the order holds.
- A subscriber whose unsent output passes 256 KiB has its events dropped, and gets `resync` once it
  is below 64 KiB again. The render path is untouched.
- `namchainctl` gains `--client`, `watch` and `set --tag`.

**Docs**
- An Events section in `daemon.md`.
- Rewrite "a diagnostic, not a document store" and the "no telemetry subscription" note.
- A note in `ui-integration-plan.md` §1.1.
- `sessions.md`: the recorder skips events.
- A pedal host needs `tcp_max_connections` of at least 8.

**Checks**
- `tests/test_events.cpp`:
  - origin and tag;
  - the resolved node, including a macro addressed by element;
  - structural changes carry the document;
  - `rig.replaced` on load, apply, and warm and cold switches;
  - mute, health and assets events;
  - coalescing: 100 ops in 50 ms give at most 2 frames, last value kept, order kept;
  - `echo: false`;
  - a slow reader gets `resync` and memory stays bounded;
  - `seq` and `if_seq`;
  - an unsubscribed client never gets an unsolicited frame;
  - SEQPACKET.
- `watch` in `tests/cli/run_ctl.cmake`, and the RTSan and TSan builds.
- On vip: `deploy-engine`, then a 10-minute soak with a subscriber and a 100 Hz knob stream. 0
  xruns and render p99 unchanged.
- **Demo:** `namchainctl watch` while a footswitch is pressed.

#### O2. pedald foundations (`docs/pedal-service.md` first)

**Identity**
- `/var/lib/pedal/state/pedal.json` holds `{id: uuid4, name: hostname, created}`. `pedald seed` and
  `run` create it, and the backup carries it.
- `GET /pedal` returns `{id, name, api: 2, service, engine: {port, protocol}, http: {port}}`.
- `PUT /pedal {name}` renames the pedal.

**`httpd.py`**
- Connection caps: 16 in all and 6 event streams, as `pedald.json` keys.
- A 5 s deadline for the first byte of a request.
- Handlers can return a stream or a file as well as JSON.
- Request bodies are streamed instead of built up with `bytes +=`.
- Thread names include the port, which also fixes the flaky thread-count test.

**The main loop**
- One `select` over the UART, the engine-event socket (from O4) and a wake pipe. This stops the spin
  when there is no UART.
- HTTP routes that need the engine queue their work to the loop and wait up to 10 s.

**`GET /events` (SSE)**
- `id:` is pedald's sequence number. A 512-event ring serves `Last-Event-ID`; anything older gets
  `resync` and then `hello`.
- A `: ka` keep-alive every 15 s.
- The events:
  - `hello`;
  - `action` (the cause `{source, kind, a, b, label}`, the action and the result);
  - `running` (rig, bank position, next rig, performance keys);
  - `saved`, `history`, `library`, `bank` and `engine`.
- A `Pedal-Client` request header names who caused a change.

**mDNS:** `devices/common/rootfs/etc/systemd/dnssd/pedal.dnssd` (`_pedal._tcp`, port 47820, TXT
`api=2 engine=47810`).
- systemd-resolved serves it: vip already runs resolved with MulticastDNS on, so no package is
  added.
- `pedal-device` restarts resolved when the file changes.

**Gaps fixed:** `library.put` accepts absolute paths; `daemon.py:808` mixes seconds and
milliseconds; `rename_in_bank` misses dict-shaped banks.

**Checks**
- `test_identity`.
- `test_sse`: format, replay, resync, keep-alive, caps, a slow client.
- `test_httpd`: caps, deadline, streams, thread names.
- The loop sleeps when there is no UART, and each fixed gap has a regression test.
- On vip: the churn gate from the "Threads" section of `pedal-service.md`, including abandoned SSE
  connections. Threads stays flat.
- From the Mac: `dns-sd -B _pedal._tcp` lists vip, and `curl -N …/events` shows a footswitch press.

#### O3. pedald: files and the catalogue

**Templates**
- `ljoss/Tools/export-templates` is built from the SwiftUI-free `Catalogue/` and
  `Engine/BlockMapping.swift`, the way `Tests/run-model-tests.sh` builds its tests.
- It writes the 27 playable blocks to `pedal.project/devices/common/rootfs/usr/local/lib/pedald/
  templates.json`, which is their one home from then on. For each block:
  - names, categories and symbols;
  - node slots and types;
  - controls, with their transforms (`direct`, `knob_decibels`, `knob_fraction`,
    `knob_attenuation`, `multiplied`, `option`, plus `engine_range`).
- Interface-only knobs are left out.
- Every transform can be inverted, so a knob's position comes from the engine's value and nothing
  extra is stored.

**`meta` conventions** (written up in `pedal-service.md`)
- Template nodes: `{template, slot}`.
- Lane gains: `{kind: "lane_gain"}`.
- Chains: `{source}`. The document: `{layout}`.
- The tuner: `{ephemeral: "tuner"}`.
- Ids stay as both apps write them today: element = block id, node = `<element>-<slot>`.

**Routes**
- `GET /catalogue`: the templates, each checked against `engine.schema` when the engine connects;
  those that fail are listed under `refused`.
- `GET /library/{models,irs}`: what `engine.assets` lists, plus `sha256` and NAM metadata.
  - The hashes are cached in `/var/lib/pedal/cache/hashes.json`, keyed by path, size and mtime.
  - A worker thread computes them.
  - The cache is left out of the backup.
- `GET /library/{models,irs}/<path>`: the file itself, with its sha256 as the ETag.
- `PUT …/<path>` with `If-None-Match: *`, which never overwrites:
  - 412 if the path exists;
  - 409 if the id already has a different file;
  - 413 if it is too large, 507 if the card is full;
  - 422 for a model that isn't 48 kHz.

  The file is staged as `.part`, hashed while it streams in, fsynced and renamed, and the engine
  rescans.
- `POST /library/refresh`.

**Retiring `scripts/sync-library`**
- Delete it. `scripts/soak/soak-replay` gets `--refresh-library-at` in its place.
- Remove its mentions:
  - pedal.project's `AGENTS.md` Commands, and `plan.md`;
  - `docs/`: `working-across-repos`, `pedal-service`, `pairing`, `pro`, `zap`, `vip-image`,
    `rig-edits`, `operations-plan`;
  - `namchain/docs/assets.md`;
  - rigpa's dev scripts and `docs/plan.md`.
- `rigpa/dev/dev-pedal` gives pedald an APFS clone of the library (`cp -c -R`), never the real
  `~/Documents/Audio`, now that pedald writes files.

**Checks**
- `test_uploads`: every refusal, no overwrite, a streamed 64 MiB upload with flat memory, staged
  files invisible.
- `test_listing`: a second listing hashes nothing.
- `test_catalogue`.
- From the Mac: upload a model and an IR, play a rig that uses them, and download one with a
  matching sha256.

#### O4. pedald keeps the rig

**Following the engine:** `pedald/events.py` opens a second engine connection as `client: pedald`,
subscribed to everything. It reconnects and resyncs with `rig.get`.

**What is playing:** `pedald/running.py`, pure, holds the engine document, the stored file and the
performance overlay. It classifies every change:

| The change | Treated as |
|---|---|
| pedald's own, tagged `perf:*` | performance |
| pedald's own, tagged `undo`, `redo`, `rename` or `load` | bookkeeping; `load` clears the overlay |
| from a named client | an edit: its keys leave the overlay, it becomes an undo step, and it is saved |
| a whole-document apply | merged key by key against the overlay; a tuner mount changes nothing once stripped |
| a document with another name | another rig is now running |
| from an unnamed client | foreign: shown, never saved |

**Autosave**
- 1 s after the last edit, pedald writes the edited document through `library.put` if it differs:
  overlay keys go back to their stored values and ephemeral nodes are stripped. SSE sends `saved`.
- A new `pedald.json` key, `autosave`, stays false on vip until O5 deploys. Until then rigpa's
  autosave is the only one running.
- Edits made while pedald was down are found on reconnect and saved as one undo step.

**Resume:** `last.json` stays the engine's document as played, performance included.
`state/resume.json` holds its hash and the overlay. At start, a matching hash restores the overlay,
so performance values keep playing and are still not saved.

**Undo** (`pedald/history.py`)
- One file per rig, `state/history/<rig>.json`, holding node-level reverse deltas. Steps and limits
  follow the defaults above.
- The file is written atomically with each autosave, moves when the rig is renamed and goes when it
  is deleted.
- `POST /undo` and `POST /redo` publish with `rig.apply`, `if_seq` and a tag, then put the current
  overlay back on top. `GET /history` lists the steps, and SSE sends `history`.

**Commands**
- `PUT /running {rig}` goes through the footswitch's path, with the cause "app". It answers 409 if
  the engine's verdict is `over`.
- `POST /library/rigs {name, from: null|rig|":running", document?, load}` covers new, duplicate and
  migration. A new rig is placed as D17 says.
- Rename also renames the running document, its history and its bank entries.
- Deleting a rig removes its history; if it was playing, the pedal moves to the bank neighbour.
- `GET /bank` and `PUT /bank`: every name must exist, no bank may be empty, and a bank holds at most 8
  rigs.

**Map actions** (in `state/midi-map.json`)
- `{block: "<element>"}` toggles that block's bypass, tagged `perf:`.
- `{param: {element, slot, param}}` on a CC drives a rampable parameter only, at most every 10 ms,
  one in flight.

**Checks**
- Unit tests: `test_running`, `test_autosave`, `test_history`, `test_resume`, `test_commands`,
  `test_bank`, and `test_mapping` for the block and param actions.
- A live test against a null-backend namchaind (skipped if there isn't one):
  - an edit reaches the file within 1 s;
  - a mapped `POST /event` toggles a block, leaves the file alone, and lists the block as
    performance;
  - undo restores the edit;
  - after both daemons restart, the document and the overlay are kept;
  - switching away and back restores the stored values.
- On vip, with autosave still off: measure press-to-switch with the T7 harness. If the loop adds
  more than 20 ms, move document parsing to the worker.

#### O5. rigpa follows the pedal (both layouts)

**Engine connection**
- `EngineClient` routes event frames.
- `EngineSession` says `client: rigpa` and subscribes with echo off.
- The status poll drops to 1 Hz, for DSP and xruns only. Levels stay polled.

**`RigSession`**
- It applies `rig.params` and replaced documents instead of re-reading the rig.
- Knob drags carry `g:<uuid>` tags, and whole applies carry `if_seq`.
- Undo and redo call pedald, and `canUndo`/`canRedo` come from SSE `history`.

**pedald's events:** `src/pedald/PedaldEvents.{h,cpp}` (SSE over `QNetworkReply`) replaces
`RigList`'s 5 s poll and C1's `PedaldStatus`.

**`RigManager`**
- Its own autosave goes, and the saved state comes from SSE.
- New, copy, rename, delete and save-as go through pedald.
- Loading a rig is `PUT /running`.

**Templates** (`src/rig/Templates.{h,cpp}`, transforms in both directions)
- `PaletteModel` lists the templates plus the engine's own types, including parallel split and
  flowEQ.
- Tiles and chips use template names.
- The node editor shows a template's 0–10 controls, and schema controls for raw nodes.
- `isLaneGain` reads `meta.kind` first, so a Gain block placed last in a lane is no longer mistaken
  for the lane's level.

**Also**
- An SSE `library` event triggers a rescan.
- A Banks view: a tab in Rigs on compact, beside the rig list on wide. It reorders by touch drag or
  the encoder and saves with `PUT /bank`.
- The Play status line shows real causes, e.g. "Footswitch 2 → Clean Lead" or
  "ljoss: Amp · Bass 6.2".

**Checks**
- Unit tests: `tst_engineevents`, `tst_pedaldevents`, `tst_templates`, and the lane-gain case in
  `tst_edits`.
- Live tests:
  - rig operations through pedald;
  - undo across clients;
  - a new `tst_follow_live`: a `namchainctl` edit reaches rigpa within 100 ms, and a `POST /event`
    shows on the status line.
- Screenshots of both layouts.
- Deploy to vip with `pedald.json` `autosave: true` in the same step.

#### O6. ljoss: pedals and viewing (macOS; iOS keeps compiling)

**New files**
- SwiftUI-free, so they compile into the test runner:
  - `Ljoss/Pedal/PedalProtocol.swift`, `SSEParser.swift`, `KnownPedals.swift`;
  - `Ljoss/Engine/EngineEvents.swift`;
  - `Ljoss/Engine/DocumentDecoder.swift`. It turns the engine document, templates and schema into
    template blocks, raw blocks and lanes, keeps the original ids, and gives a read-only reason
    for any graph it can't show.
- `meta` becomes a JSON value type, since rigpa writes numbers and booleans into it.
- `PedalDiscovery.swift`: an `NWBrowser` for `_pedal._tcp`.
- `PedalClient.swift`: URLSession, plus SSE with `Last-Event-ID`.
- `PedalSession.swift`: `@Observable`, one per pedal. It holds:
  - its `EngineSession`;
  - the running document and its view;
  - rigs, bank, saved and history state;
  - the catalogue and the file listing.

  Pedals not on screen subscribe to rig and state only.
- `PedalFleet.swift`: the known pedals, the selection, and `showDisconnected` (false by default).

**Tokens**
- Keychain service `namchain.control`, one account per pedal id. The old single token moves to the
  first pedal that answers at the old host.
- A Bonjour host is matched to a known pedal by name or address before any token is tried. If it
  matches none, "Add Pedal…" asks for a token once.
- Records are merged by id.

**`EngineSession`**
- Says `client: ljoss` and subscribes.
- On connect it reads the pedal's rig instead of applying its own. This removes "my document wins"
  (`EngineSession.swift:222-224`).
- `EngineClient.deliver` routes events.

**UI**
- A pedal list at the top of the sidebar: name, a connected dot, the "Show disconnected" toggle and
  "Add Pedal…". The selected pedal's rigs are listed below it.
- The detail shows the running rig, read-only in this milestone.
- Offline, an empty state, with the Models & IRs page still working.

**Removed:** the "This Mac" section of `Views/HardwareSettingsView.swift`, and the start at launch
(`App/LjossApp.swift:88-95` and `:114`).
- `LocalEngine*.swift` and `AppDelegate` stay.
- `RigLibrary` becomes a read-only reader of the old rigs, with no starter rigs and no writes.
- `NSBonjourServices` in `project.yml` gains `_pedal._tcp`.

**Checks**
- New test groups in `Tests/run-model-tests.sh`:
  - Decoder: an old rig encoded with meta decodes back; raw nodes made by rigpa;
    `default-rig.json`; a graph it can't show;
  - SSEParser, PedalProtocol, Registry, EngineEvent.
- Every ljoss milestone builds for macOS and also runs `xcodebuild -scheme Ljoss -destination
  'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build`.
- `Tools/check-device.sh` checks the subscription.
- **Demo:** ljoss finds vip, shows its rig, and follows a footswitch press with its cause.

#### O7. ljoss: editing through the pedal

**Templates**
- `Catalogue/Templates.swift` builds the components and mappings from the pedal's templates.
- `DocumentEncoder` takes its mappings from there, writes `meta.template` and `slot`, and keeps the
  original ids.
- `ParamTransform.invert` is added.

**Edits**, compared against the pedal's document:
- rampable values are sent as tagged patches;
- structural changes go as `rig.apply` with `if_seq`; a `conflict` adopts the pedal's document, with
  a notice;
- bypass is a patch op.

**The palette:** the pedal's templates plus the engine's own types. The ~75 unplayable blocks go,
and lane pan, splits other than Y and interface-only knobs are hidden. The picker lists the pedal's
files only.

**Commands**
- Undo and Redo (menu, toolbar, ⌘Z/⇧⌘Z) call pedald.
- New, Duplicate, Rename and Delete call pedald.
- Picking a rig is `PUT /running`.
- A `BanksView` with `.onMove` saves through `PUT /bank`.
- All of these are disabled when no pedal is connected.

**Checks**
- Templates: every transform both ways, at the knob's grid points and at `engine_range`.
- Encoder: templates as the source, meta written, ids kept.
- Edits: tags and conflicts.
- `Tools/check-streaming.sh`.
- **Demo:**
  - build a rig in ljoss on vip;
  - rigpa shows the same names and knobs;
  - Undo on rigpa reverts ljoss's edit;
  - reordering a bank changes the footswitch order.

#### O8. ljoss: files and migration

**Hashing:** `AssetEntry` gains `sha256` (a SwiftData lightweight migration). It is computed when
`AssetScan` reads a file, and the size and mtime cache stays.

**`FileComparison`**, pure:
- identical content anywhere counts as present;
- the same path with different content keeps both, the incoming file renamed after its source
  (`(vip)`, then `(vip 2)`);
- nothing is deleted or overwritten.

**`CompareFilesSheet`**
- Two ticked boxes, each with a per-file list.
- Uploads are `PUT` with `If-None-Match: *`; a 412 means rename and retry.
- Downloads go to the folder chosen once (default: the first library folder), keeping sub-folders,
  then the library rescans.
- It appears the first time ljoss meets a pedal id, and after that from "Compare files…".

**"Copy ljoss's rigs to this pedal…"**, one rig at a time:
- the rig is encoded by the old encoder and mappings, with meta;
- unplayable parts are reported and left out;
- file references are rewritten by hash, and missing files are uploaded;
- it is created with `POST /library/rigs {name, document}`;
- the old files are left alone.

**Checks:** FileComparison, Migration, and Assets (unchanged files aren't read again).
- **Demo:** compare files with vip, migrate a rig, see it in rigpa.

#### O9. Close-out (docs)

- pedal.project:
  - `plan.md` "Next session starts with";
  - `AGENTS.md`: the Architecture section, and the Commands list without sync-library;
  - `docs/working-across-repos.md`: the ljoss and rigpa rows;
  - `docs/pedal-service.md`: the staged versions, now v4;
  - `docs/pairing.md`: discovery is built.
- ljoss: `docs/ENGINE.md`, `ARCHITECTURE.md`, `ASSETS.md` and `AGENTS.md`. The `Pedal/` files join
  the test runner, and the stale local-engine-branch note goes.
- rigpa: `docs/spec.md` (Data, Saving, following other clients) and `docs/plan.md`.

## Working rules for every milestone

- Work in the repo that owns the change: engine before service before apps. Change a contract in its
  doc first: namchain's `docs/daemon.md`, pedal.project's `docs/pedal-service.md`.
- Every commit is green on its own and goes to `main`. Nothing is pushed until Rik says so, and
  `scripts/public-check` runs before any push.
- On vip: `scripts/host-lock`, a backup first, and no builds. Evidence goes in a repo's
  `bench-results/`.
- After each milestone: stop, demo on the Mac (screenshots and how to run it), and wait for review.

## Risks

- **eglfs on the DSI panel** (Mesa on `rp1-dsi`) and touch mapping. The fallback is software
  rendering on linuxfb, which is Rik's call.
- **800×480 is tight:** legibility from standing height, and a dialog has about 174 px above the
  keyboard.
- **Mistaking performance for an edit** would bake performance values into stored rigs. The
  classification, merge and resume rules carry most of the tests.
- **Events under load:** coalescing and ordering bugs, and memory on a 1 GB host (bounded by the
  outbox limit and `resync`).
- **While pedald is down,** nothing is saved and there is no undo. Edits are found when it
  reconnects.
- **Footswitch latency**, if pedald's loop parses large documents. Measured after O4.
- **Connection budgets:** namchaind's 8 TCP connections (pedald 2, rigpa 1, each ljoss 1,
  namchainctl), and pedald's own caps.
- **Mixed versions during the rollout:** feature flags, `api` and the `autosave` switch handle them.
  An old ljoss counts as foreign.
- **Undo history goes into backups,** which are committed to a public repo. It is bounded and holds
  no secrets.
- **systemd-resolved's DNS-SD responder** may misbehave. The fallback is avahi, a new package.
- **The 27 mappings exist twice** until migration is done: ljoss's old table and the pedal's
  templates. The old table goes once migration is finished.

## Verification, end to end (after O8, vip in the box)

1. ljoss starts, finds vip over Bonjour and shows it as connected. pro is hidden unless "Show
   disconnected" is on.
2. On a first meeting (a fresh card), the comparison appears with both boxes ticked. Untick one file
   and accept: files arrive both ways, a clashing file arrives renamed, and nothing is deleted.
3. Build a rig in ljoss. The pedal plays it, rigpa's play view on the panel shows the same blocks and
   names, and the pedal has saved it (`GET /library/rigs/<name>` matches) without anyone pressing
   Save.
4. Footswitch 2:
   - the rig switches;
   - ljoss and rigpa both show "Footswitch 2 → <rig>".

   Footswitch 3, mapped to a block:
   - the block toggles in every app;
   - the stored rig is unchanged;
   - reloading the rig restores it.
5. Undo on rigpa reverts ljoss's last edit. Restart the pedal: undo still works, and the
   performance toggle is still playing and still unsaved.
6. Take ljoss off the network: it shows the empty state, rig editing is disabled, and Models & IRs
   still works.

Each milestone's own checks are listed under it.

# Running the pedal as a fleet: the operations plan

**Status: a draft for the owner to check, 2026-11-03. Nothing in it is decided until then.** The
questions that need an answer are in "Decisions for the owner", near the end. `plan.md` stays the
record of where the pedal is; this page says how the work gets organised.

This repository is public, so this page names no network details, and neither must anything that
follows from it.

## The aim

We have stopped building one pedal. We now have three Cores in three kinds of box, and machines
around them that can build and test. The aim is four things that stay true from now on:

1. **Mix and match.** Any sensible combination of hardware and software can be named, checked and
   made, on purpose, without a special session of work.
2. **One way of proving things.** A Core is tested the same way as the others, scaled to what it can
   do, by a tool rather than by remembering what was run last time.
3. **Rebuildable from nothing, and shown to be.** GitHub, the cloud store and the vault are enough to
   produce every binary and a working device. We do it repeatedly, because a rebuild that worked in
   October says little about November.
4. **A public page that tells the truth.** pedal.science shows what is built with what, what it is
   running, how much of it has been proved and how recently, and what comes next, without saying
   anything that identifies the owner's home or network.

The point of all of it is pedals that get played. A phase that does not leave one of the builds
closer to that is the wrong phase, and it is cut.

## Where we are

Measured on 2026-11-03.

| Area | Today | The gap |
|---|---|---|
| Repositories | Seven public repos in `pedal-science`, one workspace, a guard (`scripts/workspace`) | stripmaster is outside `workspace.repos`, though the stripboard export reads back through it |
| CI | Only `namchain` and `NAMBench` have any, on GitHub's runners | Both are red: namchain's last push fails RTSan (a segfault in the unit tests) and TSan; NAMBench's conformance fails on three Linux jobs. Nothing covers `pedald`, firmware, rigpa, ljoss or rtpi in CI |
| What is running | `components.lock` per host: vip is on namchain `eba5eef`, piv on `d4fb8e5`, pro on `ae6f853` | Three engines on three hosts, and nothing says that is intended. Nothing states which versions belong together |
| Deploy routes | vip by image, built in colima on the Mac; piv and pro build on themselves | Three routes. Compiling on pro means it is not quiet, and its quiet was assumed until 2 Nov |
| Seeing it | `scripts/status`: text, one Core at a time, run by hand | No overall view, no history, nothing a browser can read |
| Tests | Strong but scattered: `test-pedald`, `measure-core`, `soak`, `measure-switch`, `benchtest`, `devices/<host>/check`, rigpa's live tests, ljoss's checks | Each is remembered and run by hand. pro still lacks vip's T2 and T10, and zap has nothing yet |
| Machines | M2 starts every deploy | A laptop is a single point of failure. mp has no docker, gh or ninja; piv's docker is off; no agent harness is installed on either |

**A clean clone cannot rebuild the pedal.** These exist only on the Mac:

| Input | Why it matters |
|---|---|
| `guitar-di.wav` (untracked, 7.8 MB) | `scripts/measure-core` copies it to the device, so a clean clone cannot measure a Core |
| `scripts/loop/`, `scripts/src/`, `scripts/measure-coexistence`, `scripts/README.md`, `docs/ensure-codec-amp-is-off.md`, `schematic/input-buffer/` (untracked) | Work that a lost laptop would lose |
| Kernel artefacts in `rtpi/build/` | `image.lock` pins them by hash, but they are in no archive, so nothing can fetch them |
| Model and IR library (64 models, 520 IRs, 55 MB) | Third-party files, rightly not in git. Small enough that storing it is easy |
| Enclosure sources (`*.blend`, `enclosure/assets/`) | Git-ignored, and the site's renders come from them |
| The vault's service token | In the Mac's login keychain, so only the Mac can make a card |
| Pico SDK and Arm toolchain in `~/pico` | Publicly downloadable, but not pinned by hash or fetched by a script |

**Some private details are already public.** A scan of the public repos found bench logs and a test fixture carrying a
home IPv6 prefix, a LAN address and device MAC addresses, and one committed page naming a LAN address.
The Wi-Fi name and the current external IPv4 were not found, in any tree or in history. Phase 0 deals
with it.

## The words we will use

Today "vip" means a computer, a box, and what it happens to be running. Mixing and matching needs
those apart.

| Word | Means | Example |
|---|---|---|
| **Core** | The computer that renders audio. It has an architecture, flags, a core split, a kernel route and a measured cost table | `zap`, `vip`, `pro` |
| **Part** | Anything else that goes in a pedal: a case, an audio interface, a screen, a control surface, a power source | 1590DD, WM8960, UMC202HD, 8.8″ bar, three footswitches on a Pico |
| **Build** | A named pedal: one Core plus its parts, and what the build is for | `console` |
| **Set** | A named list of commits that belong together: engine, `pedald` and `devices/`, rigpa, ljoss, kernel, firmware, with their protocol versions | `2026-11-a` |
| **Proof** | Dated evidence that something works: one rung of the ladder below | "booted from blank, 12 days ago" |

**A Core is not a build.** vip can go in the console to compare it with pro, and that should be one
line in a file, not a project.

### The three builds

The names are proposals, and the empty cells are honest.

| | `console` | `box` | `pocket` |
|---|---|---|---|
| **For** | The full pedal: a lot of NAM and a big touchscreen | The compact pedal, usable soon | One amp in a stompbox, on a battery, for a long gig |
| **Core** | pro: i5-9500T, 16 GB, x86-64 | vip: Pi 5, 1 GB | zap: Zero 2 W, 512 MB, on order |
| **A2-Full per core** | 25 (measured) | 9 (measured) | Not measured; estimated at 1-2 |
| **Kernel route** | Ubuntu's signed RT | rtpi's rebuild, in slots | Unknown: an RT kernel for this SoC is open work in rtpi |
| **Case** | Hammond 1456RH3 | 1590DD | Not chosen |
| **Audio** | UMC202HD over USB | WM8960, external buffer for now, one output | WM8960 likely |
| **Screen and UI** | 8.8″ 1920×480 touch: rigpa | Small or 4.3″: a cut-down rigpa | None, or almost none |
| **Controls** | Pico; six footswitches planned | Pico; three footswitches | Footswitches, possibly straight on the Zero's GPIO |
| **Power** | Mains | USB-C | Own lithium battery |
| **Edited from** | rigpa, ljoss | Cut-down rigpa, ljoss | The phone, mostly |

## How mix and match works

A new directory, `fleet/`, describes what things are, and a tool checks and makes them:

```
fleet/
  cores/    zap vip pro piv     what the machine is, and which devices/<host>/ it uses
  parts/    cases, audio, screens, controls, power: dimensions, ports, draw, needs
  builds/   console box pocket  one Core + parts + purpose + next steps
  sets/     2026-11-a ...       the commits that belong together
  schema/                       every file validated, as cost.json is today
```

`devices/<host>/` stays as it is and stays the home of device state. Fleet files point at it rather
than copy it (rule 1). `components.lock` remains "what is running"; a build's set is "what should be",
and the difference between them is **drift**, shown rather than discovered.

```
scripts/fleet check  console --core vip     is this combination legal?
scripts/fleet make   box --set 2026-11-a    build, install and check it
scripts/fleet status [--json]               every build and Core, one view
scripts/fleet set new                       pin today's heads as a candidate set
```

`fleet check` reads the parts' data and refuses with a reason: this screen needs a port this Core
lacks; this rig needs more than this Core's cost table allows; this Core does not fit this case; this
power source cannot carry this draw. A difference between hosts stays a file wherever it can, not a
code path, as `devices/pro` already does.

**The deploy routes become one.** `fleet make` chooses how to make binaries for a Core, always in a
clean container and never on a Core. pro stops compiling: its binaries are built on mp and its tests
run on pro when it is quiet.

**Sets are how things get promoted, without adding branches.** Work still lands on `main` (rule 4).
A set pins heads; it climbs the proof ladder on each Core; a Core moves to it when it passes. Rolling
back means going to the previous set. Anything deployed outside a set is marked `dev` on the
dashboard.

## The user interfaces

**Clients ask, they do not assume.** A UI never branches on a hostname. It reads what this Core can do
(`engine.schema`, the cost verdicts, the capability bits), so the same rig document can be opened
anywhere and refused with a reason where it does not fit.

| Surface | Used on | Approach |
|---|---|---|
| **rigpa, wide** | `console` | As now: 1920×480 touch |
| **rigpa, compact** | `box` | Keep `rigpa_core` (protocol, models, navigation) and add a second set of views. The spec's layout is in 1920×480 pixels today, so this is real work. Two sizes to design for: 800×480 touch if the 4.3″ fits, and a non-touch 3.5″-or-under driven by an encoder through the Pico. The size is chosen by a fit test, not by guessing |
| **Nothing, or LEDs** | `pocket` | Footswitches, a status LED, and the phone |
| **ljoss, desktop and iPad** | All | As now |
| **ljoss, phone** | All, and the main editor on `pocket` | A layout in ljoss, not a new app: it is one multiplatform target that already builds for iPhone, with a stack instead of a split view. Borrow from rigpa what suits one hand on a stage: rig list, big switches, tuner. Chain editing comes second |

`pocket` cannot be usable before the phone layout and the pairing work (`docs/pairing.md`) are, so
they are on its track.

**Rigs and libraries move between Cores.** A rig is the same document everywhere. Each build gets a
library profile (`sync-library --profile`), because zap's card and memory cannot hold what pro can.
x86 and ARM do not render bit-identically (a documented floor of −120 dB), so that floor becomes a
test: the same rig, rendered per architecture and compared.

## The proof ladder

Every build has a ladder, and every rung has a date. **A rung goes stale.** It turns amber past its
age limit and grey after twice that, so confidence fades unless we keep earning it.

| Rung | What it proves | How | Runs | Stale after |
|---|---|---|---|---|
| **1 Code** | Each repo's own tests pass, on each architecture | GitHub's runners, on push. Add `pedald`, firmware build, rigpa, rtpi's boot tests, ljoss's model tests. Add a Cortex-A53 qemu job | Every push | 7 days, or any new commit |
| **2 Artefacts** | Every binary builds from clean clones in a clean container | `scripts/fleet build` on mp and piv, then GitHub's runners or the M2 for Apple builds | Weekly | 14 days |
| **3 Together** | Engine, `pedald`, rigpa and ljoss talk to each other at this set's versions, without hardware | namchaind's loop backend, rigpa's live tests, ljoss's checks, replayed sessions (`tools/session`), the render parity test | Weekly, and per set | 14 days |
| **4 Install** | A complete image or install can be produced on a machine that is not the M2, from GitHub, the store and the vault only | The drill, below | Monthly, and per set | 45 days |
| **5 Device** | Blank hardware becomes a working device and passes the acceptance suite | The drill, on real hardware | Per set, at least quarterly | 120 days |
| **6 Hour** | An hour of a live rig at this Core's scale: zero xruns, no thermal throttling, no kernel messages | `soak` and vip's T10 pattern, on every Core | Per set | 90 days |
| **7 Played** | The owner played it, and says what they thought | A short dated note | When it happens | Never expires, but shows its age |

### The acceptance suite

One command for every Core, `scripts/fleet accept <build>`. What it asks is the same everywhere; the
numbers it expects come from that Core's cost table, not from the script.

- `devices/<host>/check`: the device is what its files say, and quiet.
- The cost table exists, matches this kernel and engine, and validates.
- The engine runs, adopts a rig sized to this Core, and reports no health warnings.
- **Signal passes.** See the test loop below.
- A switch is made through the Pico's console or a simulated event, and the service acts once.
- A short soak, a thermal check, and `pedal-diag`'s report.

**The test loop.** To prove audio without a person, each build keeps a loop from its second output to
its second input, where the second channel is not otherwise in use. Audio can then be played through
the real converters with the guitar channel untouched. pro's interface can do this with one lead.
`box` has only one output for now, so its signal test would be a jumper or a human step until it has
another. `measure`'s and `codec-input-noise`'s tooling already holds most of what this needs.

### The drill: proving we can rebuild

`scripts/drill <build>` starts from an empty directory on a clean machine. It may use **only** GitHub,
the store (below) and the vault. Reaching for anything else fails the drill, which is the point; the
list of things that failed is the backlog.

| Rung | Where | Clean by |
|---|---|---|
| Linux x86-64 | mp | Rolled back to a VM snapshot each time |
| Linux arm64 | piv | A throwaway container, `HOME` empty |
| Apple | GitHub's macOS runners if they carry a new enough SDK, else a clean clone and scratch user on the M2 | Fresh checkout |
| zap and vip | Spare card, flashed from the drill's own image | The card, with the real one left safe |
| pro | A spare drive; until there is one, `apply` in a VM on mp, without the RT kernel, as a partial proof | Marked partial on the page |

A drill records its inputs, the hashes it produced, how long it took, and **how many steps needed a
person** (inserting a card is fair; logging in to fix something is a failure). Its report is committed
to `bench-results/`.

**zap is born this way.** It has no history, so nothing on it may be hand-installed: its first working
state comes from the drill. pro's hand-added packages (`docs/pro.md`) move into `devices/pro/` for the
same reason.

### The store

A private bucket holding what is not in git, addressed by hash, listed in a committed `inputs.lock`:
kernel artefacts, the bench DI, the library, enclosure sources, and pinned toolchain archives.

- **Recommended: Cloudflare R2.** The site is already on Cloudflare, and a script on any machine can
  reach it with a scoped token. Dropbox is the alternative, but it is awkward to reach from a headless
  host.
- **Secrets are never stored there.** Images with Wi-Fi keys in them are rebuilt, not kept.
- **Third-party models and IRs stay private.** Public CI uses free inputs: the vendored core's example
  models and `make_test_ir.py`. The private library is for rungs 4 to 6.
- **A public kernel binary would bring a source obligation.** Nothing in this plan publishes one.

## Machines and who does what

| Machine | Role in steady state | What it needs first |
|---|---|---|
| **M2** | The desk: editing, agent sessions, Xcode (only Apple builds need it), writing cards. Nothing else depends on it being open | The vault token stops being Mac-only |
| **piv** | The lab's coordinator, because it is always on: arm64 builds, drills, running scheduled tests, publishing the dashboard. If it is down the page says so | docker enabled, harness, a scoped vault token. Bench measurement and coordination must not collide: both go through the host lock |
| **mp** | The x86-64 clean room: builds pro's binaries, conformance, drills, a second place to run an agent. A VM, so never a source of timing numbers | docker, gh, ninja, harness, a snapshot to return to |
| **pro, vip, zap** | Cores. Quiet, measured, never building | Standing permission for the lab (below) |

`scripts/bootstrap-builder` makes any Linux box a builder from nothing, using pinned versions, and it
is itself exercised by the drill.

**The lab never reaches inward from the internet.** The repos are public, so a self-hosted GitHub
runner would let outside events run code on the home network. GitHub's runners do everything
triggered by a public event; piv pulls `main` on a timer and runs the lab from there. Results go out,
and nothing comes in.

**The lab never interrupts a player.** Every lab job takes the host lock (rule 8) and first checks for
signal at the input and a do-not-disturb flag. Long jobs have quiet hours.

**Agents follow the same rules.** A harness on piv or mp opens the workspace, reads `AGENTS.md` and
holds no vault token of its own. Two agents on one repo use worktrees, as now. The rule that nothing
touches vip without asking stays until the owner replaces it (Decision 4).

## The dashboard

### What it shows

`pedal.science/status`, the "Status" page the site's outline already has a place for.

```
 Last proved from nothing:  console 12d · box 3d · pocket –        updated 2h ago

 ┌ console ──────────────┐ ┌ box ──────────────────┐ ┌ pocket ───────────────┐
 │ [render of the build] │ │ [render of the build] │ │ [outline: not built]  │
 │ Core  pro   25/core   │ │ Core  vip    9/core   │ │ Core  zap    ?        │
 │ audio screen controls │ │ audio screen controls │ │ dashed = not there yet│
 │ set 2026-11-a  ✓      │ │ set 2026-10-c  drift  │ │ no set                │
 │ proof ▮▮▮▮▮▮▯         │ │ proof ▮▮▮▮▯▯▯         │ │ proof ▮▯▯▯▯▯▯         │
 │ next: signal through  │ │ next: footswitches    │ │ next: first numbers   │
 └───────────────────────┘ └───────────────────────┘ └───────────────────────┘
```

| View | Answers |
|---|---|
| **Build cards** | What is this, what is in it, how is it doing? A picture from the 3D models where they exist, plus a diagram drawn from the fleet files with each part in its slot and missing parts dashed |
| **Software matrix** | Which build runs which commit of each component, linked to GitHub, with drift and `dev` marked |
| **Proof ladder** | Each rung's date and result, with colour for age, linked to its evidence |
| **Tracks** | Each build's next steps as a line of milestones: done, now, next. From each build's file, so the page never parses `plan.md` |
| **Capacity** | What each Core can carry, from its measured cost table, labelled with the date measured |
| **The lab** | Which support machines did what lately, with roles only |

A local version of the same page, served on the LAN, adds the private details. Only the public one is
on the web.

### Keeping it private

The public page is built from a **list of what may be shown**, not a list of what to hide. Anything new
is private until someone adds it.

```
 Cores, repos, CI  ──►  private snapshot (piv, never in git)
                              │
                     allow-list + schema ──► leak check ──► status.json ──► the page
```

- **The schema is closed.** Every field is declared, and values must be commit hashes, version
  strings, enumerated states, numbers or dates. Text from a host, such as a log line, a kernel message
  or an interface name, has nowhere to go. Free text comes only from committed files.
- **The leak check runs on every publish.** It reads the real external addresses, Wi-Fi name, IPv6
  prefix, MAC addresses, username and home path at that moment, stores none of them, and stops the
  publish on a match. A test feeds it planted values, to prove that it stops.
- **The same check guards the repos.** `scripts/public-check` runs before a push and in CI, because
  the leak we already have came from bench logs.
- **Time can identify too.** Live "online" or "playing" states would show when someone is home, so the
  page is not live: at most hourly, only on a change, with test times rounded to the day. Nothing shows
  whether a Core is on right now.
- **Never shown:** addresses, network names, device identifiers, usernames, paths, locations, machine
  serial numbers, logs.

### How it gets there

The lab writes `status.json` to a public object in the same Cloudflare account, using a token that can
write that one object. The site's page is static and reads it in the browser, so an update does not
trigger a site build or a commit, and a missing file shows "no data" rather than breaking the site. The
page shows how old its data is, and says plainly when it is stale.

`comms` owns the page and its wording; `pedal.project` owns the facts and the schema (rules 1 and 2).
Today `comms` says the NAM numbers quoted are the Pi 5's and that every claim goes through its register,
so a page showing pro's and zap's numbers needs that rule amended (Decision 5).

## The work, in order

Sizes are relative: S a session, M a few, L many. Every phase ends in **a demo and the owner's review
before the next one starts**, and any step that touches vip asks first.

### Phase 0: stop the leaks and tell the truth (S)

- Remove the private details from the public repos, after Decision 2 on history.
- Add `scripts/public-check`, and run it before pushes and in CI.
- Commit, or deliberately drop, every untracked file that a clean clone needs.
- Record zap, mp and piv's new roles in `docs/working-across-repos.md`.
- Get CI green: fix namchain's RTSan segfault and TSan job, and NAMBench's Linux jobs, or mark a
  failure as known with a reason.

**Done when:** the scan is clean on every repo's tree, CI is green or explained, and a clean clone has
every script.

### Phase 1: name everything, and see it (M)

- `fleet/` with its schema and today's truth in it: three builds, four Cores, their parts, and the set
  each is really running.
- `scripts/fleet status --json`, reading every Core, CI, locks and drift.
- **A private dashboard, served locally,** so we see the shape early and argue with it.

**Done when:** one page shows all of it, including its uncomfortable parts.

### Phase 2: inputs and builders (M)

- The store and `inputs.lock`, with kernel artefacts and the rest moved in.
- `scripts/bootstrap-builder`, run on mp and piv.
- `scripts/fleet build`: every Linux artefact from clean clones, with one route.
- pro stops compiling.
- `make-card` runs off the Mac, which means the vault token does too.

**Done when:** a rolled-back mp and a throwaway container on piv each rebuild their artefacts, with hashes
recorded and nothing fetched from the M2.

### Phase 3: zap is born from the drill (M, starts when it arrives)

- **First measurements, by hand:** the bench that is ready now (`docs/zap.md`), the real cost table.
  These decide what `pocket` can be.
- `make-card` generalised beyond the Pi 5: boot layout, kernel route, a minimal 512 MB userland.
- The first complete drill: blank card to a working device.

**Done when:** zap plays a rig from a card nobody touched by hand, and its numbers are in its table.

### Phase 4: one test suite (M)

- `scripts/fleet accept`, scaled per Core.
- Rung 1 CI added to every repo, and rung 3's together-tests.
- The lab on piv: timer, lock, do-not-disturb, reports.
- pro catches up with vip's T2 and T10, its signal test included.

**Done when:** `accept` passes on all three Cores, started by the lab, not a person. vip needs the
owner's go-ahead.

### Phase 5: the public page (M)

- The allow-list, the schema, the leak check with planted values.
- The Astro page in `comms`, the status object, and the publish job.
- The owner reviews the actual public JSON and page before it goes live.

**Done when:** `pedal.science/status` is live, and the leak test is part of publishing.

### Phase 6: keep proving it (S to set up, then ongoing)

- Scheduled drills for vip and pro. Spare card and spare drive bought if agreed.
- Sets become the normal way to deploy. Ages on the page start to matter.

**Done when:** every build has been rebuilt from nothing at least once, and the page shows when.

### Alongside: the three builds' own tracks

These carry on throughout and are what the dashboard's tracks show. They live in `plan.md` and in each
build's file.

- **`box`:** footswitches flashed and working; case closed with cooling proved; a screen chosen; rigpa
  compact; the input board made small. **Probably the first to be really usable.**
- **`console`:** signal through pro's interface; a live-rig hour; the case laid out and drilled; the
  8.8″ screen; rigpa on x86-64.
- **`pocket`:** numbers first; then decide what it is; the RT kernel; battery noise and runtime measured;
  the phone layout; pairing.

## What could go wrong

| Risk | What we do about it |
|---|---|
| Operations work eats the pedal | Phases are small and each helps a build. The tracks carry on. If a phase stops paying, stop it |
| The dashboard turns green and misleading | A rung is evidence, with a date and a link. Ages decay. Partial proofs say partial. Nothing is averaged into one score |
| Something private is published | Allow-list, closed schema, leak check with planted values, owner's review, no live state. And the repo scan, because that is where it actually happened |
| Lab jobs disturb playing or a measurement | Host lock, input-signal check, quiet hours |
| Slow Cores make tests slow | zap's tests scale to its table. The long rungs run per set, not per commit |
| Timing numbers from the wrong place | The rule stays: only a quiet real Core gives timing. CI, qemu and mp never do |
| Too many formats | Fleet files point at `devices/` and locks, and do not copy them. If one fact ends up in two files, that is a bug |

## Decisions for the owner

1. **Names:** `console`, `box` and `pocket` for the builds, and "set", "proof" and "drill" as words?
2. **The leak in git history:** rewriting `pedal.project`'s history removes the details from GitHub's
   tree but changes every later commit hash, breaks the commit references in docs and locks, and
   cannot recall any clones. The alternative is deleting them going forward and accepting that a home
   IPv6 prefix and LAN address remain in old commits. **Recommendation: fix going forward,** since the
   rewrite costs much, and check whether the prefix is still current.
3. **What "identifies me" covers:** commits already show a full name and an email address, on public
   repos, and the plan does not change that. Is that acceptable, or should the page and new commits go
   further? **Recommendation: the page shows no names; leave commits alone.**
4. **Standing permission for the lab:** today every touch of vip is asked for. The lab needs read-only
   status from vip and pro on a schedule, and tests in quiet hours. **Recommendation:** allow read-only
   on a timer now; allow tests only after you have seen them run, with a do-not-disturb flag you control.
5. **Numbers on the public page:** may it show pro's and zap's figures, and capacities? That needs
   `comms`' rules amended. **Recommendation: yes, as measurements with dates, not as claims.**
6. **The store:** Cloudflare R2, private, for kernel artefacts, the library and the rest? And is a
   private copy of third-party models acceptable to you?
7. **piv as coordinator:** the docs say it is "allowed to be busy or down". Is it now the one that stays
   up? **Recommendation: yes, with the page showing staleness when it is not.**
8. **zap's operating system:** **Recommendation: Ubuntu 26.04 arm64 from the same snapshot as vip**, so
   tooling carries over, unless a real-time kernel for this SoC turns out to be far easier elsewhere.
9. **Purchases:** a spare card per Pi, a spare drive for pro's drills, and a lead for pro's test loop.
10. **Phone scope:** iPhone only, through ljoss, for now?

## How this page relates to the others

`plan.md`'s "Next session starts with" remains the current state, and it will point here while this
work is under way. `docs/working-across-repos.md` keeps the rules; anything here that becomes a rule
moves there when it is real. `docs/zap.md` is zap's page, as `docs/pro.md` is pro's.

"""pedald — the pedal service (docs/pedal-service.md).

One process beside `namchaind`, on the housekeeping cores: the Pico link, resume, the bank and
the map, and `/status`. It is the pedal's control plane and nothing else — never ALSA, the
codec, I2C or a render buffer (D4), and never in the audio path, so the engine keeps playing
when this is down. ljoss keeps its own connection to the engine (D2); this is a second client,
not a gateway.

The loop is one thread and one poll a second, which is all the job needs: a 115200-baud link,
an engine status every second, and a STATE-frame timer. Anything that must not wait on a
client — the HTTP server, the resume read — is either cheap or on its own thread.
"""
import argparse
import json
import os
import queue
import signal
import sys
import time

from . import config as config_mod
from . import library as library_mod
from . import mapping as mapping_mod
from . import protocol
from . import resume as resume_mod
from .engine import EngineClient, EngineError
from .httpd import Server
from .link import Link

VERSION = "pedald 0.1"
STATUS_POLL_S = 1.0
STATE_S = 1.0

#: How long a bank rig's verdict is trusted before the engine is asked again.
#:
#: The engine's `engine.status` is polled at 1 Hz, but a rig's cost must not be: the table only
#: changes when the engine is reloaded (SIGHUP) and a rig only when the library is rescanned, so
#: asking about every rig every second would be 60 times the traffic for news that arrives
#: hourly. A verdict is therefore cached and invalidated by everything that can move it — see
#: `RigCost`: startup, a bank (library) change, an engine reconnect, and this interval as the
#: backstop for a change nobody told us about (a hand-edited cost.json and a SIGHUP the service
#: did not hear, a rescan driven straight at the engine by ljoss or `namchainctl`).
COST_POLL_S = 60.0

#: How long after a warm request the engine's own account of the warm set is believed over ours.
#:
#: `engine.status.warm` is the authority for what is warm, but a status read *before* a `rig.warm`
#: reached the engine would not mention the rig that was asked for, and believing it would ask the
#: engine to compile that rig a second time. A warm is installed by the engine's warm thread rather
#: than by the call that asked for it, so two status polls is longer than that takes to show up.
WARM_ADOPT_S = 2 * STATUS_POLL_S

#: How long a warm that failed is left alone before it is tried again — a rig the engine will not
#: compile, an engine that has gone away. A failure is never a failure of the *switch* (a press is
#: answered by the engine, cold if it must be), so this only bounds how often the service asks; a
#: different neighbour, or the engine coming back, is a different question and is asked at once.
WARM_RETRY_S = COST_POLL_S

#: One engine call, then report: the cost object is per rig, and the bank is `banks`, not `costs`.
#: Everything here is for display, so a second key that says nothing new is a second key to keep
#: true; ljoss reads `verdict` to decide whether a rig may be activated.
_VERDICT_KEYS = ("verdict", "cost", "headroom", "trimmed", "over")


def playable_verdict(cost):
    """Whether a rig the engine has costed may play, from the engine's own verdict.

    One rule, and only the engine gets to make it: `over` means it costs more than the table's
    headroom with every trimmable model already trimmed, so the engine would refuse to publish
    it (D9 — pedald does not re-derive this from the numbers, and never sums a cost itself).
    Anything else the engine says is playable, `trimmed` (D6) included: a rig on its Lite
    submodel is a different-sounding rig, not an unusable one, and the player is shown it.
    """
    if not isinstance(cost, dict):
        # No verdict yet — the rig has not been costed, or the engine refused to answer for it.
        # It is usable: the engine still refuses to publish what it cannot play, so a rig nobody
        # has asked about is not the service's to refuse (docs/pedal-service.md).
        return True
    return cost.get("verdict") != "over"


def _verdict(cost):
    """The engine's cost object as something small enough to cache and to put in `/status`.

    The five fields a panel needs, and nothing else: `nodes` is a per-node array — tens of
    entries for a real rig — and a bank of a hundred of them is a megabyte on a 1 Hz route,
    for numbers only a diagnostic wants. `None` for anything that is not a cost object, which
    includes the empty object this module caches for a reply that carried no usable cost:
    "asked, nothing to show", told apart from "not asked yet" by being present in the map.
    """
    if not isinstance(cost, dict):
        return None
    verdict = {key: cost.get(key) for key in _VERDICT_KEYS}
    if all(value is None for value in verdict.values()):
        # A reply that carried no cost object at all: "asked, and there was nothing to show",
        # which is not a verdict and must not read as one.
        return None
    return verdict


def flags_from(status, engine_down):
    """The STATE flags: audio ready, the engine's mute, and health (docs/pedal-service.md,
    R5 — `audible_generation > 0`, not `== generation`, or the flag flickers through every
    crossfade)."""
    if engine_down:
        return protocol.STATE_HEALTH_ERROR
    running = status.get("state") == "running" and (status.get("audible_generation") or 0) > 0
    flags = protocol.STATE_AUDIO_READY if running else 0
    if status.get("mute"):
        flags |= protocol.STATE_ENGINE_MUTED
    health = {"ok": protocol.STATE_HEALTH_OK, "warn": protocol.STATE_HEALTH_WARN,
              "error": protocol.STATE_HEALTH_ERROR}.get(status.get("health"), protocol.STATE_HEALTH_ERROR)
    return flags | health


class RigCost:
    """What every rig in the bank costs, as the engine tells it (D9, P5).

    The service owns the bank, so it owns the question "which of these can play" — but not the
    answer. It asks with `rig.cost`, one rig at a time, and keeps the reply; it never reads the
    cost table, never sums a cost and never invents a verdict, because a second cost model is
    exactly what D9 rules out. The verdicts are handed to the mapping (which skips an unusable
    rig when stepping) and to `/status` (which shows them).

    **What invalidates a verdict**, and this is the whole reason there is a cache here:

    - **The engine's cost table changes when the engine reloads it** — a SIGHUP, or a restart.
      A restart is seen as a reconnect; a SIGHUP is not seen at all, which is what the
      `COST_POLL_S` backstop below is for.
    - **A rig changes when the library is rescanned** (`engine.assets {"refresh": true}`): a
      rescan is how a new rig, an edited rig or a deleted model appears. The service's own
      `/library/refresh` (v3) is where `forget()` will be called; a rescan driven straight at
      the engine by ljoss or `namchainctl` is caught by `note_rigs` (a name that appears or
      goes) and by the backstop.
    - **Startup:** nothing is known, and everything is asked for.
    - **An engine reconnect:** a new process may have loaded a different table, so the whole
      map is dropped and rebuilt (`forget()`, from the daemon's poll).
    - **Failing to answer for a rig** — a refusal or an unreachable engine leaves `None`, not a
      stale verdict: an engine that cannot describe a rig cannot say it is still playable.
    - **`COST_POLL_S`, per rig** — the backstop for a change nobody told us about (a
      hand-edited `cost.json` and a SIGHUP the service never heard of), and the reason a
      verdict is never older than that by much.

    A `None` value means "no verdict for this rig": the engine refused to answer, or answered
    something without a usable cost. That is not a failure of the service — one rig it cannot
    describe must not stop the sweep of the others — and it is cached so the same rig is asked
    once per round rather than every tick. A rig with no entry at all has not been asked yet,
    and that is a different thing: see `playable_verdict`.

    The sweep asks about two rigs per tick rather than all of them in a row, so a bank of a
    hundred rigs costs the engine a hundred small reads spread through the poll loop instead
    of one long stall in it. `forget()` puts every rig back in front of the sweep.
    """

    def __init__(self, engine, poll_s=COST_POLL_S, log=None):
        self.engine = engine
        self.poll_s = poll_s
        self.log = log or (lambda _message: None)
        self.verdicts = {}              # rig name -> the five fields, or None
        self.asked_at = {}              # rig name -> when the engine was asked
        # The clock the verdict's age is measured against: the ask time, or `0.0` for a rig that
        # has been asked for again but not yet reached (a startup, a `forget()`, a new rig). It
        # mirrors `asked_at` but says "due now" instead of "asked then", which is what stops a
        # rig asked a moment ago from being asked again just because the bank was re-marked.
        self._asked_at = {}
        self.rigs = []
        self.failed = None              # a failure already logged, so it is logged once
        self._sweep_index = 0

    # ------------------------------------------------------------------ what the others read
    def verdict(self, name):
        return self.verdicts.get(name)

    def status(self):
        """The verdicts for `/status`: a shallow copy, so the HTTP thread reads a dict the loop
        is not inserting into, and only the rigs currently in the library."""
        return {name: self.verdicts.get(name) for name in self.rigs}

    def invalidate(self, name):
        """One rig's document changed (a save through the library API): its verdict is stale,
        and it goes to the front of the sweep. The others keep theirs."""
        self.verdicts.pop(name, None)
        self.asked_at.pop(name, None)
        self._asked_at[name] = 0.0

    def forget(self):
        """Drop every verdict: the table, the bank or the engine has changed (see the class).

        Every rig in the library is marked never-asked, so each is due at the next tick in
        library order — the whole bank, in front of the sweep, in one call.
        """
        self.verdicts.clear()
        self.asked_at.clear()
        self._asked_at = {name: 0.0 for name in self.rigs}
        self._sweep_index = 0
        self.failed = None

    def lost(self):
        """The engine will not answer at all: no verdict is true any more, so keep none.

        This is `forget()` and the same first-in-line mark, and the reasons differ, so the two
        are named apart. A verdict is only ever the engine's word about a rig; with the engine
        gone there is no word, and `/status` must say "no verdict" rather than show a cost from
        a process that may not be running. The sweep does not need the mark — nothing is asked
        while the engine is unreachable — but the next poll after it comes back does.
        """
        self.forget()

    def note_rigs(self, names, now):
        """The library's rigs, from the caller's one listing of it. A change forgets everything.

        The rigs are what the daemon already had to list to build the bank, so nothing here
        scans a directory and nothing calls `engine.assets`: the engine scans, the service
        reads what it is given. A removed rig drops its verdict; a rig that has appeared is
        marked never-asked, and it is due at the next tick (a rig the file of which was
        *edited* keeps its verdict until the backstop, because nothing in a directory listing
        says a file changed — that is what `forget()` is for, and what the backstop covers).
        """
        names = sorted(names)
        if names != self.rigs:
            gone = [name for name in self.rigs if name not in names]
            self.rigs = names
            for name in gone:
                self.verdicts.pop(name, None)
                self.asked_at.pop(name, None)
                self._asked_at.pop(name, None)
            self._sweep_index = 0
            self.failed = None
        return self.rigs

    # ------------------------------------------------------------------ the sweep
    def poll(self, now):
        """Ask the engine about the rigs that need it, a couple a tick. Never raises."""
        if not self.rigs:
            return 0
        asked = 0
        for name in self._due(now):
            self._ask(name, now)
            asked += 1
            if asked >= 2:
                break
        return asked

    def _due(self, now):
        """The rigs this pass should ask about, in priority order, each at most once per pass.

        Two ways to be due, and both are needed:

        - **Never asked** — a startup, a rig that has appeared, a bank whose verdicts were
          dropped. The whole bank goes in front of the sweep at once, and it is asked for in
          library order over the next few ticks.
        - **Asked, and `COST_POLL_S` old** — the backstop for a verdict that nothing has
          invalidated. The age is measured against `self._asked_at`: the clock of the last
          `forget()` for a rig that has not been asked since, and the ask time otherwise.
          Anchoring there rather than on `now` is what lets a re-ask pass finish — the bank is
          asked in order over several ticks, so measured against `now` the rigs before the
          cursor would go stale again while the later ones were being asked, and the pass
          would never reach them. A rig that failed once waits with the rest rather than being
          retried every tick; a sweep that meets an unreachable engine leaves the rest of the
          bank alone, so one engine failure is one log line per retry, not one per rig.

        The pass always goes round the whole bank, not just far enough for the caller's two:
        the cursor is where the last pass left it, so the bank is covered in order over a few
        ticks rather than the first two names being asked for ever.
        """
        for _ in range(len(self.rigs)):
            name = self.rigs[self._sweep_index % len(self.rigs)]
            self._sweep_index += 1
            if name not in self.asked_at:
                yield name            # never asked (a startup, a bank change): due at once
                continue
            if now - self._asked_at.get(name, 0.0) >= self.poll_s:
                yield name

    def _ask(self, name, now):
        """One `rig.cost`, and the verdict to cache for it. Never raises.

        A refusal or a broken connection is the engine's answer about *this rig*: the verdict is
        cleared (a stale one would be worse than none — the rig may have become unusable), the
        fact is logged once until the engine answers again, and the sweep carries on. An engine
        that is down is not a service failure (docs/pedal-service.md, "Failure modes"): the rigs
        it could not be asked about stay usable until it can say otherwise.
        """
        self.asked_at[name] = now
        self._asked_at[name] = now
        try:
            reply = self.engine.rig_cost(name + ".json")
        except EngineError as exc:
            self.verdicts[name] = None
            if self.failed != exc.code:
                self.failed = exc.code
                self.log(f"rig.cost {name}: {exc.code}: {exc.message}; no verdict for it")
            return None
        self.failed = None
        cost = reply.get("cost") if isinstance(reply, dict) else None
        verdict = _verdict(cost)
        self.verdicts[name] = verdict
        return verdict

    def tick(self, now):
        """Every `STATUS_POLL_S`, from the daemon's loop: sweep, then hand the verdicts to the
        mapping, which is the only other thing that reads them."""
        self.poll(now)
        return self.verdicts


def _warm_entry_name(entry):
    """A warm document's rig as *this* service names it: the stem of the rig file.

    Not the engine's `name`, which is the document's own name and need not be the file's: the
    pedal's `last.json` holds a document called `soak-three-chains`, and ljoss names the documents
    it writes. The service and its bank know a rig by its path under `rigs_root` (`<stem>.json`),
    which is also what it warms by, so the path is what is compared. A document published from a
    client with no file behind it has only a name, and that is better than nothing.
    """
    path = entry.get("rig")
    if isinstance(path, str) and path.endswith(".json"):
        return os.path.basename(path)[:-len(".json")]
    name = entry.get("name")
    return name if isinstance(name, str) and name else None


class WarmSet:
    """The warm set: the rig the footswitches reach next, held warm by the engine (P5, D4, D9, D10).

    A switch is instant because the rig it lands on is already rendering: the engine compiles a
    document, pins a thread to an inactive core and hands it over when the press comes, and the
    press costs a crossfade instead of a compile (namchain `docs/warm-set.md`). Which rig that is
    is D9's split — the engine owns the mechanism, the service owns the bank — and the answer is
    D10's, as amended: **the rigs the footswitches reach next**, one rig, in the direction the
    player last stepped (`Mapping.neighbour`). Nothing else is warmed: a jump outside the
    neighbours is a catch-up (P8), and filling the inactive cores with more of the bank is
    optimisation, after the pedal is gig-ready.

    The whole policy is four rules, and each is here because the alternative is wrong:

    - **Warm the neighbour** when it is not the rig we believe is warm. Warming *displaces* what
      was warm — the engine's own default, and its reply names what left in `replaced` — so a rig
      that has stopped being a neighbour leaves the warm set by being replaced. Nothing calls
      `rig.cool` for it: a cool naming a rig that is no longer warm is refused
      (`warm_not_ready`), and cooling first would empty the set between two presses for no gain.
    - **Empty the set when nothing is next** — `rig.cool` with no rig, which is exact whatever we
      believe (it cools what is warm and says what that was). Nothing is next when a press would
      land on the rig already playing: a bank with one usable rig in it, or a bank whose other
      rigs the engine refuses.
    - **The engine's word beats ours.** `engine.status.warm` is read on every poll and, once it is
      old enough to include our own last request (`WARM_ADOPT_S`), what it says is warm is what we
      believe. That is how a *warm switch* is followed: it swaps the two documents, so the rig the
      press landed on becomes audible and the rig it left becomes warm — not the rig that was
      asked for. Nothing is mirrored into `/status`; the engine's own object goes there, and this
      is only what the next decision is made from.
    - **Never raise, and never ask every second.** Warming is an optimisation: a refusal or an
      unreachable engine logs once, leaves the switch path exactly as it was, and is tried again
      when the neighbour changes, when the engine comes back, or after `WARM_RETRY_S`. Every
      attempt is a compile on the engine's control thread, which is why "once a tick" is too
      often. `warm_disabled` is not even a failure: a device with no `warm_cpus` has warming
      off, which is a configuration — it is logged once and nothing is asked again until the
      engine comes back as a different process, the only thing that can change it.
    """

    def __init__(self, engine, log=None, adopt_s=WARM_ADOPT_S, retry_s=WARM_RETRY_S):
        self.engine = engine
        self.log = log or (lambda _message: None)
        self.adopt_s = adopt_s
        self.retry_s = retry_s
        self.rig = None         # the rig we believe the engine holds warm, without ".json"
        self.disabled = False   # the engine says this device has no warm cores
        self.failed = None      # the code last logged, so it is logged once per kind
        self.failed_rig = None  # what that failure was about, so a new rig is tried at once
        self.asked_at = None    # when a `rig.warm` last succeeded, or None
        self.retry_at = 0.0     # a failed warm is not asked for again before this

    def lost(self):
        """The engine has gone, or come back: nothing we believed about its warm set survives.

        A new process starts with an empty warm set and may be configured differently — warm
        cores where there were none, or the other way round — so the belief, the disabled flag
        and the failure all go, and the next tick asks again.
        """
        self.rig = None
        self.disabled = False
        self.failed = None
        self.failed_rig = None
        self.asked_at = None
        self.retry_at = 0.0

    def tick(self, mapping, now, status=None, holding=None):
        """One pass: point the engine's warm set at the rig a press would reach next.

        `status` is an `engine.status` report the caller has just read, and it is the authority
        for what is warm. `holding` is for the one moment the caller knows the answer without
        asking: a *warm* switch hands the document over, so the engine now holds the rig the
        press left, not the one it landed on. Saying so is what stops that rig — the neighbour
        again, in a bank of two — from being compiled a second time. Never raises.
        """
        if self.disabled:
            return
        if holding is not None:
            self.rig = holding           # newer than any status the caller is holding
        elif status is not None:
            self._adopt(status, now)
        wanted = self._next(mapping)
        if wanted == self.rig:
            return
        if wanted is None:
            if self.rig is not None:
                self._cool(now)
            return
        if wanted != self.failed_rig or now >= self.retry_at:
            self._warm(wanted, now)

    # ------------------------------------------------------------------ the decision
    def _next(self, mapping):
        """The rig the next press reaches, or None: `mapping.neighbour`, not a second order.

        Nothing is next when that is the rig already playing (a bank with one usable rig in it):
        the engine would be asked to hold the document it is rendering.
        """
        wanted = mapping.neighbour()
        return None if wanted == mapping.current_name() else wanted

    def _adopt(self, status, now):
        """What the engine says is warm, once the answer can be about now. See the class."""
        warm = status.get("warm") if isinstance(status, dict) else None
        if not isinstance(warm, dict) or not warm.get("enabled"):
            return
        if self.asked_at is not None and now - self.asked_at < self.adopt_s:
            return          # a status read before our own warm: it cannot know about it yet
        names = [_warm_entry_name(entry) for entry in warm.get("set", [])
                 if isinstance(entry, dict) and not entry.get("audible")]
        names = [name for name in names if name]
        if names and self.rig not in names:
            # What we believed is not warm any more — a handover moved it, or somebody else
            # warmed over it — and this slice holds one warm rig, so the engine's one is ours.
            self.rig = names[0]
        elif not names:
            self.rig = None

    # ------------------------------------------------------------------ the calls
    def _warm(self, name, now):
        """One `rig.warm`, and the belief to keep for it. Never raises."""
        rig = name if name.endswith(".json") else f"{name}.json"
        try:
            reply = self.engine.rig_warm(rig)
        except EngineError as exc:
            if exc.code == "warm_disabled":
                # This device has no warm cores. Not a failure and not a switch: log it once and
                # stop asking, because only a new engine process can change it (`lost`).
                self.disabled = True
                self.log(f"rig.warm {rig}: warming is off on this device ({exc.message})")
                return
            self.failed_rig = name
            self.retry_at = now + self.retry_s
            if self.failed != exc.code:
                self.failed = exc.code
                self.log(f"rig.warm {rig} refused: {exc.code}: {exc.message}; "
                         f"a switch to it is a cold one")
            return
        self.failed = None
        self.failed_rig = None
        self.rig = name
        self.asked_at = now
        replaced = reply.get("replaced") if isinstance(reply, dict) else None
        self.log(f"warming {rig}" + (f", replacing {replaced}" if replaced else ""))

    def _cool(self, now):
        """`rig.cool` with no rig: nothing is one press away any more. Never raises."""
        try:
            reply = self.engine.rig_cool()
        except EngineError as exc:
            self.failed_rig = None
            self.retry_at = now + self.retry_s
            if self.failed != exc.code:
                self.failed = exc.code
                self.log(f"rig.cool refused: {exc.code}: {exc.message}")
            return
        self.failed = None
        self.failed_rig = None
        self.rig = None
        self.asked_at = None
        cooled = reply.get("cooled") if isinstance(reply, dict) else None
        if cooled:
            self.log("cooled %s: no rig is one press away" % ", ".join(str(rig) for rig in cooled))


class Service:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.started = time.monotonic()
        self.running = True
        self.engine_down = False
        self.status = {}
        self.status_at = 0.0
        self.pico = {}
        self.bypass = False
        self.state_key = None
        self.state_at = 0.0
        self.positions_at = 0.0
        self.bank_at = 0.0               # when the library was last listed (relist_rigs)

        try:
            token = cfg.token()
        except config_mod.ConfigError as exc:
            # The link still comes up without a token (HELLO/WELCOME, PING/PONG, STATE), but
            # nothing can be asked of the engine and every HTTP request is refused, which is
            # the right way round for a missing credential.
            log(f"no token: {exc}; the engine and /status are closed until it is readable")
            token = None
        self.token = token
        self.engine = EngineClient(host=cfg.engine_host, port=cfg.engine_port,
                                   token=token, timeout=5.0)
        self.link = Link(cfg.uart_device, cfg.uart_baud, log=log)
        self.session = protocol.Session(self.link.send, service_version=VERSION)
        self.link.attach(self.session)

        rigs = self._rig_names()
        bank = mapping_mod.load_json(os.path.join(cfg.state_root, "bank.json"), log)
        midi_map = mapping_mod.load_json(os.path.join(cfg.state_root, "midi-map.json"), log)
        self.mapping = mapping_mod.Mapping(rigs, bank=bank, midi_map=midi_map, log=log)
        # The bank's verdicts, from the engine (D9). The mapping is handed the same dict, not a
        # copy: what the service learns about a rig is what a press acts on. The pool is filled
        # by the poll loop, which is also where an engine restart drops it.
        self.cost = RigCost(self.engine, poll_s=COST_POLL_S, log=log)
        self.cost.note_rigs(rigs, time.monotonic())
        self.mapping.verdicts = self.cost.verdicts
        # The ready set, asked of the engine (D9, D10): the rig one press away is held compiled and
        # rendering on an inactive core, so a press is a handover rather than a compile (P5's warm
        # half). A device with no warm cores says so once and the press path is what it always was.
        self.warm = WarmSet(self.engine, log=log)
        # The rig library's HTTP side (v3): the routes write files on the server's threads and
        # queue what changed; the loop (apply_library_changes) is what moves the bank and the
        # verdicts, so neither is ever touched from two threads.
        self.library = library_mod.RigLibrary(cfg.rigs_root, cfg.max_rig_bytes, log=log)
        self.library_changes = queue.SimpleQueue()
        self.resume = resume_mod.Resume(self.engine, cfg.rigs_root, state_root=cfg.state_root, log=log)
        self.http = Server(cfg.http_host, cfg.http_port, token,
                           {"/status": self.handle_status,
                            "GET /library/rigs": self.handle_rigs,
                            "/library/rigs/*": self.handle_rig}, log=log,
                           # The transport cap has to be the largest upload the API allows, or
                           # a model or IR would be 413 before its route saw it (v3).
                           max_body=cfg.max_ir_bytes)

    # ------------------------------------------------------------------ helpers
    def _rig_names(self):
        try:
            names = os.listdir(self.cfg.rigs_root)
        except OSError:
            return []
        return sorted(n[:-5] for n in names
                      if n.endswith(".json") and n not in ("last.json", "last.prev.json"))

    def _save_position(self):
        path = os.path.join(self.cfg.state_root, "bank.json")
        try:
            os.makedirs(self.cfg.state_root, exist_ok=True)
            resume_mod.write_atomic(path, json.dumps(self.mapping.position_state(), indent=2) + "\n")
        except OSError as exc:
            self.log(f"could not save {path}: {exc}")

    # ------------------------------------------------------------------ link
    def on_message(self, message):
        kind = message.get("type")
        if kind == protocol.HELLO:
            self.pico = {"fw": message.get("fw"), "major": message.get("major"),
                         "minor": message.get("minor"), "caps": message.get("caps")}
            if message.get("refused"):
                # The major differs: `protocol.Session` sent ERROR and holds no session, so the
                # pedal stays where it is until the two ends match (docs/uart-protocol.md).
                self.log(f"Pico speaks protocol {self.pico['major']}.{self.pico['minor']}, this "
                         f"service speaks {protocol.VERSION_MAJOR}.{protocol.VERSION_MINOR}: "
                         f"refused with ERROR, no session")
            else:
                self.log(f"Pico says hello: fw {self.pico['fw']!r}, protocol "
                         f"{self.pico['major']}.{self.pico['minor']}, caps 0x{self.pico['caps']:04x}")
            self.state_key = None                       # one STATE per session
        elif kind == protocol.EVENT:
            self.on_event(message)

    def on_event(self, event):
        kind = {0x01: "rig_up", 0x02: "rig_down", 0x03: "rig_select", 0x04: "bank_up",
                0x05: "bank_down", 0x06: "bank_select", 0x07: "bypass_set",
                0x08: "bypass_toggle", 0x10: "cc", 0x11: "pc", 0x12: "expression"}.get(event.get("kind"))
        if kind is None:
            self.log(f"event {event.get('kind')}: unknown kind, ignored")
            return
        self.log(f"event {kind} a={event.get('a')} b={event.get('b')} "
                 f"source={event.get('source')} seq={event.get('seq')}")
        action = self.mapping.action(kind, event.get("a", 0), event.get("b", 0))
        if action is None:
            return
        if action["action"] == "bypass":
            self.bypass = action["on"]
            self.state_key = None
            return
        if action["action"] == "load":
            self.load_rig(action["rig"])

    def load_rig(self, name):
        """Make a rig audible, with `rig.switch`: a handover if the engine holds it warm, a
        publish if it does not.

        This is where every path that changes the playing rig ends: the mapping resolves a
        trigger — a footswitch `cc`, a MIDI `pc`, a bank move — to the rig it lands on, and this
        makes that rig audible with the engine's switch, which is the call that cannot end in
        silence. With its own `fallback` a rig that is not warm is loaded and crossfaded exactly
        as `rig.load` does it, so the service does not choose between a handover and a load; it
        asks for a switch and the reply says which it got (`switched`, and `reason` when cold).

        One device has no switch to ask for: with no `warm_cpus` the engine answers
        `warm_disabled` and refuses even the cold path, so there the load *is* the switch and the
        service asks for it by name. That is the only case in which this calls `rig.load`.

        The belt to the mapping's braces: the mapping walks past an unusable rig when stepping,
        but a `rig_select`, a bank move and a map entry naming a rig outright can each land on
        one too, so the refusal is repeated here — where every path to the engine goes through —
        rather than trusted to each caller. A rig with no verdict is loaded: only the engine may
        refuse a rig, and it refuses the publish if it cannot play it.
        """
        rig = name if name.endswith(".json") else f"{name}.json"
        verdict = self.cost.verdict(rig[:-len(".json")])
        if not playable_verdict(verdict):
            why = verdict.get("verdict") or "unusable"
            self.log(f"not loading {rig}: the engine says {why} (cost {verdict.get('cost')} "
                     f"against a headroom of {verdict.get('headroom')})")
            return
        # What the engine is playing before this switch, which is also what a warm switch leaves
        # in the warm set (its reply does not say, and the warm set would compile it again).
        playing = self.status.get("rig_name") if isinstance(self.status, dict) else None
        try:
            reply = self.engine.rig_switch(rig)
        except EngineError as exc:
            if exc.code != "warm_disabled":
                self.log(f"rig.switch {rig} refused: {exc.code}: {exc.message}")
                return
            try:
                self.engine.rig_load(rig)
            except EngineError as exc:
                self.log(f"rig.load {rig} refused: {exc.code}: {exc.message}")
                return
            self.log(f"loading {rig}: warming is off on this device, so there is no switch")
            reply = None
        if reply is not None:
            how = reply.get("switched") if isinstance(reply, dict) else None
            reason = reply.get("reason") if isinstance(reply, dict) else None
            # `warm` is the handover P6 exists for; `cold` is a load, and its reason says which
            # kind ("nothing is warm", "that rig is not the warm one"). Both are successes.
            self.log(f"switched to {rig} ({how or 'unknown'}"
                     + (f": {reason}" if reason else "") + ")")
        self._save_position()
        self.state_key = None
        # The rig a press reaches next has moved with the position, so the warm set follows now
        # rather than at the next poll. A warm switch swapped the two documents, so the engine
        # holds the rig this press left — said here, so it is not asked for again.
        holding = playing if reply is not None and reply.get("switched") == "warm" else None
        self.warm.tick(self.mapping, time.monotonic(), holding=holding)

    # ------------------------------------------------------------------ engine
    def poll_engine(self, now, refresh=True):
        """One `engine.status`, and what follows from it. `refresh=False` is for the tests and
        for anything that wants to see the state a poll left without the sweep running on.

        The status poll is also where the engine's coming and going is noticed, and a cost
        verdict is the engine's word about a rig: with the engine gone there is no word, so the
        verdicts are dropped on the way down and asked for again on the way up. A new engine
        process may have loaded a different cost table, so nothing from before it is kept.
        """
        self.status_at = now
        try:
            # engine.status answers {"ok": true, "status": {...}} — the report is nested, unlike
            # rig.get, which puts `document` at the top level.
            self.status = self.engine.status().get("status") or {}
        except EngineError as exc:
            # In this order: `lost()` clears the fault the verdicts are gated on, so - it must
            # come before the log line that reads it.
            self.cost.lost()
            self.warm.lost()
            if not self.engine_down:
                self.log(f"engine status failed: {exc.code}: {exc.message}; "
                         f"the bank's verdicts are dropped until it answers again")
            self.engine_down = True
            return
        if self.engine_down:
            # It was down and it is not now: a new process may have loaded a different cost
            # table, so no verdict from before it is worth keeping (`RigCost`).
            self.cost.forget()
            self.warm.lost()
            self.log("engine recovered: the bank's verdicts are being asked for again")
        self.engine_down = False
        name = self.status.get("rig_name") or ""
        if name:
            index = self.mapping.note_rig(name)
            if index != self.mapping.rig:
                self.positions_at = now
        # Cost the bank through the engine (P5, D9). Not every second: `RigCost` says what
        # actually invalidates a verdict, and sweeps only the rigs that need asking.
        if refresh:
            self.relist_rigs(now)
            self.cost.tick(now)
            # And point the warm set at the rig a press reaches next (P5's warm half, D10). Here
            # rather than on its own timer, because the status read just above is what says what
            # the engine holds warm — a poll is when the service learns it, and the policy is
            # written so that asking about the same rig twice costs nothing.
            self.warm.tick(self.mapping, now, self.status)
        # Milliseconds: the settle window is in ms, and passing seconds here would make it
        # 2000 seconds, which is a save that never happens (found by the local smoke test).
        self.resume.tick(int(now * 1000), self.status)

    def relist_rigs(self, now, names=None):
        """Notice a rig that has appeared or gone, at most once every `COST_POLL_S`.

        `rigs_root` is a directory the operator and (from v3) the upload API write to, and the
        engine's rescan is not something the service is told about. A listing is cheap and the
        service's own rule is that nothing watches the directories and nothing scans on a timer
        (docs/pedal-service.md, "Storage") — so this is not a watch and not a timer: it is the
        same listing the service already does at startup, repeated slowly, and `note_rigs` does
        nothing at all unless the set of names has changed. A rig whose *contents* changed keeps
        its verdict until `forget()` or the verdict's own age says otherwise.
        """
        if now - self.bank_at < COST_POLL_S:
            return
        self.bank_at = now
        before = list(self.cost.rigs)
        self.cost.note_rigs(self._rig_names() if names is None else names, now)
        if self.cost.rigs != before:
            self.log(f"the library changed: {len(before)} rigs, now {len(self.cost.rigs)}")

    def maybe_send_state(self, now):
        if not self.session.session_up:
            return
        name = self.status.get("rig_name") or self.mapping.current_name() or ""
        bank = self.mapping.current_bank()
        key = (flags_from(self.status, self.engine_down), self.mapping.index_of(name),
               self.mapping.bank, len(bank), name)
        if key == self.state_key and now - self.state_at < STATE_S * 1000:
            return
        self.session.send_state(flags=key[0], rig_index=key[1], bank=key[2],
                                bank_size=key[3], name=name)
        self.state_key, self.state_at = key, now

    # ------------------------------------------------------------------ http
    def link_status(self, now):
        """What the link is doing, with the timestamps a rate needs.

        A counter without a clock is not a rate: `frames_ok: 27,523` cannot say whether the link
        is alive, and `24 a second` can. `last_rx_s_ago` is the useful form for a human and for
        pedal-diag, which turns it into "nothing has arrived for 40 seconds" when it should.
        """
        def age(at):
            return None if at is None else round(now - at, 3)

        return {
            "device": self.cfg.uart_device, "baud": self.cfg.uart_baud,
            "protocol": "%d.%d" % (protocol.VERSION_MAJOR, protocol.VERSION_MINOR),
            "open": self.link.open, "session": self.session.session_up,
            "frames_ok": self.session.frames_ok,
            "frames_bad": self.session.frames_bad,
            "bytes_in": self.link.bytes_in, "bytes_out": self.link.bytes_out,
            "drops": self.link.drops,
            "last_rx_s_ago": age(self.link.last_rx_at),
            "last_tx_s_ago": age(self.link.last_tx_at),
            "open_s": age(self.link.opened_at),
            "pico": self.pico,
        }

    def handle_status(self, request):
        bank = self.mapping.current_bank()
        status = self.status if isinstance(self.status, dict) else {}
        body = {
            "service": {"version": VERSION, "uptime_s": round(time.monotonic() - self.started, 1),
                        "pid": os.getpid()},
            "engine": {
                "reachable": not self.engine_down,
                "state": status.get("state"), "health": status.get("health"),
                "device": status.get("device"), "rig": status.get("rig"),
                "rig_name": status.get("rig_name"), "rig_source": status.get("rig_source"),
                "generation": status.get("generation"),
                "audible_generation": status.get("audible_generation"),
                "params_applied": status.get("params_applied"),
                "params_stale": status.get("params_stale"),
                "xruns": status.get("xruns"), "guard_trips": status.get("guard_trips"),
                "issues": status.get("issues", []),
                # The engine's own warm-set object (P5's warm half), passed through as it
                # stands: it is the authority for what is warm, its `set` is per document, and a
                # summary here would be a second thing to keep true. Absent on a device with no
                # warm cores, which is how the engine says warming is off.
                "warm": status.get("warm"),
            },
            "link": self.link_status(time.monotonic()),
            "bank": {"banks": self.mapping.banks, "bank": self.mapping.bank,
                     "position": self.mapping.rig, "current": self.mapping.current_name(),
                     "size": len(bank),
                     # The bank's verdicts, as name -> {"verdict", "cost", "headroom",
                     # "trimmed", "over"}, or null for a rig the engine has not answered for.
                     # `verdict_max_age_s` is how long one of those verdicts is trusted before
                     # it is asked for again, so a reader can tell "no verdict" from "stale".
                     # A map beside `banks` rather than a field inside its entries: `banks` is
                     # the list the Pico's STATE and the mapping already speak, and a panel or
                     # a client wants the verdicts for the whole library, including a rig the
                     # current bank window does not show. The engine's `nodes` array is
                     # deliberately not here — it is tens of entries per rig, and this route is
                     # polled (see `_verdict`).
                     "verdicts": self.cost.status(),
                     "verdict_max_age_s": COST_POLL_S},
            "bypass": self.bypass,
        }
        return 200, body

    # ------------------------------------------------------------------ the rig library (v3)
    def running_rig(self, status=None):
        """The library rig the engine is running, by name, or None.

        The engine names its rig by path: a library rig's own file after a `rig.load`, but
        `last.json` after a boot resumed it, and then the document's name is the link — the same
        rule the bank's position uses ("Resume", Position). A document the library doesn't have
        (an app applied it) is None.
        """
        status = self.status if status is None else status
        if not isinstance(status, dict):
            return None
        names = self.library.names()
        path = status.get("rig") or ""
        directory, base = os.path.split(path)
        if (base.endswith(".json") and os.path.abspath(directory) == os.path.abspath(self.cfg.rigs_root)
                and base[:-5] in names):
            return base[:-5]
        name = status.get("rig_name")
        return name if name in names else None

    def handle_rigs(self, request):
        return 200, {"rigs": self.library.listing(), "running": self.running_rig()}

    def handle_rig(self, request):
        rest = request.path[len("/library/rigs/"):]
        action = None
        if rest.endswith("/rename"):
            rest, action = rest[:-len("/rename")], "rename"
        name = _unquote_path(rest)
        try:
            if action == "rename":
                if request.method != "POST":
                    return 405, {"error": "rename is a POST"}
                try:
                    to = json.loads(request.body or b"{}").get("to")
                except (ValueError, AttributeError):
                    return 400, {"error": "the body is {\"to\": \"<new name>\"}"}
                self.library.rename(name, to)
                self.library_changes.put(("rename", name, to))
                self.log(f"library: renamed rig '{name}' to '{to}'")
                return 200, {"name": to}
            if request.method in ("GET", "HEAD"):
                return 200, self.library.get(name)
            if request.method == "PUT":
                replaced = self.library.put(name, request.body)
                self.library_changes.put(("put", name, None))
                self.log(f"library: {'replaced' if replaced else 'stored'} rig '{name}'")
                return 201, {"name": name, "replaced": replaced}
            if request.method == "DELETE":
                self.library.delete(name)
                self.library_changes.put(("delete", name, None))
                self.log(f"library: deleted rig '{name}'")
                return 200, {"name": name, "deleted": True}
            return 405, {"error": f"{request.method} is not a rig operation"}
        except library_mod.LibraryError as exc:
            return exc.status, {"error": exc.message}

    def apply_library_changes(self, now):
        """On the loop: what the library routes changed, applied to the bank and the verdicts.

        A rename or a delete rewrites `bank.json`'s names (it names rigs, and a name that has
        gone would be a hole in the bank); then the mapping is rebuilt from the library and the
        bank as they now are, keeping the rig it was on when that rig still exists. A changed
        document's verdict is stale and is asked for again. The MIDI map is hand-written and has
        no endpoint yet, so names in it are not rewritten.
        """
        changes = []
        while True:
            try:
                changes.append(self.library_changes.get_nowait())
            except queue.Empty:
                break
        if not changes:
            return
        bank_path = os.path.join(self.cfg.state_root, "bank.json")
        bank = mapping_mod.load_json(bank_path, self.log)
        bank_changed = False
        for kind, name, to in changes:
            if kind in ("rename", "delete") and bank:
                bank, changed = library_mod.rename_in_bank(bank, name, to if kind == "rename" else None)
                bank_changed = bank_changed or changed
        if bank_changed:
            try:
                resume_mod.write_atomic_plain(bank_path, json.dumps(bank, indent=2) + "\n")
            except OSError as exc:
                self.log(f"could not save {bank_path}: {exc}")
        current = self.mapping.current_name()
        for kind, name, to in changes:
            if kind == "rename" and current == name:
                current = to
        rigs = self._rig_names()
        self.mapping = mapping_mod.Mapping(rigs, bank=bank, midi_map=self.mapping.map, log=self.log)
        if current in rigs:
            self.mapping.note_rig(current)
        self.cost.note_rigs(rigs, now)
        for kind, name, to in changes:
            if kind == "put":
                self.cost.invalidate(name)
            elif kind == "rename":
                self.cost.invalidate(to)
        self.mapping.verdicts = self.cost.verdicts
        self.bank_at = now

    # ------------------------------------------------------------------ loop
    def stop(self, *_args):
        self.running = False

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.link.open_port()
        self.http.start()
        self.log(f"{VERSION} up: link {self.cfg.uart_device}, http on "
                 f"{self.cfg.http_host}:{self.cfg.http_port}")
        self.poll_engine(time.monotonic())
        while self.running:
            now = time.monotonic()
            self.link.poll(0.05)
            for message in self.link.take_messages():
                self.on_message(message)
            self.session.tick(int(now * 1000))
            self.apply_library_changes(now)
            if now - self.status_at >= STATUS_POLL_S:
                self.poll_engine(now)
            if self.positions_at and now - self.positions_at > 2.0:
                self._save_position()
                self.positions_at = 0.0
            self.maybe_send_state(now)
        self.log("stopping")
        self.http.stop()
        self.link.close()
        self.engine.close()
        return 0


def _unquote_path(text):
    """Percent-decoding for a path component (UTF-8); unlike a query, `+` is itself."""
    if "%" not in text:
        return text
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "%" and i + 2 < len(text) and _is_hex(text[i + 1:i + 3]):
            out.append(int(text[i + 1:i + 3], 16))
            i += 3
        else:
            out.extend(text[i].encode("utf-8"))
            i += 1
    return out.decode("utf-8", errors="replace")


def _is_hex(pair):
    return len(pair) == 2 and all(c in "0123456789abcdefABCDEF" for c in pair)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pedald", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("run", "seed"))
    parser.add_argument("--config", default="/etc/pedal/pedald.json")
    parser.add_argument("--engine-config", default="/etc/namchain/namchaind.json")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)

    def log(message):
        print(f"pedald: {message}", flush=True)

    try:
        cfg = config_mod.Config.load(args.config, args.engine_config)
    except config_mod.ConfigError as exc:
        print(f"pedald: {exc}", file=sys.stderr, flush=True)
        return 2

    if args.command == "seed":
        # Seed needs no engine: it creates the tree and copies the default rig if there is none.
        return resume_mod.Resume(None, cfg.rigs_root, state_root=cfg.state_root, log=log).seed()
    return Service(cfg, log).run()

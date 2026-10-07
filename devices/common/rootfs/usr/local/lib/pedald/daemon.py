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
import signal
import sys
import time

from . import config as config_mod
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
        self.resume = resume_mod.Resume(self.engine, cfg.rigs_root, state_root=cfg.state_root, log=log)
        self.http = Server(cfg.http_host, cfg.http_port, token,
                           {"/status": self.handle_status}, log=log,
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
        """The bench path, as staged: `rig.load`. D10 keeps this off the stage until the
        ready set (v2) lands, because the first 170–340 ms of a cold load sound wrong.

        The belt to the mapping's braces: the mapping skips an unusable rig when stepping, but
        `rig_select`, `resume` and a MIDI map entry can all name one too, so the refusal is
        repeated here — where every path to the engine goes through — rather than trusted to
        each caller. A rig with no verdict is loaded: only the engine may refuse a rig, and it
        refuses the publish if it cannot play it.
        """
        rig = name if name.endswith(".json") else f"{name}.json"
        verdict = self.cost.verdict(rig[:-len(".json")])
        if not playable_verdict(verdict):
            why = verdict.get("verdict") or "unusable"
            self.log(f"not loading {rig}: the engine says {why} (cost {verdict.get('cost')} "
                     f"against a headroom of {verdict.get('headroom')})")
            return
        try:
            self.engine.rig_load(rig)
        except EngineError as exc:
            self.log(f"rig.load {rig} refused: {exc.code}: {exc.message}")
            return
        self.log(f"loading {rig}")
        self._save_position()
        self.state_key = None

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
            if not self.engine_down:
                self.log(f"engine status failed: {exc.code}: {exc.message}; "
                         f"the bank's verdicts are dropped until it answers again")
            self.engine_down = True
            return
        if self.engine_down:
            # It was down and it is not now: a new process may have loaded a different cost
            # table, so no verdict from before it is worth keeping (`RigCost`).
            self.cost.forget()
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

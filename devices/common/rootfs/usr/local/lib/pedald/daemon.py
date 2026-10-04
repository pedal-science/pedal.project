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
        ready set (v2) lands, because the first 170–340 ms of a cold load sound wrong."""
        rig = name if name.endswith(".json") else f"{name}.json"
        try:
            self.engine.rig_load(rig)
        except EngineError as exc:
            self.log(f"rig.load {rig} refused: {exc.code}: {exc.message}")
            return
        self.log(f"loading {rig}")
        self._save_position()
        self.state_key = None

    # ------------------------------------------------------------------ engine
    def poll_engine(self, now):
        self.status_at = now
        try:
            # engine.status answers {"ok": true, "status": {...}} — the report is nested, unlike
            # rig.get, which puts `document` at the top level.
            self.status = self.engine.status().get("status") or {}
            self.engine_down = False
        except EngineError as exc:
            if not self.engine_down:
                self.log(f"engine status failed: {exc.code}: {exc.message}")
            self.engine_down = True
            return
        name = self.status.get("rig_name") or ""
        if name:
            index = self.mapping.note_rig(name)
            if index != self.mapping.rig:
                self.positions_at = now
        # Milliseconds: the settle window is in ms, and passing seconds here would make it
        # 2000 seconds, which is a save that never happens (found by the local smoke test).
        self.resume.tick(int(now * 1000), self.status)

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
            "link": {"device": self.cfg.uart_device, "baud": self.cfg.uart_baud,
                     "open": self.link.open, "session": self.session.session_up,
                     "pico": self.pico},
            "bank": {"banks": self.mapping.banks, "bank": self.mapping.bank,
                     "position": self.mapping.rig, "current": self.mapping.current_name(),
                     "size": len(bank)},
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

"""The bank, the position, and what a press does (docs/pedal-service.md, "The event vocabulary").

The protocol fixes the vocabulary (`kind`, `a`, `b`) and says the tables key on `kind`, never
on `source`; this module is the policy those tables implement. It is deliberately pure: it
decides *what* an event means and returns an action, and the daemon does the calling and the
writing.

v1, as staged: `rig_up`/`rig_down` step through the bank and wrap, `rig_select` picks within
it, the `bank_*` kinds move the window, and `bypass_*` mirrors the relay's state for the
panel and the app without an engine call. `cc` and `pc` go through `midi-map.json`, which is
written by hand until v3 adds an endpoint. With no `bank.json` the bank is the library's rigs
by name, eight to a bank (R15), so the service works with nothing configured.

Names, not indexes: a CC or PC entry names a rig, because indexes are positions in a bank and
a reordering must not silently repoint a MIDI pedal.

**Unusable rigs are skipped.** The engine costs every rig and says whether it can play one
(`rig.cost`, D9); the daemon keeps those verdicts in `verdicts` and hands them here. A press
then lands on the next rig that can play rather than on the one next in the file — the rig the
engine would refuse is not a place to be, so `next` walks past it and a bank with none left
does nothing at all. A rig with **no verdict** is usable: it has not been costed (yet), and the
engine still refuses a publish it cannot play, so a rig nobody has asked about is not this
module's to refuse. A pressed rig is still a press: nothing here reaches the engine.

**The ready set is that same walk** (D10, amended 2026-10-09): `neighbour` is the rig the next
press would reach, in the direction the player last stepped, and the daemon holds it warm in the
engine. It is one rig — the neighbours, not everything MIDI could jump to, which is unbounded
and is a catch-up (P8) — and it is asked for here rather than derived again elsewhere.
"""
import json
import os

# The footswitches' default map (uart-protocol.md draft 2, U8): they are triggers like any
# other controller, and 82 is the assignable one. A switch acts on its press.
DEFAULT_CC = {"80": "rig_down", "81": "rig_up"}

KINDS = (
    "rig_up", "rig_down", "rig_select", "bank_up", "bank_down", "bank_select",
    "bypass_set", "bypass_toggle", "cc", "pc", "expression",
)


class Mapping:
    def __init__(self, rigs, *, bank=None, midi_map=None, log=None):
        self.log = log or (lambda _msg: None)
        self.rigs = sorted(rigs)
        self.banks = self._banks(bank)
        self.bank = self._start_bank(bank)
        self.rig = self._start_rig(bank)
        self.hint = self.rig
        self.bypass = False
        # The direction the player last stepped in, which is the direction the ready set is in
        # (D10): `neighbour` reads it, `_step` writes it. Up, before any press.
        self.direction = 1
        # The engine's verdicts, rig name -> {"verdict", "cost", "headroom", "trimmed", "over"},
        # or None for a rig it has not answered for. The daemon fills this in (daemon.RigCost);
        # empty means nothing is known, so everything is usable.
        self.verdicts = {}
        self.map = dict(midi_map or {})
        self.map.setdefault("cc", {})
        for number, action in DEFAULT_CC.items():
            self.map["cc"].setdefault(number, action)

    # ------------------------------------------------------------------ bank layout
    def _banks(self, bank):
        """bank.json, or the library eight to a bank. Unknown shapes are a log line, not a
        crash: a hand-written file must never take the service down."""
        if bank:
            raw = bank.get("banks")
            if isinstance(raw, list) and raw:
                out = []
                for entry in raw:
                    if isinstance(entry, dict) and isinstance(entry.get("rigs"), list):
                        out.append([r for r in entry["rigs"] if r in self.rigs])
                    elif isinstance(entry, list):
                        out.append([r for r in entry if r in self.rigs])
                    else:
                        self.log(f"bank.json: ignoring a bank that is not a list of rigs: {entry!r}")
                if out:
                    return out
            self.log("bank.json has no usable 'banks'; falling back to the library")
        return [self.rigs[i:i + 8] for i in range(0, len(self.rigs), 8)] or [[]]

    def _start_bank(self, bank):
        try:
            index = int((bank or {}).get("bank", 0))
        except (TypeError, ValueError):
            index = 0
        return index if 0 <= index < len(self.banks) else 0

    def _start_rig(self, bank):
        try:
            index = int((bank or {}).get("rig", -1))
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < len(self.current_bank()):
            return index
        self.hint = -1
        return -1

    # ------------------------------------------------------------------ position
    def current_bank(self):
        return self.banks[self.bank]

    def current_name(self):
        bank = self.current_bank()
        return bank[self.rig] if 0 <= self.rig < len(bank) else None

    def index_of(self, name):
        bank = self.current_bank()
        return bank.index(name) if name in bank else -1

    def note_rig(self, name):
        """The engine's `rig_name` is the truth; the bank gives it a position (R3). A rig the
        bank does not have stays where the hint was, so the next press steps from there."""
        index = self.index_of(name)
        if index >= 0:
            self.rig = index
        return index

    def position_state(self):
        return {"bank": self.bank, "rig": self.rig, "banks": self.banks}

    def neighbour(self, delta=None):
        """The rig the next press reaches, without moving: the ready set's one rig (D10).

        `delta` is a direction, or — the usual case — the direction the player last stepped in
        (`self.direction`), so the rig held ready is the one the footswitch under the player's
        foot would land on. This is `_step`'s own walk and not a second opinion about the bank's
        order: a rig the engine refuses is walked past here exactly as a press walks past it, so
        a rig held warm can never be one the next press would not reach.

        The rig already playing is returned when it is the only one a press could reach (a bank
        with one usable rig in it): the walk wraps onto it. Callers that would ask the engine to
        hold something decide what to do about that; the bank's order is all this knows.
        """
        index = self._walk(self.direction if delta is None else delta)
        return None if index is None else self.current_bank()[index]

    def _walk(self, delta, start=None, log_skips=False):
        """The index a step in `delta` would land on, without moving; None if there is none.

        One walk serves both the press (`_step`) and the ready set (`neighbour`), so the two can
        never disagree about where the footswitches go next. Only a press logs the rigs it walks
        past: a policy asks this repeatedly, and the same refusal every second is noise.
        """
        bank = self.current_bank()
        if not bank:
            return None
        if start is None:
            start = self.rig if self.rig >= 0 else self.hint
        if start < 0:
            # No position at all: the first press starts at the bank's first usable rig, which
            # is this same walk from before the beginning (or the end, going backwards).
            start = -1 if delta > 0 else 0
        for offset in range(1, len(bank) + 1):
            index = (start + delta * offset) % len(bank)
            if self.is_usable(bank[index]):
                return index
            if log_skips:
                self._refused(bank[index], index)
        return None

    # ------------------------------------------------------------------ what the engine says
    def is_usable(self, name):
        """Whether a press may land on this rig. No verdict yet is usable (see the module)."""
        verdict = self.verdicts.get(name)
        return not (isinstance(verdict, dict) and verdict.get("verdict") == "over")

    def first_usable(self, bank=None):
        """The index of the bank's first rig the engine will play, or None if there is none."""
        for index, rig in enumerate(self.current_bank() if bank is None else bank):
            if self.is_usable(rig):
                return index
        return None

    def _refused(self, name, index=None):
        """A line for a rig the engine will not play, and always False so it reads as a guard.

        The same message everywhere, because it is the same fact: an `over` verdict is the
        engine's, not this module's, and the player is owed the reason as well as the silence.
        """
        verdict = self.verdicts.get(name)
        where = "" if index is None else f" (bank position {index})"
        if isinstance(verdict, dict):
            why = f"the engine says {verdict.get('verdict')} (cost {verdict.get('cost')} " \
                  f"against a headroom of {verdict.get('headroom')})"
        else:
            why = "the engine has no verdict for it"
        self.log(f"rig {name!r}{where} is unusable: {why}; skipped")
        return False

    # ------------------------------------------------------------------ events
    def action(self, kind, a=0, b=0):
        """What an event means, as `{"action": ...}` for the daemon to carry out, or None."""
        if kind == "rig_up" or kind == "rig_down":
            return self._step(1 if kind == "rig_up" else -1)
        if kind == "rig_select":
            return self._select(int(a))
        if kind == "bank_up" or kind == "bank_down":
            return self._move_bank(1 if kind == "bank_up" else -1)
        if kind == "bank_select":
            return self._move_bank(0, absolute=int(a))
        if kind == "bypass_set":
            self.bypass = bool(a)
            return {"action": "bypass", "on": self.bypass}
        if kind == "bypass_toggle":
            self.bypass = not self.bypass
            return {"action": "bypass", "on": self.bypass}
        if kind == "cc":
            return self._resolve(self.map.get("cc", {}).get(str(int(a))))
        if kind == "pc":
            return self._resolve(self.map.get("pc", {}).get(str(int(a))))
        return None

    def _step(self, delta):
        """The next rig that can play, in this bank and wrapping; None if none of them can.

        The walk is the whole point of P5's skip: `next` from a usable rig lands on the next
        usable one, past any the engine says are over, and a press that finds nothing leaves
        the position — and the player's rig — exactly where they were. The direction is
        remembered, because it is also the direction the ready set is in (D10): the rig a
        second press would reach is on the far side of this one.
        """
        if not self.current_bank():
            return None
        self.direction = 1 if delta > 0 else -1
        index = self._walk(delta, log_skips=True)
        if index is None:
            self.log(f"every rig in bank {self.bank} is unusable; the press does nothing")
            return None
        self.rig = index
        return {"action": "load", "rig": self.current_bank()[index]}

    def _select(self, index):
        bank = self.current_bank()
        if not bank:
            return None
        if 0 <= index < len(bank):
            if not self.is_usable(bank[index]):
                self._refused(bank[index], index)
                return None
            self.rig = index
            return {"action": "load", "rig": bank[index]}
        self.log(f"rig_select {index}: the bank has {len(bank)} rigs")
        return None

    def _move_bank(self, delta, absolute=None):
        if absolute is not None:
            target = absolute
        else:
            target = (self.bank + delta) % len(self.banks)
        if not (0 <= target < len(self.banks)):
            self.log(f"bank {target}: there are {len(self.banks)}")
            return None
        self.bank = target
        if not self.current_bank():
            return None
        index = self.first_usable()
        if index is None:
            # The window moved so the panel can show the bank, but nothing in it can play: no
            # load, and no position either — the index belongs to the bank it was taken in, so
            # keeping it would say the new window is at the old window's rig.
            self.rig = -1
            self.log(f"every rig in bank {target} is unusable; the window moved and nothing loaded")
            return None
        self.rig = index
        return {"action": "load", "rig": self.current_bank()[index]}

    def _resolve(self, spec):
        """A trigger's action: a rig by name, a bank, another kind, or nothing."""
        if spec is None:
            return None
        if isinstance(spec, dict):
            if "rig" in spec:
                return self._by_name(spec["rig"])
            if "bank" in spec:
                return self._move_bank(0, absolute=int(spec["bank"]))
            if "action" in spec:
                return self.action(str(spec["action"]))
            self.log(f"map entry {spec!r} names no rig, bank or action")
            return None
        text = str(spec)
        if text in KINDS:
            return self.action(text)
        return self._by_name(text)

    def _by_name(self, name):
        """A rig named outright — by a MIDI entry, or by another action — is refused too."""
        if name not in self.rigs:
            self.log(f"map entry names {name!r}, which is not in the library")
            return None
        index = self.index_of(name)
        if not self.is_usable(name):
            self._refused(name, index if index >= 0 else None)
            return None
        if index < 0:
            # A rig in no bank of ours: the window moves to the bank that has it.
            for number, bank in enumerate(self.banks):
                if name in bank:
                    self.bank, self.rig = number, bank.index(name)
                    break
        return {"action": "load", "rig": name}


def load_json(path, log=None):
    """A state file that may not exist yet, or may be half-written by hand. Never raises."""
    try:
        with open(path) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        if log:
            log(f"ignoring {path}: {exc}")
        return None

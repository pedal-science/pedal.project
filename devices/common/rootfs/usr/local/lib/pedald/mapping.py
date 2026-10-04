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
        bank = self.current_bank()
        if not bank:
            return None
        start = self.rig if self.rig >= 0 else self.hint
        if start < 0:
            start = 0 if delta > 0 else len(bank) - 1
            index = start
        else:
            index = (start + delta) % len(bank)
        self.rig = index
        return {"action": "load", "rig": bank[index]}

    def _select(self, index):
        bank = self.current_bank()
        if not bank:
            return None
        if 0 <= index < len(bank):
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
        self.rig = 0
        return {"action": "load", "rig": self.current_bank()[0]}

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
        if name in self.rigs:
            index = self.index_of(name)
            if index < 0:
                # A rig in no bank of ours: the window moves to the bank that has it.
                for number, bank in enumerate(self.banks):
                    if name in bank:
                        self.bank, self.rig = number, bank.index(name)
                        break
            return {"action": "load", "rig": name}
        self.log(f"map entry names {name!r}, which is not in the library")
        return None


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

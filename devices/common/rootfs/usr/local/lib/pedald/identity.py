"""Which pedal this is: an id made once, and a name the owner may change (docs/pedal-service.md).

`state/pedal.json` is the pedal's own data, so the backup carries it: a restored card is the same
pedal, and a fresh card is a new one. `pedald seed` runs as root before the engine starts and `pedald
run` as the service's user, and either may be the first to need it.
"""
import datetime
import json
import os
import socket
import threading
import uuid

from .resume import write_atomic_plain

FILE = "pedal.json"
MAX_NAME = 64


class IdentityError(Exception):
    """A name the pedal can't take: the message says why."""


def check_name(name):
    if not isinstance(name, str) or not name.strip():
        raise IdentityError("a pedal needs a name")
    if len(name) > MAX_NAME:
        raise IdentityError(f"a pedal's name is at most {MAX_NAME} characters")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        raise IdentityError("a pedal's name may not contain control characters")
    return name.strip()


class Identity:
    def __init__(self, state_root, log=None, hostname=None):
        self.path = os.path.join(state_root, FILE)
        self.log = log or (lambda _message: None)
        self.hostname = hostname or socket.gethostname().split(".")[0]
        self._lock = threading.Lock()   # PUT /pedal is on an HTTP thread, and two may race
        self.data = self._load()

    @property
    def id(self):
        return self.data["id"]

    @property
    def name(self):
        return self.data["name"]

    def rename(self, name):
        name = check_name(name)
        with self._lock:
            data = dict(self.data, name=name)
            self._write(data)
            self.data = data
        return name

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"] \
                    and isinstance(data.get("name"), str) and data["name"]:
                return data
            self._set_aside("it is not a pedal's identity")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self._set_aside(exc)
        data = {"id": str(uuid.uuid4()), "name": self.hostname,
                "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            self._write(data)
            self.log(f"this pedal is new: {data['name']}, {data['id']}")
        except OSError as exc:
            # Still answerable, under an id that lasts until the next start. Not worth stopping the
            # pedal for; a view sees a new pedal, and the journal says why.
            self.log(f"could not save {self.path}: {exc}; this id lasts until the next start")
        return data

    def _set_aside(self, why):
        self.log(f"{self.path} can't be used ({why}): moving it aside and making a new identity")
        try:
            os.replace(self.path, self.path + ".corrupt")
        except OSError as exc:
            self.log(f"could not move {self.path} aside: {exc}")

    def _write(self, data):
        write_atomic_plain(self.path, json.dumps(data, indent=2) + "\n")

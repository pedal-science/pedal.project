"""The model and IR library: uploads, listings and each file's hash.

docs/pedal-service.md, "Files". The engine's scan says what the library holds and this module adds
what the scan doesn't: a file's sha256 and its `.nam` metadata, so two libraries can be compared by
content. An upload never replaces a file. It is staged as a dot-file at the top of its root (the
engine's scan skips dot-names), hashed as it arrives, fsynced, and linked into place, and a link
fails if the name has been taken, so nothing can be overwritten even by a file dropped in by hand.

The engine is the loop's to ask (engine.py), so this module never talks to it: `set_scan` is given
each scan, and the route asks the loop for a rescan after an upload. Hashing happens on one thread
of its own, and what it finds is kept in `hashes.json`, keyed by path, size and mtime. That file is
a cache: it stays out of the backup, and losing it costs one pass.
"""

import hashlib
import json
import mmap
import os
import re
import threading
import unicodedata

#: What each root may hold. A document names an id, not a file, so one id has one file.
EXTENSIONS = {"models": (".nam",), "irs": (".wav", ".nam")}
MAX_PATH = 200
#: What an upload must leave free, so a full card can't stop the rig being saved.
MIN_FREE_BYTES = 64 << 20
#: The engine's sniff windows (namchain docs/assets.md), so both describe a file the same way.
FRONT_BYTES = 16 << 10
TAIL_BYTES = 1 << 10
CHUNK = 64 << 10
#: An upload is flushed this often as it arrives. A single fsync of 64 MiB at the end holds up the
#: filesystem's journal for seconds, and every other fsync on the card waits behind it, the loop's
#: saving of the rig's position among them: 2.2 s for a press, measured on vip (2026-11-09).
SYNC_EVERY = 2 << 20
#: A `.nam`'s metadata is a few hundred bytes. One bigger than this isn't kept in the cache.
MAX_METADATA_BYTES = 4 << 10
#: How many files are hashed between saves of the cache, so a power cut loses few.
SAVE_EVERY = 32
_fdatasync = getattr(os, "fdatasync", os.fsync)    # the Mac, where the tests run, has no fdatasync
RATE = re.compile(rb'"sample_rate"\s*:\s*([0-9][0-9.eE+-]*)')
STAGED_PREFIX = ".upload-"
STAGED_SUFFIX = ".part"


class Refusal(Exception):
    """A request refused, with the HTTP status that says why."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def check_path(kind, relative):
    """The rules for a path under a root. Returns it, or raises Refusal(400)."""
    if not relative:
        raise Refusal(400, "a file needs a path")
    if len(relative) > MAX_PATH:
        raise Refusal(400, f"a path is at most {MAX_PATH} characters")
    if "\\" in relative:
        raise Refusal(400, "a path may not contain a backslash")
    if relative.startswith("/"):
        raise Refusal(400, "a path is relative to the library")
    if any(ord(c) < 0x20 or ord(c) == 0x7F or c == "�" for c in relative):
        raise Refusal(400, "a path may not contain control characters or invalid UTF-8")
    for part in relative.split("/"):
        if not part or part.startswith("."):
            raise Refusal(400, "no part of a path may be empty or start with '.'")
    extensions = EXTENSIONS[kind]
    if not relative.lower().endswith(extensions):
        raise Refusal(400, f"a file in {kind} ends in {' or '.join(extensions)}")
    if len(os.path.basename(relative)) <= len(os.path.splitext(relative)[1]):
        raise Refusal(400, "a file needs a name before its extension")
    return relative


def file_id(relative):
    return os.path.splitext(relative)[0]


def _fold(text):
    """Two ids that differ only in case or Unicode form are one id on the Mac's filesystem."""
    return unicodedata.normalize("NFC", text).casefold()


def declared_rate(path):
    """The rate a `.nam` declares, or None: the same sniff as the engine's, tail first."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        if size > TAIL_BYTES:
            handle.seek(size - TAIL_BYTES)
        matches = RATE.findall(handle.read(TAIL_BYTES))
        if not matches:
            handle.seek(0)
            matches = RATE.findall(handle.read(FRONT_BYTES))[:1]
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def nam_metadata(path):
    """A `.nam`'s top-level `metadata` object, or None, without parsing the weights.

    The last occurrence, because a slimmable model repeats the key for each model it holds, and the
    file's own comes after them. Weights are numbers, so nothing there can look like the key.
    """
    if os.path.getsize(path) == 0:
        return None
    with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        at = data.rfind(b'"metadata"')
        if at < 0:
            return None
        colon = data.find(b":", at, at + 64)
        if colon < 0:
            return None
        text = data[colon + 1:colon + 1 + MAX_METADATA_BYTES].decode("utf-8", "replace").lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Files:
    def __init__(self, roots, caps, cache_path, log=None, publish=None, statvfs=os.statvfs):
        self.roots = roots
        self.caps = caps
        self.cache_path = cache_path
        self.log = log or (lambda _message: None)
        self.publish = publish or (lambda _kind, _data: None)
        self.statvfs = statvfs
        self._lock = threading.Lock()
        self._place_lock = threading.Lock()   # two uploads may need the same new folder
        self._scan = None
        self._hashes = {kind: {} for kind in roots}
        self._dirty = False
        self._in_flight = {}             # (kind, folded id) -> bytes promised
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread = None
        self.hashed = 0                  # how many files this process has hashed
        self._load_cache()

    # ------------------------------------------------------------------ the thread
    def start(self):
        for kind in self.roots:
            self._sweep_staged(kind)
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="pedald-hash", daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    def threads(self):
        return [self._thread] if self._thread is not None and self._thread.is_alive() else []

    def _sweep_staged(self, kind):
        """What a power cut left of an upload. Only ever at the top of the root."""
        try:
            names = os.listdir(self.roots[kind])
        except OSError:
            return
        for name in names:
            if name.startswith(STAGED_PREFIX) and name.endswith(STAGED_SUFFIX):
                self.log(f"removing an upload a restart interrupted: {kind}/{name}")
                try:
                    os.unlink(os.path.join(self.roots[kind], name))
                except OSError as exc:
                    self.log(f"could not remove {name}: {exc}")

    def _run(self):
        while not self._stopping.is_set():
            self._wake.wait()
            self._wake.clear()
            try:
                self._hash_pass()
            except Exception as exc:     # a bad file must not end the thread
                self.log(f"hashing stopped for now: {exc!r}")

    def _pending(self):
        with self._lock:
            scan = self._scan
            if scan is None:
                return []
            return [(kind, entry["relative"]) for kind in self.roots for entry in scan.get(kind, ())
                    if self._valid(kind, entry) is None]

    def _hash_pass(self):
        pending = self._pending()
        done = 0
        for kind, relative in pending:
            if self._stopping.is_set():
                break
            if self._hash_file(kind, relative):
                done += 1
                if done % SAVE_EVERY == 0:
                    self._save_cache()
        self._prune()
        self._save_cache()
        if done:
            self.log(f"library: hashed {done} files")
            self.publish("library", {"library": "files", "change": "hashed", "files": done})

    def _hash_file(self, kind, relative):
        path = os.path.join(self.roots[kind], relative)
        try:
            before = os.stat(path)
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
            metadata = nam_metadata(path) if relative.lower().endswith(".nam") else None
            after = os.stat(path)
        except OSError as exc:
            self.log(f"could not hash {kind}/{relative}: {exc.strerror}")
            return False
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return False                 # it changed as it was read: the next pass has it
        self._note(kind, relative, after, digest.hexdigest(), metadata)
        self.hashed += 1
        return True

    def _note(self, kind, relative, stat, sha256, metadata):
        if metadata is not None and len(json.dumps(metadata)) > MAX_METADATA_BYTES:
            metadata = None
        with self._lock:
            self._hashes[kind][relative] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                            "sha256": sha256, "metadata": metadata}
            self._dirty = True

    def _prune(self):
        """Forget files the scan no longer has."""
        with self._lock:
            if self._scan is None:
                return
            for kind in self.roots:
                held = {entry["relative"] for entry in self._scan.get(kind, ())}
                for relative in [r for r in self._hashes[kind] if r not in held]:
                    del self._hashes[kind][relative]
                    self._dirty = True

    # ------------------------------------------------------------------ the cache
    def _load_cache(self):
        try:
            with open(self.cache_path, encoding="utf-8") as handle:
                document = json.load(handle)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            self.log(f"ignoring {self.cache_path}: {exc}")
            return
        if isinstance(document, dict):
            for kind in self.roots:
                if isinstance(document.get(kind), dict):
                    self._hashes[kind] = document[kind]

    def _save_cache(self):
        with self._lock:
            if not self._dirty:
                return
            text = json.dumps(self._hashes, ensure_ascii=False)
            self._dirty = False
        staged = self.cache_path + ".part"
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(staged, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, self.cache_path)
        except OSError as exc:
            self.log(f"could not save {self.cache_path}: {exc}")

    # ------------------------------------------------------------------ the scan
    def _valid(self, kind, entry):
        """The cache's record of a scanned file, if it is still that file. The engine reports
        whole seconds, so this asks nothing of the disk, and a listing costs no system call."""
        held = self._hashes[kind].get(entry["relative"])
        if held is None or held.get("size") != entry.get("size"):
            return None
        mtime = entry.get("mtime")
        if mtime is None or held.get("mtime_ns", 0) // 1_000_000_000 != int(mtime):
            return None
        return held

    def set_scan(self, reply):
        """The engine's answer to `engine.assets`. Wakes the hashing thread for anything new."""
        scan = {"scan": reply.get("scan"), "roots": reply.get("roots")}
        for kind in self.roots:
            scan[kind] = reply.get(kind) or []
        with self._lock:
            self._scan = scan
        self._wake.set()

    @property
    def scan_number(self):
        with self._lock:
            return self._scan["scan"] if self._scan else None

    def counts(self):
        with self._lock:
            if self._scan is None:
                return None
            return {"scan": self._scan["scan"],
                    **{kind: len(self._scan[kind]) for kind in self.roots},
                    "hashing": sum(1 for kind in self.roots for entry in self._scan[kind]
                                   if self._valid(kind, entry) is None)}

    def listing(self, kind):
        """What the engine lists, plus each file's hash and metadata. None before the first scan.

        A file not hashed yet has `sha256: null`, `hashing` says how many, and a `library` event
        says when they are done. `path` is left out: a client must send the id (assets.md).
        """
        with self._lock:
            if self._scan is None:
                return None
            files, hashing = [], 0
            for entry in self._scan[kind]:
                held = self._valid(kind, entry)
                hashing += held is None
                row = {key: value for key, value in entry.items() if key != "path"}
                row["sha256"] = held["sha256"] if held else None
                row["metadata"] = held["metadata"] if held else None
                files.append(row)
            root = (self._scan.get("roots") or {}).get(kind) or {}
            return {"kind": kind, "scan": self._scan["scan"], "readable": root.get("readable"),
                    "error": root.get("error"), "hashing": hashing, "files": files}

    # ------------------------------------------------------------------ one file
    def locate(self, kind, relative):
        """(path, sha256) of a file in the library, hashing it now if the thread hasn't."""
        check_path(kind, relative)
        root = self.roots[kind]
        path = os.path.join(root, relative)
        # The engine follows a link only while it stays in the root, and so does this.
        real_root = os.path.realpath(root)
        if not os.path.realpath(path).startswith(real_root + os.sep) or not os.path.isfile(path):
            raise Refusal(404, f"no file '{relative}' in {kind}")
        stat = os.stat(path)
        with self._lock:
            held = self._hashes[kind].get(relative)
            fresh = held and (held.get("size"), held.get("mtime_ns")) == (stat.st_size, stat.st_mtime_ns)
            if fresh:
                return path, held["sha256"]
        if not self._hash_file(kind, relative):
            raise Refusal(404, f"no file '{relative}' in {kind}")
        self._wake.set()                 # the thread saves the cache
        with self._lock:
            return path, self._hashes[kind][relative]["sha256"]

    def store(self, kind, relative, stream, length):
        """Keep an upload, or refuse it. Returns what the reply says; raises Refusal."""
        check_path(kind, relative)
        if length > self.caps[kind]:
            raise Refusal(413, f"a file in {kind} is at most {self.caps[kind]} bytes")
        root = self.roots[kind]
        key = (kind, _fold(file_id(relative)))
        self._claim(kind, relative, key, length)
        staged = None
        try:
            os.makedirs(root, exist_ok=True)
            staged = os.path.join(root, STAGED_PREFIX + os.urandom(8).hex() + STAGED_SUFFIX)
            digest = self._receive(stream, staged, relative)
            if kind == "models":
                rate = declared_rate(staged)
                if rate is not None and rate != 48000:
                    raise Refusal(422, f"'{relative}' declares {rate:g} Hz; the engine can't "
                                       "resample a model, so it has to be 48000")
            metadata = nam_metadata(staged) if relative.lower().endswith(".nam") else None
            target = os.path.join(root, relative)
            with self._place_lock:
                self._place(staged, target, root, relative, kind)
            staged = None
        except OSError as exc:
            raise Refusal(500, f"could not store '{relative}': {exc.strerror}") from exc
        finally:
            with self._lock:
                self._in_flight.pop(key, None)
            if staged is not None:
                try:
                    os.unlink(staged)
                except OSError:
                    pass
        self._note(kind, relative, os.stat(target), digest, metadata)
        self._save_cache()
        return {"id": file_id(relative), "relative": relative, "size": length, "sha256": digest,
                "metadata": metadata}

    def _claim(self, kind, relative, key, length):
        """Everything that can be refused before a byte is read, and a promise of the space."""
        root = self.roots[kind]
        with self._lock:
            if os.path.lexists(os.path.join(root, relative)):
                raise Refusal(412, f"'{relative}' already exists; a file is never replaced")
            if key in self._in_flight:
                raise Refusal(409, f"'{relative}' is being uploaded already")
            for existing in self._files_under(root):
                if _fold(file_id(existing)) == key[1]:
                    raise Refusal(409, f"the id '{file_id(relative)}' already has the file '{existing}'")
            try:
                stats = self.statvfs(root)
            except OSError as exc:
                raise Refusal(500, f"cannot look at {kind}: {exc.strerror}") from exc
            free = stats.f_bavail * stats.f_frsize - sum(self._in_flight.values())
            if free - length < MIN_FREE_BYTES:
                raise Refusal(507, f"the card has {free} bytes free, and this needs {length} and "
                                   f"{MIN_FREE_BYTES} to spare")
            self._in_flight[key] = length

    @staticmethod
    def _files_under(root):
        for directory, directories, names in os.walk(root):
            directories[:] = [d for d in directories if not d.startswith(".")]
            for name in names:
                if not name.startswith("."):
                    yield os.path.relpath(os.path.join(directory, name), root).replace(os.sep, "/")

    @staticmethod
    def _receive(stream, staged, relative):
        digest = hashlib.sha256()
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb", buffering=0) as handle:
            try:
                unsynced = 0
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        view = view[handle.write(view):]
                    unsynced += len(chunk)
                    if unsynced >= SYNC_EVERY:
                        _fdatasync(handle.fileno())
                        unsynced = 0
                os.fsync(handle.fileno())
            except OSError as exc:
                if exc.errno == 28:      # ENOSPC, in spite of the check: someone else was writing
                    raise Refusal(507, f"the card filled while storing '{relative}'") from exc
                raise
        return digest.hexdigest()

    @staticmethod
    def _place(staged, target, root, relative, kind):
        """Create what the path needs and link the file in. A link never replaces anything."""
        directory = os.path.dirname(target)
        made = []
        walk = directory
        while walk != root and not os.path.exists(walk):
            made.append(walk)
            walk = os.path.dirname(walk)
        try:
            for path in reversed(made):
                os.mkdir(path, 0o755)
            os.link(staged, target)
        except FileExistsError:
            raise Refusal(412, f"'{relative}' already exists; a file is never replaced") from None
        except NotADirectoryError:
            raise Refusal(409, f"part of '{relative}' is a file in {kind}") from None
        os.unlink(staged)
        for path in [directory] + [os.path.dirname(p) for p in made]:
            _sync_directory(path)

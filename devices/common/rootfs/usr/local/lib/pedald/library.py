"""The rig library: the documents under `rigs_root`, read and written for the HTTP API.

docs/pedal-service.md, "The upload API": a rig is `rigs/<name>.json`, its name is its file's and
its document's `name`, names are unique, and `last` and `last.prev` belong to resume. Writes are
staged as a dot-file in the same directory (the engine's scan and this listing both skip
dot-names, so a half-written rig is invisible), fsynced, renamed into place, and the directory
fsynced: a power cut costs the write, never a good file.

This module only touches files. What a change means for the bank, the verdicts and the map is the
daemon's business, on its own loop: every write here returns, and the HTTP route then tells the
loop what changed.

Rig documents are stored, not applied (D2): the app owns the document and applies it to the
engine itself.
"""

import json
import os
import threading

RESERVED = ("last", "last.prev")
MAX_NAME = 200


class LibraryError(Exception):
    """A request the library refuses, with the HTTP status that says why."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def check_name(name):
    """The name rules (pedal-service.md, "The upload API"), for a rig: a single component."""
    if not isinstance(name, str) or not name:
        raise LibraryError(400, "a rig needs a name")
    if len(name) > MAX_NAME:
        raise LibraryError(400, f"a rig name is at most {MAX_NAME} characters")
    if name in RESERVED:
        raise LibraryError(400, f"'{name}' is reserved for resume")
    if name.startswith(".") or name in ("..",):
        raise LibraryError(400, "a rig name may not start with '.'")
    if "/" in name or "\\" in name:
        raise LibraryError(400, "a rig name may not contain '/' or '\\'")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        raise LibraryError(400, "a rig name may not contain control characters")
    return name


class RigLibrary:
    def __init__(self, root, max_bytes=1 << 20, log=None):
        self.root = root
        self.max_bytes = max_bytes
        self.log = log or (lambda _message: None)
        # One write at a time: a rename that checks for a clash and then renames must not
        # interleave with a put of the same name from another connection.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ reading
    def names(self):
        """Every rig, sorted, without the resume files and anything staged."""
        try:
            entries = os.listdir(self.root)
        except OSError:
            return []
        return sorted(e[:-5] for e in entries
                      if e.endswith(".json") and not e.startswith(".") and e[:-5] not in RESERVED)

    def listing(self):
        rigs = []
        for name in self.names():
            try:
                st = os.stat(self._path(name))
            except OSError:
                continue
            rigs.append({"name": name, "modified": round(st.st_mtime, 3), "size": st.st_size})
        return rigs

    def get(self, name):
        check_name(name)
        try:
            with open(self._path(name), "rb") as handle:
                data = handle.read()
        except FileNotFoundError:
            raise LibraryError(404, f"no rig named '{name}'") from None
        except OSError as exc:
            raise LibraryError(500, f"cannot read '{name}': {exc.strerror}") from exc
        try:
            return json.loads(data)
        except ValueError as exc:
            raise LibraryError(500, f"'{name}' is not valid JSON: {exc}") from exc

    def find(self, name):
        """The library's spelling of `name`, ignoring case, or None. Two rigs whose names differ
        only in case would be one file on a case-insensitive filesystem (the Mac's), so the
        library treats them as one name everywhere."""
        folded = name.casefold()
        for existing in self.names():
            if existing.casefold() == folded:
                return existing
        return None

    # ------------------------------------------------------------------ writing
    def put(self, name, body):
        """Store a document under `name`, replacing one of that name. Returns whether it did."""
        check_name(name)
        if len(body) > self.max_bytes:
            raise LibraryError(413, f"a rig is at most {self.max_bytes} bytes")
        try:
            document = json.loads(body)
        except ValueError as exc:
            raise LibraryError(400, f"the body is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise LibraryError(400, "a rig document is a JSON object")
        if "chains" not in document and "nodes" not in document:
            raise LibraryError(400, "a rig document has 'chains' (or a bare graph's 'nodes')")
        given = document.get("name")
        if given is None:
            document["name"] = name
        elif given != name:
            raise LibraryError(400, f"the document is named '{given}', not '{name}'")
        with self._lock:
            existing = self.find(name)
            if existing is not None and existing != name:
                raise LibraryError(409, f"the library already has '{existing}'")
            replaced = existing is not None
            self._write(name, document)
        return replaced

    def delete(self, name):
        check_name(name)
        with self._lock:
            path = self._path(name)
            try:
                os.unlink(path)
            except FileNotFoundError:
                raise LibraryError(404, f"no rig named '{name}'") from None
            self._sync_directory()

    def rename(self, name, to):
        """Rename a rig: its file and its document's `name`. The new file is written in full
        before the old one goes, so a power cut leaves one of them, never neither."""
        check_name(name)
        check_name(to)
        with self._lock:
            document = self.get(name)
            existing = self.find(to)
            if existing is not None and existing != name:
                raise LibraryError(409, f"the library already has '{existing}'")
            if isinstance(document, dict):
                document["name"] = to
            if to.casefold() == name.casefold():
                # Only the case changes: on a case-insensitive filesystem (the Mac's) the new
                # path *is* the old file, so writing it and unlinking the old would delete the
                # rig. Rewrite it in place, then rename it to its new spelling.
                self._write(name, document)
                os.rename(self._path(name), self._path(to))
                self._sync_directory()
            else:
                self._write(to, document)
                os.unlink(self._path(name))
                self._sync_directory()

    # ------------------------------------------------------------------ files
    def _path(self, name):
        path = os.path.join(self.root, name + ".json")
        # check_name already rules out separators; this is the belt to its braces.
        if os.path.dirname(os.path.abspath(path)) != os.path.abspath(self.root):
            raise LibraryError(400, "a rig name names a file in the library")
        return path

    def _write(self, name, document):
        os.makedirs(self.root, exist_ok=True)
        path = self._path(name)
        staged = os.path.join(self.root, f".{name}.json.part")
        text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        with open(staged, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
        self._sync_directory()

    def _sync_directory(self):
        fd = os.open(self.root, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def rename_in_bank(bank, old, new):
    """`bank.json`'s banks with one rig renamed (or removed, when `new` is None)."""
    banks = bank.get("banks") if isinstance(bank, dict) else None
    if not isinstance(banks, list):
        return bank, False
    changed = False
    out = []
    for entries in banks:
        if not isinstance(entries, list):
            out.append(entries)
            continue
        kept = []
        for entry in entries:
            if entry == old:
                changed = True
                if new is not None:
                    kept.append(new)
            else:
                kept.append(entry)
        if kept or not entries:
            out.append(kept)
        else:
            changed = True  # a bank that held only the deleted rig goes with it
    result = dict(bank)
    result["banks"] = out
    return result, changed

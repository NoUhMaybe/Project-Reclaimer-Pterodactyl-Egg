"""Bounded, symlink-rejecting storage. No RCON or subprocess dependencies."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import uuid

MAX_JSON = 4 * 1024 * 1024


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).absolute()

    def path(self, name):
        if not isinstance(name, str) or not name or "\\" in name or ":" in name:
            raise ValueError("Use a relative path inside this storage area.")
        parts = PurePosixPath(name).parts
        if name.startswith("/") or any(p in ("..", ".", "") for p in name.split("/")):
            raise ValueError("Path traversal is not allowed.")
        path = self.root
        # Check the area itself and its parents, including dangling symlinks.
        for parent in [*reversed(self.root.parents), self.root]:
            if parent.is_symlink():
                raise ValueError("Symlinked storage areas are not allowed.")
        for part in parts:
            path = path / part
            if path.is_symlink():
                raise ValueError("Symlinked files and directories are not allowed.")
        if self.root.resolve() not in path.resolve().parents:
            raise ValueError("Path escapes the storage area.")
        return path

    def read_bytes(self, name, limit=MAX_JSON):
        path = self.path(name)
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("File exceeds the size limit.")
        return data

    def read(self, name):
        return json.loads(self.read_bytes(name).decode("utf-8"))

    def digest(self, name):
        path = self.path(name)
        return hashlib.sha256(self.read_bytes(name)).hexdigest() if path.exists() else None

    def atomic_bytes(self, name, data, backup=True, expected="any"):
        path = self.path(name)
        if expected != "any" and self.digest(name) != expected:
            raise Conflict("File changed since it was opened; reopen it before saving.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path(name)
        if backup and path.exists():
            self.backup(name)
        fd, temporary = tempfile.mkstemp(prefix=".manager-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self.path(name)
            os.replace(temporary, path)
            if os.name == "posix":
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def write(self, name, value, expected="any"):
        data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        if len(data) > MAX_JSON:
            raise ValueError("JSON exceeds the size limit.")
        self.atomic_bytes(name, data, expected=expected)

    def backup(self, name):
        target = ".backups/" + uuid.uuid4().hex + ".json"
        self.atomic_bytes(target, self.read_bytes(name), backup=False)
        return target

    def delete(self, name):
        backup = self.backup(name)
        self.path(name).unlink()
        return backup

    def names(self, pattern="*.json"):
        # Enumeration never follows directory links.
        self.path("boundary-check")
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.glob(pattern) if not p.is_symlink() and p.is_file())

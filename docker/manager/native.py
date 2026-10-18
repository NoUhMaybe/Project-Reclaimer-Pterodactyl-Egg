"""Bounded upstream filesystem CLI operations; no RCON or shell execution."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from .filesystem import Store


class NativeTools:
    def __init__(self, server_dir, executable=None, env=None):
        self.server = Path(server_dir)
        self.executable = executable
        self.env = {k: v for k, v in (os.environ if env is None else env).items()
                    if not k.startswith("RECLAIMER_DEDICATED_") or k == "RECLAIMER_DEDICATED_ONLY"}
        self.lock = threading.Lock()
        self.process = None
        self.closed = False

    def close(self):
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.kill()

    def run(self, args, version=False):
        command = ([str(self.executable)] if version else [str(self.executable), "dedicated"]) if self.executable else (["project-reclaimer"] if version else ["dedicated"])
        try:
            with self.lock:
                if self.closed:
                    raise ValueError("Server is stopping; native operation cancelled.")
                proc = subprocess.Popen([*command, *args], cwd=self.server, env=self.env,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", errors="replace")
                self.process = proc
            try:
                out, err = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise ValueError("Native CLI timed out; no candidate file was activated.") from None
            if proc.returncode:
                # Native parse errors may reproduce file content, including secrets.
                raise ValueError("Upstream CLI rejected the candidate. Check settings, installed game assets and content; no candidate was activated.")
            return out.rstrip()
        except OSError:
            raise ValueError("Upstream CLI is unavailable; no candidate was activated.") from None
        finally:
            with self.lock:
                self.process = None

    @contextmanager
    def stage(self):
        store = Store(self.server)
        parent = store.path(".manager/staging")
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="native-", dir=parent) as directory:
            root = Path(directory)
            # Absolute paths preserve real installed content; mutable outputs stay
            # in this private staging area. No Workshop configuration is copied.
            config = "\n".join(key + " = " + json.dumps(str(self.server / relative))
                               for key, relative in (("game", "game"), ("content", "content")))
            config += '\ndata = "data"\nbans = "bans.json"\nauto_update = false\n[master]\nenabled = false\n[[server]]\nname = "Validation"\nport = 49176\nmap = "Guardian"\ngame = "Slayer"\n'
            Store(root).atomic_bytes("dedicated.toml", config.encode(), backup=False)
            yield root

    def validate_playlist(self, data):
        with self.stage() as root:
            Store(root).write("playlists/candidate.json", data, expected=None)
            return self.run(["playlist", "show", "--config", str(root / "dedicated.toml"), str(root / "playlists/candidate.json")])

    def create_playlist(self, name, maps, modes, seconds):
        from .playlists import safe_reference
        if not isinstance(name, str) or any(c in name for c in ("/", "\\", ":")) or ".." in name or not name.strip() or len(name) > 128:
            raise ValueError("Native creation needs a display name without path characters, up to 128 characters.")
        for ref in [*maps, *modes]:
            safe_reference(ref)
        if type(seconds) is not int or not 5 <= seconds <= 120:
            raise ValueError("Voting duration must be 5-120 seconds.")
        if any("," in ref for ref in [*maps, *modes]):
            raise ValueError("Native bulk creation uses comma-separated references; edit entries individually for names containing commas.")
        with self.stage() as root:
            self.run(["playlist", "new", "--config", str(root / "dedicated.toml"),
                      "--maps", ",".join(maps), "--games", ",".join(modes), "--vote-seconds", str(seconds), "--", name])
            names = Store(root / "playlists").names()
            if len(names) != 1:
                raise ValueError("Native authoring did not produce exactly one playlist; nothing was saved.")
            return Store(root / "playlists").read(names[0])

    def content(self, search=None):
        with self.stage() as root:
            return self.run(["content", "--config", str(root / "dedicated.toml"), "--", *([search] if search else [])])

    def validate_configuration(self, text):
        # A candidate beside dedicated.toml keeps relative path resolution intact.
        # The supervisor watches its real config, never this private temporary name.
        store = Store(self.server)
        store.path("dedicated.toml")
        fd, filename = tempfile.mkstemp(prefix=".manager-check-", suffix=".toml", dir=self.server)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
            self.run(["content", "--config", filename])
        finally:
            Path(filename).unlink(missing_ok=True)

    def version(self):
        return self.run(["--version"], version=True)

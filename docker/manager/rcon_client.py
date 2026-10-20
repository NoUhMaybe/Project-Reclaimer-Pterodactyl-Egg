"""Existing local dedicated rcon transport; argv becomes structured RCON args."""
from dataclasses import dataclass
import json
import os
import re
import subprocess
import threading
from .events import Events


def command_text(tokens):
    """Validate tokens and format a display/reference command (never shell code).

    The official 0.9.13, 0.9.20 and 0.9.21 CLIs send argv as a structured JSON args array.
    Transport must pass split tokens, NOT this reconstructed display string.
    """
    if not tokens or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", tokens[0]):
        raise ValueError("Invalid RCON command name.")
    def quote(value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Control characters are not allowed in commands.")
        if value and re.fullmatch(r"[\w./:#@+-]+", value):
            return value
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return " ".join(quote(str(v)) for v in tokens)


@dataclass
class Reply:
    ok: bool
    text: str
    data: object = None


class RconClient:
    def __init__(self, server_dir, enabled, env=None):
        self.server_dir = server_dir
        self.enabled = enabled
        self.env = dict(os.environ if env is None else env)
        self.secrets = [self.env.get(k, "") for k in ("RCON_PASSWORD", "SERVER_PASSWORD")]
        self.lock = threading.Lock()
        self.process = None
        self.closed = False
        self.connected = False
        self.events = Events(server_dir, self.env)

    def redact(self, text):
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "[redacted]")
        return text

    def close(self):
        self.events.close()
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.kill()

    def execute(self, tokens, json_reply=False):
        if not self.enabled:
            return Reply(False, "Enable RCON and set a password in Startup, then restart. Persistent menus remain available.")
        command_text(tokens)
        sensitive = tokens[0].lower() == "password" and len(tokens) > 1
        if sensitive and tokens[1]:
            self.secrets.append(tokens[1])
        # End CLI option parsing so names/reasons beginning with -- cannot
        # become upstream --config/--server options.
        args = ["dedicated", "rcon"] + (["--json"] if json_reply else []) + ["--", *tokens]
        try:
            with self.lock:
                if self.closed:
                    return Reply(False, "Server is stopping.")
                self.process = subprocess.Popen(args, cwd=self.server_dir, env=self.env,
                                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
                proc = self.process
            try:
                out, err = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                self.connected = False
                return Reply(False, "RCON timed out; the game may still be starting. Outcome unknown; commands are never retried automatically.")
            data = None
            if json_reply:
                try:
                    data = json.loads(out)
                except (ValueError, TypeError):
                    pass
            ok = proc.returncode == 0
            if isinstance(data, dict) and (data.get("ok") is False or data.get("error")):
                ok = False
            self.connected = ok
            message = "\n".join(s.rstrip() for s in (out, err) if s.strip())
            if not ok:
                message += "\nRCON request failed; authentication, prerequisites or server availability may be responsible."
            return Reply(ok, "Password request completed; value hidden." if sensitive else self.redact(message), data)
        except OSError:
            self.connected = False
            return Reply(False, "Local RCON client unavailable; check server startup and the image installation.")
        finally:
            with self.lock:
                self.process = None

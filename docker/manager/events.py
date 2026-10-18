"""Optional event observation through the existing local CLI (no new protocol)."""
from collections import deque
import json
import subprocess
import threading
import time


class Events:
    def __init__(self, server_dir, env):
        self.server_dir, self.env = server_dir, env
        self.process = None
        self.lock = threading.Lock()
        self.closed = False
        self.recent = deque(maxlen=24)

    def start(self):
        with self.lock:
            if self.closed or self.process is not None:
                return
            try:
                self.process = subprocess.Popen(["dedicated", "rcon", "--json", "--watch"],
                                                cwd=self.server_dir, env=self.env, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                text=True, encoding="utf-8", errors="replace")
            except OSError:
                return
            threading.Thread(target=self.read, name="rcon-control-events", daemon=True).start()

    def read(self):
        # Accept single-line or pretty-printed JSON. Ignore non-JSON banners.
        decoder, buffer = json.JSONDecoder(), ""
        proc = self.process
        try:
            for line in proc.stdout:
                buffer += line
                if len(buffer) > 65536:
                    buffer = ""
                    continue
                while buffer.strip():
                    try:
                        event, end = decoder.raw_decode(buffer.lstrip())
                        buffer = buffer.lstrip()[end:]
                    except ValueError:
                        if not buffer.lstrip().startswith(("{", "[")):
                            buffer = ""
                        break
                    self.record(event)
        finally:
            proc.stdout.close()
            proc.wait()

    def record(self, event):
        if isinstance(event, dict) and event.get("event") == "control":
            # Do not retain player telemetry, chat or authentication data.
            with self.lock:
                self.recent.append((time.monotonic(), {k: event[k] for k in ("action", "ok", "text") if k in event}))

    def since(self, timestamp):
        with self.lock:
            return [event for received, event in self.recent if received >= timestamp]

    def close(self):
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.kill()

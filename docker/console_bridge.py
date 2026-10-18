#!/usr/bin/env python3
"""Forward Pterodactyl console input to Project Reclaimer local RCON.

The server remains supervised as a child. Signals and exit codes propagate.
"""
import os
from pathlib import Path
import queue
import selectors
import shlex
import signal
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manager.capabilities import Capabilities
from manager.commands import LiveOperations
from manager.configuration import Configuration
from manager.content import Content
from manager.playlists import Playlists
from manager.rcon_client import RconClient
from manager.session import Session


def parse_command(line):
    line = line.strip()
    if not line:
        return None
    if line.lower() in ("help", "consolehelp"):
        return "help"
    if line.lower() in ("menu", "manager", "console help"):
        return "menu"
    if line == "\x03" or line.lower() in ("stop", "quit", "exit"):
        return "stop"
    try:
        return shlex.split(line)
    except ValueError as exc:
        raise ValueError(f"Invalid quoting: {exc}") from exc


def main():
    if len(sys.argv) < 2:
        print("Usage: console_bridge.py reclaimer-entrypoint start", file=sys.stderr)
        return 2

    enabled = os.environ.get("RCON_ENABLED", "0").lower() in ("1", "true") and bool(os.environ.get("RCON_PASSWORD"))
    child = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, start_new_session=True)
    stopping = False
    server_dir = Path(os.environ.get("RECLAIMER_SERVER_DIR", "/home/container/server"))
    client = RconClient(server_dir, enabled)
    capabilities = Capabilities(os.environ.get("RECLAIMER_IMAGE_VERSION", "0.9.13"))
    live = LiveOperations(client, capabilities)
    content = Content(server_dir)
    configuration = Configuration(server_dir)
    def emit(message):
        print(client.redact(str(message)), flush=True)
    session = Session(live, Playlists(server_dir, content), content, configuration, child, emit)
    commands = queue.Queue(maxsize=32)

    def input_worker():
        while True:
            line = commands.get()
            if stopping or child.poll() is not None:
                return
            try:
                if session.handle(line):
                    continue
                command = parse_command(line)
                if command == "stop":
                    stop_child()
                elif command == "help":
                    emit("[console] Type menu (or manager / console help) for management. Raw commands: status, maps, modes, players, load \"The Pit\" \"Capture the Flag\", nextmap, endround, endgame. stop shuts down.")
                elif isinstance(command, list):
                    emit(client.execute(command).text)
            except ValueError as exc:
                emit("[console] " + str(exc))
            except Exception:
                # A malformed response must not take down the supervisor or
                # spill credentials through an exception traceback.
                session.flow = None
                emit("[console] Operation failed safely. Use menu/refresh; inspect files with File Manager if needed.")

    threading.Thread(target=input_worker, name="console-input", daemon=True).start()

    def stop_child(_signum=None, _frame=None):
        nonlocal stopping
        if stopping or child.poll() is not None:
            return
        stopping = True
        print("[console] Stopping Project Reclaimer...", flush=True)
        try:
            os.killpg(child.pid, signal.SIGINT)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, stop_child)
    signal.signal(signal.SIGTERM, stop_child)

    selector = selectors.DefaultSelector()
    try:
        selector.register(sys.stdin, selectors.EVENT_READ)
    except (OSError, ValueError):
        pass

    print("[console] Bridge ready. Type help to see available commands.", flush=True)
    if not enabled:
        print("[console] RCON disabled: set Enable RCON=true and a password in Startup.", flush=True)

    try:
        return supervise(child, selector, commands, stop_child, lambda: stopping, emit)
    finally:
        client.close()
        selector.close()


def supervise(child, selector, commands, stop_child, is_stopping, emit):
    """Keep the existing process group and escalation schedule independent of UI."""
    buffer = b""
    dropping = False
    def submit(raw):
        line = raw.decode("utf-8", errors="replace").rstrip("\r")
        # Stop never waits behind an RCON request or an unfinished prompt.
        if line.strip().lower() in ("stop", "quit") or line.strip() == "\x03":
            stop_child()
            return
        try:
            commands.put_nowait(line)
        except queue.Full:
            emit("[console] Input queue full; wait for the pending operation. stop remains available.")

    while child.poll() is None:
        if is_stopping():
            try:
                return child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print("[console] Graceful stop timed out; sending SIGTERM.", flush=True)
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    return child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    return child.wait()
        for key, _ in selector.select(timeout=0.2):
            chunk = os.read(key.fileobj.fileno(), 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                if buffer:
                    submit(buffer)
                    buffer = b""
                continue
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if dropping:
                    dropping = False
                elif len(raw) <= 65536:
                    submit(raw)
                else:
                    emit("[console] Input line exceeds 64 KiB; discarded.")
            if len(buffer) > 65536:
                buffer = b""
                dropping = True
                emit("[console] Input line exceeds 64 KiB; discarded.")
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())

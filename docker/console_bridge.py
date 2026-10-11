#!/usr/bin/env python3
"""Forward Pterodactyl console input to Project Reclaimer local RCON.

The server remains supervised as a child. Signals and exit codes propagate.
"""
import os
import selectors
import shlex
import signal
import subprocess
import sys


def parse_command(line):
    line = line.strip()
    if not line:
        return None
    if line.lower() in ("help", "consolehelp"):
        return "help"
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

    while child.poll() is None:
        if stopping:
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
            line = key.fileobj.readline()
            if not line:
                selector.unregister(key.fileobj)
                continue
            try:
                command = parse_command(line)
            except ValueError as exc:
                print(f"[console] {exc}", flush=True)
                continue
            if command is None:
                continue
            if command == "stop":
                stop_child()
                break
            if command == "help":
                print("[console] Try: maps, modes, players, load Guardian Slayer, nextmap Valhalla Slayer, endround, endgame, stop.", flush=True)
                continue
            if not enabled:
                print("[console] Enable RCON and set a password, then restart.", flush=True)
                continue
            try:
                result = subprocess.run(
                    ["dedicated", "rcon", *command],
                    stdin=subprocess.DEVNULL, capture_output=True,
                    text=True, timeout=15, check=False,
                )
                if result.stdout.strip():
                    print(result.stdout.rstrip(), flush=True)
                if result.stderr.strip():
                    print(result.stderr.rstrip(), flush=True)
                if result.returncode:
                    print(f"[console] RCON command failed (exit {result.returncode}).", flush=True)
            except subprocess.TimeoutExpired:
                print("[console] RCON timed out; the game may still be starting.", flush=True)
            except OSError as exc:
                print(f"[console] RCON client failed: {exc}", flush=True)
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())

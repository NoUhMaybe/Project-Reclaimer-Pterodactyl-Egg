"""Compact, bounded diagnostics without credentials or player identifiers."""
import re


def versions(native, capabilities, env):
    detected = "unavailable (no runtime inference from the image label)"
    if native:
        try:
            detected = native.version()
        except ValueError:
            pass
    lines = ["Pinned image upstream: " + capabilities.version, "Detected dedicated executable: " + detected,
             "Command capabilities: " + capabilities.summary(),
             "Clients and server must use exactly the same Project Reclaimer version. Individual client versions are not exposed by documented RCON; mismatch is not inferred from player names or counts.",
             "Automatic updates: " + ("explicitly enabled in Startup; the running version can differ from the pin" if env.get("AUTO_UPDATE", "0").lower() in ("1", "true") else "disabled by default; this upgrade does not enable them")]
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", detected)
    if match and match.group(1) != capabilities.version.lstrip("v"):
        lines.append("VERSION MISMATCH: detected executable differs from the pin; capability gates remain conservative. Verify matching clients before testing.")
    lines.append("Native CLI authoring needs installed assets. Mod replacement still requires restart. Camera is on-foot multiplayer policy; campaign/Firefight, vehicles and modes with fixed cameras are exceptions.")
    return "\n".join(lines)


def report(content, configuration, client, capabilities, child):
    lines = ["Process: " + ("running" if child.poll() is None else "exited"),
             "RCON: " + ("last request connected" if client.connected else "disabled / not yet connected / unavailable"),
             "Image upstream build: " + capabilities.version + " (runtime auto-update may differ)",
             "Allocation: UDP " + configuration.env.get("SERVER_PORT", "unknown") + "; RCON loopback TCP only",
             "Manager overrides (file state; reload/startup status must be confirmed): " + str(configuration.read())]
    for relative in ("game/halo3/halo3.dll", "game/halo3/maps/shared.map"):
        path = content.server / relative
        lines.append(relative + ": " + ("present" if path.is_file() else "MISSING"))
    prefix = content.server.parent / ".wine-prefix" / "system.reg"
    lines.append("Wine prefix registry: " + ("present" if prefix.is_file() else "MISSING (presence check only)"))
    lines.append("Live status/vote: use Diagnostics 2/3. Log excerpts omit chat and sensitive identifiers.")
    return "\n".join(lines)


def recent_errors(server_dir):
    from .filesystem import Store
    store = Store(server_dir / "data")
    lines = []
    if store.root.exists():
        for path in sorted(store.root.glob("*/server.log"))[-4:]:
            relative = path.relative_to(store.root).as_posix()
            path = store.path(relative)
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 32768))
                tail = stream.read(32768).decode("utf-8", errors="replace")
            for line in tail.splitlines():
                if re.search(r"error|failed|missing|crash", line, re.I):
                    # Player IDs, IPs, secrets and chat must not be exported.
                    if re.search(r"password|token|secret|player|chat|refused|ban|kick|rcon", line, re.I):
                        continue
                    line = re.sub(r"\b[0-9a-fA-F]{16,}\b|\b\d{1,3}(?:\.\d{1,3}){3}\b", "[redacted]", line)
                    lines.append(line[:400])
    return "\n".join(lines[-15:]) or "No safe recent error excerpts. Full logs remain in File Manager."

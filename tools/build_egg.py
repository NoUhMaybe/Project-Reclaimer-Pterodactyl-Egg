#!/usr/bin/env python3
"""Maintenance tool: regenerate egg-project-reclaimer.json from scripts/install.sh.

Keeping the install script as a standalone, shellcheck-able file and
generating the PTDL_v2 JSON from it avoids manually re-escaping a 60+ line
Bash heredoc script by hand (error prone) and keeps the two in sync.

Run from the repository root:
    python3 tools/build_egg.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def variable(
    name: str,
    description: str,
    env_variable: str,
    default_value: str,
    rules: str,
    user_viewable: bool = True,
    user_editable: bool = True,
    field_type: str = "text",
) -> dict:
    return {
        "name": name,
        "description": description,
        "env_variable": env_variable,
        "default_value": default_value,
        "user_viewable": user_viewable,
        "user_editable": user_editable,
        "rules": rules,
        "field_type": field_type,
    }


def build() -> dict:
    install_script = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    variables = [
        variable(
            "Server Name",
            "The server's name, shown in the Server Browser. Required and unique, up to 48 characters.",
            "SERVER_NAME",
            "My Project Reclaimer Server",
            "required|string|between:1,48",
        ),
        variable(
            "Community Name",
            "Optional text shown beneath the server's name in the Server Browser (dedicated.toml host_name).",
            "HOST_NAME",
            "",
            "nullable|string|max:64",
        ),
        variable(
            "Max Players",
            "Maximum players admitted at once (1-127, split-screen counted). Campaign co-op is capped at 16 by upstream regardless of this value.",
            "MAX_PLAYERS",
            "16",
            "required|integer|between:1,127",
        ),
        variable(
            "Min Players",
            "Players the server waits for in its lobby before a playlist vote or automatic start begins (1-MAX_PLAYERS).",
            "MIN_PLAYERS",
            "1",
            "required|integer|between:1,127",
        ),
        variable(
            "Server Password",
            "Optional password players must enter to join. Leave blank for an open server. Separate from the RCON password.",
            "SERVER_PASSWORD",
            "",
            "nullable|string|max:128",
        ),
        variable(
            "Publicly Listed",
            "When enabled, the server reports to the public master server list (Server Browser). Disable to require Direct Connect.",
            "SERVER_PUBLIC",
            "true",
            "required|in:true,false",
        ),
        variable(
            "Playlist",
            "Path (relative to the server folder) to a playlist file to run, e.g. playlists/community.playlist.json. Upload the file first. Leave blank to use Map/Game Type below, or upstream's Slayer-on-Guardian default if those are also blank.",
            "PLAYLIST",
            "",
            "nullable|string|max:128",
        ),
        variable(
            "Map",
            "Base map name to host when Playlist is blank, e.g. Guardian. Ignored if Playlist is set.",
            "MAP",
            "",
            "nullable|string|max:64",
        ),
        variable(
            "Game Type",
            "Game mode to host when Playlist is blank, e.g. Slayer. Ignored if Playlist is set.",
            "GAME_TYPE",
            "",
            "nullable|string|max:64",
        ),
        variable(
            "Automatic Updates",
            "Let the server update Project Reclaimer itself on start and hourly (does not update this Docker image or MCC). Interrupts games in progress when it updates.",
            "AUTO_UPDATE",
            "false",
            "required|in:true,false",
        ),
        variable(
            "Enable RCON",
            "Turn on the password-protected remote console. Requires RCON Password to also be set.",
            "RCON_ENABLED",
            "false",
            "required|in:true,false",
        ),
        variable(
            "RCON Password",
            "Password for the remote console (8-128 characters). RCON stays disabled while this is blank, even if Enable RCON is on. RCON is unencrypted: prefer an SSH tunnel or VPN to reach it, see TROUBLESHOOTING.md.",
            "RCON_PASSWORD",
            "",
            "nullable|string|between:8,128",
        ),
        variable(
            "Anti-Cheat",
            "enforce kicks on detected cheating (default), detect only logs, off disables protection.",
            "ANTI_CHEAT",
            "enforce",
            "required|string|in:enforce,detect,off",
        ),
        variable(
            "Block VPN / Proxy Connections",
            "Refuse players connecting through a known VPN, proxy or hosting provider.",
            "BLOCK_VPN",
            "true",
            "required|in:true,false",
        ),
    ]

    egg = {
        "_comment": "Hand-authored PTDL_v2 egg for Project Reclaimer. Generated by tools/build_egg.py from scripts/install.sh; do not hand-edit the 'script' field below without also updating scripts/install.sh.",
        "meta": {"version": "PTDL_v2", "update_url": None},
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "name": "Project Reclaimer",
        "author": "nouhmaybe@users.noreply.github.com",
        "description": (
            "Community-developed Halo 3 dedicated multiplayer server (Project Reclaimer), "
            "run via a thin Pterodactyl-compatibility wrapper around the official "
            "ghcr.io/projectreclaimer/project-reclaimer-dedicated image. Requires your own "
            "legally-owned Halo 3 (MCC) game files; none are included. See "
            "https://projectreclaimer.dev/host for upstream documentation and "
            "https://github.com/NoUhMaybe/Project-Reclaimer-Pterodactyl-Egg for this egg."
        ),
        "features": [],
        "docker_images": {
        "ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.0-dev.1": "ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.0-dev.1"
        },
        "file_denylist": [],
        "startup": "reclaimer-entrypoint start",
        "config": {
            "files": "{}",
            "startup": "{}",
            "logs": "{}",
            "stop": "^C",
        },
        "scripts": {
            "installation": {
                "script": install_script,
                "container": "ghcr.io/ptero-eggs/installers:debian",
                "entrypoint": "bash",
            }
        },
        "variables": variables,
    }
    return egg


def main() -> None:
    egg = build()
    out_path = ROOT / "egg-project-reclaimer.json"
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(egg, fh, indent=4, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

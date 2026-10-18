"""Static menu rendering; all navigation uses submitted lines."""
MENUS = {
    "main": ("PROJECT RECLAIMER CONTROL CENTER", ["Live Game Control", "Playlist Manager", "Voting Manager", "Player Management", "Maps, Modes & Mods", "Server Configuration", "Diagnostics & Logs", "Help & Command Reference"]),
    "live": ("LIVE GAME CONTROL", ["Status / current map, mode and round", "Installed maps", "Installed modes", "Change map", "Change mode", "Change map and mode", "Queue next game", "Inspect next-game override", "End round", "End game"]),
    "playlists": ("PLAYLIST MANAGER", ["List playlists", "Create playlist", "Edit / inspect playlist", "Activate playlist for next start", "Duplicate playlist", "Validate playlist", "Delete playlist", "Import uploaded playlist", "List backups / restore"]),
    "draft": ("PLAYLIST EDITOR (unsaved session draft)", ["Add game", "Edit game", "Remove game", "Change voting duration", "Preview weight shares", "Validate", "Save playlist", "Rename playlist"]),
    "voting": ("VOTING MANAGER", ["Active vote / ballot counts", "Start playlist ballot", "Start endround vote", "Start endgame vote", "Start shuffle vote", "Start kick vote", "Pass vote", "Cancel vote"]),
    "players": ("PLAYER MANAGEMENT", ["Players / IDs, teams and available scores", "Inspect player", "Global announcement", "Private message", "Kick player", "Temporary ban", "Permanent ban", "Inspect bans", "Unban", "Mute", "Unmute", "Move player to team", "Shuffle teams", "Redistribute teams", "VPN status / allowances", "Allow VPN target", "Revoke VPN target", "Admins (0.9.16+)", "Add admin (0.9.16+)", "Remove admin (0.9.16+)", "Pardon kick (0.9.16+)"]),
    "content": ("MAPS, MODES & MODS", ["Running map inventory", "Running mode inventory", "Uploaded saved maps", "Uploaded game modes", "Installed mod folders / metadata", "Enable installed mod (restart)", "Disable installed mod (restart)", "Vote images", "Manual upload instructions"]),
    "config": ("SERVER CONFIGURATION", ["Inspect persistent manager overrides", "Set persistent setting (restart)", "Return to Startup / manual defaults", "Rename running server (live only)", "Set running ping limit (live only)", "Password / static / version-gated settings"]),
    "diagnostics": ("DIAGNOSTICS & LOGS", ["Process / storage / configuration health", "Live status", "Current vote", "Recent safe error excerpts", "Validate a playlist", "Runtime command reference"]),
    "help": ("HELP & COMMAND REFERENCE", ["Navigation and operation safety", "Upstream command reference", "Version / compatibility", "Persistence and rollback"]),
}
SECTIONS = ["live", "playlists", "voting", "players", "content", "config", "diagnostics", "help"]


def render(section):
    title, options = MENUS[section]
    lines = ["", title, "-" * len(title)]
    lines += [f"[{i}] {label}" for i, label in enumerate(options, 1)]
    lines += ["[0] " + ("Exit to RCON console" if section == "main" else "Back / discard unfinished draft"),
              "Select option > (help, refresh, back, cancel, exit; rcon <command>)"]
    return "\n".join(lines)

"""Persistent overrides; explicitly materialized for reload or applied at startup."""
import hashlib
import os
from .filesystem import Store

# Setting: type/range or choices, minimum version. Secrets stay in Startup.
SETTINGS = {
    "name": ("text", 1, 48), "host_name": ("text", 0, 64),
    "max_players": ("int", 1, 127), "min_players": ("int", 1, 127),
    "max_ping": ("int", 0, 1000), "anti_cheat": ("enforce", "detect", "off"),
    "block_vpn": ("bool",), "hidden": ("bool",), "votes": ("bool",),
    "team_changing": ("balanced", "game_type", "off"), "voice": ("bool",), "voice_team_only": ("bool",),
    "text_chat": ("bool",), "share_mods": ("bool",), "share_rate": ("int", 0, 1000000),
    "friendly_fire": ("bool",), "welcome": ("text", 0, 300),
    "voice_global": ("bool",), "voice_team": ("bool",), "voice_proximity": ("bool",),
    "load_timeout": ("int", 0, 600), "trust_player_games": ("bool",),
    "camera": ("first_person", "player_choice", "third_person"),
}

NEXT_GAME = {"friendly_fire", "team_changing", "camera"}
IDLE_RESTART = {"name", "hidden", "block_vpn", "anti_cheat"}


def timing(key):
    if key in NEXT_GAME:
        return "after reload, from the next multiplayer game; campaign/ODST game settings can require an idle restart"
    if key in IDLE_RESTART:
        return "after reload, when the server is empty (name may change its data folder); no forced match restart"
    return "after a confirmed reload, immediately for subsequent admission/game communication"


def validate_setting(key, value):
    if key not in SETTINGS:
        raise ValueError("Unsupported setting. Passwords, ports and RCON must be changed in Startup.")
    spec = SETTINGS[key]
    if spec[0] == "bool":
        if type(value) is not bool:
            raise ValueError("Enter true or false.")
    elif spec[0] == "int":
        if type(value) is not int or not spec[1] <= value <= spec[2]:
            raise ValueError(f"Enter an integer from {spec[1]} to {spec[2]}.")
    elif spec[0] == "text":
        if not isinstance(value, str) or not spec[1] <= len(value) <= spec[2] or any(ord(c) < 32 for c in value):
            raise ValueError(f"Enter {spec[1]}-{spec[2]} printable characters.")
    elif value not in spec:
        raise ValueError("Choose: " + ", ".join(spec))
    return value


class Configuration:
    def __init__(self, server_dir, env=None):
        self.store = Store(os.path.join(server_dir, ".manager"))
        self.env = dict(os.environ if env is None else env)

    def read(self):
        data = self.store.read("overrides.json") if self.store.path("overrides.json").exists() else {"version": 1, "settings": {}}
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("settings"), dict):
            raise ValueError("Invalid manager overrides; restore a backup or repair .manager/overrides.json.")
        for key, value in data["settings"].items():
            validate_setting(key, value)
        playlist = data.get("playlist")
        if playlist is not None:
            # Playlist is only an identifier; it is never a general-purpose path.
            from .playlists import filename
            filename(playlist)
            Store(self.store.root.parent / "playlists").path(playlist)
        return data

    def save_setting(self, key, value):
        data = self.read()
        data["settings"][key] = validate_setting(key, value)
        minimum = data["settings"].get("min_players", int(self.env.get("MIN_PLAYERS", "1")))
        maximum = data["settings"].get("max_players", int(self.env.get("MAX_PLAYERS", "16")))
        if minimum > maximum:
            raise ValueError("Minimum players cannot exceed maximum players; adjust the other limit first.")
        self.store.write("overrides.json", data)

    def activate(self, name):
        from .playlists import filename
        filename(name)
        if not Store(self.store.root.parent / "playlists").path(name).is_file():
            raise ValueError("Selected playlist is missing.")
        data = self.read()
        data["playlist"] = name
        self.store.write("overrides.json", data)

    def reset(self):
        self.store.write("overrides.json", {"version": 1, "settings": {}})

    def materialize(self, native):
        # Import only the existing sentinel renderer, never process supervision.
        from configure import patch_existing, render_server_block
        store = Store(self.store.root.parent)
        original = store.read_bytes("dedicated.toml").decode("utf-8")
        updated, appended = patch_existing(original, render_server_block(self.env, self.read()))
        if appended:
            raise ValueError("Managed block is missing. Restart to repair it before using live reload.")
        native.validate_configuration(updated)
        if updated != original:
            store.atomic_bytes("dedicated.toml", updated.encode("utf-8"), expected=hashlib.sha256(original.encode("utf-8")).hexdigest())
        return "Managed TOML prepared atomically; running state must be confirmed by the RCON reload reply."

"""Version gates checked through the 0.9.21 executable and versioned references."""
import re


class Capabilities:
    def __init__(self, version="0.9.21"):
        self.version = version
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
        self.number = tuple(map(int, match.groups())) if match else (0, 0, 0)

    def supports(self, feature):
        minimum = {"admin": (0, 9, 16), "admins": (0, 9, 16),
                   "pardon": (0, 9, 16), "reload": (0, 9, 18),
                   "playlist_cli": (0, 9, 15), "content_cli": (0, 9, 15),
                   "friendly_fire": (0, 9, 14), "welcome": (0, 9, 15),
                   "voice_global": (0, 9, 15), "voice_team": (0, 9, 15), "voice_proximity": (0, 9, 15),
                   "trust_player_games": (0, 9, 16), "camera": (0, 9, 20)}.get(feature, (0, 8, 14))
        return self.number >= minimum

    def summary(self):
        return ", ".join(feature + ("=yes" if self.supports(feature) else "=no")
                         for feature in ("playlist_cli", "content_cli", "admin", "pardon", "reload", "camera"))

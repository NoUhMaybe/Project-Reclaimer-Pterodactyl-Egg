"""Conservative version gates; the image pin remains 0.9.13."""
import re


class Capabilities:
    def __init__(self, version="0.9.13"):
        self.version = version
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
        self.number = tuple(map(int, match.groups())) if match else (0, 0, 0)

    def supports(self, feature):
        minimum = {"admin": (0, 9, 16), "admins": (0, 9, 16),
                   "pardon": (0, 9, 16), "reload": (0, 9, 18),
                   "playlist_cli": (0, 9, 15)}.get(feature, (0, 8, 14))
        return self.number >= minimum

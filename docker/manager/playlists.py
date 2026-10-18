"""Version-2 playlist editor. Pure filesystem backend; inventory is injected."""
import copy
import json
import math
import re
from .filesystem import Store


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def filename(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.json", name) or ".." in name:
        raise ValueError("Use a JSON filename, e.g. community.playlist.json; no directories or traversal.")
    return name


class Playlists:
    def __init__(self, server_dir, content):
        self.store = Store(content.server / "playlists")
        self.content = content

    def filename(self, name):
        filename(name)
        self.store.path(name)
        return name

    def load(self, name):
        return self.store.read(self.filename(name))

    def validate(self, data, maps, modes):
        errors = []
        if not isinstance(data, dict):
            return ["Playlist must be a JSON object."]
        if type(data.get("version", 2)) is not int or data.get("version", 2) != 2:
            errors.append("Only playlist version 2 is supported.")
        if not isinstance(data.get("name"), str) or not data["name"].strip() or len(data["name"]) > 128:
            errors.append("Name must contain 1-128 characters.")
        if not integer(data.get("vote_seconds", 20), 5, 120):
            errors.append("Voting duration must be an integer from 5 to 120.")
        games = data.get("games")
        if not isinstance(games, list) or not 3 <= len(games) <= 128:
            return errors + ["A playlist needs 3-128 games."]
        seen, images, modmaps, packages = set(), set(), set(), set()
        mapnames = {m.casefold() for m in maps}
        modenames = {m.casefold() for m in modes}
        for index, entry in enumerate(games, 1):
            prefix = f"Game {index}: "
            if not isinstance(entry, dict):
                errors.append(prefix + "must be an object.")
                continue
            for key, available, folder in (("map", mapnames, "Maps"), ("game", modenames, "Game Modes")):
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(prefix + key + " is required.")
                    continue
                if value.casefold() not in available:
                    errors.append(prefix + key + " is not in the running server's installed inventory: " + value)
                if value.startswith(folder + "/"):
                    try:
                        if not self.content.store.path(value).is_file():
                            errors.append(prefix + "saved content is missing: " + value)
                    except ValueError as exc:
                        errors.append(prefix + str(exc))
                if key == "map" and value.lower().startswith("workshop:"):
                    modmaps.add(value.casefold())
                    packages.add(value.split("/", 1)[0].casefold())
                if key == "game" and (value.casefold() in ("forge", "map editor", "editing") or "forge" == value.casefold().split("/")[-1].split(".")[0]):
                    errors.append(prefix + "Forge editing sessions cannot be playlist games.")
            if not integer(entry.get("weight", 1), 1, 100):
                errors.append(prefix + "weight must be an integer from 1 to 100.")
            if "name" in entry and (not isinstance(entry["name"], str) or len(entry["name"]) > 128):
                errors.append(prefix + "display name must be text up to 128 characters.")
            for field in ("rules", "options", "world"):
                if field not in entry:
                    continue
                value = entry[field]
                if not isinstance(value, dict) or any(not isinstance(k, str) or not k or not isinstance(v, (str, int, float, bool)) or isinstance(v, float) and not math.isfinite(v) for k, v in value.items()):
                    errors.append(prefix + field + " must be an object with scalar values.")
            for field in ("anti_cheat", "voice_team_only"):
                if field in entry and type(entry[field]) is not bool:
                    errors.append(prefix + field + " must be boolean.")
            if entry.get("anti_cheat") is True:
                errors.append(prefix + "anti_cheat may only turn protection off; omit it to use server policy.")
            world = entry.get("world", {})
            if isinstance(world, dict):
                if "sprint" in world and world["sprint"] not in ("off", "unlimited", "stamina"):
                    errors.append(prefix + "invalid sprint choice.")
                for field, low, high in (("sprint_speed_percent", 110, 200), ("sprint_stamina_seconds", 1, 30)):
                    if field in world and not integer(world[field], low, high):
                        errors.append(prefix + "invalid " + field)
            if "base_map" in entry:
                base = entry["base_map"]
                if not isinstance(base, str) or base.casefold() not in mapnames:
                    errors.append(prefix + "base_map is not installed.")
                elif base.lower().startswith("workshop:"):
                    modmaps.add(base.casefold())
                    packages.add(base.split("/", 1)[0].casefold())
            identity = {k: v for k, v in entry.items() if k not in ("name", "weight", "preview_image")}
            for field in ("rules", "options", "world"):
                if identity.get(field) == {}:
                    identity.pop(field)
            if identity.get("voice_team_only") is False:
                identity.pop("voice_team_only")
            signature = json.dumps(identity, sort_keys=True).casefold()
            if signature in seen:
                errors.append(prefix + "duplicate game; adjust the existing game's weight instead.")
            seen.add(signature)
            if "preview_image" in entry:
                image = entry["preview_image"]
                try:
                    if not isinstance(image, str) or "/" in image or "\\" in image or not image.lower().endswith((".png", ".jpg", ".jpeg")):
                        raise ValueError("Preview must be a PNG/JPEG filename.")
                    raw = self.content.store.read_bytes("Images/" + image)
                    if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
                        raise ValueError("Preview content is not PNG/JPEG.")
                    images.add(image)
                except (OSError, ValueError) as exc:
                    errors.append(prefix + "invalid/missing preview image: " + str(exc))
        if len(images) > 32:
            errors.append("At most 32 distinct vote images are supported.")
        if len(modmaps) > 23 or len(packages) > 16:
            errors.append("Playlist exceeds 23 distinct mod maps or 16 mod packages.")
        return errors

    def save(self, name, data, maps, modes, expected="any"):
        errors = self.validate(data, maps, modes)
        if errors:
            raise ValueError("\n".join(errors))
        self.store.write(self.filename(name), data, expected=expected)

    def duplicate(self, source, target, maps, modes):
        data = copy.deepcopy(self.load(source))
        self.save(target, data, maps, modes, expected=None)

    def restore(self, backup, target, maps, modes):
        if not re.fullmatch(r"[a-f0-9]{32}\.json", backup):
            raise ValueError("Select a backup ID from the backup list.")
        data = self.store.read(".backups/" + backup)
        self.save(target, data, maps, modes)

    @staticmethod
    def preview(data):
        games = data.get("games", [])
        total = sum(g.get("weight", 1) for g in games)
        lines = [f"{data.get('name', '')} | voting {data.get('vote_seconds', 20)}s | {len(games)} games"]
        for i, game in enumerate(games, 1):
            weight = game.get("weight", 1)
            share = 100 * weight / total if total else 0
            lines.append(f"{i:3} | {game.get('map', '?')} | {game.get('game', '?')} | weight {weight} | {share:.1f}% weight share | {game.get('name', '')}")
        lines.append("Weight shares are not ballot inclusion probabilities: draws exclude repeats and the previous game.")
        return "\n".join(lines)

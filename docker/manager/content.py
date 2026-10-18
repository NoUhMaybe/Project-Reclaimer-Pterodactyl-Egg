"""Read-only content discovery and persistent mod switches."""
import os
from pathlib import Path
from .filesystem import Store


class Content:
    def __init__(self, server_dir):
        self.server = Path(server_dir)
        self.store = Store(self.server / "content")

    def files(self, folder):
        root = self.store.path(folder)
        found = []
        if not root.exists():
            return found
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                relative = (Path(directory) / name).relative_to(self.store.root).as_posix()
                if not self.store.path(relative).is_symlink():
                    found.append(relative)
                if len(found) > 4096:
                    raise ValueError("Content inventory exceeds 4096 files; inspect using File Manager.")
        return found

    def mods(self):
        root = self.store.path("Mods")
        disabled = self.disabled().get("packages", [])
        result = []
        if root.exists():
            candidates = []
            for directory, dirs, files in os.walk(root, followlinks=False):
                path = Path(directory)
                dirs[:] = sorted(d for d in dirs if not (path / d).is_symlink())
                if "ModInfo.json" in files or any(name.lower().endswith(".map") for name in files) or "halo3" in dirs:
                    candidates.append(path)
                    dirs[:] = []
            # Empty/manual packages still appear so a switch can be prepared.
            candidates.extend(path for path in root.iterdir() if path.is_dir() and not path.is_symlink() and not any(path == c or path in c.parents for c in candidates))
            for path in sorted(set(candidates)):
                reference = path.relative_to(self.store.root).as_posix()
                metadata = {}
                if self.store.path(reference + "/ModInfo.json").is_file():
                    metadata = self.store.read(reference + "/ModInfo.json")
                result.append({"folder": reference, "enabled_after_restart": not any(reference == d or reference.startswith(d + "/") for d in disabled),
                               "metadata": metadata})
        return result

    def disabled_reference(self, reference):
        """Recognize installed Workshop references when their source is explicit.

        ModInfo schemas are not guessed. Only the documented Workshop directory
        and reclaimer-workshop.json marker establish an item ID here.
        """
        import re
        match = re.fullmatch(r"workshop:(\d+)/([^/]+)", reference, re.I)
        if not match:
            return False
        item, _mapfile = match.groups()
        for mod in self.mods():
            folder = mod["folder"]
            known_item = folder.split("/")[-1] if folder.startswith("Mods/Workshop/") else None
            marker = folder + "/reclaimer-workshop.json"
            if self.store.path(marker).is_file():
                value = self.store.read(marker)
                if isinstance(value, dict):
                    known_item = str(value.get("item", known_item))
            if known_item == item and not mod["enabled_after_restart"]:
                return True
        return False

    def disabled(self):
        path = self.store.path("disabled-mods.json")
        data = self.store.read("disabled-mods.json") if path.exists() else {"packages": []}
        if not isinstance(data, dict) or not isinstance(data.get("packages"), list) or not all(isinstance(p, str) for p in data["packages"]):
            raise ValueError("Invalid disabled-mods.json; leaving it untouched.")
        return data

    def set_enabled(self, reference, enabled):
        if reference not in [m["folder"] for m in self.mods()]:
            raise ValueError("Select an installed mod folder exactly as listed.")
        data = self.disabled()
        if enabled and any(reference.startswith(p + "/") for p in data["packages"]):
            raise ValueError("A parent mod folder is disabled. Update that parent entry using File Manager before enabling this package.")
        data["packages"] = [p for p in data["packages"] if p != reference]
        if not enabled:
            data["packages"].append(reference)
        self.store.write("disabled-mods.json", data)
        return "Mod switch saved with backup. Restart required; running games have not changed."

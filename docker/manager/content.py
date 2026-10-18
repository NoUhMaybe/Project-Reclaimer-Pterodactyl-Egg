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
            for path in sorted(root.iterdir()):
                if path.is_dir() and not path.is_symlink():
                    reference = "Mods/" + path.name
                    metadata = {}
                    if self.store.path(reference + "/ModInfo.json").is_file():
                        metadata = self.store.read(reference + "/ModInfo.json")
                    result.append({"folder": reference, "enabled_after_restart": reference not in disabled,
                                   "metadata": metadata})
        return result

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
        data["packages"] = [p for p in data["packages"] if p != reference]
        if not enabled:
            data["packages"].append(reference)
        self.store.write("disabled-mods.json", data)
        return "Mod switch saved with backup. Restart required; running games have not changed."

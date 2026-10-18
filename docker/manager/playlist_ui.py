"""Console prompts for playlist operations."""
import copy
import json
from .filesystem import Store


class PlaylistWorkflow:
    def select_playlist(self):
        return (yield from self.choose("playlist", self.playlists.store.names()))

    def validate(self, name, data):
        maps, modes = self.inventory()
        errors = self.playlists.validate(data, maps, modes)
        if errors:
            raise ValueError("\n".join(errors))
        self.emit("Local structural/inventory validation passed. Engine option keys, hidden saved-map dependencies and map-ID conflicts are not fully verified.")
        if self.live.capabilities.supports("playlist_cli") and name:
            # Native validator is a filesystem operation, never an RCON command.
            import subprocess
            try:
                result = subprocess.run(["dedicated", "playlist", "show", "playlists/" + name],
                                        cwd=self.content.server, capture_output=True, text=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError("Native playlist validator unavailable/timed out; no activation applied.") from None
            if result.returncode:
                raise ValueError("Native playlist validation failed; inspect the file with the upstream validator.")
            self.emit("Native playlist show completed successfully.")
        return maps, modes

    def playlist_action(self, choice):
        if choice == 1:
            self.emit("\n".join(self.playlists.store.names()) or "No playlists; choose Create.")
            return
        if choice == 2:
            filename = yield from self.ask("New filename (e.g. community.playlist.json)", self.playlists.filename)
            if self.playlists.store.path(filename).exists():
                raise ValueError("File exists; choose Edit instead.")
            name = yield from self.ask("Playlist display name")
            seconds = yield from self.ask("Voting duration seconds", self.number(5, 120), 20)
            self.filename, self.expected = filename, None
            self.draft = {"version": 2, "name": name, "vote_seconds": seconds, "games": []}
            self.section = "draft"
            return
        if choice == 9:
            backups = Store(self.playlists.store.root / ".backups").names()
            backup = yield from self.choose("backup", backups)
            target = yield from self.ask("Restore to playlist filename", self.playlists.filename)
            data = self.playlists.store.read(".backups/" + backup)
            maps, modes = self.validate(None, data)
            yield from self.confirm("restore playlist; existing target will be backed up")
            self.playlists.restore(backup, target, maps, modes)
            self.emit("Restored. Restart required if this playlist is active on 0.9.13.")
            return
        name = yield from self.select_playlist()
        data = self.playlists.load(name)
        if choice == 3:
            if not isinstance(data, dict) or not isinstance(data.get("games"), list):
                raise ValueError("Invalid playlist structure; import a version-2 playlist.")
            self.filename = name
            self.expected = self.playlists.store.digest(name)
            self.draft = copy.deepcopy(data)
            self.section = "draft"
        elif choice in (4, 6):
            self.validate(name, data)
            self.emit(self.playlists.preview(data))
            if choice == 4:
                yield from self.confirm("make playlist authoritative over Startup PLAYLIST/MAP/GAME_TYPE at next start; no running match interrupted")
                # The operator may have changed the file over SFTP while the
                # confirmation was pending. Validate the current copy again.
                self.validate(name, self.playlists.load(name))
                self.configuration.activate(name)
                self.emit("Playlist activation saved. Restart through Panel when ready; current rotation is unchanged.")
        elif choice in (5, 8):
            maps, modes = self.validate(name, data)
            target = yield from self.ask("New copy filename", self.playlists.filename)
            yield from self.confirm("save validated copy")
            self.playlists.duplicate(name, target, maps, modes)
            self.emit("Playlist copied. Unknown fields preserved; inspect engine compatibility before activation.")
        elif choice == 7:
            config = self.configuration.read()
            toml = self.content.server / "dedicated.toml"
            if config.get("playlist") == name or self.configuration.env.get("PLAYLIST", "").endswith(name) or toml.is_file() and name in toml.read_text(encoding="utf-8"):
                raise ValueError("This playlist is selected in configuration. Select another, restart and then delete it.")
            yield from self.confirm("delete " + name + "; a backup will be kept")
            backup = self.playlists.store.delete(name)
            self.emit("Deleted; backup " + backup)

    def draft_action(self, choice):
        draft = self.draft
        if not draft:
            raise ValueError("Open or create a playlist first.")
        if choice in (1, 2):
            index = None
            previous = {}
            if choice == 2:
                index = (yield from self.ask("Game number", self.number(1, len(draft["games"])))) - 1
                previous = draft["games"][index]
                if not isinstance(previous, dict):
                    previous = {}
            maps, modes = self.inventory()
            map_name = yield from self.choose("map", maps)
            mode = yield from self.choose("mode (engine checks compatibility)", modes)
            weight = yield from self.ask("Voting weight", self.number(1, 100), previous.get("weight", 1))
            display = yield from self.ask("Optional display name (- for none)", default=previous.get("name", "-"))
            entry = copy.deepcopy(previous)
            entry.update(map=map_name, game=mode, weight=weight)
            entry.pop("name", None)
            if display != "-":
                entry["name"] = display
            self.emit("Optional entry fields: rules, options, world, anti_cheat, voice_team_only, base_map, preview_image. Use - to preserve existing fields.")
            def options(value):
                if value == "-":
                    return {}
                obj = json.loads(value)
                allowed = {"rules", "options", "world", "anti_cheat", "voice_team_only", "base_map", "preview_image"}
                if not isinstance(obj, dict) or set(obj) - allowed:
                    raise ValueError("Use a JSON object containing only the listed fields.")
                return obj
            extra = yield from self.ask("Optional fields JSON, or -", options, "-")
            for key, value in extra.items():
                if value is None:
                    entry.pop(key, None)
                else:
                    entry[key] = value
            if index is None:
                draft["games"].append(entry)
            else:
                draft["games"][index] = entry
        elif choice == 3:
            index = (yield from self.ask("Game number", self.number(1, len(draft["games"])))) - 1
            del draft["games"][index]
        elif choice == 4:
            draft["vote_seconds"] = yield from self.ask("Voting seconds", self.number(5, 120), draft.get("vote_seconds", 20))
        elif choice == 5:
            self.emit(self.playlists.preview(draft))
        elif choice in (6, 7):
            maps, modes = self.validate(None, draft)
            if choice == 7:
                yield from self.confirm("save " + self.filename + "; previous version will be backed up")
                self.playlists.save(self.filename, draft, maps, modes, expected=self.expected)
                self.expected = self.playlists.store.digest(self.filename)
                self.emit("Playlist saved atomically. On 0.9.13, restart to apply edits to a running rotation.")
        elif choice == 8:
            draft["name"] = yield from self.ask("Playlist display name")


"""Console prompts for administration operations."""
import json
from .configuration import SETTINGS
from .parsing import text


class AdministrationWorkflow:
    def content_action(self, choice):
        if choice in (1, 2):
            self.reply(self.live.run(["maps" if choice == 1 else "modes"]))
        elif choice in (3, 4, 8):
            self.emit("\n".join(self.content.files({3: "Maps", 4: "Game Modes", 8: "Images"}[choice])) or "No uploaded content.")
        elif choice == 5:
            self.emit(json.dumps(self.content.mods(), indent=2, ensure_ascii=False))
        elif choice in (6, 7):
            mod = yield from self.choose("mod folder", [m["folder"] for m in self.content.mods()])
            yield from self.confirm(("enable " if choice == 6 else "disable ") + mod + "; restart required; validate affected playlists before restarting")
            self.emit(self.content.set_enabled(mod, choice == 6))
        else:
            self.emit("Upload compatible packages to server/content/Mods/<folder>/ using Pterodactyl File Manager or SFTP. Preserve ModInfo.json and halo3/maps layout. Upload saved maps/modes to content/Maps and content/Game Modes; PNG/JPEG vote images to content/Images (4 MiB each, 32 per playlist). No Steam/SteamCMD downloader is installed. Restart after mod changes; run playlist validation first.")

    def config_action(self, choice):
        if choice == 1:
            self.emit(json.dumps(self.configuration.read(), indent=2))
            self.emit("All stored overrides apply on next container start and win over Startup defaults. Runtime RCON changes remain independent.")
        elif choice == 2:
            key = yield from self.choose("persistent setting", sorted(SETTINGS))
            def parse(value):
                from .configuration import validate_setting
                spec = SETTINGS[key]
                if spec[0] == "bool":
                    if value.lower() not in ("true", "false"):
                        raise ValueError("Enter true or false.")
                    value = value.lower() == "true"
                elif spec[0] == "int":
                    value = int(value)
                else:
                    value = text(value)
                return validate_setting(key, value)
            value = yield from self.ask("New " + key + " (restart required)", parse)
            yield from self.confirm("persist " + key + "; Startup defaults remain shadowed until overrides reset")
            self.configuration.save_setting(key, value)
            self.emit("Saved with backup. Restart through Panel when ready; no live setting changed.")
        elif choice == 3:
            yield from self.confirm("clear all manager settings and playlist selection; return authority to Startup/manual settings at next start")
            self.configuration.reset()
            self.emit("Overrides reset with backup. Restart required.")
        elif choice in (4, 5):
            value = yield from self.ask("New live name" if choice == 4 else "Maximum ping (0 disables limit)", text if choice == 4 else self.number(0, 1000))
            yield from self.confirm("apply live change only; not persisted")
            self.reply(self.live.run(["servername" if choice == 4 else "maxping", str(value)]))
        else:
            self.emit("Join password and RCON password: use Startup, then restart. Console input is visible in Panel history; never enter secrets here. RCON bind/ports and game paths are static. welcome/voice scopes need 0.9.15, friendly_fire needs 0.9.14, character customization needs 0.9.18; this 0.9.13 image does not enable them. share_rate is Mbit/s; 0 means unlimited.")


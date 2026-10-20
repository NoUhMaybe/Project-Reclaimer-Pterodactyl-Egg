"""Console prompts for administration operations."""
import json
from .configuration import SETTINGS, timing
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
        elif choice == 10:
            if not self.native or not self.live.capabilities.supports("content_cli"):
                raise ValueError("Native content discovery requires 0.9.15+.")
            search = yield from self.ask("Native content search (- lists inventory summary)", default="-")
            self.emit(self.native.content(None if search == "-" else search))
        else:
            self.emit("Upload compatible packages to server/content/Mods/<folder>/ using Pterodactyl File Manager or SFTP. Preserve ModInfo.json and halo3/maps layout. Upload saved maps/modes to content/Maps and content/Game Modes; PNG/JPEG vote images to content/Images (4 MiB each, 32 per playlist). No Steam/SteamCMD downloader is installed. Restart after mod changes; run playlist validation first.")

    def config_action(self, choice):
        if choice == 1:
            self.emit(json.dumps(self.configuration.read(), indent=2))
            self.emit("Stored overrides win over Startup defaults. Pending edits require Apply/reload (option 7) or next startup; this display alone does not prove live application.")
        elif choice == 2:
            key = yield from self.choose("persistent setting", sorted(k for k in SETTINGS if self.live.capabilities.supports(k)))
            def parse(value):
                from .configuration import validate_setting
                spec = SETTINGS[key]
                if spec[0] == "bool":
                    if value.lower() not in ("true", "false"):
                        raise ValueError("Enter true or false.")
                    value = value.lower() == "true"
                elif spec[0] == "int":
                    value = int(value)
                elif spec[0] == "text" and spec[1] == 0 and value == "-":
                    value = ""
                else:
                    value = text(value)
                return validate_setting(key, value)
            value = yield from self.ask("New " + key + " (pending until apply/reload or restart; - clears optional text)", parse)
            self.emit("Application timing: " + (timing(key) if self.live.capabilities.supports("reload") else "restart required"))
            if key == "camera":
                self.emit("Camera controls on-foot multiplayer views. Modes built around third person and vehicle views keep their own cameras. Campaign co-op and Firefight are unaffected.")
            yield from self.confirm("persist " + key + "; does not yet generate live TOML; Startup defaults remain shadowed until overrides reset")
            self.configuration.save_setting(key, value)
            self.emit("Pending override saved with backup. Use option 7 to prepare TOML and request reload, or restart; no live change is claimed.")
        elif choice == 3:
            yield from self.confirm("clear all manager settings and playlist selection; return authority to Startup/manual settings at next start")
            self.configuration.reset()
            self.emit("Overrides reset with backup. Apply/reload or restart to regenerate the managed TOML.")
        elif choice in (4, 5):
            value = yield from self.ask("New live name" if choice == 4 else "Maximum ping (0 disables limit)", text if choice == 4 else self.number(0, 1000))
            yield from self.confirm("apply live change only; not persisted")
            self.reply(self.live.run(["servername" if choice == 4 else "maxping", str(value)]))
        elif choice == 7:
            if not self.native or not self.live.capabilities.supports("reload"):
                raise ValueError("Safe native reload requires 0.9.18+; restart to apply pending overrides on older images.")
            if not self.live.client.enabled:
                raise ValueError("Enable RCON and restart before requesting reload. Pending overrides remain saved for next startup.")
            yield from self.confirm("prepare/validate managed TOML and request reload; immediate settings may change now, game settings next game, and process changes at idle; no forced restart")
            self.emit(self.configuration.materialize(self.native))
            reply = self.reply(self.live.run(["reload"]))
            self.emit("Server confirmed the reload request above; follow its immediate/next-game/idle timing. Refresh for reload_applied events." if reply.ok else
                      "Reload was not confirmed. Generated files remain saved; the engine may retain its previous configuration or auto-reload separately. Resolve the error and inspect status/events before retrying.")
        else:
            self.emit("Passwords, allocation ports and paths stay in Startup/admin files. Console input cannot be hidden. Welcome, friendly fire, voice scopes and camera are available on 0.9.20+; save pending overrides then use Apply/reload. Camera changes from the next multiplayer game; campaign/Firefight and mode-specific/vehicle cameras are exceptions. Character-pack configuration and ODST/campaign authoring stay in administrator files; no Steam/SteamCMD downloader is added. share_rate is Mbit/s.")


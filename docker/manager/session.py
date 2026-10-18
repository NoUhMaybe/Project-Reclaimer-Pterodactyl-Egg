"""Per-bridge menu session. No input(), terminal control or shared draft files."""
import shlex
from . import menus
from .parsing import text
from .playlist_ui import PlaylistWorkflow
from .players_ui import PlayerWorkflow
from .administration_ui import AdministrationWorkflow
from .diagnostics import report, recent_errors


class Cancelled(Exception):
    pass


class Session(PlaylistWorkflow, PlayerWorkflow, AdministrationWorkflow):
    def __init__(self, live, playlists, content, configuration, child, emit=print, native=None):
        self.live = live
        self.playlists = playlists
        self.content = content
        self.configuration = configuration
        self.child = child
        self.emit = emit
        self.native = native
        self.active = False
        self.section = "main"
        self.flow = None
        self.prompt = ""
        self.draft = None
        self.filename = None
        self.expected = None

    def show(self):
        if self.section == "draft" and self.draft:
            self.emit(self.playlists.preview(self.draft))
        self.emit(menus.render(self.section))

    def leave(self):
        self.flow = None
        self.draft = None
        self.active = False
        self.section = "main"
        self.emit("[manager] Returned to RCON console. Server continues running.")

    def handle(self, line):
        line = line.strip()
        lower = line.lower()
        if lower in ("menu", "manager", "console help"):
            self.active = True
            if self.flow:
                self.emit(self.prompt)
            else:
                self.show()
            return True
        if not self.active:
            return False
        try:
            if lower == "exit":
                self.leave()
            elif lower in ("back", "cancel", "0"):
                # A zero typed as a valid prompt value is data, except at a
                # confirmation, where it safely cancels.
                if line == "0" and self.flow and not self.prompt.startswith("Confirm"):
                    self.advance(line)
                elif self.flow:
                    self.flow = None
                    self.emit("Operation cancelled; no pending change applied.")
                    self.show()
                elif self.section == "main":
                    self.leave()
                else:
                    self.section = "playlists" if self.section == "draft" else "main"
                    self.draft = None
                    self.show()
            elif lower == "help":
                self.emit("Submit a numbered option. exit returns to raw RCON; back/0 navigates. cancel abandons a prompt; refresh re-queries state. rcon <command> sends a raw command. stop always shuts down. Passwords belong in Startup because Panel input cannot be hidden.")
                if self.flow:
                    self.emit(self.prompt)
            elif lower == "refresh":
                if self.section in ("main", "live", "diagnostics"):
                    self.reply(self.live.status())
                elif self.section == "voting":
                    self.reply(self.live.run(["vote"]))
                elif self.section == "players":
                    self.reply(self.live.run(["players"]))
                if self.flow:
                    self.emit(self.prompt)
                else:
                    self.show()
            elif lower.startswith("rcon "):
                tokens = shlex.split(line[5:])
                if tokens and tokens[0].lower() in ("stop", "quit", "exit"):
                    raise ValueError("Use stop directly for a supervised graceful shutdown.")
                self.reply(self.live.run(tokens))
                if self.flow:
                    self.emit(self.prompt)
            elif self.flow:
                self.advance(line)
            else:
                if not line.isdigit() or not 1 <= int(line) <= len(menus.MENUS[self.section][1]):
                    raise ValueError("Invalid selection. Submit a listed number, help or exit.")
                if self.section == "main":
                    self.section = menus.SECTIONS[int(line) - 1]
                    self.show()
                else:
                    self.flow = self.action(self.section, int(line))
                    self.advance()
        except Cancelled:
            self.flow = None
            self.emit("Operation cancelled; nothing applied.")
            self.show()
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.flow = None
            self.emit("[manager] " + self.live.client.redact(str(exc)))
            self.emit("Use help, refresh or another option.")
        return True

    def advance(self, value=None):
        try:
            self.prompt = next(self.flow) if value is None else self.flow.send(value)
            self.emit(self.prompt)
        except StopIteration:
            self.flow = None
            self.show()

    def ask(self, prompt, parse=text, default=None):
        while True:
            value = yield prompt + (f" [{default}]" if default is not None else "") + " >"
            if not value and default is not None:
                value = str(default)
            try:
                return parse(value)
            except (ValueError, TypeError) as exc:
                self.emit("Invalid value: " + str(exc))

    def number(self, low, high):
        def parse(value):
            value = int(value)
            if not low <= value <= high:
                raise ValueError(f"Choose {low}-{high}.")
            return value
        return parse

    def confirm(self, description):
        answer = yield "Confirm: " + description + " | type yes to apply; no/cancel to abandon >"
        if answer.strip().lower() != "yes":
            raise Cancelled()

    def reply(self, reply):
        self.emit(reply.text or ("Request accepted." if reply.ok else "Request failed."))
        return reply

    def inventory(self):
        return self.live.names("maps"), self.live.names("modes")

    def choose(self, label, values):
        if not values:
            raise ValueError("No " + label + " available.")
        self.emit("\n".join(f"{i:3} | {value}" for i, value in enumerate(values, 1)))
        def parse(value):
            if value.isdigit() and 1 <= int(value) <= len(values):
                return values[int(value) - 1]
            value = text(value)
            match = [item for item in values if item.casefold() == value.casefold()]
            if len(match) != 1:
                raise ValueError("Choose a listed number or exact reference.")
            return match[0]
        return (yield from self.ask("Select " + label, parse))

    def action(self, section, choice):
        if section == "live":
            queries = {1: "status", 2: "maps", 3: "modes", 8: "nextmap"}
            if choice in queries:
                self.reply(self.live.status() if choice == 1 else self.live.run([queries[choice]]))
            elif choice in (9, 10):
                cmd = "endround" if choice == 9 else "endgame"
                yield from self.confirm(cmd + " interrupts the current match")
                self.reply(self.live.run([cmd]))
            else:
                maps, modes = self.inventory()
                tokens = [{4: "map", 5: "mode", 6: "load", 7: "nextmap"}[choice]]
                if choice != 5:
                    tokens.append((yield from self.choose("map", maps)))
                if choice != 4:
                    tokens.append((yield from self.choose("mode", modes)))
                yield from self.confirm("queue next game" if choice == 7 else "change current game; active match will end")
                self.reply(self.live.run(tokens))
        elif section == "playlists":
            yield from self.playlist_action(choice)
        elif section == "draft":
            yield from self.draft_action(choice)
        elif section == "voting":
            if choice == 1:
                self.reply(self.live.run(["vote"]))
            elif choice in (7, 8):
                cmd = "passvote" if choice == 7 else "cancelvote"
                yield from self.confirm(cmd + " changes the current vote")
                self.reply(self.live.run([cmd]))
            else:
                kind = {2: "playlist", 3: "endround", 4: "endgame", 5: "shuffle", 6: "kick"}[choice]
                target = (yield from self.player()) if kind == "kick" else None
                yield from self.confirm("start " + kind + " vote")
                self.reply(self.live.vote(kind, target))
        elif section == "players":
            yield from self.player_action(choice)
        elif section == "content":
            yield from self.content_action(choice)
        elif section == "config":
            yield from self.config_action(choice)
        elif section == "diagnostics":
            if choice == 1:
                self.emit(report(self.content, self.configuration, self.live.client, self.live.capabilities, self.child))
            elif choice in (2, 3, 6):
                self.reply(self.live.status() if choice == 2 else self.live.run(["vote" if choice == 3 else "help"]))
            elif choice == 4:
                self.emit(self.live.client.redact(recent_errors(self.content.server)))
            elif choice == 5:
                yield from self.playlist_action(6)
            elif choice == 7:
                self.emit(self.version_report())
        elif section == "help":
            if choice == 2:
                self.reply(self.live.run(["help"]))
            elif choice == 3:
                self.emit(self.version_report())
            elif choice == 4:
                self.emit(".manager/overrides.json wins over Startup defaults in the managed server block. Save pending settings, then use Config 7 to prepare TOML and request a confirmed reload, or restart. Config 3 resets overrides. Restore playlists using Playlist 9. Roll back new settings/TOML before returning to 0.9.13.")
            else:
                self.emit("menu/manager enters. exit returns to raw RCON. back/0 navigates; cancel abandons a prompt. refresh re-queries; rcon <command> escapes. stop and Panel Stop shut down. No TTY required. Drafts are lost on exit/disconnect/restart. RCON accepted is not transition completed; refresh status and inspect logs.")

    def version_report(self):
        from .diagnostics import versions
        return versions(self.native, self.live.capabilities, self.configuration.env)







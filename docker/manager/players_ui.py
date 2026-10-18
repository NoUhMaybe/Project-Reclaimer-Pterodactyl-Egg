"""Console prompts for players operations."""
from .commands import payload


class PlayerWorkflow:
    def player(self):
        reply = self.reply(self.live.run(["players"]))
        if not reply.ok:
            raise ValueError("Cannot select a player while RCON is unavailable.")
        data = payload(reply.data)
        players = data.get("players") if isinstance(data, dict) else data
        if players == []:
            raise ValueError("No connected players.")
        ids = []
        if isinstance(players, list):
            for player in players:
                if isinstance(player, dict) and player.get("id", player.get("player_id")):
                    ids.append(str(player.get("id", player.get("player_id"))))
        if ids:
            return (yield from self.choose("connected player ID", ids))
        return (yield from self.ask("Connected player ID or #number from players (server validates)"))

    def player_action(self, choice):
        queries = {1: "players", 8: "bans", 15: "vpn", 18: "admins"}
        if choice in queries:
            self.reply(self.live.run([queries[choice]]))
            return
        cmd = {2: "players", 3: "say", 4: "tell", 5: "kick", 6: "ban", 7: "ban", 9: "unban", 10: "mute", 11: "unmute", 12: "team", 13: "shuffle", 14: "teamcount", 16: "vpnallow", 17: "vpnrevoke", 19: "admin", 20: "admin", 21: "pardon"}[choice]
        if not self.live.capabilities.supports(cmd):
            self.reply(self.live.run([cmd]))
            return
        tokens = [cmd]
        if choice in (19, 20):
            tokens.append("add" if choice == 19 else "remove")
        if choice in (2, 4, 5, 6, 7, 10, 11, 12, 19):
            target = yield from self.player()
            if choice == 2:
                self.emit("Selected player ID " + target + "; inspect the players response above. Ping/score fields depend on upstream.")
                return
            tokens.append(target)
        elif choice in (9, 16, 17, 20, 21):
            tokens.append((yield from self.ask("Exact player ID / address / range / stored name")))
        if choice in (3, 4):
            tokens.append((yield from self.ask("Message")))
        if choice == 6:
            def duration(value):
                import re
                if not re.fullmatch(r"[1-9][0-9]{0,5}[mhdw]", value):
                    raise ValueError("Use a duration such as 30m, 12h, 7d or 2w.")
                return value
            tokens.append((yield from self.ask("Ban duration", duration)))
        if choice in (5, 6, 7, 10, 16):
            reason = yield from self.ask("Optional reason/note (- for none)", default="-")
            if reason != "-":
                tokens.append(reason)
        if choice == 12:
            tokens.append((yield from self.choose("team", ["red", "blue", "green", "orange", "purple", "gold", "brown", "pink"])))
        if choice == 14:
            tokens.append(str((yield from self.ask("Number of teams", self.number(2, 8)))))
        yield from self.confirm(cmd + " request for selected target(s); shared bans/admins/VPN changes affect other servers using the same ban list")
        self.reply(self.live.run(tokens))


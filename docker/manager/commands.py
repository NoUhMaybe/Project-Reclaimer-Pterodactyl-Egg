"""Runtime command semantics; this backend never writes persistent files."""
from .rcon_client import Reply
import time
from .formatting import structured


def payload(data):
    if isinstance(data, dict):
        for key in ("result", "data"):
            if isinstance(data.get(key), (dict, list)):
                return data[key]
    return data


class LiveOperations:
    def __init__(self, client, capabilities):
        self.client = client
        self.capabilities = capabilities
        self.pending = None
        self.request_time = 0

    def run(self, tokens):
        if not tokens:
            raise ValueError("Enter an RCON command after rcon.")
        tokens = [tokens[0].lower(), *tokens[1:]]
        if not self.capabilities.supports(tokens[0]):
            return Reply(False, f"{tokens[0]} is unavailable on {self.capabilities.version}; admin/pardon need 0.9.16, reload needs 0.9.18.")
        if self.client.enabled and ((tokens[0] in ("map", "mode", "load", "nextmap", "team", "teamcount") and len(tokens) > 1) or tokens[0] in ("shuffle", "reload")):
            self.client.events.start()
            self.request_time = time.monotonic()
        # Reload replies contain the authoritative timing/result text. Do not
        # replace it with a null JSON data payload from the CLI.
        reply = self.client.execute(tokens, json_reply=tokens[0] != "reload")
        if reply.ok and reply.data is not None and tokens[0] != "reload":
            formatted = structured(tokens[0], reply.data)
            if formatted:
                reply.text = formatted
        if reply.ok and tokens[0] in ("map", "mode", "load", "nextmap") and len(tokens) > 1:
            self.pending = tuple(tokens)
            reply.text += ("\nNext-game request accepted; current game continues. Inspect nextmap and refresh status."
                           if tokens[0] == "nextmap" else
                           "\nChange request accepted; transition is NOT confirmed. Refresh status to observe it.")
        return reply

    def status(self):
        queried_at = time.monotonic()
        reply = self.run(["status"])
        for event in self.client.events.since(self.request_time):
            if event.get("action") in ("load", "team", "shuffle", "teamcount", "reload", "reload_applied"):
                outcome = "completed" if event.get("ok") else "FAILED"
                reply.text += "\nObserved control event: " + str(event.get("action")) + " " + outcome + ": " + str(event.get("text", ""))
                if event.get("action") == "load":
                    self.pending = None
        self.request_time = queried_at
        state = payload(reply.data)
        if self.pending and isinstance(state, dict):
            command, *values = self.pending
            wanted_map = values[0] if command in ("map", "load") else None
            wanted_mode = values[-1] if command in ("mode", "load") else None
            actual_map = state.get("map")
            actual_mode = state.get("mode", state.get("game"))
            same = lambda actual, wanted: isinstance(actual, str) and actual.casefold() == wanted.casefold()
            if command != "nextmap" and (wanted_map or wanted_mode):
                if (not wanted_map or same(actual_map, wanted_map)) and (not wanted_mode or same(actual_mode, wanted_mode)):
                    reply.text += "\nRequested map/mode observed in status (polling; no control-event confirmation)."
                    self.pending = None
                else:
                    reply.text += "\nRequested transition not observed yet. It may be pending or failed; inspect game logs."
        return reply

    def vote(self, kind, target=None):
        status = self.status()
        if not status.ok:
            return status
        state = payload(status.data)
        if isinstance(state, dict):
            if state.get("votes") is False and kind != "playlist":
                return Reply(False, "Player votes are disabled in the running configuration.")
            if kind == "playlist":
                rotation_reply = self.run(["nextmap"])
                if not rotation_reply.ok:
                    return rotation_reply
                rotation = payload(rotation_reply.data)
                if isinstance(rotation, dict) and "rotation" in rotation and not rotation["rotation"]:
                    return Reply(False, "Playlist voting requires an active rotation loaded by the running server; restart after saving activation.")
            if kind in ("endround", "shuffle") and state.get("phase") not in (None, "playing"):
                return Reply(False, "This vote requires an active round.")
            if kind == "shuffle" and state.get("team_game") is False:
                return Reply(False, "Shuffle voting requires a team game.")
            players = state.get("players")
            count = len(players) if isinstance(players, list) else players
            if isinstance(count, int) and kind in ("kick", "shuffle") and count < (3 if kind == "kick" else 2):
                return Reply(False, "Not enough players for this vote.")
            if state.get("vote"):
                return Reply(False, "Another moderation vote is already active.")
        # The server is the authority for prerequisites absent from its JSON.
        if kind == "kick" and not target:
            return Reply(False, "Select a connected player ID or #number.")
        return self.run(["startvote", kind] + ([target] if target else []))

    def names(self, kind):
        reply = self.run([kind])
        if not reply.ok:
            raise ValueError(reply.text)
        data = payload(reply.data)
        if isinstance(data, dict) and kind in data:
            data = data[kind]
        names = []
        def collect(value):
            if isinstance(value, str):
                names.append(value)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                name = value.get("reference", value.get("name"))
                if isinstance(name, str):
                    names.append(name)
                else:
                    for item in value.values():
                        if isinstance(item, list):
                            collect(item)
        collect(data)
        if not names:
            raise ValueError("No structured inventory available. Use raw maps/modes to inspect output; playlist validation requires a verified inventory.")
        return sorted(set(names), key=str.casefold)

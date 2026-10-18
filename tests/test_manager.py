"""Portable backend/menu tests. No game assets, RCON service or TTY needed."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "docker"))
from manager.capabilities import Capabilities
from manager.commands import LiveOperations
from manager.configuration import Configuration
from manager.content import Content
from manager.events import Events
from manager.filesystem import Store, Conflict
from manager.playlists import Playlists
from manager.rcon_client import Reply, RconClient, command_text
from manager.session import Session

MAPS = ["Guardian", "The Pit", "Valhalla"]
MODES = ["Slayer", "Capture the Flag", "Forge"]


def rotation():
    return {"version": 2, "name": "Community", "vote_seconds": 25, "games": [
        {"map": m, "game": "Slayer", "weight": i} for i, m in enumerate(MAPS, 1)]}


class FakeClient:
    def __init__(self):
        self.enabled = True
        self.connected = True
        self.calls = []
        self.state = {"map": "Guardian", "mode": "Slayer", "players": 4, "phase": "playing", "votes": True}
        self.players = [{"id": "a" * 64, "number": 1, "name": "Master Chief", "team": "red"}]
        self.events = MagicMock()
        self.events.since.return_value = []

    def redact(self, value):
        return value

    def execute(self, tokens, json_reply=False):
        self.calls.append(tokens)
        if not self.enabled:
            return Reply(False, "Enable RCON and set a password")
        data = {"maps": {"entries": [{"reference": m, "name": m, "kind": "base"} for m in MAPS]},
                "modes": {"entries": [{"reference": m, "name": m, "kind": "mode"} for m in MODES]},
                "status": self.state, "players": {"players": self.players},
                "nextmap": {"rotation": rotation()["games"]}}.get(tokens[0], {})
        return Reply(True, "reply " + tokens[0], data)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "server"
        self.root.mkdir()
        self.content = Content(self.root)
        self.playlists = Playlists(self.root, self.content)
        self.config = Configuration(self.root, {"SERVER_PORT": "49176"})
        self.client = FakeClient()
        self.live = LiveOperations(self.client, Capabilities())
        self.out = []
        self.child = MagicMock()
        self.child.poll.return_value = None
        self.session = Session(self.live, self.playlists, self.content, self.config, self.child, self.out.append)

    def lines(self, *values):
        for value in values:
            self.session.handle(value)


class MenuTests(Fixture):
    def test_aliases_navigation_exit_and_raw_return(self):
        for alias in ("menu", "manager", "console help"):
            self.lines(alias)
            self.assertTrue(self.session.active)
            self.assertIn("CONTROL CENTER", self.out[-1])
            self.lines("1", "back", "0")
            self.assertFalse(self.session.active)
            self.assertFalse(self.session.handle('load "The Pit" "Capture the Flag"'))
        self.assertEqual(self.client.calls, [])

    def test_invalid_help_refresh_and_raw_escape(self):
        self.lines("menu", "abc", "help", "refresh", 'rcon load "The Pit" "Capture the Flag"')
        self.assertIn("Invalid selection", "\n".join(self.out))
        self.assertIn(["status"], self.client.calls)
        self.assertIn(["load", "The Pit", "Capture the Flag"], self.client.calls)

    def test_disruptive_command_cancel_and_confirm(self):
        self.lines("menu", "1", "10", "no")
        self.assertNotIn(["endgame"], self.client.calls)
        self.lines("10", "yes")
        self.assertIn(["endgame"], self.client.calls)

    def test_exit_in_prompt_clears_pending_action(self):
        self.lines("menu", "1", "10", "exit", "yes")
        self.assertNotIn(["endgame"], self.client.calls)
        self.assertFalse(self.session.active)

    def test_disabled_rcon_and_offline_file_menu(self):
        self.client.enabled = False
        self.lines("menu", "1", "1")
        self.assertIn("Enable RCON", "\n".join(self.out))
        self.lines("back", "2", "1")
        self.assertIn("No playlists", "\n".join(self.out))

    def test_create_edit_save_playlist_entirely_by_menu(self):
        self.lines("menu", "2", "2", "community.json", "Community", "25")
        for mapname in MAPS:
            self.lines("1", mapname, "Slayer", "2", "-", "-")
        self.assertFalse(self.playlists.store.path("community.json").exists())
        self.lines("7", "yes")
        data = self.playlists.load("community.json")
        self.assertEqual(len(data["games"]), 3)
        self.lines("2", "1", '"The Pit"', '"Capture the Flag"', "3", "CTF", "-")
        self.lines("7", "yes")
        self.assertEqual(self.playlists.load("community.json")["games"][0]["game"], "Capture the Flag")
        self.assertEqual(len(Store(self.playlists.store.root / ".backups").names()), 1)

    def test_draft_cancel_has_no_disk_changes(self):
        self.lines("menu", "2", "2", "draft.json", "Unsaved", "20", "1", "Guardian", "cancel", "exit")
        self.assertFalse(self.playlists.store.path("draft.json").exists())

    def test_playlist_activation_is_confirmed_and_persistent(self):
        self.playlists.save("community.json", rotation(), MAPS, MODES)
        self.lines("menu", "2", "4", "1", "cancel")
        self.assertNotIn("playlist", self.config.read())
        self.lines("4", "1", "yes")
        self.assertEqual(Configuration(self.root).read()["playlist"], "community.json")
        self.assertNotIn(["reload"], self.client.calls)

    def test_moderation_targets_stable_id_and_confirms(self):
        self.lines("menu", "4", "6", "1", "30m", "reason", "yes")
        self.assertIn(["ban", "a" * 64, "30m", "reason"], self.client.calls)
        self.lines("5", "1", "-", "cancel")
        self.assertFalse(any(c[0] == "kick" for c in self.client.calls))

    def test_empty_players_and_version_gate(self):
        self.client.players = []
        self.lines("menu", "4", "5")
        self.assertIn("No connected players", "\n".join(self.out))
        self.lines("19")
        self.assertFalse(any(c[0] == "admin" for c in self.client.calls))

    def test_duplicate_import_delete_restore_flows(self):
        self.playlists.save("original.json", rotation(), MAPS, MODES)
        self.lines("menu", "2", "8", "original.json", "copy.json", "yes")
        self.assertEqual(self.playlists.load("copy.json"), rotation())
        self.lines("7", "copy.json", "yes")
        self.assertFalse(self.playlists.store.path("copy.json").exists())
        self.lines("9", "1", "restored.json", "yes")
        self.assertEqual(self.playlists.load("restored.json"), rotation())


class PlaylistTests(Fixture):
    def test_valid_structure_and_unknown_fields_preserved(self):
        data = rotation()
        data["future_supported_field"] = {"x": 1}
        self.playlists.save("a.json", data, MAPS, MODES)
        self.playlists.duplicate("a.json", "b.json", MAPS, MODES)
        self.assertEqual(self.playlists.load("b.json"), data)
        with self.assertRaises(Conflict):
            self.playlists.duplicate("a.json", "b.json", MAPS, MODES)

    def test_rejects_bad_bounds_types_references_and_duplicates(self):
        variants = [{"version": 3}, {"name": ""}, {"vote_seconds": 4}, {"vote_seconds": 121}, {"games": []}]
        for update in variants:
            data = rotation()
            data.update(update)
            self.assertTrue(self.playlists.validate(data, MAPS, MODES), update)
        for update in ({"map": "Missing"}, {"game": "Missing"}, {"game": "Forge"}, {"weight": True},
                       {"weight": 101}, {"rules": []}, {"options": {"bad": []}}, {"anti_cheat": True},
                       {"world": {"sprint": "fast"}}, {"base_map": "missing"}, {"preview_image": "../secret.png"}):
            data = rotation()
            data["games"][0].update(update)
            self.assertTrue(self.playlists.validate(data, MAPS, MODES), update)
        data = rotation()
        data["games"][1] = dict(data["games"][0], name="A different name", weight=100)
        self.assertTrue(self.playlists.validate(data, MAPS, MODES))

    def test_preview_image_content_and_size(self):
        self.content.store.atomic_bytes("Images/a.png", b"\x89PNG\r\n\x1a\nexample")
        data = rotation()
        data["games"][0]["preview_image"] = "a.png"
        self.assertEqual(self.playlists.validate(data, MAPS, MODES), [])
        self.content.store.atomic_bytes("Images/a.png", b"not a png")
        self.assertTrue(self.playlists.validate(data, MAPS, MODES))

    def test_mod_limits(self):
        data = rotation()
        data["games"] = [{"map": f"workshop:{i + 1}/arena", "game": "Slayer"} for i in range(24)]
        errors = self.playlists.validate(data, [g["map"] for g in data["games"]], MODES)
        self.assertIn("23 distinct mod maps", "\n".join(errors))

    def test_concurrent_edits_fail_without_overwriting(self):
        self.playlists.save("a.json", rotation(), MAPS, MODES)
        digest = self.playlists.store.digest("a.json")
        changed = rotation()
        changed["name"] = "SFTP edit"
        self.playlists.save("a.json", changed, MAPS, MODES)
        with self.assertRaises(Conflict):
            self.playlists.save("a.json", rotation(), MAPS, MODES, expected=digest)
        self.assertEqual(self.playlists.load("a.json")["name"], "SFTP edit")

    def test_atomic_failure_keeps_original_and_backup_restore(self):
        self.playlists.save("a.json", rotation(), MAPS, MODES)
        with patch("manager.filesystem.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.playlists.save("a.json", rotation(), MAPS, MODES)
        self.assertEqual(self.playlists.load("a.json"), rotation())
        backup = self.playlists.store.delete("a.json").split("/")[-1]
        self.playlists.restore(backup, "a.json", MAPS, MODES)
        self.assertEqual(self.playlists.load("a.json"), rotation())

    def test_unsafe_paths_and_symlinks(self):
        for value in ("../a.json", "sub/a.json", "C:\\a.json", "/a.json", "..json", ".backups/a.json"):
            with self.assertRaises(ValueError):
                self.playlists.filename(value)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        try:
            (self.root / "content").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires Windows developer mode or POSIX")
        with self.assertRaises(ValueError):
            self.content.store.write("disabled-mods.json", {"packages": []})
        self.assertEqual(list(outside.iterdir()), [])


class RuntimeTests(Fixture):
    def test_documented_entries_schema(self):
        self.assertEqual(self.live.names("maps"), MAPS)

    def test_vote_prerequisites_and_server_errors(self):
        self.client.state["phase"] = "no_game"
        self.assertFalse(self.live.vote("endround").ok)
        self.client.state["phase"] = "playing"
        self.client.state["players"] = 1
        self.assertFalse(self.live.vote("shuffle").ok)
        self.client.state["players"] = 4
        self.assertTrue(self.live.vote("playlist").ok)
        self.assertIn(["nextmap"], self.client.calls)
        self.client.state["vote"] = {"subject": "kick"}
        self.assertFalse(self.live.vote("endgame").ok)

    def test_transition_acceptance_and_status_observation(self):
        reply = self.live.run(["load", "The Pit", "Capture the Flag"])
        self.assertIn("NOT confirmed", reply.text)
        self.assertIn("not observed", self.live.status().text)
        self.client.state.update(map="The Pit", mode="Capture the Flag")
        self.assertIn("observed in status", self.live.status().text)

    def test_control_event_failures_are_distinct(self):
        self.live.run(["map", "The Pit"])
        self.client.events.since.return_value = [{"action": "load", "ok": False, "text": "Missing map"}]
        self.assertIn("FAILED: Missing map", self.live.status().text)

    def test_mod_enable_disable_preserves_unknown_fields(self):
        (self.root / "content" / "Mods" / "canyon").mkdir(parents=True)
        self.content.store.write("disabled-mods.json", {"packages": [], "extra": 7})
        self.content.set_enabled("Mods/canyon", False)
        self.assertEqual(self.content.disabled(), {"packages": ["Mods/canyon"], "extra": 7})
        self.content.set_enabled("Mods/canyon", True)
        self.assertEqual(self.content.disabled()["packages"], [])
        with self.assertRaises(ValueError):
            self.content.set_enabled("../../outside", False)

    def test_nested_workshop_and_disabled_playlist_reference(self):
        self.content.store.write("Mods/Workshop/123/ModInfo.json", {"name": "Canyon"})
        self.content.set_enabled("Mods/Workshop/123", False)
        self.assertEqual(self.content.mods()[0]["folder"], "Mods/Workshop/123")
        data = rotation()
        data["games"][0]["map"] = "workshop:123/arena"
        errors = self.playlists.validate(data, MAPS + ["workshop:123/arena"], MODES)
        self.assertIn("disabled for next startup", "\n".join(errors))

    def test_activation_revalidates_after_confirmation(self):
        self.playlists.save("community.json", rotation(), MAPS, MODES)
        self.lines("menu", "2", "4", "1")
        data = rotation()
        data["games"][0]["map"] = "missing"
        self.playlists.store.write("community.json", data)
        self.lines("yes")
        self.assertNotIn("playlist", self.config.read())

    def test_persistent_settings_and_limits(self):
        self.config.save_setting("max_players", 24)
        self.config.save_setting("min_players", 8)
        self.config.save_setting("team_changing", "balanced")
        for key, value in (("min_players", 25), ("team_changing", True), ("password", "secret"), ("max_players", True)):
            with self.assertRaises(ValueError):
                self.config.save_setting(key, value)
        self.assertEqual(Configuration(self.root).read()["settings"]["max_players"], 24)
        self.config.reset()
        self.assertEqual(self.config.read()["settings"], {})


class TransportTests(unittest.TestCase):
    def test_quoting_round_trip_without_shell_interpretation(self):
        for args in (["load", "The Pit", "Capture the Flag"], ["password", ""],
                     ["say", 'quotes " and \\ and $() ` ;'], ["kick", "#3", "a reason"]):
            self.assertEqual(shlex.split(command_text(args)), args)
        with self.assertRaises(ValueError):
            command_text(["say", "newline\nstop"])

    @patch("manager.rcon_client.subprocess.Popen")
    def test_transport_preserves_structured_arguments_no_credentials(self, popen):
        proc = popen.return_value
        proc.communicate.return_value = ('{"map":"The Pit"}', "")
        proc.returncode = 0
        client = RconClient("server", True, {"RCON_PASSWORD": "sensitive"})
        reply = client.execute(["load", "The Pit", "Capture the Flag"], json_reply=True)
        args = popen.call_args.args[0]
        self.assertEqual(args, ["dedicated", "rcon", "--json", "--", "load", "The Pit", "Capture the Flag"])
        self.assertNotIn("sensitive", str(args))
        self.assertTrue(reply.ok)

    @patch("manager.rcon_client.subprocess.Popen")
    def test_auth_failure_redacted_and_timeout_not_retried(self, popen):
        proc = popen.return_value
        proc.communicate.return_value = ("", "bad password sensitive")
        proc.returncode = 1
        client = RconClient("server", True, {"RCON_PASSWORD": "sensitive"})
        result = client.execute(["status"])
        self.assertFalse(result.ok)
        self.assertNotIn("sensitive", result.text)
        proc.communicate.side_effect = [subprocess.TimeoutExpired("not printed", 15), ("", "")]
        self.assertIn("Outcome unknown", client.execute(["kick", "#1"]).text)
        proc.kill.assert_called_once()
        self.assertEqual(popen.call_count, 2)

    def test_disabled_client_never_starts_process(self):
        with patch("manager.rcon_client.subprocess.Popen") as popen:
            self.assertFalse(RconClient("server", False).execute(["status"]).ok)
            popen.assert_not_called()

    def test_events_only_retain_control_data(self):
        events = Events("server", {})
        events.record({"event": "chat", "id": "private", "text": "chat"})
        events.record({"event": "control", "action": "load", "ok": True, "text": "Loaded", "password": "hidden"})
        self.assertEqual(events.since(0), [{"action": "load", "ok": True, "text": "Loaded"}])


if __name__ == "__main__":
    unittest.main()

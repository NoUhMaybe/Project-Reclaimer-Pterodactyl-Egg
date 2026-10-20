"""0.9.13 state migration and current native/reload/UI contracts."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))
from manager.capabilities import Capabilities
from manager.commands import LiveOperations
from manager.configuration import Configuration, timing
from manager.diagnostics import versions
from manager.native import NativeTools
from manager.rcon_client import Reply
from test_manager import Fixture, MAPS, MODES, rotation


class UpgradeTests(Fixture):
    def setUp(self):
        super().setUp()
        self.live.capabilities = Capabilities("0.9.21")
        self.native = MagicMock(spec=NativeTools)
        self.native.version.return_value = "project-reclaimer 0.9.21"
        self.native.validate_playlist.return_value = "3 games checked"
        self.session.native = self.native
        self.playlists.native = self.native

    def test_native_validation_before_every_write_preserves_original_on_failure(self):
        self.playlists.save("community.json", rotation(), MAPS, MODES)
        original = self.playlists.store.read_bytes("community.json")
        self.native.validate_playlist.side_effect = ValueError("native rejected unsupported options")
        changed = rotation()
        changed["games"][0]["options"] = {"invalid.key": "bad"}
        with self.assertRaises(ValueError):
            self.playlists.save("community.json", changed, None, None)
        self.assertEqual(self.playlists.store.read_bytes("community.json"), original)

    def test_migrates_existing_version1_overrides_without_discarding_fields(self):
        self.config.store.write("overrides.json", {"version": 1, "settings": {"max_players": 24}, "playlist": "legacy.json", "other": "preserved"})
        self.playlists.save("legacy.json", rotation(), MAPS, MODES)
        self.config.save_setting("camera", "player_choice")
        current = Configuration(self.root).read()
        self.assertEqual(current["version"], 1)
        self.assertEqual(current["playlist"], "legacy.json")
        self.assertEqual(current["other"], "preserved")
        self.assertEqual(current["settings"], {"max_players": 24, "camera": "player_choice"})

    def test_camera_and_other_new_settings_require_explicit_apply(self):
        self.lines("menu", "6", "2", "camera", "third_person", "yes")
        self.assertEqual(self.config.read()["settings"]["camera"], "third_person")
        self.assertFalse((self.root / "dedicated.toml").exists())
        self.assertFalse(any(c[0] == "reload" for c in self.client.calls))
        self.assertIn("next multiplayer game", "\n".join(self.out))
        self.lines("2", "welcome", "-", "yes")
        self.assertEqual(self.config.read()["settings"]["welcome"], "")

    def prepare_toml(self):
        from configure import render_server_block
        text = 'auto_update = false\n# administrator content\n[defaults]\n' + render_server_block({"SERVER_NAME": "Old", "SERVER_PORT": "49176"}) + '\n'
        (self.root / "dedicated.toml").write_text(text, encoding="utf-8")
        return text

    def test_prepare_and_reload_preserve_admin_config_and_report_server_failure(self):
        original = self.prepare_toml()
        self.config.save_setting("camera", "player_choice")
        original_execute = self.client.execute
        def execute(tokens, json_reply=False):
            if tokens == ["reload"]:
                self.client.calls.append(tokens)
                return Reply(False, "Engine rejected reload: missing dependency")
            return original_execute(tokens, json_reply)
        self.client.execute = execute
        self.lines("menu", "6", "7", "yes")
        text = (self.root / "dedicated.toml").read_text(encoding="utf-8")
        self.assertIn('# administrator content', text)
        self.assertIn('camera = "player_choice"', text)
        self.assertIn("Reload was not confirmed", "\n".join(self.out))
        self.assertNotIn("Server confirmed the reload", "\n".join(self.out))
        self.assertEqual(len(list((self.root / ".backups").glob("*.json"))), 1)

    def test_invalid_config_candidate_never_replaces_real_toml(self):
        original = self.prepare_toml()
        self.config.save_setting("camera", "third_person")
        self.native.validate_configuration.side_effect = ValueError("native config rejected")
        self.lines("menu", "6", "7", "yes")
        self.assertEqual((self.root / "dedicated.toml").read_text(encoding="utf-8"), original)
        self.assertNotIn(["reload"], self.client.calls)

    def test_config_changed_during_native_validation_is_not_overwritten(self):
        original = self.prepare_toml()
        self.config.save_setting("camera", "third_person")
        changed = original + '# external admin edit\n'
        self.native.validate_configuration.side_effect = lambda _: (self.root / 'dedicated.toml').write_text(changed, encoding='utf-8')
        self.lines("menu", "6", "7", "yes")
        self.assertEqual((self.root / 'dedicated.toml').read_text(encoding='utf-8'), changed)
        self.assertNotIn(["reload"], self.client.calls)

    def test_native_bulk_creation_stays_a_draft_until_save(self):
        self.native.create_playlist.return_value = rotation()
        self.lines("menu", "2", "10", "native.json", "Native", "25", "Guardian,The Pit,Valhalla", "Slayer")
        self.assertEqual(self.session.section, "draft")
        self.assertFalse(self.playlists.store.path("native.json").exists())
        self.lines("7", "yes")
        self.assertEqual(self.playlists.load("native.json"), rotation())

    def test_native_inventory_and_admin_pardon_are_reachable(self):
        self.native.content.return_value = "Guardian / Maps/example.json"
        self.lines("menu", "5", "10", "Guardian")
        self.native.content.assert_called_once_with("Guardian")
        self.lines("back", "4", "19", "1", "yes", "21", "stored-player-id", "yes")
        self.assertIn(["admin", "add", "a" * 64], self.client.calls)
        self.assertIn(["pardon", "stored-player-id"], self.client.calls)

    def test_detected_version_and_mismatch_do_not_invent_client_versions(self):
        self.native.version.return_value = "project-reclaimer 0.9.13"
        text = versions(self.native, self.live.capabilities, {})
        self.assertIn("VERSION MISMATCH", text)
        self.assertIn("Individual client versions are not exposed", text)
        self.assertIn("disabled by default", text)

    def test_new_setting_validation_and_gates(self):
        for value in ("first_person", "player_choice", "third_person"):
            self.config.save_setting("camera", value)
        with self.assertRaises(ValueError):
            self.config.save_setting("camera", "invalid")
        self.assertTrue(Capabilities("0.9.20").supports("camera"))
        self.assertFalse(Capabilities("0.9.19").supports("camera"))
        self.assertIn("next multiplayer game", timing("camera"))
        self.assertFalse(Capabilities("latest").supports("reload"))


class NativeContracts(Fixture):
    def test_staging_uses_real_readonly_content_and_private_playlist_outputs(self):
        tools = NativeTools(self.root)
        def run(args):
            candidate = Path(args[-1])
            self.assertEqual(json.loads(candidate.read_text()), rotation())
            self.assertTrue(str(candidate).startswith(str(self.root / ".manager")))
            config = Path(args[args.index("--config") + 1]).read_text()
            self.assertIn(json.dumps(str(self.root / "content")), config)
            self.assertIn('auto_update = false', config)
            return "validated"
        with patch.object(tools, "run", side_effect=run):
            self.assertEqual(tools.validate_playlist(rotation()), "validated")
        self.assertEqual(list((self.root / ".manager/staging").iterdir()), [])
        self.assertFalse((self.root / "playlists").exists())

    def test_native_creation_rejects_paths_and_bad_duration_before_subprocess(self):
        tools = NativeTools(self.root)
        with patch.object(tools, "run") as run:
            for name, maps, seconds in (("../escape", MAPS, 20), ("OK", ["../outside"], 20), ("OK", MAPS, 121)):
                with self.assertRaises(ValueError):
                    tools.create_playlist(name, maps, ["Slayer"], seconds)
            run.assert_not_called()

    def test_native_timeout_kills_client_and_keeps_process_supervision_independent(self):
        tools = NativeTools(self.root)
        with patch("manager.native.subprocess.Popen") as popen:
            popen.return_value.communicate.side_effect = [subprocess.TimeoutExpired("hidden", 30), ("", "")]
            with self.assertRaises(ValueError):
                tools.version()
            popen.return_value.kill.assert_called_once()

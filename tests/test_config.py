"""Unit tests for docker/configure.py's dedicated.toml sentinel patcher.

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGURE_PATH = ROOT / "docker" / "configure.py"

spec = importlib.util.spec_from_file_location("configure", CONFIGURE_PATH)
configure = importlib.util.module_from_spec(spec)
sys.modules["configure"] = configure
spec.loader.exec_module(configure)  # type: ignore[union-attr]


class TomlStringTests(unittest.TestCase):
    def test_escapes_quotes_and_backslashes(self):
        self.assertEqual(configure.toml_string('he said "hi"'), '"he said \\"hi\\""')
        self.assertEqual(configure.toml_string("a\\b"), '"a\\\\b"')


class RenderServerBlockTests(unittest.TestCase):
    def test_basic(self):
        env = {"SERVER_NAME": "My Server", "SERVER_PORT": "49176"}
        block = configure.render_server_block(env)
        self.assertIn(configure.SENTINEL_START, block)
        self.assertIn(configure.SENTINEL_END, block)
        self.assertIn('name = "My Server"', block)
        self.assertIn("port = 49176", block)
        self.assertNotIn("playlist", block)
        self.assertNotIn("map =", block)

    def test_prefers_playlist_over_map_game(self):
        env = {
            "SERVER_NAME": "X",
            "SERVER_PORT": "49176",
            "PLAYLIST": "playlists/foo.playlist.json",
            "MAP": "Guardian",
            "GAME_TYPE": "Slayer",
        }
        block = configure.render_server_block(env)
        self.assertIn('playlist = "playlists/foo.playlist.json"', block)
        self.assertNotIn("map =", block)
        self.assertNotIn("game =", block)

    def test_falls_back_to_map_and_game(self):
        env = {"SERVER_NAME": "X", "SERVER_PORT": "49176", "MAP": "Guardian", "GAME_TYPE": "Slayer"}
        block = configure.render_server_block(env)
        self.assertIn('map = "Guardian"', block)
        self.assertIn('game = "Slayer"', block)

    def test_truncates_long_name(self):
        env = {"SERVER_NAME": "X" * 100, "SERVER_PORT": "49176"}
        block = configure.render_server_block(env)
        # 48 chars of X plus two quote characters.
        self.assertIn('"' + ("X" * 48) + '"', block)

    def test_rejects_invalid_port(self):
        env = {"SERVER_NAME": "X", "SERVER_PORT": "not-a-number"}
        with self.assertRaises(SystemExit) as ctx:
            configure.render_server_block(env)
        self.assertEqual(ctx.exception.code, 1)

    def test_rejects_out_of_range_port(self):
        env = {"SERVER_NAME": "X", "SERVER_PORT": "80"}
        with self.assertRaises(SystemExit):
            configure.render_server_block(env)


class PatchExistingTests(unittest.TestCase):
    def test_appends_when_no_sentinel_present(self):
        original = "game = \"game\"\n[defaults]\n"
        block = "# >>> X >>>\n[[server]]\nname = \"a\"\n# <<< X <<<"
        updated, appended = configure.patch_existing(original, block)
        self.assertTrue(appended)
        self.assertIn(original, updated)
        self.assertIn(block, updated)

    def test_replaces_only_managed_block(self):
        original = (
            "game = \"game\"\n"
            "admins = [\"abc\"]\n"
            f"{configure.SENTINEL_START}\n[[server]]\nname = \"old\"\nport = 1\n{configure.SENTINEL_END}\n"
            "[rcon]\npassword = \"\"\n"
        )
        new_block = f"{configure.SENTINEL_START}\n[[server]]\nname = \"new\"\nport = 2\n{configure.SENTINEL_END}"
        updated, appended = configure.patch_existing(original, new_block)
        self.assertFalse(appended)
        self.assertIn('admins = ["abc"]', updated)
        self.assertIn("[rcon]", updated)
        self.assertNotIn('name = "old"', updated)
        self.assertIn('name = "new"', updated)

    def test_is_idempotent(self):
        original = "x = 1\n"
        block = f"{configure.SENTINEL_START}\nname = \"a\"\n{configure.SENTINEL_END}"
        once, _ = configure.patch_existing(original, block)
        twice, _ = configure.patch_existing(once, block)
        self.assertEqual(once, twice)


class MainEndToEndTests(unittest.TestCase):
    """Exercises configure.py's full main() flow, independent of any game
    startup — corresponds to the "Configuration generation" runtime test
    scenario, at the unit level (see tests/test-runtime-b-configuration.sh
    for the container-level equivalent)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.server_dir = Path(self.tmpdir.name) / "server"

    def _run_main(self, env: dict) -> str:
        import os

        old_environ = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        os.environ["RECLAIMER_SERVER_DIR"] = str(self.server_dir)
        try:
            configure.main()
        finally:
            os.environ.clear()
            os.environ.update(old_environ)
        return (self.server_dir / "dedicated.toml").read_text(encoding="utf-8")

    def test_creates_file_with_correct_port_and_name(self):
        content = self._run_main({"SERVER_NAME": "Test Server", "SERVER_PORT": "49176"})
        self.assertIn('name = "Test Server"', content)
        self.assertIn("port = 49176", content)

    def test_is_idempotent_across_full_runs(self):
        env = {"SERVER_NAME": "Test Server", "SERVER_PORT": "49176"}
        first = self._run_main(env)
        second = self._run_main(env)
        self.assertEqual(first, second)

    def test_preserves_hand_edited_content_on_subsequent_runs(self):
        env = {"SERVER_NAME": "Test Server", "SERVER_PORT": "49176"}
        self._run_main(env)
        toml_path = self.server_dir / "dedicated.toml"
        hand_edited = toml_path.read_text(encoding="utf-8") + "\n[master]\npeers = [\"https://example.com\"]\n"
        toml_path.write_text(hand_edited, encoding="utf-8")

        updated = self._run_main({"SERVER_NAME": "Renamed Server", "SERVER_PORT": "49177"})

        self.assertIn('peers = ["https://example.com"]', updated)
        self.assertIn('name = "Renamed Server"', updated)
        self.assertIn("port = 49177", updated)
        self.assertNotIn("Test Server", updated)

    def test_escapes_special_characters_in_server_name(self):
        content = self._run_main({"SERVER_NAME": 'Quote " Test', "SERVER_PORT": "49176"})
        self.assertIn('name = "Quote \\" Test"', content)

    def test_manager_activation_survives_startup_playlist_and_map_defaults(self):
        from manager.configuration import Configuration
        self.server_dir.mkdir(parents=True)
        (self.server_dir / "playlists").mkdir()
        (self.server_dir / "playlists" / "community.json").write_text('{"version":2}', encoding="utf-8")
        manager = Configuration(self.server_dir)
        manager.activate("community.json")
        manager.save_setting("max_players", 24)
        env = {"SERVER_NAME": "Test", "SERVER_PORT": "49176", "PLAYLIST": "playlists/startup.json", "MAP": "Guardian", "GAME_TYPE": "Slayer"}
        first = self._run_main(env)
        second = self._run_main(dict(env, PLAYLIST="playlists/another.json"))
        self.assertEqual(first, second)
        self.assertIn('playlist = "playlists/community.json"', second)
        self.assertIn("max_players = 24", second)
        self.assertNotIn('map = "Guardian"', second)
        manager.reset()
        self.assertIn('playlist = "playlists/startup.json"', self._run_main(env))

    def test_control_characters_are_escaped_and_rcon_is_loopback(self):
        content = self._run_main({"SERVER_NAME": "A\rB", "SERVER_PORT": "49176", "RCON_ENABLED": "1", "RCON_PASSWORD": "pass\\word\"test"})
        self.assertIn('name = "A\\rB"', content)
        self.assertIn('address = "127.0.0.1"', content)
        self.assertIn('password = "pass\\\\word\\"test"', content)


if __name__ == "__main__":
    unittest.main()

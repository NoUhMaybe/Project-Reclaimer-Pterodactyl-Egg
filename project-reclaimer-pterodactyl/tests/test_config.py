"""Unit tests for docker/configure.py's dedicated.toml sentinel patcher.

Runnable standalone (python tests/test_config.py) or via pytest; no third
party dependencies required.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGURE_PATH = ROOT / "docker" / "configure.py"

spec = importlib.util.spec_from_file_location("configure", CONFIGURE_PATH)
configure = importlib.util.module_from_spec(spec)
sys.modules["configure"] = configure
spec.loader.exec_module(configure)  # type: ignore[union-attr]


def test_toml_string_escapes_quotes_and_backslashes():
    assert configure.toml_string('he said "hi"') == '"he said \\"hi\\""'
    assert configure.toml_string("a\\b") == '"a\\\\b"'


def test_render_server_block_basic():
    env = {"SERVER_NAME": "My Server", "SERVER_PORT": "49176"}
    block = configure.render_server_block(env)
    assert configure.SENTINEL_START in block
    assert configure.SENTINEL_END in block
    assert 'name = "My Server"' in block
    assert "port = 49176" in block
    assert "playlist" not in block and "map =" not in block


def test_render_server_block_prefers_playlist_over_map_game():
    env = {
        "SERVER_NAME": "X",
        "SERVER_PORT": "49176",
        "PLAYLIST": "playlists/foo.playlist.json",
        "MAP": "Guardian",
        "GAME_TYPE": "Slayer",
    }
    block = configure.render_server_block(env)
    assert 'playlist = "playlists/foo.playlist.json"' in block
    assert "map =" not in block
    assert "game =" not in block


def test_render_server_block_falls_back_to_map_and_game():
    env = {"SERVER_NAME": "X", "SERVER_PORT": "49176", "MAP": "Guardian", "GAME_TYPE": "Slayer"}
    block = configure.render_server_block(env)
    assert 'map = "Guardian"' in block
    assert 'game = "Slayer"' in block


def test_render_server_block_truncates_long_name():
    env = {"SERVER_NAME": "X" * 100, "SERVER_PORT": "49176"}
    block = configure.render_server_block(env)
    # 48 chars of X plus two quote characters.
    assert '"' + ("X" * 48) + '"' in block


def test_render_server_block_rejects_invalid_port():
    env = {"SERVER_NAME": "X", "SERVER_PORT": "not-a-number"}
    try:
        configure.render_server_block(env)
        raise AssertionError("expected SystemExit for invalid port")
    except SystemExit as exc:
        assert exc.code == 1


def test_patch_existing_appends_when_no_sentinel_present():
    original = "game = \"game\"\n[defaults]\n"
    block = "# >>> X >>>\n[[server]]\nname = \"a\"\n# <<< X <<<"
    updated, appended = configure.patch_existing(original, block)
    assert appended is True
    assert original in updated
    assert block in updated


def test_patch_existing_replaces_only_managed_block():
    original = (
        "game = \"game\"\n"
        "admins = [\"abc\"]\n"
        f"{configure.SENTINEL_START}\n[[server]]\nname = \"old\"\nport = 1\n{configure.SENTINEL_END}\n"
        "[rcon]\npassword = \"\"\n"
    )
    new_block = f"{configure.SENTINEL_START}\n[[server]]\nname = \"new\"\nport = 2\n{configure.SENTINEL_END}"
    updated, appended = configure.patch_existing(original, new_block)
    assert appended is False
    assert 'admins = ["abc"]' in updated
    assert '[rcon]' in updated
    assert 'name = "old"' not in updated
    assert 'name = "new"' in updated


def test_patch_existing_is_idempotent():
    original = "x = 1\n"
    block = f"{configure.SENTINEL_START}\nname = \"a\"\n{configure.SENTINEL_END}"
    once, _ = configure.patch_existing(original, block)
    twice, _ = configure.patch_existing(once, block)
    assert once == twice


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)

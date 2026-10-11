"""Static validation of egg-project-reclaimer.json against the PTDL_v2 shape.

This does not talk to a real Pterodactyl Panel; it checks structural and
schema-level correctness so an obviously broken egg is caught in CI before
anyone tries to import it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EGG_PATH = ROOT / "egg-project-reclaimer.json"

REQUIRED_TOP_LEVEL_KEYS = {
    "meta",
    "name",
    "author",
    "description",
    "docker_images",
    "startup",
    "config",
    "scripts",
    "variables",
}

REQUIRED_VARIABLE_KEYS = {
    "name",
    "description",
    "env_variable",
    "default_value",
    "user_viewable",
    "user_editable",
    "rules",
}

ENV_VAR_RE = re.compile(r"^[A-Z0-9_]+$")


def load_egg() -> dict:
    with EGG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_file_is_valid_json():
    load_egg()  # raises if not valid JSON


def test_required_top_level_keys_present():
    egg = load_egg()
    missing = REQUIRED_TOP_LEVEL_KEYS - egg.keys()
    assert not missing, f"missing top-level keys: {missing}"


def test_meta_is_ptdl_v2():
    egg = load_egg()
    assert egg["meta"]["version"] == "PTDL_v2"


def test_docker_images_are_non_empty_strings():
    egg = load_egg()
    images = egg["docker_images"]
    assert isinstance(images, dict) and images, "docker_images must be a non-empty object"
    for label, image in images.items():
        assert isinstance(label, str) and label
        assert isinstance(image, str) and ":" in image, f"image '{image}' should include a tag"


def test_config_has_required_sub_keys():
    egg = load_egg()
    config = egg["config"]
    for key in ("files", "startup", "logs", "stop"):
        assert key in config, f"config.{key} is required"
    # files/startup/logs are JSON encoded as strings in PTDL_v2.
    for key in ("files", "startup", "logs"):
        json.loads(config[key])  # must itself be valid JSON


def test_install_script_present_and_non_trivial():
    egg = load_egg()
    install = egg["scripts"]["installation"]
    assert install["script"].strip(), "install script must not be empty"
    assert "set -e" in install["script"], "install script should fail fast on errors"
    assert install["container"], "install container must be set"
    assert install["entrypoint"], "install entrypoint must be set"


def test_variables_have_required_keys_and_valid_env_names():
    egg = load_egg()
    seen_env_vars = set()
    for var in egg["variables"]:
        missing = REQUIRED_VARIABLE_KEYS - var.keys()
        assert not missing, f"variable {var.get('name')} missing keys: {missing}"
        env = var["env_variable"]
        assert ENV_VAR_RE.match(env), f"env_variable '{env}' must be UPPER_SNAKE_CASE"
        assert env not in seen_env_vars, f"duplicate env_variable: {env}"
        seen_env_vars.add(env)
        assert isinstance(var["rules"], str) and var["rules"], f"{env} missing validation rules"


def test_no_builtin_variable_names_are_redefined():
    # Pterodactyl provides these automatically; redefining them would be
    # confusing and could conflict with Wings' own substitution.
    builtin = {"SERVER_MEMORY", "SERVER_IP", "SERVER_PORT", "STARTUP", "TZ"}
    egg = load_egg()
    env_vars = {v["env_variable"] for v in egg["variables"]}
    clashes = builtin & env_vars
    assert not clashes, f"variables redefine built-in names: {clashes}"


def test_rcon_password_rules_enforce_minimum_length():
    egg = load_egg()
    rcon = next(v for v in egg["variables"] if v["env_variable"] == "RCON_PASSWORD")
    assert "between:8,128" in rcon["rules"]


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

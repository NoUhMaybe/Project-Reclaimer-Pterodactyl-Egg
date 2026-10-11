"""Static validation of egg-project-reclaimer.json against the PTDL_v2 shape.

This does not talk to a real Pterodactyl Panel; it checks structural and
schema-level correctness so an obviously broken egg is caught in CI before
anyone tries to import it.

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EGG_PATH = ROOT / "egg-project-reclaimer.json"
INSTALL_SH_PATH = ROOT / "scripts" / "install.sh"

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


class EggStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.egg = load_egg()

    def test_file_is_valid_json(self):
        self.assertIsInstance(self.egg, dict)

    def test_required_top_level_keys_present(self):
        missing = REQUIRED_TOP_LEVEL_KEYS - self.egg.keys()
        self.assertFalse(missing, f"missing top-level keys: {missing}")

    def test_meta_is_ptdl_v2(self):
        self.assertEqual(self.egg["meta"]["version"], "PTDL_v2")

    def test_docker_images_are_non_empty_strings(self):
        images = self.egg["docker_images"]
        self.assertIsInstance(images, dict)
        self.assertTrue(images, "docker_images must be a non-empty object")
        for label, image in images.items():
            self.assertIsInstance(label, str)
            self.assertTrue(label)
            self.assertIsInstance(image, str)
            self.assertIn(":", image, f"image '{image}' should include a tag")

    def test_docker_image_is_not_the_old_placeholder(self):
        images = " ".join(self.egg["docker_images"].values())
        self.assertNotIn("REPLACE_WITH_YOUR_ORG", images)

    def test_config_has_required_sub_keys(self):
        config = self.egg["config"]
        for key in ("files", "startup", "logs", "stop"):
            self.assertIn(key, config, f"config.{key} is required")
        # files/startup/logs are JSON encoded as strings in PTDL_v2.
        for key in ("files", "startup", "logs"):
            json.loads(config[key])  # must itself be valid JSON

    def test_stop_command_matches_upstream_stop_signal(self):
        # Verified upstream image config declares StopSignal: SIGINT; "^C" is
        # Wings' documented way to send SIGINT rather than a literal command.
        self.assertEqual(self.egg["config"]["stop"], "^C")

    def test_startup_command_is_genuine_not_a_placeholder(self):
        startup = self.egg["startup"]
        self.assertNotIn("echo", startup.lower())
        self.assertIn("reclaimer-entrypoint", startup)

    def test_install_script_present_and_non_trivial(self):
        install = self.egg["scripts"]["installation"]
        self.assertTrue(install["script"].strip(), "install script must not be empty")
        self.assertIn("set -e", install["script"], "install script should fail fast on errors")
        self.assertTrue(install["container"], "install container must be set")
        self.assertTrue(install["entrypoint"], "install entrypoint must be set")

    def test_install_script_matches_canonical_file(self):
        canonical = INSTALL_SH_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            self.egg["scripts"]["installation"]["script"],
            canonical,
            "egg-project-reclaimer.json's install script is out of sync with "
            "scripts/install.sh; run 'python3 tools/build_egg.py' and commit "
            "the result",
        )

    def test_variables_have_required_keys_and_valid_env_names(self):
        seen_env_vars = set()
        for var in self.egg["variables"]:
            missing = REQUIRED_VARIABLE_KEYS - var.keys()
            self.assertFalse(missing, f"variable {var.get('name')} missing keys: {missing}")
            env = var["env_variable"]
            self.assertRegex(env, ENV_VAR_RE, f"env_variable '{env}' must be UPPER_SNAKE_CASE")
            self.assertNotIn(env, seen_env_vars, f"duplicate env_variable: {env}")
            seen_env_vars.add(env)
            self.assertTrue(
                isinstance(var["rules"], str) and var["rules"], f"{env} missing validation rules"
            )

    def test_no_builtin_variable_names_are_redefined(self):
        # Pterodactyl provides these automatically; redefining them would be
        # confusing and could conflict with Wings' own substitution.
        builtin = {"SERVER_MEMORY", "SERVER_IP", "SERVER_PORT", "STARTUP", "TZ"}
        env_vars = {v["env_variable"] for v in self.egg["variables"]}
        clashes = builtin & env_vars
        self.assertFalse(clashes, f"variables redefine built-in names: {clashes}")

    def test_rcon_password_rules_enforce_minimum_length(self):
        rcon = next(v for v in self.egg["variables"] if v["env_variable"] == "RCON_PASSWORD")
        self.assertIn("between:8,128", rcon["rules"])

    def test_no_puid_pgid_variables(self):
        # PUID/PGID are inert under Wings (see TROUBLESHOOTING.md); exposing
        # them as egg variables would be misleading.
        env_vars = {v["env_variable"] for v in self.egg["variables"]}
        self.assertFalse({"PUID", "PGID"} & env_vars)


if __name__ == "__main__":
    unittest.main()

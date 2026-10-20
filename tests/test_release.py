"""Release identity, reproducible packaging and real installer regressions."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_egg
import check_release

GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = str(GIT_BASH) if os.name == "nt" and GIT_BASH.is_file() else shutil.which("bash")
SHA = "a" * 40


class InstallerTests(unittest.TestCase):
    def setUp(self):
        if not BASH:
            self.skipTest("Bash is unavailable")
        self.temporary = tempfile.TemporaryDirectory(prefix="reclaimer-installer-")
        self.addCleanup(self.temporary.cleanup)
        self.mount = Path(self.temporary.name) / "mount"
        self.script = json.loads((ROOT / "egg-project-reclaimer.json").read_text(encoding="utf-8"))["scripts"]["installation"]["script"]

    def install(self):
        return subprocess.run([BASH, "-s"], input=self.script.replace("/mnt/server", self.mount.as_posix()),
                              text=True, capture_output=True, timeout=20)

    def test_empty_mount_initializes_expected_layout(self):
        self.mount.mkdir()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative in ("game/halo3/maps", "content/Maps", "content/Game Modes", "content/Mods", "playlists", "data"):
            self.assertTrue((self.mount / "server" / relative).is_dir(), relative)
        self.assertEqual(json.loads((self.mount / "server/bans.json").read_text()), {"players": [], "ips": [], "vpn_allowed": []})
        self.assertFalse((self.mount / "server/dedicated.toml").exists())

    def test_reinstall_preserves_all_operator_state(self):
        self.mount.mkdir()
        self.assertEqual(self.install().returncode, 0)
        originals = {"dedicated.toml": b'# administrator config\n', "bans.json": b'{"players":[{"id":"fixture"}]}',
                     "game/halo3/maps/owned-asset.fixture": b'owned data fixture', "playlists/custom.json": b'{"custom":true}',
                     "content/Mods/example/metadata.fixture": b'package fixture', ".manager/overrides.json": b'{"version":1,"settings":{}}',
                     "data/instance/state.fixture": b'instance state'}
        for name, content in originals.items():
            path = self.mount / "server" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, content in originals.items():
            self.assertEqual((self.mount / "server" / name).read_bytes(), content, name)

    def test_missing_mount_fails_without_creating_anything(self):
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected Pterodactyl install mount", result.stderr)
        self.assertFalse(self.mount.exists())


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("VERSION", "Dockerfile", "egg-project-reclaimer.json", "scripts/install.sh"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_release_and_upstream_identity(self):
        values = check_release.validate(self.root)
        self.assertEqual(values["version"], (ROOT / "VERSION").read_text().strip())
        self.assertEqual(values["upstream"], "0.9.21")
        self.assertEqual(values["prerelease"], "false")
        self.assertTrue(values["image"].endswith(":" + values["version"]))

    def test_old_image_or_stale_installer_is_rejected(self):
        egg = json.loads((self.root / "egg-project-reclaimer.json").read_text(encoding="utf-8"))
        for key, value in (("docker_images", {"old": "ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.0"}),
                           ("scripts", {"installation": {"script": "exit 0"}})):
            bad = copy.deepcopy(egg)
            bad[key] = value
            (self.root / "egg-project-reclaimer.json").write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                check_release.validate(self.root)

    def test_unsupported_pin_and_invalid_release_version_are_rejected(self):
        original = (self.root / "Dockerfile").read_text(encoding="utf-8")
        for pin in ("0.9.20", "latest"):
            with self.subTest(pin=pin):
                (self.root / "Dockerfile").write_text(original.replace("ARG RECLAIMER_VERSION=0.9.21", "ARG RECLAIMER_VERSION=" + pin), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Reviewed upstream pin"):
                    check_release.validate(self.root)
        (self.root / "Dockerfile").write_text(original, encoding="utf-8")
        (self.root / "VERSION").write_text("latest\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            check_release.validate(self.root)

    def test_generator_is_deterministic_and_regeneration_leaves_identical_bytes(self):
        first, second = build_egg.build(self.root), build_egg.build(self.root)
        first.pop("exported_at"); second.pop("exported_at")
        self.assertEqual(first, second)
        with patch.object(build_egg, "ROOT", self.root):
            build_egg.main()
            generated = (self.root / "egg-project-reclaimer.json").read_bytes()
            build_egg.main()
            self.assertEqual((self.root / "egg-project-reclaimer.json").read_bytes(), generated)

    def test_startup_configuration_and_variables_remain_compatible(self):
        actual = build_egg.build(self.root)
        # SHA256 of these public fields in v0.1.0 (74c9bbd...), independent
        # of local Git history and available even in a shallow CI checkout.
        contract = {key: actual[key] for key in ("startup", "config", "variables", "features", "file_denylist")}
        self.assertEqual(hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest(),
                         "990d091150e9fa8815de144d9c899bd82d3ca55aec243f59e0b48127e5d75be9")
        self.assertTrue(all(not v["default_value"] for v in actual["variables"] if "PASSWORD" in v["env_variable"]))

    def test_publishing_checks_exact_tag_and_refuses_existing_image(self):
        values = check_release.validate(self.root)
        env = dict(GITHUB_REPOSITORY=check_release.REPOSITORY, GITHUB_EVENT_NAME="push", GITHUB_REF="refs/tags/" + values["version"], GITHUB_SHA=SHA)
        registry = MagicMock()
        registry.manifest.return_value = None
        check_release.publishing(values, env, resolve=lambda _: SHA, registry=registry)
        for change in ({"GITHUB_REF": "refs/tags/v0.1.0"}, {"GITHUB_REPOSITORY": "fork/repo"},
                       {"UPSTREAM_VERSION": "0.9.13"}, {"TAG_LATEST": "true"}, {"GITHUB_REF": "refs/heads/feature"}):
            with self.assertRaises(ValueError):
                check_release.publishing(values, dict(env, **change), resolve=lambda _: SHA, registry=registry)
        with self.assertRaises(ValueError):
            check_release.publishing(values, env, resolve=lambda _: "b" * 40, registry=registry)
        registry.manifest.return_value = ("sha256:existing", {})
        with self.assertRaisesRegex(ValueError, "already exists"):
            check_release.publishing(values, env, resolve=lambda _: SHA, registry=registry)

    def test_version_bump_updates_image_instead_of_inheriting_prior_release(self):
        (self.root / "VERSION").write_text("v99.0.0\n", encoding="utf-8")
        newer = build_egg.build(self.root)
        self.assertEqual(newer["docker_images"], {check_release.IMAGE + 'v99.0.0': check_release.IMAGE + 'v99.0.0'})
        with self.assertRaises(ValueError):
            check_release.validate(self.root)  # old generated file cannot publish

    def test_public_image_verification_checks_real_config_digest_and_version(self):
        values = check_release.validate(self.root)
        config = {"os": "linux", "architecture": "amd64", "config": {
            "Labels": {"org.opencontainers.image.revision": SHA,
                       "org.opencontainers.image.source": "https://github.com/" + check_release.REPOSITORY,
                       "org.opencontainers.image.version": values["version"]},
            "Entrypoint": ["/usr/bin/tini", "--", "/pterodactyl/entrypoint.sh"], "Cmd": ["start"],
            "Env": ["RECLAIMER_IMAGE_VERSION=0.9.21"]}}
        registry = MagicMock()
        def supply(value):
            raw = json.dumps(value).encode()
            registry.manifest.return_value = ("sha256:manifest", {"config": {"digest": "sha256:" + hashlib.sha256(raw).hexdigest()}})
            registry.get.return_value = (raw, {})
        supply(config)
        self.assertEqual(check_release.verify_published(values, SHA, registry)["digest"], "sha256:manifest")
        with self.assertRaises(ValueError):
            check_release.verify_published(values, "b" * 40, registry)
        config["config"]["Labels"]["org.opencontainers.image.version"] = "v0.1.0"
        supply(config)
        with self.assertRaises(ValueError):
            check_release.verify_published(values, SHA, registry)
        registry.get.return_value = (b"corrupt config", {})
        with self.assertRaises(ValueError):
            check_release.verify_published(values, SHA, registry)


if __name__ == "__main__":
    unittest.main()

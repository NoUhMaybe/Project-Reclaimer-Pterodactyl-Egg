"""Regression tests guarding the Dockerfile/entrypoint.sh's assumptions
about the upstream image's ENTRYPOINT/CMD contract.

These exist because an earlier revision of this egg incorrectly assumed
Docker's CMD-inheritance alone would preserve upstream's actual startup
program when ENTRYPOINT was replaced — it would not have (see git history /
TROUBLESHOOTING.md "Verified upstream image metadata" for the full story).

Two layers of protection:
  1. Static checks (always run, no network) on the Dockerfile and
     entrypoint.sh text itself.
  2. A live check (skipped, not failed, if the network/registry is
     unreachable) against the actual published image's config, so a future
     upstream release that changes its own Entrypoint/Cmd/WorkingDir is
     caught here instead of silently breaking container startup.

Run with: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE_PATH = ROOT / "Dockerfile"
ENTRYPOINT_PATH = ROOT / "docker" / "entrypoint.sh"

REGISTRY = "ghcr.io"
REPOSITORY = "projectreclaimer/project-reclaimer-dedicated"


def _default_reclaimer_version() -> str:
    text = DOCKERFILE_PATH.read_text(encoding="utf-8")
    match = re.search(r"^ARG RECLAIMER_VERSION=(\S+)", text, re.MULTILINE)
    if not match:
        raise AssertionError("Dockerfile must declare ARG RECLAIMER_VERSION=<default>")
    return match.group(1)


def _fetch_json(url: str, token: str | None = None, timeout: float = 10.0) -> dict:
    headers = {"Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed registry host
        return json.load(resp)


def _fetch_upstream_config() -> dict:
    token_url = f"https://{REGISTRY}/token?scope=repository:{REPOSITORY}:pull&service={REGISTRY}"
    token = _fetch_json(token_url).get("token")
    version = _default_reclaimer_version()
    manifest = _fetch_json(
        f"https://{REGISTRY}/v2/{REPOSITORY}/manifests/{version}", token=token
    )
    config_digest = manifest["config"]["digest"]
    config_blob_req = urllib.request.Request(
        f"https://{REGISTRY}/v2/{REPOSITORY}/blobs/{config_digest}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(config_blob_req, timeout=10.0) as resp:  # noqa: S310
        return json.load(resp)


class DockerfileStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.entrypoint = ENTRYPOINT_PATH.read_text(encoding="utf-8")

    def test_entrypoint_names_the_real_upstream_program(self):
        # The Dockerfile's own ENTRYPOINT array must still reference
        # "reclaimer-entrypoint" by name; silently dropping it (e.g. by
        # replacing ENTRYPOINT and relying only on inherited CMD, which is
        # just ["start"] with no program name) was the original bug.
        self.assertIn("reclaimer-entrypoint", self.dockerfile)
        entrypoint_line = next(
            line for line in self.dockerfile.splitlines() if line.startswith("ENTRYPOINT")
        )
        self.assertIn("/pterodactyl/entrypoint.sh", entrypoint_line)

    def test_cmd_is_declared_explicitly(self):
        self.assertRegex(self.dockerfile, re.compile(r'^CMD \["start"\]\s*$', re.MULTILINE))

    def test_symlinks_created_at_build_time_not_runtime(self):
        # These must be RUN steps in the Dockerfile (build time, root), not
        # left to the entrypoint (runtime, non-root under Wings) — see
        # TROUBLESHOOTING.md for why a runtime rm -rf/ln -s cannot work.
        self.assertIn("ln -s /home/container/server /server", self.dockerfile)
        self.assertIn("ln -s /home/container/.cache/reclaimer /cache", self.dockerfile)
        self.assertIn("ln -s /home/container/.wine-prefix /home/reclaimer/.wine", self.dockerfile)

    def test_home_reclaimer_permissions_are_relaxed(self):
        # Regression guard: upstream's `useradd --create-home` leaves
        # /home/reclaimer at mode 0700 (confirmed directly from the image's
        # own layer — see TROUBLESHOOTING.md "Verified upstream image
        # metadata"), which denies any UID other than 1000 or root even
        # traversal into it — including Wings' assigned UID. That made the
        # .wine symlink above unreachable (lstat() EACCES, indistinguishable
        # from "does not exist") until this chmod was added.
        self.assertIn("chmod 755 /home/reclaimer", self.dockerfile)

    def test_entrypoint_does_not_blindly_exec_dollar_at(self):
        # A bare `exec "$@"` with no explicit program name was the original
        # bug (CMD alone is just ["start"], not a runnable program).
        self.assertNotRegex(self.entrypoint, re.compile(r'^exec "\$@"\s*$', re.MULTILINE))

    def test_entrypoint_calls_prepare_prefix(self):
        self.assertIn("prepare-prefix", self.entrypoint)

    def test_entrypoint_honors_wings_startup_variable(self):
        self.assertIn("${STARTUP", self.entrypoint)


class UpstreamImageLiveTests(unittest.TestCase):
    """Network-dependent: skips (does not fail) if the registry cannot be
    reached, e.g. in an offline development sandbox. Always attempted in
    CI, which has internet access."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.image = _fetch_upstream_config()
            cls.config = cls.image["config"]
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise unittest.SkipTest(f"registry unreachable: {exc}") from exc

    def test_entrypoint_matches_what_this_image_was_built_for(self):
        self.assertEqual(
            self.config["Entrypoint"],
            ["/usr/bin/tini", "--", "reclaimer-entrypoint"],
            "upstream image's Entrypoint changed — review Dockerfile/entrypoint.sh "
            "and TROUBLESHOOTING.md before rebuilding",
        )

    def test_cmd_matches_what_this_image_was_built_for(self):
        self.assertEqual(self.config["Cmd"], ["start"])

    def test_architecture_user_and_stop_signal_match(self):
        self.assertEqual(self.image["architecture"], "amd64")
        self.assertEqual(self.image["os"], "linux")
        self.assertEqual(self.config["User"], "root")
        self.assertEqual(self.config["StopSignal"], "SIGINT")

    def test_working_dir_matches_what_this_image_was_built_for(self):
        self.assertEqual(self.config["WorkingDir"], "/server")

    def test_wineprefix_env_matches_what_this_image_was_built_for(self):
        env = dict(item.split("=", 1) for item in self.config["Env"] if "=" in item)
        self.assertEqual(env.get("WINEPREFIX"), "/home/reclaimer/.wine")


if __name__ == "__main__":
    unittest.main()

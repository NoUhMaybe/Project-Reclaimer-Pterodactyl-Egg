"""Validate release packaging; publishing mode also guards tag/source identity and GHCR."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from build_egg import build
from test_image import Registry, REPOSITORY, metadata, require

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:"


def validate(root=ROOT):
    root = Path(root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    require(re.fullmatch(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", version),
            "VERSION must contain an explicit semantic release tag, e.g. v0.1.2.")
    text = (root / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"^ARG RECLAIMER_VERSION=(\S+)\s*$", text, re.M)
    require(match and match.group(1) == "0.9.21", "Reviewed upstream pin must remain 0.9.21.")
    raw = (root / "egg-project-reclaimer.json").read_bytes()
    actual = json.loads(raw)
    expected = build(root)
    require({k: v for k, v in actual.items() if k != "exported_at"} ==
            {k: v for k, v in expected.items() if k != "exported_at"},
            "Generated egg is stale; run python tools/build_egg.py.")
    require(actual["docker_images"] == {IMAGE + version: IMAGE + version}, "Egg must reference only the intended versioned image.")
    require(actual["meta"]["version"] == "PTDL_v2", "Expected PTDL_v2 egg.")
    require(actual["startup"] == "reclaimer-entrypoint start" and actual["config"]["stop"] == "^C", "Startup/Stop contract changed.")
    for key in ("files", "startup", "logs"):
        json.loads(actual["config"][key])
    require(all(not v["default_value"] for v in actual["variables"]
                if any(word in v["env_variable"].lower() for word in ("password", "token", "secret"))),
            "Release egg must not contain populated secret defaults.")
    return {"version": version, "upstream": match.group(1), "image": IMAGE + version,
            "artifact_sha256": hashlib.sha256(raw).hexdigest(), "prerelease": "true" if "-" in version else "false"}


def publishing(values, env=os.environ, resolve=None, registry=None):
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY, "Publishing is restricted to the intended repository.")
    event, ref = env.get("GITHUB_EVENT_NAME"), env.get("GITHUB_REF", "")
    require(event in ("push", "workflow_dispatch"), "Unsupported publication trigger.")
    tag = ref.removeprefix("refs/tags/") if ref.startswith("refs/tags/") else env.get("RELEASE_TAG", "")
    require(tag == values["version"], "Git release tag must match VERSION and the egg image.")
    require(ref == "refs/tags/" + tag or event == "workflow_dispatch" and ref == "refs/heads/main",
            "Release publishing requires its tag or an explicitly selected main commit.")
    require(env.get("TAG_LATEST", "false") == "false", "This workflow publishes immutable version tags only; update mutable aliases separately.")
    require(env.get("UPSTREAM_VERSION", "") in ("", values["upstream"]), "Upstream override differs from the reviewed Dockerfile pin.")
    sha = env.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "Expected a full source SHA.")
    if resolve is None:
        resolve = lambda ref: subprocess.check_output(["git", "rev-parse", "--verify", ref], cwd=ROOT, text=True).strip()
    require(resolve("HEAD") == sha and resolve("refs/tags/" + tag + "^{commit}") == sha,
            "Release tag does not point to this exact source commit; do not move it automatically.")
    registry = registry if registry is not None else Registry()
    require(registry.manifest(tag) is None, "Versioned image already exists. Never overwrite it; select a new release version.")


def verify_published(values, sha, registry=None):
    registry = registry if registry is not None else Registry()
    result = registry.manifest(values["version"])
    require(result, "Release image has not been published yet.")
    digest, manifest = result
    if "manifests" in manifest:
        children = [m for m in manifest["manifests"] if m.get("platform", {}).get("os") == "linux" and m["platform"].get("architecture") == "amd64"]
        require(len(children) == 1, "Expected exactly one linux/amd64 image.")
        manifest = registry.manifest(children[0]["digest"])[1]
    config_digest = manifest["config"]["digest"]
    raw, _ = registry.get("blobs/" + config_digest)
    require("sha256:" + hashlib.sha256(raw).hexdigest() == config_digest, "Config digest does not match registry content.")
    config = json.loads(raw)
    metadata(config, sha, values["upstream"])
    require(config["config"]["Labels"]["org.opencontainers.image.version"] == values["version"], "Published image version label differs from VERSION.")
    return dict(values, digest=digest, source_sha=sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publishing", action="store_true")
    mode.add_argument("--verify-published", action="store_true")
    args = parser.parse_args()
    try:
        values = validate()
        if args.publishing:
            publishing(values)
        if args.verify_published:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            values = verify_published(values, sha)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                for key, value in values.items():
                    stream.write(f"{key}={value}\n")
        print(json.dumps(values, indent=2))
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print("Release preflight failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Guards and anonymous GHCR verification for PR #5's manual test publisher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "NoUhMaybe/Project-Reclaimer-Pterodactyl-Egg"
PACKAGE = "nouhmaybe/project-reclaimer-pterodactyl"
IMAGE = "ghcr.io/" + PACKAGE
BRANCH = "refs/heads/feature/console-manager"
UPGRADE_BRANCH = "refs/heads/feature/console-manager-upstream-0.9.20"
# Explicit, reviewed source/version/tag combinations. No arbitrary build inputs.
TARGETS = {
    BRANCH: ("0.9.13", "console-manager-pr5-"),
    UPGRADE_BRANCH: ("0.9.20", "console-manager-pr5-reclaimer-0.9.20-"),
}
REQUIRED_JOBS = {"validate-json", "python-tests (ubuntu-latest)", "python-tests (windows-latest)",
                 "shell-syntax", "shellcheck", "docker-build", "docker-runtime-tests"}
ACCEPT = ", ".join(("application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json",
                    "application/vnd.docker.distribution.manifest.list.v2+json", "application/vnd.docker.distribution.manifest.v2+json"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def request(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60) as response:
        return response.read(), response.headers


def api(path):
    token = os.environ["GITHUB_TOKEN"]
    raw, _ = request("https://api.github.com/repos/" + REPOSITORY + "/" + path,
                     {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})
    return json.loads(raw)


def validate_inputs(repository, event, ref, workflow_sha, source_sha, tag, latest, upstream):
    require(repository == REPOSITORY, "Test publishing is restricted to the intended repository.")
    require(event == "workflow_dispatch" and ref in TARGETS, "Manually dispatch an allowlisted Console Manager branch.")
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha or ""), "Supply a full lowercase 40-character source SHA.")
    require(workflow_sha == source_sha, "Dispatch ref and explicit source SHA must resolve to the same commit.")
    version, prefix = TARGETS[ref]
    require(re.fullmatch(re.escape(prefix) + r"test\.[1-9][0-9]*", tag or ""), "Test tag must match the reviewed branch namespace.")
    require(latest == "false", "Test publishing never permits latest tagging.")
    require(upstream == version, "Upstream pin must match the reviewed branch.")
    return prefix + "sha-" + source_sha


def validate_pr(pr, sha, ref=BRANCH):
    require(ref in TARGETS, "Unexpected source branch.")
    require(pr["state"] == "open" and not pr.get("merged"), "Source PR must remain open and unmerged.")
    require(pr["head"]["repo"]["full_name"] == REPOSITORY and pr["head"]["ref"] == ref.removeprefix("refs/heads/"),
            "Forks and arbitrary pull-request branches cannot publish with this workflow.")
    require(pr["head"]["sha"] == sha, "Source must be the trusted PR's current head, not an outdated commit.")
    if ref == UPGRADE_BRANCH:
        require(pr["base"]["repo"]["full_name"] == REPOSITORY and pr["base"]["ref"] == "feature/console-manager",
                "Upgrade PR must target the preserved Console Manager branch.")


def current_source(sha, ref):
    if ref == BRANCH:
        pr = api("pulls/5")
    else:
        query = urllib.parse.urlencode({"state": "open", "head": "NoUhMaybe:" + ref.removeprefix("refs/heads/"),
                                        "base": "feature/console-manager"})
        matches = api("pulls?" + query)
        require(len(matches) == 1, "Expected exactly one open upgrade PR against feature/console-manager.")
        pr = api("pulls/" + str(matches[0]["number"]))
    validate_pr(pr, sha, ref)


def environment_inputs():
    return validate_inputs(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"],
                           os.environ["GITHUB_SHA"], os.environ["SOURCE_SHA"], os.environ["TEST_TAG"],
                           os.environ["TAG_LATEST"], os.environ["UPSTREAM_VERSION"])


def validate_jobs(jobs):
    require(len(jobs) == 7 and {job["name"] for job in jobs} == REQUIRED_JOBS, "Expected all seven Validate egg CI jobs.")
    require(all(job["status"] == "completed" and job["conclusion"] == "success" for job in jobs),
            "Every CI job must have completed successfully for this exact source commit.")


def outputs(values):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")


def guard():
    sha, tag = os.environ["SOURCE_SHA"], os.environ["TEST_TAG"]
    sha_tag = environment_inputs()
    current_source(sha, os.environ["GITHUB_REF"])
    query = urllib.parse.urlencode({"head_sha": sha, "event": "pull_request", "per_page": 100})
    runs = api("actions/workflows/validate.yml/runs?" + query)["workflow_runs"]
    candidates = [run for run in runs if run["head_sha"] == sha]
    require(candidates and candidates[0]["status"] == "completed" and candidates[0]["conclusion"] == "success",
            "The latest Validate egg run for this exact SHA must pass before dispatching.")
    run = candidates[0]
    jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
    validate_jobs(jobs)
    values = {"sha": sha, "test_tag": tag, "sha_tag": sha_tag, "ci_run": run["html_url"], "upstream": os.environ["UPSTREAM_VERSION"]}
    outputs(values)
    print(json.dumps(values, indent=2))


class Registry:
    """Uses an anonymous pull-scope registry token; never a GitHub credential."""
    def __init__(self):
        scope = urllib.parse.urlencode({"service": "ghcr.io", "scope": "repository:" + PACKAGE + ":pull"})
        raw, _ = request("https://ghcr.io/token?" + scope)
        self.token = json.loads(raw)["token"]

    def get(self, suffix):
        return request("https://ghcr.io/v2/" + PACKAGE + "/" + suffix,
                       {"Authorization": "Bearer " + self.token, "Accept": ACCEPT})

    def manifest(self, reference):
        try:
            raw, headers = self.get("manifests/" + urllib.parse.quote(reference, safe=":"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        require(headers.get("Docker-Content-Digest") == digest, "Registry manifest digest mismatch.")
        return digest, json.loads(raw)

    def tags(self):
        raw, headers = self.get("tags/list?n=1000")
        require(not headers.get("Link"), "Tag pagination requires review before taking a complete baseline.")
        return json.loads(raw).get("tags") or []


def reserve(path):
    sha_tag = environment_inputs()
    tag = os.environ["TEST_TAG"]
    # Publication can follow a long build. Refuse an outdated branch head.
    current_source(os.environ["SOURCE_SHA"], os.environ["GITHUB_REF"])
    registry = Registry()
    require(registry.manifest(tag) is None and registry.manifest(sha_tag) is None, "A proposed tag already exists; never overwrite it.")
    baseline = {"image": IMAGE, "source_sha": os.environ["SOURCE_SHA"], "test_tag": tag, "sha_tag": sha_tag,
                "upstream": os.environ["UPSTREAM_VERSION"],
                "existing_tags": {existing: registry.manifest(existing)[0] for existing in registry.tags()}}
    Path(path).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(baseline, indent=2))


def metadata(config, sha, upstream="0.9.13"):
    require(config["os"] == "linux" and config["architecture"] == "amd64", "Expected linux/amd64 image.")
    runtime = config["config"]
    require(runtime["Labels"]["org.opencontainers.image.revision"] == sha, "Published image source revision does not match.")
    require(runtime["Labels"]["org.opencontainers.image.source"] == "https://github.com/" + REPOSITORY, "Unexpected image source.")
    require(runtime["Entrypoint"] == ["/usr/bin/tini", "--", "/pterodactyl/entrypoint.sh"], "tini startup changed.")
    require(runtime["Cmd"] == ["start"], "Upstream startup command changed.")
    require(upstream in {value[0] for value in TARGETS.values()}, "Unexpected upstream pin.")
    require("RECLAIMER_IMAGE_VERSION=" + upstream in runtime["Env"], "Upstream version changed.")


def verify(path):
    baseline = json.loads(Path(path).read_text(encoding="utf-8"))
    registry = Registry()
    test = registry.manifest(baseline["test_tag"])
    immutable = registry.manifest(baseline["sha_tag"])
    require(test and immutable and test[0] == immutable[0], "Both published tags must exist and resolve to the same digest.")
    manifest = test[1]
    if "manifests" in manifest:
        children = [m for m in manifest["manifests"] if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64"]
        require(len(children) == 1, "Expected exactly one linux/amd64 image.")
        manifest = registry.manifest(children[0]["digest"])[1]
    digest = manifest["config"]["digest"]
    raw, _ = registry.get("blobs/" + digest)
    require("sha256:" + hashlib.sha256(raw).hexdigest() == digest, "Registry config digest mismatch.")
    metadata(json.loads(raw), baseline["source_sha"], baseline["upstream"])
    for tag, old_digest in baseline["existing_tags"].items():
        current = registry.manifest(tag)
        require(current and current[0] == old_digest, "Existing tag changed during publication: " + tag)
    report = {"image": IMAGE + ":" + baseline["test_tag"], "sha_tag": IMAGE + ":" + baseline["sha_tag"],
              "source_sha": baseline["source_sha"], "upstream": baseline["upstream"], "digest": test[0], "platform": "linux/amd64",
              "anonymous_manifest_and_config": True, "existing_tags_unchanged": baseline["existing_tags"]}
    Path("publication.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    outputs({"digest": test[0]})
    print(json.dumps(report, indent=2))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("## Isolated PR #5 image\n\n```json\n" + json.dumps(report, indent=2) + "\n```\n\nAnonymous Docker pull and module verification run in the final verification job. Live Wings validation remains manual.\n")


def inspect_local():
    data = json.loads(subprocess.check_output(["docker", "image", "inspect", os.environ["LOCAL_IMAGE"]], text=True))[0]
    metadata({"os": data["Os"], "architecture": data["Architecture"], "config": data["Config"]}, os.environ["SOURCE_SHA"], os.environ["UPSTREAM_VERSION"])
    if os.environ.get("EXPECTED_DIGEST"):
        require(IMAGE + "@" + os.environ["EXPECTED_DIGEST"] in data["RepoDigests"], "Anonymous pull returned an unexpected digest.")
    print("Local image metadata verified: linux/amd64, source revision, upstream " + os.environ["UPSTREAM_VERSION"] + " and tini entrypoint.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("guard", "reserve", "verify", "inspect"))
    parser.add_argument("--baseline", default="production-tags-before.json")
    args = parser.parse_args()
    try:
        if args.operation == "guard":
            guard()
        elif args.operation == "reserve":
            reserve(args.baseline)
        elif args.operation == "verify":
            verify(args.baseline)
        else:
            inspect_local()
    except (ValueError, OSError, KeyError) as exc:
        # No request headers, tokens or secret environment values are printed.
        print("Test-image guard failed: " + ("HTTP " + str(exc.code) if isinstance(exc, urllib.error.HTTPError) else str(exc)), file=sys.stderr)
        sys.exit(1)

"""Publishing boundaries: source/CI identity and experimental tags only."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import test_image

SHA = "a" * 40


class TestImageGuards(unittest.TestCase):
    def inputs(self, **updates):
        values = dict(repository=test_image.REPOSITORY, event="workflow_dispatch", ref=test_image.BRANCH,
                      workflow_sha=SHA, source_sha=SHA, tag="console-manager-pr5-test.1", latest="false", upstream="0.9.13")
        values.update(updates)
        return test_image.validate_inputs(**values)

    def test_explicit_trusted_sha_and_experimental_tag(self):
        self.assertEqual(self.inputs(), "console-manager-pr5-sha-" + SHA)

    def test_upgrade_branch_requires_its_own_version_and_tag_namespace(self):
        values = dict(ref=test_image.UPGRADE_BRANCH, upstream="0.9.20", tag="console-manager-pr5-reclaimer-0.9.20-test.1")
        self.assertEqual(self.inputs(**values), "console-manager-pr5-reclaimer-0.9.20-sha-" + SHA)
        for changes in ({"upstream": "0.9.13"}, {"tag": "console-manager-pr5-test.2"}, {"ref": test_image.BRANCH}):
            with self.assertRaises(ValueError):
                self.inputs(**dict(values, **changes))

    def test_release_tags_and_shell_like_tags_rejected(self):
        for tag in ("latest", "v0.1.0", "v0.1.0-dev.5", "console-manager-pr5-test.0", "console-manager-pr5-test.1;echo", "console-manager-pr5-test.1\nlatest", "../tag"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                self.inputs(tag=tag)

    def test_wrong_source_trigger_namespace_and_upstream_rejected(self):
        for change in ({"repository": "attacker/repo"}, {"event": "pull_request_target"}, {"ref": "refs/heads/main"},
                       {"workflow_sha": "b" * 40}, {"source_sha": "main"}, {"latest": "true"}, {"upstream": "latest"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.inputs(**change)

    def test_ci_must_have_all_seven_successful_jobs(self):
        jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in test_image.REQUIRED_JOBS]
        test_image.validate_jobs(jobs)
        for bad in (jobs[:-1], [dict(j, conclusion="failure") if i == 0 else j for i, j in enumerate(jobs)]):
            with self.assertRaises(ValueError):
                test_image.validate_jobs(bad)

    def test_pr_must_be_current_trusted_branch_and_not_merged(self):
        pr = {"state": "open", "merged": False, "head": {"repo": {"full_name": test_image.REPOSITORY}, "ref": "feature/console-manager", "sha": SHA}}
        test_image.validate_pr(pr, SHA)
        fork = copy.deepcopy(pr)
        fork["head"]["repo"]["full_name"] = "attacker/fork"
        for bad in (dict(pr, merged=True), dict(pr, state="closed"), fork):
            with self.assertRaises(ValueError):
                test_image.validate_pr(bad, SHA)
        with self.assertRaises(ValueError):
            test_image.validate_pr(pr, "b" * 40)

    def test_upgrade_pr_cannot_be_a_fork_or_target_main(self):
        pr = {"state": "open", "merged": False,
              "head": {"repo": {"full_name": test_image.REPOSITORY}, "ref": "feature/console-manager-upstream-0.9.20", "sha": SHA},
              "base": {"repo": {"full_name": test_image.REPOSITORY}, "ref": "feature/console-manager"}}
        test_image.validate_pr(pr, SHA, test_image.UPGRADE_BRANCH)
        for key, value in (("ref", "main"), ("repo", {"full_name": "attacker/repo"})):
            bad = copy.deepcopy(pr)
            bad["base"][key] = value
            with self.assertRaises(ValueError):
                test_image.validate_pr(bad, SHA, test_image.UPGRADE_BRANCH)

    def test_image_architecture_revision_upstream_and_tini_are_required(self):
        value = {"os": "linux", "architecture": "amd64", "config": {
            "Labels": {"org.opencontainers.image.revision": SHA, "org.opencontainers.image.source": "https://github.com/" + test_image.REPOSITORY},
            "Entrypoint": ["/usr/bin/tini", "--", "/pterodactyl/entrypoint.sh"], "Cmd": ["start"],
            "Env": ["RECLAIMER_IMAGE_VERSION=0.9.13"]}}
        test_image.metadata(value, SHA)
        for change in ({"architecture": "arm64"}, {"os": "windows"}):
            with self.assertRaises(ValueError):
                test_image.metadata(dict(value, **change), SHA)
        with self.assertRaises(ValueError):
            test_image.metadata(value, "b" * 40)
        broken = copy.deepcopy(value)
        broken["config"]["Entrypoint"] = ["sh"]
        with self.assertRaises(ValueError):
            test_image.metadata(broken, SHA)
        upgraded = copy.deepcopy(value)
        upgraded["config"]["Env"] = ["RECLAIMER_IMAGE_VERSION=0.9.20"]
        test_image.metadata(upgraded, SHA, "0.9.20")
        with self.assertRaises(ValueError):
            test_image.metadata(upgraded, SHA, "0.9.13")

    def test_existing_test_tag_aborts_before_snapshot_or_push(self):
        pr = {"state": "open", "merged": False, "head": {"repo": {"full_name": test_image.REPOSITORY}, "ref": "feature/console-manager", "sha": SHA}}
        with patch.dict(test_image.os.environ, {"SOURCE_SHA": SHA, "TEST_TAG": "console-manager-pr5-test.1",
                                              "GITHUB_REPOSITORY": test_image.REPOSITORY, "GITHUB_EVENT_NAME": "workflow_dispatch",
                                              "GITHUB_REF": test_image.BRANCH, "GITHUB_SHA": SHA,
                                              "UPSTREAM_VERSION": "0.9.13", "TAG_LATEST": "false"}), \
             patch.object(test_image, "api", return_value=pr), \
             patch.object(test_image, "Registry") as registry, \
             patch.object(test_image.Path, "write_text") as write:
            registry.return_value.manifest.return_value = ("sha256:existing", {})
            with self.assertRaises(ValueError):
                test_image.reserve("unused.json")
            write.assert_not_called()

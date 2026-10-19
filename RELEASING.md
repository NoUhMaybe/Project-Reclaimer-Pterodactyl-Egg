# Release preflight and publishing procedure

This is a runbook, not authorization to publish, move/delete tags, overwrite images
or deploy. Merge, tag creation, GitHub Release publication and any server test need
the owner's explicit approval. This maintenance task only prepares and validates
a PR. Keep the upstream pin at 0.9.20.

## Existing identifiers: 2026-10-19 audit

| Identifier | Observed state |
| --- | --- |
| main when repair started | 651da9a8159a8821b355227a4f49a8929ca8c386 |
| v0.1.1 local and remote Git tag | Same old commit, 651da9a8159a8821b355227a4f49a8929ca8c386 |
| v0.1.1 GitHub Release | Deleted; public API returns 404 |
| v0.1.1 GHCR image | Already public; sha256:1a0b174a23b1c2ba05628fe0f1f67f53b50a03b085400204e88ea992f08a244a |
| v0.1.0 Git tag | Preserved at 74c9bbd9be7a7b9853a76d984616cf3b117ff8f6 |
| v0.1.0 GHCR image | Preserved; sha256:a80a061b096499c3c5e0f560151f3fad0a3fcc8d3ad38c5c2d9f22e76ab8796b |

Deleting a GitHub Release does not remove its Git tag or Docker image. Recreating
that release at the existing v0.1.1 tag would select the old, uncorrected source.
The new publisher intentionally rejects reusing the existing versioned image.
**Republishing corrected source as v0.1.1 is not safe with the current identifiers.**

Prefer a new unused patch version, such as v0.1.2, after approval. Change VERSION,
update current-version documentation/notes, regenerate the egg and pass CI again.
Do not force-update, delete or recreate the old tags or replace the existing image.
Any exceptional history reconciliation requires a separate explicit decision;
this runbook supplies no automatic destructive reconciliation commands.

## Prepare the corrected commit

1. Review and approve the maintenance PR after every Validate egg job passes.
   Merge only with approval. Fetch main and record its full corrected SHA; a merge
   commit can differ from the tested PR head. Validate the resulting main commit.
2. Resolve the occupied version by selecting an approved unused patch version and
   updating VERSION plus the version table/notes. The prepared maintenance files
   currently say v0.1.1 as requested; they do not silently select a different version.
3. Run the following from a clean checkout of the intended final source:

   ```bash
   python3 tools/build_egg.py
   python3 tools/check_release.py
   python3 -m unittest discover -s tests -v
   bash -n scripts/install.sh
   git diff --exit-code
   git rev-parse HEAD
   ```

   The JSON must select ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:<VERSION>.
   No difference after regeneration is expected once the generated file is committed.
   CI additionally runs Linux/Windows tests, ShellCheck, real upstream CLI probes,
   Docker build and runtime A/B/C/E/F. Without local Docker, wait for those CI jobs.
4. Inspect local and remote tag refs and anonymously check the corresponding GHCR
   manifest. Both identifiers must be unused for a new corrected release. Record
   the exact main SHA, VERSION, upstream 0.9.20 and JSON SHA256. These must agree.

## Approved publication only

1. After separate authorization, create the new version tag at the recorded exact
   corrected main commit and push only that tag. Use an explicit commit rather than
   assuming HEAD is correct. Never force-push a release tag. For an unused version:

   ```bash
   version=$(cat VERSION)
   # approved_commit must be the reviewed, validated full SHA recorded above.
   git tag "$version" "$approved_commit"
   git push origin "refs/tags/$version"
   ```

2. The tag push starts Publish image to GHCR. Alternatively, if the approved tag
   already exists at that exact source and its image is still absent, manually run
   publish.yml from that tag with release_tag=<VERSION>, reclaimer_version=0.9.20,
   tag_latest=false and empty test_tag/source_sha. Do not retry once an image exists.
3. Watch the preflight, complete tests, build, runtime tests and push. Preflight
   compares the Git tag, VERSION, JSON, canonical installer, source SHA and upstream
   pin. It refuses existing image tags both before build and immediately before
   push. Publication uses only the immutable version tag; it never moves latest.
4. Check the anonymous published-image verification and record its digest. On an
   independent Docker host, pull the full image with an empty authentication config
   and compare its RepoDigest, architecture and OCI source/version labels with the
   workflow. The publisher also verifies them via anonymous registry requests.
5. Only after image verification and release approval, create the GitHub Release
   using the already approved tag. Do not let GitHub create a tag from a guessed
   target branch. Use the corrected title, e.g. Project Reclaimer Pterodactyl Egg
   v0.1.2 — Reclaimer v0.9.20 when that is the chosen version. Paste RELEASE-NOTES.md
   as GitHub-flavored Markdown after updating the intended egg version; no HTML.

## JSON attachment and download verification

The publisher preserves contents:read/packages:write permissions. It uploads
egg-project-reclaimer.json as an Actions artifact. A separate release-assets.yml
responds to publication of an existing GitHub Release, or an explicit manual retry
for that existing release. Its upload job alone has contents:write (required for
release assets), with no package-write permission. It validates source JSON,
tag/VERSION equality, stable/prerelease status and published image source/digest
before calling gh release upload. It never creates a release or uses --clobber.
See [GitHub's release event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)
and [upload command](https://cli.github.com/manual/gh_release_upload).

Publish the image first; if release-assets runs before the image exists, it fails
safely. Retry that workflow with release_tag=<VERSION> after verification. If the
attachment already exists, it is not replaced. Inspect its checksum and investigate
any mismatch instead of overwriting it.

Manual fallback, only with release-asset approval:

1. Check out the exact approved release tag into a clean directory.
2. Run python3 tools/check_release.py --verify-published and verify its source SHA,
   image digest and artifact_sha256. Do not regenerate a different asset after this.
3. On the existing GitHub Release's Edit page, attach that checkout's validated
   egg-project-reclaimer.json and save. Alternatively use
   `gh release upload "$version" egg-project-reclaimer.json` without --clobber.
4. Download the public egg attachment and compare its SHA256 and JSON image value
   with the validated file. Test the release's actual download link while signed out.
   Ensure README/INSTALL and the release notes reference that real attachment.

The generated JSON is a release artifact, not a Panel export. Community catalog
submission still needs importing it into a test Nest, reviewing/saving the correct
image and settings, then exporting the egg from an actual Panel and comparing it.

## Approved fresh-install acceptance

On a separate authorized test server, verify a genuinely empty installation mount,
upload owned Halo 3 assets, confirm correct persistent layout, matching .20 clients,
raw RCON/menu, LAN/WAN multiplayer and graceful Stop/Restart. Reinstall and compare
assets, bans, playlists and administrator configuration. Follow WINGS-VALIDATION.md
for the full checklist. Do not touch production servers as part of release preparation.

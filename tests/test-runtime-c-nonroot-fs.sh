#!/bin/bash
# Runtime Test C — Non-root filesystem behavior.
#
# Runs the container with an explicit, disposable non-root UID:GID (never
# root, and deliberately NOT whatever UID happens to own files on the CI
# runner) against a fresh empty volume, approximating how Wings always
# starts containers (see TROUBLESHOOTING.md "Verified ground truth").
#
# Verifies: directory initialization and symlink resolution succeed, the
# resulting files are owned by the UID/GID we ran as (never root), and the
# container fails for the *expected* reason (missing game assets) rather
# than a permission error — proving the non-root path is reached safely.
#
# Does NOT exercise reclaimer-entrypoint prepare-prefix / a real Wine
# prefix init under this UID (validate-assets.sh intentionally exits
# before reaching it — see entrypoint.sh). That is covered separately by
# tests/test-runtime-e-wine-prefix.sh (automated, no game assets needed,
# but does run real Wine/Xvfb so it is kept as its own test rather than
# folded in here) and, with a real game process, by
# tests/test-runtime-d-full-startup.sh (manual, real assets required).
#
# Usage: IMAGE=<built image tag> ./tests/test-runtime-c-nonroot-fs.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/lib/cleanup.sh
source "$SCRIPT_DIR/lib/cleanup.sh"

# Deliberately not 0, not 1000 (upstream's baked-in "reclaimer" UID), and
# not whatever UID owns files on the host running this script.
TEST_UID=2000
TEST_GID=2000
CONTAINER_NAME="reclaimer-test-c-$$"
WORKDIR="$(mktemp -d)"
# This test deliberately runs the container as a UID that will essentially
# never match whoever is running this script (e.g. the CI runner), so the
# files it creates cannot be removed with a plain host-side `rm -rf` —
# safe_rm_rf's container-based fallback (root inside a throwaway
# container, which can remove any UID's files) is required here, not just
# a nice-to-have as in Tests A/B.
trap 'docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true; safe_rm_rf "$WORKDIR" "$IMAGE"' EXIT

mkdir -p "$WORKDIR/home-container"

# A freshly created host directory is owned by whoever is running this
# script (e.g. the CI runner), not by $TEST_UID:$TEST_GID. Wings always
# chowns a server's real volume to the exact UID/GID it is about to run
# the container as *before* starting it — without doing the same here,
# $TEST_UID would hit a genuine (and misleading) "Permission denied"
# writing into a directory it does not own, which is not what this test
# is meant to check. A regular (non-root) user cannot `chown` to an
# arbitrary UID it doesn't own, so this runs as root inside a throwaway
# container instead, exactly like safe_rm_rf's cleanup fallback does.
echo "==> Priming the bind mount's ownership to $TEST_UID:$TEST_GID (as Wings would)"
docker run --rm \
    --user root \
    --entrypoint chown \
    -v "$WORKDIR/home-container:/target" \
    "$IMAGE" \
    -R "$TEST_UID:$TEST_GID" /target

echo "==> Running $IMAGE as non-root UID:GID $TEST_UID:$TEST_GID, no game assets"
set +e
docker run --name "$CONTAINER_NAME" \
    --user "$TEST_UID:$TEST_GID" \
    -e SERVER_NAME="Test C Server" \
    -e SERVER_PORT=49176 \
    -v "$WORKDIR/home-container:/home/container" \
    "$IMAGE" >"$WORKDIR/log.txt" 2>&1
exit_code=$?
set -e

cat "$WORKDIR/log.txt"

# Regression guard: a restrictive-parent-directory permission bug (fixed by
# `chmod 755 /home/reclaimer` in the Dockerfile; see TROUBLESHOOTING.md
# "Verified upstream image metadata") previously made this exact check
# fail for UID 2000, since /home/reclaimer was 0700 (owner UID 1000 only) —
# lstat() on the .wine symlink returned EACCES, which entrypoint.sh's
# `[ -L path ]` check cannot distinguish from the symlink not existing.
if grep -q "is not the symlink this image's Dockerfile is supposed to create" "$WORKDIR/log.txt"; then
    echo "FAIL: symlink validation failed under UID $TEST_UID:$TEST_GID — this is the" >&2
    echo "restrictive /home/reclaimer permission regression, not the missing-assets" >&2
    echo "failure this test expects. See TROUBLESHOOTING.md." >&2
    exit 1
fi

if grep -qi "permission denied" "$WORKDIR/log.txt"; then
    echo "FAIL: a permission error occurred running as non-root UID $TEST_UID:$TEST_GID" >&2
    exit 1
fi

if ! grep -q "MISSING (required)" "$WORKDIR/log.txt"; then
    echo "FAIL: expected the same missing-assets failure as Test A, got something else" >&2
    exit 1
fi

if [ "$exit_code" -eq 0 ]; then
    echo "FAIL: container exited 0 despite missing required game assets" >&2
    exit 1
fi

echo "==> Checking ownership of files created under /home/container"
for rel in server server/game server/content server/playlists server/data .cache .cache/reclaimer .wine-prefix; do
    path="$WORKDIR/home-container/$rel"
    if [ ! -e "$path" ]; then
        echo "FAIL: expected directory not created: $rel" >&2
        exit 1
    fi
    owner_uid=$(stat -c '%u' "$path")
    owner_gid=$(stat -c '%g' "$path")
    if [ "$owner_uid" != "$TEST_UID" ] || [ "$owner_gid" != "$TEST_GID" ]; then
        echo "FAIL: $rel is owned by $owner_uid:$owner_gid, expected $TEST_UID:$TEST_GID (found root-owned or wrong-UID output)" >&2
        exit 1
    fi
done

echo "PASS: Test C — non-root UID initializes directories correctly, no permission errors, no root-owned output."

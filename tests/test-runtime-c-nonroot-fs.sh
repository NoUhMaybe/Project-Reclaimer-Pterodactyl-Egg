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
# prefix init under this UID (that needs the full Wine+Xvfb stack and
# meaningful CPU/time, and validate-assets.sh intentionally exits before
# reaching it — see entrypoint.sh). That remains covered only by Test D
# with real game assets on a real Docker host.
#
# Usage: IMAGE=<built image tag> ./tests/test-runtime-c-nonroot-fs.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
# Deliberately not 0, not 1000 (upstream's baked-in "reclaimer" UID), and
# not whatever UID owns files on the host running this script.
TEST_UID=2000
TEST_GID=2000
CONTAINER_NAME="reclaimer-test-c-$$"
WORKDIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true; rm -rf "$WORKDIR"' EXIT

mkdir -p "$WORKDIR/home-container"

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

#!/bin/bash
# Runtime Test E — Wine prefix initialization and persistence (regression
# test for the restrictive /home/reclaimer permissions bug; see
# TROUBLESHOOTING.md "Verified upstream image metadata").
#
# Invokes `reclaimer-entrypoint prepare-prefix` directly (bypassing our own
# entrypoint.sh entirely, like Test B does for configure.py) as a
# disposable non-root, non-owner UID, twice against the same persistent
# volume:
#   1. First run: must actually initialize a working Wine prefix (resolve
#      the /home/reclaimer/.wine symlink, run wineboot, write system.reg)
#      — this is the exact codepath that used to fail with "Permission
#      denied" once the restrictive /home/reclaimer fix is regressed.
#   2. Second run: must recognize the existing, persistent prefix and
#      leave it untouched (upstream's own idempotence check), rather than
#      re-initializing it — proving the prefix actually survives container
#      recreation the way a Wings server restart needs it to.
#
# Does not require game assets (never touches validate-assets.sh or the
# game process) but does run real Wine + Xvfb, so expect this to take
# noticeably longer than Tests A/B/C (tens of seconds, not milliseconds).
#
# Usage: IMAGE=<built image tag> ./tests/test-runtime-e-wine-prefix.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/lib/cleanup.sh
source "$SCRIPT_DIR/lib/cleanup.sh"

# Deliberately not 0, not 1000 (upstream's baked-in "reclaimer" UID), and
# different from Test C's UID so the two tests can never mask each other.
TEST_UID=2001
TEST_GID=2001
WORKDIR="$(mktemp -d)"
trap 'safe_rm_rf "$WORKDIR" "$IMAGE"' EXIT

mkdir -p "$WORKDIR/home-container/.wine-prefix"

echo "==> Priming the bind mount's ownership to $TEST_UID:$TEST_GID (as Wings would)"
docker run --rm \
    --user root \
    --entrypoint chown \
    -v "$WORKDIR/home-container:/target" \
    "$IMAGE" \
    -R "$TEST_UID:$TEST_GID" /target

run_prepare_prefix() {
    docker run --rm \
        --user "$TEST_UID:$TEST_GID" \
        --entrypoint reclaimer-entrypoint \
        -v "$WORKDIR/home-container:/home/container" \
        "$IMAGE" \
        prepare-prefix
}

SYSTEM_REG="$WORKDIR/home-container/.wine-prefix/system.reg"

echo "==> First run: initializing a fresh Wine prefix as UID $TEST_UID:$TEST_GID"
if ! run_prepare_prefix >"$WORKDIR/log1.txt" 2>&1; then
    cat "$WORKDIR/log1.txt"
    echo "FAIL: prepare-prefix failed on first run under non-root UID $TEST_UID:$TEST_GID" >&2
    exit 1
fi
cat "$WORKDIR/log1.txt"

if grep -q "is not the symlink this image's Dockerfile is supposed to create" "$WORKDIR/log1.txt"; then
    echo "FAIL: symlink validation failed — restrictive /home/reclaimer permission regression" >&2
    exit 1
fi

if grep -qi "permission denied" "$WORKDIR/log1.txt"; then
    echo "FAIL: a permission error occurred initializing the Wine prefix as non-root UID $TEST_UID:$TEST_GID" >&2
    exit 1
fi

if [ ! -f "$SYSTEM_REG" ]; then
    echo "FAIL: prepare-prefix reported success but $SYSTEM_REG was never created" >&2
    exit 1
fi

owner_uid=$(stat -c '%u' "$SYSTEM_REG")
owner_gid=$(stat -c '%g' "$SYSTEM_REG")
if [ "$owner_uid" != "$TEST_UID" ] || [ "$owner_gid" != "$TEST_GID" ]; then
    echo "FAIL: $SYSTEM_REG is owned by $owner_uid:$owner_gid, expected $TEST_UID:$TEST_GID" >&2
    exit 1
fi

echo "==> Second run: the existing prefix must persist, not be reinitialized"
before_hash=$(sha256sum "$SYSTEM_REG" | cut -d ' ' -f 1)

if ! run_prepare_prefix >"$WORKDIR/log2.txt" 2>&1; then
    cat "$WORKDIR/log2.txt"
    echo "FAIL: prepare-prefix failed on second run against an existing prefix" >&2
    exit 1
fi
cat "$WORKDIR/log2.txt"

after_hash=$(sha256sum "$SYSTEM_REG" | cut -d ' ' -f 1)
if [ "$before_hash" != "$after_hash" ]; then
    echo "FAIL: system.reg changed on the second run — the prefix was reinitialized" >&2
    echo "instead of being recognized as already-present and persistent" >&2
    exit 1
fi

echo "PASS: Test E — Wine prefix initializes correctly under a non-root UID and persists across runs."

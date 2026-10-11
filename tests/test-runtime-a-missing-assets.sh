#!/bin/bash
# Runtime Test A — Missing assets.
#
# Verifies the container behaves correctly when started with NO Halo 3
# game assets uploaded: asset validation must run, name exactly what is
# missing, explain how to fix it, and exit nonzero — never looping forever
# or reporting a misleading "ready" state. See entrypoint.sh for why this
# intentionally differs from upstream's own infinite retry loop.
#
# Usage: IMAGE=<built image tag> ./tests/test-runtime-a-missing-assets.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
CONTAINER_NAME="reclaimer-test-a-$$"
WORKDIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true; rm -rf "$WORKDIR"' EXIT

mkdir -p "$WORKDIR/home-container"

echo "==> Running $IMAGE with no game assets uploaded"
set +e
docker run --name "$CONTAINER_NAME" \
    -e SERVER_NAME="Test A Server" \
    -e SERVER_PORT=49176 \
    -v "$WORKDIR/home-container:/home/container" \
    "$IMAGE" >"$WORKDIR/log.txt" 2>&1
exit_code=$?
set -e

cat "$WORKDIR/log.txt"

if [ "$exit_code" -eq 0 ]; then
    echo "FAIL: container exited 0 despite missing required game assets" >&2
    exit 1
fi

if ! grep -q "MISSING (required)" "$WORKDIR/log.txt"; then
    echo "FAIL: log does not identify the specific missing required files" >&2
    exit 1
fi

if ! grep -qi "upload" "$WORKDIR/log.txt"; then
    echo "FAIL: log does not explain how to fix the problem (upload instructions)" >&2
    exit 1
fi

if docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q true; then
    echo "FAIL: container is still running after a fatal asset-validation error" >&2
    exit 1
fi

echo "PASS: Test A — missing assets correctly identified, fails fast with exit code $exit_code, no misleading running state."

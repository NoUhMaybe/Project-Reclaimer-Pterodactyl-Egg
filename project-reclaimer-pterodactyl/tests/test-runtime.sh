#!/bin/bash
# Manual/live runtime smoke test.
#
# This is NOT run automatically in CI: it requires a real Docker host,
# the built project-reclaimer-pterodactyl image, and your own legally
# obtained Halo 3 game files placed under ./fixtures/game (see below).
# It approximates what Wings does (bind-mount a single persistent
# directory at /home/container, publish one UDP+TCP port) without
# requiring an actual Pterodactyl Panel/Wings install.
#
# Usage:
#   IMAGE=project-reclaimer-pterodactyl:local ./tests/test-runtime.sh
#
# What this script DOES verify (if it passes):
#   - the image starts, the entrypoint runs without crashing
#   - dedicated.toml is generated with the expected name/port
#   - the container keeps running (does not immediately exit)
#   - the UDP game port is open
#
# What this script does NOT verify (manual testing required, see
# TROUBLESHOOTING.md "What has and has not been tested"):
#   - a real Halo 3 client can actually join and play a match
#   - server browser / master visibility from a different network
#   - RCON end to end
#   - graceful shutdown timing under real game load

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
WORKDIR="$(mktemp -d)"
CONTAINER_NAME="reclaimer-runtime-test-$$"
PORT=49176

cleanup() {
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    rm -rf "$WORKDIR"
}
trap cleanup EXIT

mkdir -p "$WORKDIR/home-container"

echo "==> Starting container from $IMAGE"
docker run -d --name "$CONTAINER_NAME" \
    -e SERVER_NAME="Runtime Test Server" \
    -e SERVER_PORT="$PORT" \
    -e MAX_PLAYERS=16 \
    -p "${PORT}:${PORT}/udp" \
    -p "${PORT}:${PORT}/tcp" \
    -v "$WORKDIR/home-container:/home/container" \
    "$IMAGE" >/dev/null

echo "==> Waiting up to 30s for the container to still be running"
for _ in $(seq 1 30); do
    if ! docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" | grep -q true; then
        echo "FAIL: container exited early. Logs:" >&2
        docker logs "$CONTAINER_NAME" >&2 || true
        exit 1
    fi
    if [ -f "$WORKDIR/home-container/server/dedicated.toml" ]; then
        break
    fi
    sleep 1
done

TOML="$WORKDIR/home-container/server/dedicated.toml"
if [ ! -f "$TOML" ]; then
    echo "FAIL: dedicated.toml was never generated" >&2
    docker logs "$CONTAINER_NAME" >&2 || true
    exit 1
fi

if ! grep -q 'name = "Runtime Test Server"' "$TOML"; then
    echo "FAIL: dedicated.toml does not contain the expected server name" >&2
    cat "$TOML" >&2
    exit 1
fi

if ! grep -q "port = $PORT" "$TOML"; then
    echo "FAIL: dedicated.toml does not contain the expected port" >&2
    cat "$TOML" >&2
    exit 1
fi

echo "PASS: container started, dedicated.toml generated correctly."
echo "NOTE: this does not confirm the game server itself is joinable;"
echo "it only confirms the Pterodactyl adaptation layer worked. Without"
echo "uploaded Halo 3 assets, validate-assets.sh is expected to have"
echo "exited non-zero inside the container after this point (check"
echo "'docker logs $CONTAINER_NAME' above for the exact message)."

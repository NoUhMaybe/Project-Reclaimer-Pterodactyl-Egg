#!/bin/bash
# Runtime Test D — Full startup with real Halo 3 assets (manual, requires
# your own legally-owned game files; never run in CI).
#
# This script cannot be executed automatically here: it requires copying
# real, legally obtained Halo 3 files into a server directory first. It is
# provided so the manual steps are documented precisely, not to pretend
# the test has been run — see tests/test-runtime.sh, which refuses to mark
# this as passed and explains exactly what remains to be verified by hand.
#
# Usage:
#   GAME_DIR=/path/to/your/halo3/game/folder IMAGE=<built image tag> \
#       ./tests/test-runtime-d-full-startup.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
GAME_DIR="${GAME_DIR:?set GAME_DIR=<path to your own halo3 game/ folder, containing halo3/halo3.dll and halo3/maps/shared.map> before running this script}"

if [ ! -f "$GAME_DIR/halo3/halo3.dll" ] || [ ! -f "$GAME_DIR/halo3/maps/shared.map" ]; then
    echo "ERROR: GAME_DIR does not look like a valid Halo 3 game folder" >&2
    echo "(expected $GAME_DIR/halo3/halo3.dll and $GAME_DIR/halo3/maps/shared.map)" >&2
    exit 1
fi

CONTAINER_NAME="reclaimer-test-d-$$"
WORKDIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true; rm -rf "$WORKDIR"' EXIT

mkdir -p "$WORKDIR/home-container/server/game"
cp -r "$GAME_DIR/." "$WORKDIR/home-container/server/game/"

echo "==> Starting $IMAGE with real game assets (this will take longer: Wine prefix init + map load)"
docker run -d --name "$CONTAINER_NAME" \
    -e SERVER_NAME="Test D Server" \
    -e SERVER_PORT=49176 \
    -e MAP=Guardian \
    -e GAME_TYPE=Slayer \
    -p 49176:49176/udp \
    -p 49176:49176/tcp \
    -v "$WORKDIR/home-container:/home/container" \
    "$IMAGE"

echo "==> Manual verification checklist (this script only starts the container — it does"
echo "    not and cannot automatically confirm the following; check by hand):"
echo "    1. docker logs -f $CONTAINER_NAME   # watch for Wine starting the game executable"
echo "    2. Confirm no Wine crash / missing DLL errors appear."
echo "    3. Confirm the UDP port is bound: an external 'server-status' check against"
echo "       this host's public IP:49176, or joining with a real Halo 3 client."
echo "    4. Confirm the server appears in the in-game Server Browser (server-browser"
echo "       visibility through the public master, see CONFIGURATION.md 'Networking')."
echo "    5. Join with a client, start a match, confirm map rotation works."
echo "    6. docker stop $CONTAINER_NAME   # confirm graceful shutdown within ~30s (SIGINT)"
echo "    7. docker start $CONTAINER_NAME  # confirm persistent state (dedicated.toml,"
echo "       Wine prefix) survives and the server comes back up without re-initializing."
echo ""
echo "This script intentionally does not declare PASS/FAIL for this test: see"
echo "TROUBLESHOOTING.md 'What has and has not been tested' — none of the above has"
echo "been executed by the agent that wrote this egg, only documented precisely."

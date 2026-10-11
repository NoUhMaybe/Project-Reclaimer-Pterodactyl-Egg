#!/bin/bash
# Runtime Test B — Configuration generation, independent of game startup.
#
# Runs docker/configure.py directly (overriding the image's entrypoint),
# never touching Wine, asset validation, or the game process at all.
# Verifies dedicated.toml generation: correct port/name, correct escaping,
# idempotent re-runs, and preservation of hand-edited content outside the
# Pterodactyl-managed block.
#
# Usage: IMAGE=<built image tag> ./tests/test-runtime-b-configuration.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/lib/cleanup.sh
source "$SCRIPT_DIR/lib/cleanup.sh"

WORKDIR="$(mktemp -d)"
trap 'safe_rm_rf "$WORKDIR" "$IMAGE"' EXIT
mkdir -p "$WORKDIR/home-container"

run_configure() {
    # Run as the calling user's own UID/GID (configure.py doesn't care
    # which UID runs it) so dedicated.toml is written with an owner this
    # script can always clean up directly, without needing cleanup.sh's
    # container-based fallback in the common case.
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        --entrypoint python3 \
        -v "$WORKDIR/home-container:/home/container" \
        -e SERVER_NAME="$1" \
        -e SERVER_PORT="$2" \
        -e "PLAYLIST=${3:-}" \
        "$IMAGE" /pterodactyl/configure.py
}

echo "==> First run: fresh dedicated.toml"
run_configure "Config Test Server" 49176 "playlists/foo.playlist.json"

TOML="$WORKDIR/home-container/server/dedicated.toml"
if [ ! -f "$TOML" ]; then
    echo "FAIL: dedicated.toml was not created" >&2
    exit 1
fi
grep -q 'name = "Config Test Server"' "$TOML" || { echo "FAIL: server name missing/incorrect" >&2; exit 1; }
grep -q "port = 49176" "$TOML" || { echo "FAIL: port missing/incorrect" >&2; exit 1; }
grep -q 'playlist = "playlists/foo.playlist.json"' "$TOML" || { echo "FAIL: playlist missing/incorrect" >&2; exit 1; }

echo "==> Second run with identical inputs: must be byte-for-byte idempotent"
cp "$TOML" "$WORKDIR/first.toml"
run_configure "Config Test Server" 49176 "playlists/foo.playlist.json"
if ! diff -q "$WORKDIR/first.toml" "$TOML" >/dev/null; then
    echo "FAIL: dedicated.toml changed on a repeated run with identical inputs" >&2
    diff "$WORKDIR/first.toml" "$TOML" || true
    exit 1
fi

echo "==> Hand-editing a section outside the managed block, then changing inputs"
printf '\n[master]\npeers = ["https://example.com"]\n' >> "$TOML"
run_configure "Renamed Server" 49177 ""

if ! grep -q 'peers = \["https://example.com"\]' "$TOML"; then
    echo "FAIL: hand-edited content outside the managed block was not preserved" >&2
    exit 1
fi
grep -q 'name = "Renamed Server"' "$TOML" || { echo "FAIL: server name was not updated" >&2; exit 1; }
grep -q "port = 49177" "$TOML" || { echo "FAIL: port was not updated" >&2; exit 1; }
if grep -q "Config Test Server" "$TOML"; then
    echo "FAIL: old server name was not replaced" >&2
    exit 1
fi

echo "==> Verifying special-character escaping"
run_configure 'Quote " Server' 49178 ""
grep -q 'name = "Quote \\" Server"' "$TOML" || { echo "FAIL: quote character was not escaped correctly" >&2; exit 1; }

echo "PASS: Test B — configuration generation is correct, idempotent, and preserves hand-edited content."

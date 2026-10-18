#!/bin/bash
# Pterodactyl compatibility wrapper for the official Project Reclaimer image.
#
# Responsibilities (in order):
#   1. Create the real directories the build-time symlinks in the Dockerfile
#      point at (/server, /cache, the Wine prefix), under /home/container —
#      the only path Wings guarantees is writable by whatever UID it runs
#      this container as. See Dockerfile for why this cannot be done here
#      via rm -rf + ln -s at runtime (parent-directory permissions).
#   2. Translate egg variables into upstream's documented
#      RECLAIMER_DEDICATED_* environment variable overrides.
#   3. Generate or patch dedicated.toml via configure.py.
#   4. Validate that required Halo 3 game assets have been uploaded, and
#      fail fast with an actionable message if not (see note below on why
#      this intentionally does not match upstream's own infinite-retry
#      behavior).
#   5. Initialize the Wine prefix for whatever UID we are actually running
#      as (reclaimer-entrypoint prepare-prefix), since the one upstream
#      baked into the image at build time belongs to a fixed UID that will
#      not generally match the UID Wings assigns (see Dockerfile).
#   6. Hand off to the real upstream program, honoring Pterodactyl's
#      Wings-injected $STARTUP variable the same way the official
#      "Creating a Custom Docker Image" guide's example entrypoint does.
#
# Verified against ghcr.io/projectreclaimer/project-reclaimer-dedicated's
# actual published image config and entrypoint script (see
# TROUBLESHOOTING.md "Verified upstream image metadata"); this is not a
# guess about upstream's internal paths.

set -euo pipefail

TZ="${TZ:-UTC}"
export TZ

export USER=container
export HOME=/home/container
cd "$HOME"

echo "-----------------------------------------------------------"
echo " Project Reclaimer — Pterodactyl compatibility entrypoint"
echo "-----------------------------------------------------------"

# ---------------------------------------------------------------------------
# 1. Create the targets of the symlinks baked in at image build time
#    (/server -> here, /cache -> here, /home/reclaimer/.wine -> here).
#    Only mkdir is needed: the symlinks themselves already exist in the
#    image and point here, and /home/container is always writable by
#    whatever UID Wings assigned this container, regardless of what UID
#    that turns out to be on a given node.
# ---------------------------------------------------------------------------
SERVER_DIR="$HOME/server"
CACHE_DIR="$HOME/.cache/reclaimer"
WINE_PREFIX_DIR="$HOME/.wine-prefix"

# Use the actual Wings-owned persistent directory rather than the
# upstream root-owned Wine-prefix symlink.
export WINEPREFIX="$WINE_PREFIX_DIR"

mkdir -p "$SERVER_DIR/game" "$SERVER_DIR/content/Maps" "$SERVER_DIR/content/Game Modes" \
         "$SERVER_DIR/content/Mods" "$SERVER_DIR/content/Images" "$SERVER_DIR/playlists" "$SERVER_DIR/data" \
         "$CACHE_DIR" "$WINE_PREFIX_DIR"

for path in /server /cache /home/reclaimer/.wine; do
    if [ ! -L "$path" ]; then
        echo "ERROR: $path is not the symlink this image's Dockerfile is supposed to create." >&2
        echo "This indicates the image was built incorrectly, the upstream base image" >&2
        echo "changed its own directory layout in a way this wrapper does not expect, or" >&2
        echo "this path's parent directory denies traversal to the current UID (a failed" >&2
        echo "lstat() looks identical to 'does not exist' to this check) — compare:" >&2
        # shellcheck disable=SC2012
        ls -ld "$(dirname "$path")" "$path" 2>&1 | sed 's/^/  /' >&2
        echo "id: $(id)" >&2
        echo "See TROUBLESHOOTING.md 'Verified upstream image metadata'." >&2
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# 2. Translate egg variables to upstream's documented environment overrides.
#
# PUID/PGID are deliberately NOT set here: upstream's reclaimer-entrypoint
# only reads them when it finds itself already running as root, to decide
# which UID/GID to drop privileges to. Wings never runs containers as root
# (it always passes an explicit non-root --user), so that code path never
# triggers under Pterodactyl and PUID/PGID would be silently ignored either
# way — see TROUBLESHOOTING.md.
# ---------------------------------------------------------------------------
export RECLAIMER_DEDICATED_HOST_NAME="${HOST_NAME:-}"
export RECLAIMER_DEDICATED_MAX_PLAYERS="${MAX_PLAYERS:-16}"
export RECLAIMER_DEDICATED_MIN_PLAYERS="${MIN_PLAYERS:-1}"
export RECLAIMER_DEDICATED_PASSWORD="${SERVER_PASSWORD:-}"
export RECLAIMER_DEDICATED_PLAYLIST="${PLAYLIST:-}"
case "${AUTO_UPDATE:-0}" in
    1|true) export RECLAIMER_DEDICATED_AUTO_UPDATE=true ;;
    *) export RECLAIMER_DEDICATED_AUTO_UPDATE=false ;;
esac
export RECLAIMER_DEDICATED_ANTI_CHEAT="${ANTI_CHEAT:-enforce}"
case "${BLOCK_VPN:-1}" in
    1|true) export RECLAIMER_DEDICATED_BLOCK_VPN=true ;;
    *) export RECLAIMER_DEDICATED_BLOCK_VPN=false ;;
esac

# SERVER_PUBLIC=true (default) means the server IS listed -> hidden=false.
if [ "${SERVER_PUBLIC:-1}" = "1" ] || [ "${SERVER_PUBLIC:-1}" = "true" ]; then
    export RECLAIMER_DEDICATED_HIDDEN=false
else
    export RECLAIMER_DEDICATED_HIDDEN=true
fi

# RCON is off unless explicitly enabled with a password. The existing
# Pterodactyl console bridge reaches it on container loopback; public
# gameplay uses UDP and does not require exposing the RCON TCP listener.
if { [ "${RCON_ENABLED:-0}" = "1" ] || [ "${RCON_ENABLED:-0}" = "true" ]; } && [ -n "${RCON_PASSWORD:-}" ]; then
    export RECLAIMER_DEDICATED_RCON_PASSWORD="${RCON_PASSWORD}"
    export RECLAIMER_DEDICATED_RCON_ADDRESS=127.0.0.1
else
    export RECLAIMER_DEDICATED_RCON_PASSWORD=""
fi

# A per-container local master is redundant (it would only ever list this
# one server) and would need its own Pterodactyl port allocation to be
# reachable externally; disable it. Per upstream docs, servers report to
# the public default masters "either way", independent of this setting.
export RECLAIMER_DEDICATED_MASTER_ENABLED=false

# UPnP only works with host networking, which Wings does not use.
export RECLAIMER_DEDICATED_UPNP=false

# Leave RECLAIMER_DEDICATED_PUBLIC_ADDRESS unset: outbound detection via
# api.ipify.org still reports the host's real public IP through Docker's
# NAT. Not yet verified end-to-end from behind Wings' bridge network on a
# live node — see TROUBLESHOOTING.md.

# ---------------------------------------------------------------------------
# 3. Generate / patch dedicated.toml (only touches the Pterodactyl-managed
#    sentinel block; everything else the admin edits by hand is preserved).
# ---------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    python3 /pterodactyl/configure.py
else
    echo "ERROR: python3 not found in image; cannot generate dedicated.toml." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Validate uploaded Halo 3 assets. Fails fast with a nonzero exit code
#    and an actionable message, rather than the infinite 15-second retry
#    loop upstream's own "dedicated check" performs for the same condition.
#    We deliberately diverge from upstream here: a crashed/failed Wings
#    server with a clear log is a better admin experience than a container
#    stuck indefinitely in "starting", and this check runs well before any
#    Wine/game process exists, so there is nothing stateful to clean up.
# ---------------------------------------------------------------------------
/pterodactyl/validate-assets.sh "$SERVER_DIR"

# ---------------------------------------------------------------------------
# 5. Initialize the Wine prefix for whichever UID we are actually running
#    as. Idempotent (upstream's prepare_prefix skips work once
#    $WINEPREFIX/system.reg exists), so this is a no-op after the first
#    start of a given server.
# ---------------------------------------------------------------------------
echo "Wine prefix: $WINEPREFIX"
echo "Runtime UID/GID: $(id -u):$(id -g)"
stat -c 'Wine prefix owner: %u:%g permissions: %a' "$WINEPREFIX"

if ! reclaimer-entrypoint prepare-prefix; then
    echo "ERROR: failed to initialize the Wine prefix (reclaimer-entrypoint prepare-prefix)." >&2
    echo "Check the log above for the underlying Wine error." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Hand off to the real upstream program, honoring Wings' $STARTUP
#    variable the same way Pterodactyl's own "Creating a Custom Docker
#    Image" guide's example entrypoint does. Falls back to this image's
#    CMD (["start"]) when run outside Wings (e.g. manual `docker run`,
#    tests/test-runtime-*.sh) where $STARTUP is never set.
# ---------------------------------------------------------------------------
STARTUP="${STARTUP:-$*}"
PARSED=$(echo "${STARTUP}" | sed -e 's/{{/${/g' -e 's/}}/}/g' | eval echo "$(cat -)")

if [ -z "$PARSED" ]; then
    echo "ERROR: no startup command available (neither \$STARTUP nor a CMD argument was set)." >&2
    exit 1
fi

echo "Starting Project Reclaimer dedicated server: $PARSED"
# shellcheck disable=SC2086
exec python3 /pterodactyl/console_bridge.py $PARSED

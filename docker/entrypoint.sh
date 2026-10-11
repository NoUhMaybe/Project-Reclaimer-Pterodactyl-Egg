#!/bin/bash
# Pterodactyl compatibility wrapper for the official Project Reclaimer image.
#
# Responsibilities (in order):
#   1. Adapt upstream's hardcoded /server and /cache paths onto Pterodactyl's
#      single persistent volume at /home/container, via symlinks, so data
#      survives container restarts without needing extra Docker volumes
#      (which Pterodactyl eggs cannot declare).
#   2. Translate egg variables into the upstream RECLAIMER_DEDICATED_* /
#      PUID / PGID environment variables.
#   3. Generate or patch dedicated.toml via configure.py.
#   4. Validate that required Halo 3 game assets have been uploaded.
#   5. Hand off to the image's own original startup command, inherited
#      automatically as "$@" because this Dockerfile never overrides CMD.
#
# This script intentionally never invents or hardcodes the upstream image's
# internal binary paths (see Dockerfile and TROUBLESHOOTING.md).

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
# 1. Persistent directory layout under /home/container, symlinked onto the
#    paths the upstream binary expects.
# ---------------------------------------------------------------------------
SERVER_DIR="$HOME/server"
CACHE_DIR="$HOME/.cache/reclaimer"

mkdir -p "$SERVER_DIR/game" "$SERVER_DIR/content/Maps" "$SERVER_DIR/content/Game Modes" \
         "$SERVER_DIR/content/Mods" "$SERVER_DIR/playlists" "$SERVER_DIR/data" "$CACHE_DIR"

if [ -e /server ] && [ ! -L /server ]; then
    # A real (non-symlink) /server from the base image layer; it can only
    # contain upstream's own baked-in (empty) scaffold, never user data,
    # because /home/container is the only path Wings persists across
    # restarts. Safe to replace with our symlink.
    rm -rf /server
fi
[ -L /server ] || ln -s "$SERVER_DIR" /server

if [ -e /cache ] && [ ! -L /cache ]; then
    rm -rf /cache
fi
[ -L /cache ] || ln -s "$CACHE_DIR" /cache

# ---------------------------------------------------------------------------
# 2. Translate egg variables to upstream environment variables.
# ---------------------------------------------------------------------------
# Wings always runs this container as the owner of the mounted volume
# (never literally "root"), so PUID/PGID are set to match the process's own
# identity, making any upstream chown/setuid-to-PUID logic a safe no-op.
export PUID="${PUID:-$(id -u)}"
export PGID="${PGID:-$(id -g)}"

export RECLAIMER_DEDICATED_HOST_NAME="${HOST_NAME:-}"
export RECLAIMER_DEDICATED_MAX_PLAYERS="${MAX_PLAYERS:-16}"
export RECLAIMER_DEDICATED_MIN_PLAYERS="${MIN_PLAYERS:-1}"
export RECLAIMER_DEDICATED_PASSWORD="${SERVER_PASSWORD:-}"
export RECLAIMER_DEDICATED_PLAYLIST="${PLAYLIST:-}"
export RECLAIMER_DEDICATED_AUTO_UPDATE="${AUTO_UPDATE:-false}"
export RECLAIMER_DEDICATED_ANTI_CHEAT="${ANTI_CHEAT:-enforce}"
export RECLAIMER_DEDICATED_BLOCK_VPN="${BLOCK_VPN:-true}"

# SERVER_PUBLIC=true (default) means the server IS listed -> hidden=false.
if [ "${SERVER_PUBLIC:-true}" = "true" ]; then
    export RECLAIMER_DEDICATED_HIDDEN=false
else
    export RECLAIMER_DEDICATED_HIDDEN=true
fi

# RCON is off unless explicitly enabled with a password. Wings uses bridge
# networking (never network_mode: host), so the console must listen on
# every interface to be reachable through the published allocation; it is
# still only reachable on the same TCP port as the game, which Pterodactyl
# firewalls to the allocation owner like any other port.
if [ "${RCON_ENABLED:-false}" = "true" ] && [ -n "${RCON_PASSWORD:-}" ]; then
    export RECLAIMER_DEDICATED_RCON_PASSWORD="${RCON_PASSWORD}"
    export RECLAIMER_DEDICATED_RCON_ADDRESS=0.0.0.0
else
    export RECLAIMER_DEDICATED_RCON_PASSWORD=""
fi

# A per-container local master is redundant (it would only ever list this
# one server) and would need its own Pterodactyl port allocation to be
# reachable externally; disable it. The server still reports itself to the
# public default masters over its own game port regardless of this setting.
export RECLAIMER_DEDICATED_MASTER_ENABLED=false

# UPnP only works with host networking, which Wings does not use.
export RECLAIMER_DEDICATED_UPNP=false

# Leave RECLAIMER_DEDICATED_PUBLIC_ADDRESS unset: outbound detection via
# api.ipify.org still reports the host's real public IP through Docker's
# NAT, which is what players need to connect to.

# ---------------------------------------------------------------------------
# 3. Generate / patch dedicated.toml (only touches the Pterodactyl-managed
#    sentinel block; everything else the admin edits by hand is preserved).
# ---------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    python3 /pterodactyl/configure.py
else
    echo "WARNING: python3 not found in image; dedicated.toml was not generated." >&2
    echo "Create $SERVER_DIR/dedicated.toml manually before starting." >&2
fi

# ---------------------------------------------------------------------------
# 4. Validate uploaded Halo 3 assets. Fails fast with an actionable message
#    rather than letting the server silently start without being joinable.
# ---------------------------------------------------------------------------
/pterodactyl/validate-assets.sh "$SERVER_DIR"

# ---------------------------------------------------------------------------
# 5. Hand off to the upstream image's own original command.
# ---------------------------------------------------------------------------
if [ "$#" -eq 0 ]; then
    echo "ERROR: no command was inherited from the base image's CMD." >&2
    echo "This indicates the upstream image changed its Dockerfile in a way" >&2
    echo "this wrapper does not expect. See TROUBLESHOOTING.md." >&2
    exit 1
fi

echo "Starting Project Reclaimer dedicated server (inherited command: $*)"
exec "$@"

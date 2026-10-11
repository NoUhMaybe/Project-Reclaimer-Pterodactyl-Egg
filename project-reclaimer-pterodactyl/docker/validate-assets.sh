#!/bin/bash
# Validate that required Halo 3 game assets have been uploaded by the admin
# before letting the server start. This script never downloads, modifies or
# deletes any file — it only reports what is missing, per the project's
# "do not redistribute Halo 3 assets" requirement.
#
# Usage: validate-assets.sh <server-dir>

set -uo pipefail

SERVER_DIR="${1:?usage: validate-assets.sh <server-dir>}"
GAME_DIR="$SERVER_DIR/game"

missing_required=0
warnings=0

check_required() {
    local path="$1" description="$2"
    if [ ! -e "$path" ]; then
        echo "MISSING (required): $description" >&2
        echo "  expected at: $path" >&2
        missing_required=1
    fi
}

check_optional() {
    local path="$1" description="$2"
    if [ ! -e "$path" ]; then
        echo "MISSING (optional): $description" >&2
        echo "  expected at: $path" >&2
        warnings=1
    fi
}

echo "-----------------------------------------------------------"
echo " Validating uploaded Halo 3 game assets in: $GAME_DIR"
echo "-----------------------------------------------------------"

if [ ! -d "$GAME_DIR" ]; then
    echo "ERROR: $GAME_DIR does not exist." >&2
    echo "Upload your Halo 3 game files via SFTP/File Manager before starting." >&2
    echo "See INSTALL.md 'Uploading Halo 3 game assets' for exactly what to copy." >&2
    exit 1
fi

check_required "$GAME_DIR/halo3/halo3.dll" \
    "halo3.dll (the Halo 3 game engine library from your MCC installation)"

check_required "$GAME_DIR/halo3/maps/shared.map" \
    "shared.map (required by every multiplayer map)"

check_optional "$GAME_DIR/halo3/maps/campaign.map" \
    "campaign.map (required for Forge's campaign vehicles/AI and campaign co-op)"

check_optional "$GAME_DIR/halo3/maps/040_voi.map" \
    "040_voi.map (required alongside campaign.map for Forge's campaign vehicles/AI)"

map_count=0
if [ -d "$GAME_DIR/halo3/maps" ]; then
    map_count=$(find "$GAME_DIR/halo3/maps" -maxdepth 1 -name '*.map' ! -name 'shared.map' ! -name 'campaign.map' ! -name '040_voi.map' | wc -l)
fi
if [ "$map_count" -eq 0 ]; then
    echo "WARNING: no playable multiplayer map files found alongside shared.map." >&2
    echo "  Copy at least one map (e.g. Guardian.map) into: $GAME_DIR/halo3/maps/" >&2
    warnings=1
fi

if [ "$missing_required" -ne 0 ]; then
    echo "-----------------------------------------------------------" >&2
    echo " Required game assets are missing. Refusing to start." >&2
    echo " This is not a bug: Project Reclaimer and this egg do not" >&2
    echo " redistribute Halo 3 files. Upload your own legally-owned copy" >&2
    echo " via SFTP or the Pterodactyl File Manager, then restart." >&2
    echo "-----------------------------------------------------------" >&2
    exit 1
fi

if [ "$warnings" -ne 0 ]; then
    echo "-----------------------------------------------------------"
    echo " Optional assets are missing (see warnings above). The server"
    echo " will still start, but some features (Forge campaign objects,"
    echo " campaign co-op, or any map you intended to host) may not work."
    echo "-----------------------------------------------------------"
fi

echo "Asset validation passed."
exit 0

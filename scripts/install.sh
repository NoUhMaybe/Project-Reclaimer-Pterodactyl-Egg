#!/bin/bash
# Project Reclaimer — Pterodactyl install script.
#
# Runs once per install/reinstall inside a throwaway installer container
# (ghcr.io/ptero-eggs/installers:debian), with /mnt/server bound to the
# server's real persistent directory. Anything NOT under /mnt/server here
# is discarded once this script exits; only /mnt/server survives into the
# runtime container as /home/container.
#
# This script never downloads or generates Halo 3 game files, and never
# touches dedicated.toml (that is generated idempotently by configure.py on
# every container start instead, see docker/entrypoint.sh) so that a
# reinstall never clobbers an admin's hand-edited configuration.

set -euo pipefail

echo "-----------------------------------------------------------"
echo " Project Reclaimer — Pterodactyl install script"
echo "-----------------------------------------------------------"

SERVER_DIR="/mnt/server/server"

if [ ! -d /mnt/server ]; then
    echo "ERROR: $SERVER_DIR does not exist (expected Pterodactyl install mount)." >&2
    exit 1
fi

cd "$SERVER_DIR"

echo "Creating persistent directory skeleton..."
mkdir -p \
    "$SERVER_DIR/game/halo3/maps" \
    "$SERVER_DIR/content/Maps" \
    "$SERVER_DIR/content/Game Modes" \
    "$SERVER_DIR/content/Mods" \
    "$SERVER_DIR/playlists" \
    "$SERVER_DIR/data"

# bans.json is shared/authoritative state; never overwrite an existing one
# on reinstall.
if [ ! -f "$SERVER_DIR/bans.json" ]; then
    echo '{"players": [], "ips": [], "vpn_allowed": []}' > "$SERVER_DIR/bans.json"
    echo "Created empty bans.json"
else
    echo "bans.json already exists, leaving it untouched"
fi

# A short, always-overwritable pointer file (not configuration, so safe to
# refresh on every install) explaining what the admin still needs to do.
cat > "$SERVER_DIR/UPLOAD_GAME_ASSETS_HERE.txt" <<'EOF'
Project Reclaimer requires your own legally-owned copy of Halo 3 from
Halo: The Master Chief Collection. No game files are included with this
egg or with Project Reclaimer itself.

Upload the following into this server's "server/game" folder via SFTP
or the Pterodactyl File Manager, preserving the folder structure shown:

  server/game/halo3/halo3.dll                     (required)
  server/game/halo3/maps/shared.map               (required)
  server/game/halo3/maps/<MapName>.map            (one per map you want to host)
  server/game/halo3/maps/campaign.map             (optional: Forge campaign vehicles/AI)
  server/game/halo3/maps/040_voi.map              (optional: Forge campaign vehicles/AI)

See INSTALL.md in the egg repository for the full, up to date list and
step-by-step instructions, including how to copy these files from a
Windows PC with the game installed using `project-reclaimer.exe dedicated
init --from`.

The server will refuse to start (with a clear error in the console) until
halo3.dll and shared.map are present.
EOF

echo "-----------------------------------------------------------"
echo " Directory skeleton ready under $SERVER_DIR"
echo " dedicated.toml will be generated automatically on first start."
echo " Remember to upload your Halo 3 game files before starting the"
echo " server — see UPLOAD_GAME_ASSETS_HERE.txt in the file manager."
echo "-----------------------------------------------------------"
echo "Installation completed."

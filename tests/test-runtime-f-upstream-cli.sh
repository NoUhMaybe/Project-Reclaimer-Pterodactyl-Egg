#!/bin/bash
# Real bundled 0.9.20 executable under Wine, disposable non-root storage.
# No game assets: prove command availability, version, parser and failure safety;
# successful playlist validation/authoring still requires live owned assets.
set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/lib/cleanup.sh
source "$SCRIPT_DIR/lib/cleanup.sh"
WORKDIR="$(mktemp -d)"
trap 'safe_rm_rf "$WORKDIR" "$IMAGE"' EXIT
mkdir -p "$WORKDIR/home-container/server" "$WORKDIR/home-container/.wine-prefix" "$WORKDIR/home-container/.cache/reclaimer"
docker run --rm --user root --entrypoint chown \
    -v "$WORKDIR/home-container:/target" "$IMAGE" -R 2002:2002 /target

docker run --rm -i --user 2002:2002 --entrypoint bash \
    -v "$WORKDIR/home-container:/home/container" "$IMAGE" -s <<'SCRIPT'
set -euo pipefail
test "$RECLAIMER_IMAGE_VERSION" = 0.9.20
# The image bundles a distinct build from the downloadable Windows release asset.
# Verified directly from the official .20 manifest's executable layer.
printf '%s  %s\n' 15c2b745e2c7dd1563a69f9fa09ba399ac3702eb3da200afa8d42d9a271f03d7 /opt/reclaimer/project-reclaimer.exe | sha256sum --check
reclaimer-entrypoint prepare-prefix
version=$(timeout 45 project-reclaimer --version | tr -d '\r')
test "$version" = 'project-reclaimer 0.9.20'
echo "Actual bundled executable: $version"
for command in 'playlist new' 'playlist show' content reload; do
    # Intentional splitting: these are fixed command words, never operator input.
    # shellcheck disable=SC2086
    timeout 30 dedicated $command --help > /tmp/native-help.txt
    grep -q -- '--config' /tmp/native-help.txt
done
cd /pterodactyl
python3 - <<'PY'
from pathlib import Path
from manager.native import NativeTools

root = Path('/home/container/server')
native = NativeTools(root)
assert native.version() == 'project-reclaimer 0.9.20'
candidate = {'version': 2, 'name': 'Probe', 'vote_seconds': 20,
             'games': [{'map': 'Guardian', 'game': 'Slayer'}] * 3}
try:
    native.validate_playlist(candidate)
except ValueError:
    pass  # Actual CLI must reject missing game assets, without touching active files.
else:
    raise AssertionError('Native validator accepted an asset-free server')
assert not (root / 'playlists').exists()
assert list((root / '.manager/staging').iterdir()) == []
print('Real native validation failed safely without assets; private staging cleaned.')
PY
SCRIPT
echo 'PASS: Test F - actual 0.9.20 bundled checksum/version, CLI availability and safe native failure under Wine.'

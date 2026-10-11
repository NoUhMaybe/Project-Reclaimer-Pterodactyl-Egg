#!/bin/bash
# Runtime test orchestrator.
#
# Runs Tests A, B, C and E (all automatable against a disposable Docker
# host, no game assets required) and then explicitly reports Test D as
# requiring manual execution — it is never silently skipped or claimed as
# passed.
#
# An earlier revision of this script tried to do all of this in one place
# and ended up asserting contradictory things (expecting the container to
# both exit on missing assets AND stay running) — see TROUBLESHOOTING.md
# and tests/test-runtime-a-missing-assets.sh / -b-configuration.sh /
# -c-nonroot-fs.sh / -d-full-startup.sh / -e-wine-prefix.sh for the
# corrected, separated tests.
#
# Usage:
#   IMAGE=project-reclaimer-pterodactyl:local ./tests/test-runtime.sh

set -euo pipefail

IMAGE="${IMAGE:?set IMAGE=<built image tag> before running this script}"
export IMAGE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failures=0

run_test() {
    local name="$1" script="$2"
    echo ""
    echo "=============================================================="
    echo " $name"
    echo "=============================================================="
    if bash "$SCRIPT_DIR/$script"; then
        echo "$name: PASS"
    else
        echo "$name: FAIL" >&2
        failures=$((failures + 1))
    fi
}

run_test "Test A — missing assets" test-runtime-a-missing-assets.sh
run_test "Test B — configuration generation" test-runtime-b-configuration.sh
run_test "Test C — non-root filesystem" test-runtime-c-nonroot-fs.sh
run_test "Test E — Wine prefix initialization and persistence" test-runtime-e-wine-prefix.sh

echo ""
echo "=============================================================="
echo " Test D — full startup with real Halo 3 assets"
echo "=============================================================="
echo "SKIPPED: requires your own legally obtained Halo 3 game files and is"
echo "never run automatically. This is NOT reported as passed. To run it"
echo "manually: GAME_DIR=/path/to/game IMAGE=$IMAGE $SCRIPT_DIR/test-runtime-d-full-startup.sh"
echo "See TROUBLESHOOTING.md 'What has and has not been tested' for exactly"
echo "what remains unverified without it."

echo ""
if [ "$failures" -ne 0 ]; then
    echo "RESULT: $failures automated test(s) failed."
    exit 1
fi
echo "RESULT: all automated tests (A, B, C, E) passed. Test D remains manual — see above."

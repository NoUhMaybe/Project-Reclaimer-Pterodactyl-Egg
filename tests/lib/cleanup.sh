#!/bin/bash
# Shared helper, sourced (not executed) by tests/test-runtime-*.sh.
#
# Docker-created files under a test's bind-mounted temp directory can end
# up owned by root (Test A/B, if the container runs with its default user)
# or by a deliberately different non-host UID (Test C, which must keep
# testing a specific non-root UID per its own design). A plain host-side
# `rm -rf` as whoever is running these scripts (e.g. the unprivileged
# "runner" user on GitHub-hosted Actions runners) can then fail with
# "Permission denied" and, left unhandled, make the whole test report
# failure even though the test itself already passed.
#
# safe_rm_rf() fixes this generically: try the normal, fast host-side
# removal first (works whenever the container ran as the caller's own
# UID); if that fails, fall back to removing the contents from inside a
# throwaway root container (root inside a standard, non-user-namespaced
# Docker container can always remove files regardless of which UID
# originally created them) before retrying the host-side removal.

# Refuses to touch anything that isn't clearly a disposable `mktemp -d`
# directory, so a bug elsewhere can never turn this into a wide `rm -rf`.
_runtime_test_path_is_safe_to_wipe() {
    local dir="$1"
    case "$dir" in
        "" | "/" | "/*") return 1 ;;
        "${TMPDIR:-/tmp}"/*) return 0 ;;
        /tmp/* | /var/folders/*) return 0 ;;
        *) return 1 ;;
    esac
}

# safe_rm_rf <dir> [helper-image]
#
# Cleanup-only: intentionally swallows its own failures (after exhausting
# both removal strategies) so that it never overwrites or masks the exit
# code of the actual test logic that ran before it. Callers must determine
# PASS/FAIL from the test itself *before* calling this.
safe_rm_rf() {
    local dir="$1" helper_image="${2:-}"

    [ -e "$dir" ] || return 0

    if ! _runtime_test_path_is_safe_to_wipe "$dir"; then
        echo "safe_rm_rf: refusing to remove suspicious path '$dir' (not under a temp dir)" >&2
        return 1
    fi

    if rm -rf -- "$dir" 2>/dev/null; then
        return 0
    fi

    if [ -n "$helper_image" ] && command -v docker >/dev/null 2>&1; then
        echo "==> host-side cleanup of $dir hit a permission error (expected if the" >&2
        echo "    container under test ran as root or a deliberately different non-host" >&2
        echo "    UID, e.g. Test C); retrying via a throwaway root container." >&2
        docker run --rm \
            --user root \
            --entrypoint sh \
            -v "$dir:/cleanup-target" \
            "$helper_image" \
            -c 'cd /cleanup-target && rm -rf -- * .[!.]* ..?* 2>/dev/null; exit 0' \
            >/dev/null 2>&1 || true
    fi

    if rm -rf -- "$dir" 2>/dev/null; then
        return 0
    fi

    echo "WARNING: could not fully remove $dir; it may still contain leftover" >&2
    echo "root-owned or non-host-UID files. Manual cleanup may require:" >&2
    echo "  sudo rm -rf '$dir'" >&2
    return 0
}

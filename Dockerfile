# Project Reclaimer — Pterodactyl compatibility image
#
# Architecture: "thin compatibility wrapper" (Approach B, see README.md).
# Builds FROM the official, unmodified upstream image and adapts only what
# Wings requires. See TROUBLESHOOTING.md "Verified upstream image metadata"
# for the exact Entrypoint/Cmd/User/WorkingDir/Env this was built against
# (inspected directly from the published image manifest+config, and from
# the actual reclaimer-entrypoint script extracted from its layer — not
# guessed).
#
# Verified facts driving this Dockerfile:
#   - Upstream's own ENTRYPOINT is ["/usr/bin/tini", "--", "reclaimer-entrypoint"]
#     with CMD ["start"]. "reclaimer-entrypoint" is a real, named script
#     installed at /usr/local/bin/reclaimer-entrypoint — not CMD. Replacing
#     ENTRYPOINT without accounting for this (as an earlier revision of this
#     Dockerfile did) silently drops the actual program to run; see
#     tests/test_dockerfile.py for a regression test against this mistake.
#   - Wings always runs server containers with an explicit, non-root
#     `--user <uid>:<gid>` (see TROUBLESHOOTING.md), regardless of the
#     image's own USER directive. The upstream entrypoint only drops
#     privileges / remaps PUID-PGID when it finds itself running AS root;
#     under Wings that code path never triggers, so PUID/PGID are inert.
#   - Deleting/replacing a directory entry needs write access to its PARENT
#     directory, not the entry itself. "/" and "/home/reclaimer" are
#     root-owned, so a non-root Wings UID can never symlink /server, /cache,
#     or the Wine prefix (/home/reclaimer/.wine) onto /home/container at
#     container *runtime* — only at *build time*, while this Dockerfile is
#     still running as root. That is what the RUN steps below do; the
#     entrypoint only ever needs to `mkdir -p` the symlink *targets* under
#     /home/container at runtime, which Wings always makes writable.

ARG RECLAIMER_VERSION=0.9.21
FROM ghcr.io/projectreclaimer/project-reclaimer-dedicated:${RECLAIMER_VERSION}
ARG RECLAIMER_VERSION
ENV RECLAIMER_IMAGE_VERSION=${RECLAIMER_VERSION}

LABEL maintainer="NoUhMaybe" \
      org.opencontainers.image.title="Project Reclaimer (Pterodactyl compatibility image)" \
      org.opencontainers.image.description="Pterodactyl-compatible wrapper around the official Project Reclaimer dedicated server image" \
      org.opencontainers.image.source="https://github.com/NoUhMaybe/Project-Reclaimer-Pterodactyl-Egg" \
      org.opencontainers.image.licenses="MIT" \
      io.pterodactyl.egg.upstream.entrypoint="/usr/bin/tini -- reclaimer-entrypoint" \
      io.pterodactyl.egg.upstream.cmd="start"

USER root

# Python 3 (any modern version — configure.py uses only stdlib re/pathlib,
# no tomllib or third-party dependency) is required by our wrapper scripts.
# Installed defensively in case the base image does not already provide it.
RUN set -eux; \
    if command -v python3 >/dev/null 2>&1; then \
        echo "python3 already present: $(python3 --version)"; \
    elif command -v apt-get >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*; \
    elif command -v apk >/dev/null 2>&1; then \
        apk add --no-cache python3; \
    else \
        echo "WARNING: no supported package manager found to install python3" >&2; \
    fi

# Replace upstream's fixed-path directories with symlinks onto Pterodactyl's
# single persistent volume (/home/container). Done here (build time, as
# root) rather than in the entrypoint, because removing/recreating these
# entries requires write access to their *parent* directories (/ and
# /home/reclaimer), which a non-root Wings-assigned UID never has at
# runtime — only their eventual *targets* under /home/container need to
# exist at runtime, and Wings always makes /home/container writable by
# whatever UID it runs the container as.
#
# This intentionally discards the Wine prefix upstream pre-built (baked for
# UID 1000, whoever "reclaimer" happened to be at image build time) because
# Wings' own container UID is not a fixed, predictable value (see
# TROUBLESHOOTING.md) — a prefix baked for one UID would not be readable by
# a differently-assigned UID on another Wings node. The entrypoint
# regenerates it fresh, as whatever UID Wings actually assigns, on each
# server's own first start (one-time cost, see CONFIGURATION.md).
#
# Also relaxes /home/reclaimer itself to 755: upstream's `useradd
# --create-home` leaves it 0700 (owner-only), which is fine for upstream's
# own use but means ANY other UID — not just Wings' assigned one, every
# UID except 1000 and root — gets "Permission denied" just traversing into
# it, even to lstat() the .wine symlink below; that failure is
# indistinguishable from the symlink not existing at all (see
# TROUBLESHOOTING.md "Verified upstream image metadata" for how this was
# confirmed directly from the image's own layer). 755 only grants
# traverse/read, never write — nothing needs to be written directly under
# /home/reclaimer, since Wine always resolves through the symlink to
# /home/container/.wine-prefix for actual I/O.
RUN rm -rf /server /cache /home/reclaimer/.wine \
    && ln -s /home/container/server /server \
    && ln -s /home/container/.cache/reclaimer /cache \
    && ln -s /home/container/.wine-prefix /home/reclaimer/.wine \
    && chmod 755 /home/reclaimer

# Required by every Pterodactyl egg image. Safe alongside upstream's own
# WINEPREFIX (an absolute path Wine always prefers over $HOME-relative
# lookups) and WORKDIR /server (now a symlink, and the entrypoint/upstream
# script both `cd` there explicitly regardless of the image's WORKDIR).
ENV USER=container HOME=/home/container
WORKDIR /home/container

COPY --chmod=755 docker/entrypoint.sh /pterodactyl/entrypoint.sh
COPY --chmod=755 docker/validate-assets.sh /pterodactyl/validate-assets.sh
COPY --chmod=644 docker/configure.py /pterodactyl/configure.py
COPY --chmod=644 docker/console_bridge.py /pterodactyl/console_bridge.py
COPY docker/manager /pterodactyl/manager

# tini stays PID 1 for correct signal forwarding/zombie reaping (matching
# upstream's own choice); our entrypoint does Pterodactyl-specific setup
# and then hands off to the real reclaimer-entrypoint program by name.
ENTRYPOINT ["/usr/bin/tini", "--", "/pterodactyl/entrypoint.sh"]
CMD ["start"]

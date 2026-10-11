# Project Reclaimer — Pterodactyl compatibility image
#
# Architecture: "thin compatibility wrapper" (Approach B, see README.md).
# We build FROM the official upstream image untouched and only add a small
# wrapper entrypoint that adapts the upstream filesystem layout
# (/server, /cache) to Pterodactyl's single persistent volume
# (/home/container), generates dedicated.toml from egg variables, and then
# hands control to the image's own original startup command.
#
# We deliberately do NOT reimplement or guess the upstream image's internal
# binary paths or launch logic: by setting ENTRYPOINT without setting CMD,
# Docker automatically inherits the base image's original CMD, which our
# entrypoint script receives as "$@" and executes last via `exec "$@"`.
# This keeps the egg compatible even if upstream changes its internal paths,
# as long as the image's ENTRYPOINT/CMD contract stays the same.
#
# UNVERIFIED ASSUMPTION (see TROUBLESHOOTING.md): the upstream image's
# source is closed, so its exact internal startup behavior when launched as
# a non-root UID (as Wings always enforces) has not been confirmed against
# a live container. Validate this with a real Wings node before production
# use.

ARG RECLAIMER_VERSION=0.9.13
FROM ghcr.io/projectreclaimer/project-reclaimer-dedicated:${RECLAIMER_VERSION}

LABEL maintainer="project-reclaimer-pterodactyl" \
      org.opencontainers.image.source="https://github.com/your-org/project-reclaimer-pterodactyl" \
      org.opencontainers.image.description="Pterodactyl-compatible wrapper around the official Project Reclaimer dedicated server image" \
      org.opencontainers.image.licenses="MIT"

# Required by every Pterodactyl egg image.
ENV USER=container HOME=/home/container
WORKDIR /home/container

# Python 3 (any modern version — configure.py uses only stdlib re/pathlib,
# no tomllib or third-party dependency) and bash are required by our
# wrapper scripts. Installed defensively in case the base image does not
# already provide a Python interpreter.
USER root
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

COPY --chmod=755 docker/entrypoint.sh /pterodactyl/entrypoint.sh
COPY --chmod=755 docker/validate-assets.sh /pterodactyl/validate-assets.sh
COPY --chmod=644 docker/configure.py /pterodactyl/configure.py

# Wings always runs the container as the UID/GID that owns the mounted
# /home/container volume, never as literally "root", regardless of this
# Dockerfile's own USER directive — this is left on root only so the build
# steps above (apt/apk) work; Wings overrides the runtime user itself.
ENTRYPOINT ["/pterodactyl/entrypoint.sh"]

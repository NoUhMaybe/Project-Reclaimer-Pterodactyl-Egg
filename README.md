# Project Reclaimer — Pterodactyl Egg

A [PTDL_v2](https://docs.pterodactyl.io/v1/guides/egg-creation/creating-custom-egg)
egg that runs [Project Reclaimer](https://projectreclaimer.dev/) — a
community-developed Halo 3 dedicated multiplayer server — under
[Pterodactyl](https://pterodactyl.io/) Panel 1.x / Wings 1.x.

> **Status: development prerelease with successful live Wings testing.**
> Image `v0.1.0-dev.3` was verified on an Ubuntu Wings node: game assets
> validated, Guardian Slayer match played to completion and automatically
> repeated, local player joined, Pterodactyl Console RCON commands succeeded,
> and clean Stop/Start worked. The current installation is also reported by
> its operator to support WAN connections and multiple players. This branch's
> new console manager requires a separate live regression run; public listing
> and independent fresh-install coverage remain separate checks.

## What this is

Project Reclaimer ships an official Docker image
(`ghcr.io/projectreclaimer/project-reclaimer-dedicated`) designed for
`docker compose`, with `network_mode: host` and a dedicated `/cache` volume.
Pterodactyl/Wings does not support host networking or extra per-server
volumes for a standard egg, and its working directory convention
(`/home/container`) differs from upstream's (`/server`, `/cache`).

This repository builds a **thin compatibility image** on top of the
official, unmodified upstream image, adapting only what Wings requires:

- build-time symlinks mapping `/server` and `/cache` into
  `/home/container` (Wings' single persistent volume) so data survives
  restarts without extra volumes,
- translation of Pterodactyl egg variables into upstream's own
  `RECLAIMER_DEDICATED_*` environment variable overrides (no invented
  configuration keys — every mapping below is verified against the
  [official hosting docs](https://projectreclaimer.dev/host)),
- a minimal, idempotent `dedicated.toml` generator for the two fields that
  have no environment-variable override (`name`, `port`),
- asset validation that checks for required Halo 3 files without ever
  downloading, bundling, or redistributing them.

We deliberately never rebuild Project Reclaimer from source, and never
reimplement its Wine/supervisor logic — see
[Architecture decision](#architecture-decision) below.

## Repository layout

```
.
├── egg-project-reclaimer.json          # the importable PTDL_v2 egg (generated, see tools/build_egg.py)
├── Dockerfile                          # thin wrapper FROM the official upstream image
├── docker/
│   ├── entrypoint.sh                   # baked into the image; adapts paths and starts supervised server
│   ├── console_bridge.py               # Pterodactyl stdin commands -> local RCON
│   ├── configure.py                    # dedicated.toml sentinel-block generator/patcher
│   └── validate-assets.sh              # checks for required Halo 3 files before start
├── scripts/
│   └── install.sh                      # Pterodactyl "Install Script" (runs in a separate installer container)
├── tools/
│   └── build_egg.py                    # regenerates egg-project-reclaimer.json from scripts/install.sh
├── config/
│   └── dedicated.toml.example          # annotated reference, not used directly at runtime
├── tests/
│   ├── lib/
│   │   └── cleanup.sh                  # shared safe_rm_rf() helper: removes root/other-UID-owned test artifacts reliably
│   ├── test_egg.py                     # unittest: structural/schema validation of the egg JSON
│   ├── test_config.py                  # unittest: configure.py unit + end-to-end tests
│   ├── test_dockerfile.py              # unittest: static + live regression tests for the upstream ENTRYPOINT/CMD contract
│   ├── test-runtime.sh                 # orchestrator: runs A/B/C/E, reports D as manual-only
│   ├── test-runtime-a-missing-assets.sh
│   ├── test-runtime-b-configuration.sh
│   ├── test-runtime-c-nonroot-fs.sh
│   ├── test-runtime-d-full-startup.sh  # requires your own Halo 3 assets; never run in CI
│   └── test-runtime-e-wine-prefix.sh   # Wine prefix init + persistence under a non-root UID; no game assets needed
├── .github/workflows/
│   ├── validate.yml                    # JSON/schema, unit tests, shellcheck, separate docker-build + docker-runtime-tests jobs
│   └── publish.yml                     # builds + pushes to GHCR — only on a version tag push or manual dispatch
├── README.md / INSTALL.md / CONFIGURATION.md / TROUBLESHOOTING.md
└── LICENSE
```

This deviates from a fully flat `scripts/{start,configure,validate-assets}.sh`
layout: those scripts are baked into the Docker image (under `docker/`) so
they are always present at a fixed path regardless of install/reinstall
history, rather than relying on the install script to place them in the
persistent volume.

## Architecture decision

Three approaches were evaluated, per the project brief:

| Approach | Description | Verdict |
| --- | --- | --- |
| A. Direct upstream image | Use `project-reclaimer-dedicated` unmodified in the egg | **Rejected.** Upstream expects `/server` + `/cache` (not `/home/container`) and its compose example uses `network_mode: host`, unavailable under Wings. Not importable without adaptation. |
| **B. Thin compatibility image** | Build `FROM` the upstream image, add only a small adaptation entrypoint | **Chosen.** Minimizes modification, preserves upstream's Wine/supervisor logic entirely, satisfies "do not rebuild from source". |
| C. Custom Wine-based image | Install Project Reclaimer into a generic Pterodactyl Wine yolk | **Rejected.** Project Reclaimer's source is closed; there is no public installer/package to install into a generic Wine image, only the prebuilt Docker image. |

### How upstream's internals were verified, not guessed

Project Reclaimer's Docker image *source repository* is not public, but the
image it *publishes* is, and its exact metadata and entrypoint script were
fetched directly from `ghcr.io` using the plain registry HTTP API (anonymous
token + manifest + config blob + one small layer — no `docker pull` or local
Docker daemon required; see `tests/test_dockerfile.py` for a regression test
that repeats this check automatically). This confirmed:

- Upstream's own `Entrypoint` is `["/usr/bin/tini", "--", "reclaimer-entrypoint"]`
  with `Cmd: ["start"]` — `reclaimer-entrypoint` is a real, named program
  installed at `/usr/local/bin/reclaimer-entrypoint`, **not** part of `Cmd`.
  An earlier revision of this Dockerfile replaced `ENTRYPOINT` and relied on
  Docker inheriting `CMD` alone (`["start"]`) as the program to run — that
  would have executed the literal, non-existent command `start`. This is
  fixed: the Dockerfile's `ENTRYPOINT` now names `reclaimer-entrypoint`
  explicitly, and `tests/test_dockerfile.py` guards against regressing this.
- Wings always runs server containers as an explicit, non-root `uid:gid`
  (confirmed from the `pterodactyl/wings` source, `environment/docker/container.go`),
  regardless of the image's own `USER` directive — and that UID is **not**
  guaranteed to be `988`; it is whatever UID Wings' own `useradd --system`
  happened to allocate on that specific node. Upstream's entrypoint only
  drops privileges to its baked-in `PUID`/`PGID` when it is already running
  as root, which never happens under Wings — so `/home/reclaimer/.wine` (the
  Wine prefix baked into the image for UID 1000 at build time) would belong
  to the wrong user on essentially every real Wings node. The Dockerfile
  replaces it with a symlink onto `/home/container`, and the entrypoint
  re-initializes a fresh prefix for whichever UID Wings actually assigns on
  each server's first boot (a one-time cost — see CONFIGURATION.md).

See [docker/entrypoint.sh](docker/entrypoint.sh) and
[TROUBLESHOOTING.md](TROUBLESHOOTING.md#verified-upstream-image-metadata) for
the full details, including the exact commands used to verify all of this.

One consequence of preserving upstream's real program unchanged: the egg's
**Startup Command** field is still largely informational rather than a
free-form shell command (it is honored via Pterodactyl's standard `$STARTUP`
mechanism, but there is only one correct value — `reclaimer-entrypoint
start` — since that is upstream's actual, verified entrypoint program, not a
placeholder).

## Quick start

See [INSTALL.md](INSTALL.md) for the full walkthrough. Summary:

1. Use the published versioned compatibility image or build your own.
2. Import [`egg-project-reclaimer.json`](egg-project-reclaimer.json) into a
   Nest in your Panel.
3. Verify the egg's Docker Image is a published tag (currently v0.1.0-dev.4 when released).
4. Create a server, set its variables, upload your own legally-owned Halo 3
   files, and start it.

### Building and publishing the image

The egg references `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.0-dev.4`
for the upcoming development prerelease. Previous development images are
already published to GHCR. For a normal installation, pull the published
tag; local builds are optional.

```bash
docker build -t project-reclaimer-pterodactyl:local .
```

The `RECLAIMER_VERSION` build arg pins the upstream base image tag (default
`0.9.13`, confirmed to exist via a live registry query against
`ghcr.io/projectreclaimer/project-reclaimer-dedicated` — see
[tests/test_dockerfile.py](tests/test_dockerfile.py), which re-checks this
automatically in CI):

```bash
docker build --build-arg RECLAIMER_VERSION=0.9.13 -t project-reclaimer-pterodactyl:0.9.13 .
```

Point your own server's egg Docker Image field at whatever you build/push —
Pterodactyl does not require the image to be on GHCR specifically; any
registry reachable from your Wings node(s) works, including a private one.

#### Publishing to GHCR

[`.github/workflows/publish.yml`](.github/workflows/publish.yml) builds and
pushes `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl` using the
repository's own `GITHUB_TOKEN` (no separate PAT/secret needed, scoped to
`packages: write`). It is **not** triggered by ordinary commits — only by:

- pushing a version tag matching `v*.*.*` (e.g. `git tag v0.1.0 && git push
  origin v0.1.0`) — pushes that tag as the image tag, and also `:latest` if
  the tag has no prerelease suffix (`v0.1.0-beta.1` does not get `:latest`);
  or
- running it manually from the Actions tab (`workflow_dispatch`), optionally
  overriding the upstream `RECLAIMER_VERSION` to pin and choosing whether to
  also push `:latest`.

The workflow runs the full unit test suite first and only builds/pushes if
that passes. It builds for `linux/amd64` only (matching the two Wings nodes
described in this project's deployment target) and attaches standard
`org.opencontainers.image.*` labels. No image has been pushed as part of
writing this egg — that remains a deliberate, manually-authorized step for
the repository owner.

CI (`.github/workflows/validate.yml`) separately builds the image on every
push/PR to catch Dockerfile errors and runs the automatable runtime tests
against it (see "Testing" below), but never pushes it anywhere.

## Testing

```bash
# Unit tests (JSON/schema validation, configure.py logic, upstream
# Entrypoint/Cmd regression checks against the live registry — ~1s, no
# Docker required):
python3 -m unittest discover -s tests -v

# Shell syntax checks (no Docker required):
bash -n docker/entrypoint.sh docker/validate-assets.sh scripts/install.sh

# ShellCheck (requires shellcheck installed locally, or rely on CI):
shellcheck docker/*.sh scripts/*.sh tests/*.sh

# Build the image (requires Docker):
docker build -t project-reclaimer-pterodactyl:local .

# Runtime integration tests A/B/C (requires Docker; no game assets needed):
IMAGE=project-reclaimer-pterodactyl:local tests/test-runtime.sh

# Test D — full startup (requires Docker AND your own legally obtained
# Halo 3 files; see the script for exactly what it does and does not verify):
GAME_DIR=/path/to/your/game IMAGE=project-reclaimer-pterodactyl:local \
    tests/test-runtime-d-full-startup.sh
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#what-has-and-has-not-been-tested)
for exactly which of these have actually been run and with what results.

## Resource recommendations

Based on upstream's own measurements (per-server, not per-machine):

| Scenario | CPU | Memory | Storage |
| --- | --- | --- | --- |
| Small private game (≤8 players) | 0.5 core | 1 GB | 10 GB |
| Standard multiplayer (16–32 players) | 1 core | 2 GB | 15 GB |
| Large community server (63+ players) | 1–2 cores | 3 GB | 20 GB |
| Multiple instances on one node | 1 core **each** | 2–3 GB **each** | 15–20 GB **each**, isolated storage per instance |

Upstream reports ~85 MB / <0.1 core idle, ~0.6–0.9 GB / ~0.25–1 core during
a full 63-player game, with a brief spike to ~1.4 GB while a map loads.
Storage scales with how many maps you upload (~1.5 GB for one map, ~5.5 GB
for the full multiplayer map set, +~4 GB more for the full campaign).

## Upstream references used

- Pterodactyl: [Creating a Custom Egg](https://docs.pterodactyl.io/v1/guides/egg-creation/creating-custom-egg), [Egg Docker Images](https://docs.pterodactyl.io/v1/guides/egg-creation/egg-docker-images), [Egg Config Parser](https://docs.pterodactyl.io/v1/guides/egg-creation/egg-config-parser), [Egg Variables](https://docs.pterodactyl.io/v1/guides/egg-creation/egg-variables), [Egg Install Script](https://docs.pterodactyl.io/v1/guides/egg-creation/egg-install-script), [Creating a Custom Image](https://docs.pterodactyl.io/v1/guides/egg-creation/creating-custom-image)
- Pterodactyl Wings source (`pterodactyl/wings`, `develop` branch): `config/config.go` (`EnsurePterodactylUser`, `System.User`) and `environment/docker/container.go` (`Create()`'s `conf.User` assignment) — used to verify how Wings assigns the container's runtime UID/GID, not assumed.
- Project Reclaimer: [Host a dedicated server](https://projectreclaimer.dev/host), [projectreclaimer.dev](https://projectreclaimer.dev/), published `compose.yaml` / `compose.single.yaml` / `env.example`
- The published `ghcr.io/projectreclaimer/project-reclaimer-dedicated:0.9.13` image itself: manifest, image config, and the `reclaimer-entrypoint` script extracted from its own layer, fetched directly via the registry HTTP API (see `tests/test_dockerfile.py`).
- [ProjectReclaimer/project-reclaimer-releases](https://github.com/ProjectReclaimer/project-reclaimer-releases) — official release repository referenced for version numbering context.
- Reference eggs: [pterodactyl/game-eggs](https://github.com/pterodactyl/game-eggs) (Icarus dedicated egg), [pterodactyl/yolks](https://github.com/pterodactyl/yolks)

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full list of unresolved
and unverified items that remain before this can be called production-ready.

## Interactive administration from Pterodactyl

Build this branch's wrapper image to include the console manager, then type
`menu` (also `manager` or `console help`) in the existing **Console** tab.
Navigate eight numbered categories for live games, playlists, voting, players,
content/mods, configuration, diagnostics and help. `exit` returns to raw RCON
without ending the match. No TTY, additional web server or Panel change is used.

Playlists can be created, edited, validated, copied, activated and restored from
backups entirely through console input. Persistent operations use a separate
filesystem backend; live actions use local RCON. Explicit manager overrides win
over Startup defaults at the next start and can be reset through the menu.
The upstream image stays pinned to **0.9.13**; persistent changes require restart.

See [CONSOLE-MANAGER.md](CONSOLE-MANAGER.md) for workflows/security/rollback,
[CAPABILITIES.md](CAPABILITIES.md) for version gates and testing limits,
[ARCHITECTURE.md](ARCHITECTURE.md) for process/backend boundaries, and
[WINGS-VALIDATION.md](WINGS-VALIDATION.md) for the required live acceptance run.

With `RCON_ENABLED=true` and a strong `RCON_PASSWORD`, the existing web
Console tab accepts `help`, `maps`, `modes`, `players`,
`load Valhalla Slayer`, `nextmap Guardian Slayer`, and other documented
Project Reclaimer RCON commands. The console bridge binds RCON to container
loopback (`127.0.0.1`), not the public TCP interface. Use UDP port forwarding
for game clients. See [CONFIGURATION.md](CONFIGURATION.md#rcon-and-the-interactive-pterodactyl-console).

## Live test status

- **Verified:** non-root startup, persistent Wine prefix, game assets,
  complete Guardian Slayer match and automatic next game, LAN client,
  live RCON commands, graceful Stop and Start on `v0.1.0-dev.3`.
- **Operator-reported current regression baseline:** multiple simultaneous
  players and WAN connectivity also work. Preserve these with the manager.
- **This branch:** automated menu/backend tests and an official 0.9.13 CLI test
  against a loopback mock service; actual manager gameplay remains unverified
  until the Wings checklist is completed. No new image has been published.
- **Other remaining checks:** public browser listing and independent fresh install.
- **Assets:** never included or redistributed. Copy licensed Halo 3 files
  into `server/game/halo3/` in the Pterodactyl File Manager.

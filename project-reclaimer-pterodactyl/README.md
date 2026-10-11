# Project Reclaimer — Pterodactyl Egg

A [PTDL_v2](https://docs.pterodactyl.io/v1/guides/egg-creation/creating-custom-egg)
egg that runs [Project Reclaimer](https://projectreclaimer.dev/) — a
community-developed Halo 3 dedicated multiplayer server — under
[Pterodactyl](https://pterodactyl.io/) Panel 1.x / Wings 1.x.

> **Status: implemented and statically validated, not yet live-tested.**
> Docker was not available in the environment this egg was built in, so the
> Dockerfile/image has not been built or run against a real Wings node. See
> [TROUBLESHOOTING.md](TROUBLESHOOTING.md#what-has-and-has-not-been-tested)
> for exactly what has and has not been verified before you rely on this in
> production.

## What this is

Project Reclaimer ships an official Docker image
(`ghcr.io/projectreclaimer/project-reclaimer-dedicated`) designed for
`docker compose`, with `network_mode: host` and a dedicated `/cache` volume.
Pterodactyl/Wings does not support host networking or extra per-server
volumes for a standard egg, and its working directory convention
(`/home/container`) differs from upstream's (`/server`, `/cache`).

This repository builds a **thin compatibility image** on top of the
official, unmodified upstream image, adapting only what Wings requires:

- a wrapper entrypoint that symlinks `/server` and `/cache` onto
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
project-reclaimer-pterodactyl/
├── egg-project-reclaimer.json   # the importable PTDL_v2 egg (generated, see tools/build_egg.py)
├── Dockerfile                   # thin wrapper FROM the official upstream image
├── docker/
│   ├── entrypoint.sh            # baked into the image; adapts paths, generates config, hands off to upstream
│   ├── configure.py             # dedicated.toml sentinel-block generator/patcher
│   └── validate-assets.sh       # checks for required Halo 3 files before start
├── scripts/
│   └── install.sh               # Pterodactyl "Install Script" (runs in a separate installer container)
├── tools/
│   └── build_egg.py             # regenerates egg-project-reclaimer.json from scripts/install.sh
├── config/
│   └── dedicated.toml.example   # annotated reference, not used directly at runtime
├── tests/
│   ├── test_egg.py              # structural/schema validation of the egg JSON
│   ├── test_config.py           # unit tests for configure.py
│   └── test-runtime.sh          # manual/live smoke test (requires Docker + real game assets)
├── .github/workflows/validate.yml
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

### How the wrapper avoids guessing upstream's internals

Project Reclaimer's Docker image source is **not public** ("the source stays
private for now" — projectreclaimer.dev), so this egg cannot know upstream's
exact internal binary paths or entrypoint script. The Dockerfile sets a new
`ENTRYPOINT` but never sets `CMD`, so Docker automatically inherits the
upstream image's original `CMD` and passes it to our entrypoint as `"$@"`.
Our entrypoint does its adaptation work and finishes with `exec "$@"`,
running whatever upstream's own startup command actually is — without this
repository ever needing to hardcode it. See
[docker/entrypoint.sh](docker/entrypoint.sh) for the full reasoning.

One consequence: the egg's **Startup Command** field is not functionally
used (upstream's own command does not read Pterodactyl's `STARTUP`
variable). It is set to a self-documenting placeholder. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Quick start

See [INSTALL.md](INSTALL.md) for the full walkthrough. Summary:

1. Build and push the compatibility image (see below), or point the egg at
   your own registry.
2. Import [`egg-project-reclaimer.json`](egg-project-reclaimer.json) into a
   Nest in your Panel.
3. Edit the egg's Docker Image to your published image.
4. Create a server, set its variables, upload your own legally-owned Halo 3
   files, and start it.

### Building and publishing the image

```bash
docker build -t ghcr.io/YOUR_ORG/project-reclaimer-pterodactyl:latest .
docker push ghcr.io/YOUR_ORG/project-reclaimer-pterodactyl:latest
```

The `RECLAIMER_VERSION` build arg pins the upstream base image tag
(default `0.9.13` at the time this was written — **verify this tag still
exists** at `ghcr.io/projectreclaimer/project-reclaimer-dedicated` before
building, since it could not be confirmed with a live `docker pull` in the
environment this egg was authored in):

```bash
docker build --build-arg RECLAIMER_VERSION=0.9.13 -t ghcr.io/YOUR_ORG/project-reclaimer-pterodactyl:0.9.13 .
```

CI (`.github/workflows/validate.yml`) builds the image to catch Dockerfile
errors but never pushes it automatically, per the project's security
requirements around unattended publishing.

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
- Project Reclaimer: [Host a dedicated server](https://projectreclaimer.dev/host), [projectreclaimer.dev](https://projectreclaimer.dev/), published `compose.yaml` / `compose.single.yaml` / `env.example`
- Reference eggs: [pterodactyl/game-eggs](https://github.com/pterodactyl/game-eggs) (Icarus dedicated egg), [pterodactyl/yolks](https://github.com/pterodactyl/yolks)

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full list of unresolved
and unverified items that remain before this can be called production-ready.

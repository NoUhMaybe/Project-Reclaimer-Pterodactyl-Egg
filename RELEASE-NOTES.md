# Project Reclaimer Pterodactyl Egg v0.1.2 — Reclaimer v0.9.20

Prepared maintenance notes; v0.1.2 has not been published by this repair task.
The candidate uses a new patch version while preserving the earlier v0.1.1 Git
tag and image. See RELEASING.md for the approved publication procedure.

| Component | Version |
| --- | --- |
| Pterodactyl Egg | v0.1.2 (prepared candidate) |
| Project Reclaimer Dedicated Server | v0.9.20 |
| Required Project Reclaimer Client | v0.9.20 |
| Architecture | linux/amd64 |

- The installer creates the server directory before entering it, allowing a
  genuinely empty persistent mount to initialize. Reinstallation preserves
  uploaded assets, bans, playlists, administrator configuration and manager data.
- A single VERSION file drives the egg's default image. Generation is repeatable
  and preflight rejects stale JSON, mismatched tags, unsupported upstream pins
  and any existing versioned image.
- Publishing runs unit, installer, shell and container checks before pushing the
  tested image. A separate workflow attaches validated JSON to an existing release
  without creating the release or replacing assets.
- Startup variables, RCON, Console Manager and graceful Stop behavior are retained.

Download the validated egg JSON attached to the final release and import it into
a test Nest. Users must supply legally obtained Halo 3 (MCC) assets beneath
server/game/halo3/. No Halo assets or credentials are included in the egg.
Client and server Project Reclaimer versions must match exactly. Optional mod
compatibility and live gameplay effects still need the documented Wings checks;
automated packaging tests do not establish those results.

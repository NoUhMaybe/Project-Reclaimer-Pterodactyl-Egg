# Console manager compatibility matrix

This branch pins **0.9.20**. The original `feature/console-manager` branch and
`console-manager-pr5-test.1` image retain 0.9.13 for rollback. Build-version
gates disable unknown/nonrelease tags; raw RCON remains available. Diagnostics
reports the actual executable separately from the pin. Automatic updates remain
disabled by default; explicit existing operator choices are preserved. Clients
must match the server's exact Project Reclaimer version.

## Evidence and limits

Checked October 18, 2026 against the [hosting guide](https://projectreclaimer.dev/host),
[latest release](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/latest),
notes for [0.9.15](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.15),
[0.9.16](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.16),
[0.9.17](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.17),
[0.9.18](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.18),
[0.9.19](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.19)
and [0.9.20](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.20),
and their versioned RCON.md release assets (example:
[0.9.20 RCON](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/download/v0.9.20/RCON.md)).
The official 0.9.14 release API returned **404** and its versioned reference was
unavailable. The guide attributes friendly fire to 0.9.14; that attribution is
marked below rather than claiming an unavailable artifact was verified.

Actual official Windows binaries, checksum verified:

| Version | Dedicated executable SHA256 | Verified without game assets |
| --- | --- | --- |
| .13 | `afe11ddc1bd57b451f668e820d4236c1eea44798fff365eecd680d6dc8122a91` | Version, help, structured RCON arguments against loopback fixture |
| .20 | `e0d0861b265109cd623e2c991b63c60f08512bca2ae2bc028cb0af996c7bfe3d` | Above plus playlist/content/reload help, new TOML fields parsing, invalid camera rejection, validation failing safely without assets |
| .20 image bundle | `15c2b745e2c7dd1563a69f9fa09ba399ac3702eb3da200afa8d42d9a271f03d7` | Distinct upstream build extracted from the official image layer; actual --version is .20; same CLI/protocol/parser probes |

CI Test F also runs the actual bundled binary under Wine as a non-root UID,
checking checksum/version and native CLI availability. Successful native
authoring/validation requires owned game assets and is **not** established by
mocks or missing-asset tests. Engine effects, LAN/WAN and multiplayer await
[Wings validation](WINGS-VALIDATION.md). See [the image audit](UPSTREAM-0.9.20.md).

## Per-version availability

`R` = documented RCON; `C` = local upstream CLI; `F` = persistent files;
`S` = restart; `A` = automatic engine improvement; `—` = absent; `?` = .14
artifact unavailable. Intermediate-version support comes from versioned docs,
not execution of every historical binary. Actual binaries checked: .13 and .20.

| Functionality | .13 | .14 | .15 | .16 | .17 | .18 | .19 | .20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Maps/modes/status/next game/match control/votes/players/moderation | R | ? | R | R | R | R | R | R |
| Version-2 playlists, Python editor, manual content/mods | F/S | ? | F/S | F/S | F/S | F + reload/S | same | same |
| Native playlist new/show/list, content | — | ? | C | C | C | C | C | C |
| Friendly fire | — | F/S (guide) | F/S | F/S | F/S | F + reload, next game | same | same |
| Welcome, independent voice scopes | — | ? | F/S | F/S | F/S | F + reload | same | same |
| Admin list/add/remove, kick pardon | — | ? | — | R | R | R | R | R |
| Campaign trust_player_games | — | ? | — | F/S | F/S | F + reload | same | same |
| Reduced idle/lobby CPU, shared gameplay improvements | — | ? | — | — | A | A | A | A |
| Config/content reload and reload control events | — | ? | — | — | — | R/C + F | same | same |
| Character-pack configuration | — | ? | — | — | — | F, idle S | F, expanded packs | same |
| Expanded ODST co-op/Firefight, dedicated crash fixes | — | ? | — | — | — | — | A, owned assets | same |
| Server camera policy | — | ? | — | — | — | — | — | F + reload, next game |

The menu/session/process architecture is independent of these engine features.
No client-only Theater, renderer, input or appearance UI was added. Character-pack
and campaign/ODST authoring remain administrator-file operations; this egg's
asset preflight and guided gameplay scope remain Halo 3.

## 0.9.20 operations and timing

| Operation | Backend | Application timing / test evidence |
| --- | --- | --- |
| Maps/modes/load, nextmap, endround/endgame | RCON | Engine transition/next lobby; acceptance differs from completion. Real structured transport, menu tests; gameplay pending |
| Votes, players, say/tell, kick/ban/unban/mute/team/VPN | RCON | Runtime, engine prerequisites/shared ban-list scope apply; existing regression tests, live pending |
| Admins/add/remove, pardon | RCON admins/admin/pardon | Runtime, engine-managed persistence; .20 reference/stable-ID tests, live pending |
| Playlist create/edit/copy/restore | Python files + staged native playlist show | Atomic save; active files may auto-reload from next vote. Paths/conflicts/backups tested; native success with assets pending |
| Bulk authoring | Staged native playlist new | Private draft until confirmed Save; arguments/draft tests, actual positive authoring pending |
| Native content discovery | dedicated content --config <private config> [search] | Read-only installed inventory, text output (no invented JSON flag); real help and UI tests, asset inventory pending |
| Playlist activation / setting edit | .manager/overrides.json v1 | Pending until Configuration 7 or startup generates TOML; legacy state/Startup precedence tested |
| Apply/reload | Native-validated atomic TOML, then independent RCON reload | Actual server timing reply plus optional reload/reload_applied events; failed candidate writes nothing; rejected reply not called success |
| name/host_name/password/player limits/ping/load_timeout/welcome/admins/votes/voice/text/mod sharing/trust | Persistent TOML + reload | Immediate when confirmed, except name changing data folder needs idle restart; new field parsing verified, live effects pending |
| friendly_fire/team_changing/camera | Persistent TOML + reload | Next multiplayer game; campaign/ODST game settings can idle-restart; real camera enum/parser and UI timing tests |
| Ports/RCON, hidden/chat_log/block_vpn/anti_cheat, data-folder rename, content type/customization | Startup/admin TOML + reload | Idle restart or explicit container restart; engine timing from guide, no forced restart |
| Mod upload/replacement/enable/disable | Manual upload, content/disabled-mods.json | Restart required; atomic switch/unknown-field preservation tests, engine compatibility pending |
| Diagnostics | Executable --version, image pin, RCON/files | Snapshot; reports executable/pin mismatch, never invents individual client versions |
| Menu/raw return, Stop, unexpected child exit | Existing bridge | Portable menu and Linux process-group tests; live regression pending |

Camera values: `first_person`, `player_choice`, `third_person`. On-foot multiplayer
policy; modes built around third person (including UNSC vs Covenant classes) and
vehicle views retain their own cameras. Campaign co-op and Firefight are unaffected.
Saving a setting never proves live application. Upstream `auto_reload` defaults to
true from .18, so direct playlist/admin-file edits may independently reload; the
manager does not suppress that existing policy.

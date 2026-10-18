# Console manager compatibility matrix

The Dockerfile remains pinned to **0.9.13**. No upgrade is necessary for this
implementation, and the existing published image is the rollback option.
`RECLAIMER_IMAGE_VERSION` records the build argument; it is not proof of the
runtime version when upstream auto-update is enabled. Gates use the build version
conservatively, and unknown/nonrelease build tags disable guided runtime features.
Raw RCON remains available for explicit operator use outside the manager.

Evidence checked October 18, 2026:

- [Official hosting guide](https://projectreclaimer.dev/host), including its
  playlist reference, environment precedence, content layout and version notes.
- [0.9.13 release](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.13)
  and its [versioned RCON reference](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/download/v0.9.13/RCON.md).
- Actual official 0.9.13 dedicated executable `--help`, `dedicated --help`,
  `dedicated rcon --help`; its dedicated subcommands contain **no** `playlist`,
  `content` or `reload`. Binary SHA256:
  `afe11ddc1bd57b451f668e820d4236c1eea44798fff365eecd680d6dc8122a91`.
- Actual CLI against a loopback mock WebSocket endpoint, verifying structured
  argument transport and JSON data output without game assets.

“Mock” below means automated menu/backend tests, not a live Halo engine test.
All gameplay effects of this change require the [Wings checklist](WINGS-VALIDATION.md).

| Feature | Upstream requirement | Mechanism | Live | File changes | Restart | Implementation / testing |
| --- | --- | --- | --- | --- | --- | --- |
| Menu/navigation/raw return | Wrapper | Existing bridge `menu`, `manager`, `console help` | Yes | No | No | Implemented; portable and Linux-only supervisor tests |
| Status/current game/round/count | 0.9.13 documented | RCON `status` | Yes | No | No | Implemented; mock JSON/empty states |
| Maps/modes/saved variants | 0.8.14+; 0.9.13 confirmed | RCON `maps`, `modes`, `entries.reference` | Yes | Read only | New uploads: yes on 0.9.13 | Implemented; versioned schema fixture |
| Change map/mode/both | 0.8.14+ | RCON `map`, `mode`, `load` | Queued lobby transition; active game ends | No | No | Implemented with confirmation; mock acceptance/status/event failures |
| Next game/override inspection | 0.8.14+ | RCON `nextmap` | Next lobby, current game continues | No | No | Implemented; mock selection/rotation |
| Round/game end | 0.9.13 documented | RCON `endround`, `endgame` | Yes | No | No | Implemented with confirmation; mock cancellation |
| Completion events | 0.9.13 confirmed | Local CLI `rcon --json --watch`, `control` | Best effort stream | No | No | Implemented; parser/retention tests; real event/game behavior unverified |
| Playlist ballots/moderation votes | 0.8.14+ | RCON `vote`, `startvote`, `passvote`, `cancelvote` | Prerequisites apply | No | Active rotation must already be loaded | Implemented; mock phase/count/rotation/errors |
| Players, teams, telemetry | 0.9.13 documented | RCON `players` | Yes | No | No | Implemented; missing fields displayed honestly; mock IDs/empty states |
| Global/private announcements | 0.9.13 documented | RCON `say`, `tell` | Yes | Chat logs upstream | No | Implemented with confirmation; stable target selection |
| Kick / timed or permanent bans | 0.9.13 documented | RCON `kick`, `ban` | Yes | Engine writes ban list for bans | No | Implemented; mock stable-ID/timed-ban command assertions |
| Bans/unban | 0.9.13 documented | RCON `bans`, `unban` | Yes | Engine updates linked entries | No | Implemented with confirmation; engine decides ambiguous matches |
| Mute/unmute | 0.9.13 documented | RCON `mute`, `unmute` | Yes | No persistent menu file | Cleared by restart | Implemented; duration also available through raw command |
| Team move/shuffle/redistribution | Team move 0.9.0+ | RCON `team`, `shuffle`, `teamcount` | Requires valid teams/round | No | No | Implemented with confirmation; engine authority for team constraints |
| VPN allowlist | 0.9.2+ | RCON `vpn`, `vpnallow`, `vpnrevoke` | Shared ban-list scope | Engine persists allowances | No | Implemented with confirmation; menu command construction |
| Admin list/add/remove; kick pardon | **0.9.16+** | RCON `admins`, `admin`, `pardon` | On compatible builds | Engine-managed | No | Visible but gated on 0.9.13; gate tests; newer engine unverified |
| Playlist create/edit/copy/import/delete | Version 2 on 0.9.13 | Local Python JSON editor under `server/playlists` | Edits do not update loaded engine | Yes, atomic + backup | 0.9.13: yes | Implemented; full menu create/edit/save/duplicate/restore tests |
| Playlist structure/content validation | 0.9.13 local fallback | Injected running inventories + bounded reads | Validation only | Read only | No | Implemented; conservative, not full option or dependency validation |
| Official playlist/content CLI | **0.9.15+** | `dedicated playlist show`; other authoring remains local | No runtime effect | Validator reads files | No | Existing-file validator gated; never called on 0.9.13; newer binary unverified |
| Persistent playlist activation | Wrapper + upstream per-server precedence | `.manager/overrides.json` -> managed TOML at boot | No | Yes | **Yes** | Implemented; tested across repeated configure runs and conflicting Startup values |
| Mod packages/metadata inspection | Existing content directories | Local bounded traversal | Shows disk state | Read only | No | Implemented; metadata shown without inferring compatibility |
| Manual mod upload | 0.9.13 layout | File Manager/SFTP -> `content/Mods` | No | Uploaded by operator | **Yes** | Documented; no Steam/SteamCMD downloader |
| Mod enable/disable | Official documented packages list | `content/disabled-mods.json` | No | Atomic + backup | **Yes** | Implemented; preserve unknown fields; live engine switch unverified |
| Custom vote images | **0.9.13+** | `preview_image`, `content/Images` | Next loaded rotation | Yes, manual upload | 0.9.13: yes | Implemented signature/size/path validation; no image decoder |
| Live server name/ping | Name 0.8.14+, ping 0.9.2+ | RCON `servername`, `maxping` | Yes | No | Lost at restart | Implemented; separated from persistence |
| Guided persistent server settings | 0.9.13 fields only | Manager overrides -> managed `[[server]]` | No | Atomic + backup | **Yes** | Implemented; scalar/range/policy checks; engine semantics need Wings |
| Join/RCON passwords, ports, paths | Existing egg/upstream | Startup/admin files | Static guided policy | Startup files/env | Yes | Password entry excluded from menu due to Panel echo/history; raw commands preserved |
| Friendly fire policy | **0.9.14+** | `friendly_fire` | Newer version behavior | TOML | 0.9.13 unsupported | Explained, not offered as a working 0.9.13 setting |
| Welcome / independent voice scopes | **0.9.15+** | `welcome`, `voice_global/team/proximity` | Newer version behavior | TOML | 0.9.13 unsupported | Explained; no unsupported fields generated |
| Character mod settings | **0.9.18+** | `customization`, related settings | Newer version behavior | TOML | Idle restart in newer versions | Explained; unavailable on 0.9.13 |
| Config/content live reload | **0.9.18+** | RCON `reload` | Immediate/next vote/idle restart by upstream | Changes read from files | Version/setting dependent | Raw escape gated; menu persistence intentionally next-start; no automatic restart/reload |
| Health/log diagnostics | Wrapper | RCON + bounded asset/prefix/log reads | Snapshot | Read only | No | Implemented; presence/last-request checks, filtered excerpts |
| Non-root, Wine, WAN, multiplayer, Stop/Start | Existing egg regression baseline | Unchanged upstream launch/group/output path | Yes | Persistent volume retained | Existing behavior | Existing user-reported working baseline; this change's live regression run pending |

The current guide documents releases newer than the image pin. In particular,
0.9.18 reload timing must not be attributed to 0.9.13. This manager never restarts
a server on its own. The previous image and unmodified Startup settings remain
available for rollback; see [the console guide](CONSOLE-MANAGER.md#diagnostics-security-and-rollback).

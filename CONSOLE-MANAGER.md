# Pterodactyl console manager

The existing **Console** tab is the entire interface. This extends
`docker/console_bridge.py`; there is no web service, extra port, Panel change,
TTY, keyboard listener, or terminal UI dependency. Build this branch's wrapper
image to include the manager; the egg's existing published image does not
magically gain new source files. Publication/deployment require separate approval.

## Start and navigate

Enable **RCON** and set an 8-128 character **RCON Password** in Startup, then
restart. RCON stays on `127.0.0.1` **inside** the container; UDP gameplay and WAN
allocations are unchanged. Submit each line in the normal console command field.
Offline playlist listing, editing an existing draft's basic fields, persistent
settings and content browsing remain available with RCON disabled. Live pickers
and runtime operations need working RCON. On .20 native content discovery and
playlist validation/saving can operate without RCON when owned assets are installed.

```text
> menu
PROJECT RECLAIMER CONTROL CENTER
[1] Live Game Control
[2] Playlist Manager
[3] Voting Manager
[4] Player Management
[5] Maps, Modes & Mods
[6] Server Configuration
[7] Diagnostics & Logs
[8] Help & Command Reference
[0] Exit to RCON console
Select option >
> 1
LIVE GAME CONTROL
...
> 1
Status      | Value
------------+---------
map         | Guardian
mode        | Slayer
phase       | playing
players     | 4
...
> exit
[manager] Returned to RCON console. Server continues running.
> players
```

`manager` and `console help` also enter the manager. `exit` leaves from anywhere;
`back`/`0` returns to the parent menu or cancels a pending prompt. At the root,
`0` returns to raw RCON. During a value prompt, `0` is interpreted as a value
(for example a ping limit of zero); use `cancel` to abandon that prompt.
`cancel` discards a pending action; leaving the editor discards its unsaved draft.
`help` explains controls; `refresh` updates live status, vote or player screens.
An empty submission accepts a displayed default. If Panel does not submit empty
lines, type the default explicitly. Answer a confirmation with exactly `yes`.

`rcon <command>` executes a raw RCON command inside menus. Raw commands outside
the manager retain their existing behavior. `stop`, `quit`, Ctrl+C, and the Panel
Stop signal always request graceful shutdown. For backward compatibility, raw
`exit` outside menu mode is also a shutdown alias. Use menu `exit` to leave safely.
Raw RCON escape commands are privileged and do not add guided confirmations.

State belongs to the bridge session in memory. Pterodactyl shares one container
stdin among console viewers, so multiple administrators also share this session;
the Panel supplies no distinct viewer identity. Browser disconnects do not send
an identifiable session-end message. Use `exit` before handing administration to
someone else. Actual stdin EOF does not stop the server or keep a crashed server
alive. Game logs continue normally and never trigger menu repainting.

## Menu categories

| Menu | Operations |
| --- | --- |
| Live Game Control | Status, map/mode inventories, change map, mode or both, queue/inspect next game, end round/game |
| Playlist Manager | List, create/edit, native bulk authoring, staged native validation, copy/import, activate, delete/restore |
| Voting Manager | Inspect ballot/tallies, start playlist/endround/endgame/shuffle/kick votes, pass/cancel |
| Player Management | Player IDs, teams and available telemetry; inspect, say/tell, kick, timed/permanent ban, bans/unban, mute/unmute, team/shuffle/teamcount, VPN allowances; gated admins/pardon |
| Maps, Modes & Mods | Running maps/modes, native installed-content search, uploaded content/mod metadata, persistent enable/disable, vote images |
| Server Configuration | Pending overrides, reset authority, explicit Apply/reload, camera/voice/welcome, live name/ping |
| Diagnostics & Logs | Detected executable and image pin, exact client matching, capabilities, process/RCON/assets/prefix, status/vote/errors |
| Help | Navigation, upstream help, version gates, persistence/rollback |

## Create and activate a rotation

1. Submit `menu`, `2`, `2`. Enter a new filename such as
   `community.playlist.json`, display name and voting duration (5-120 seconds).
2. In the editor select `1` to add a game. Choose a listed map and mode by number
   or exact reference, then a weight (1-100) and optional display name (`-` means
   none). Names containing spaces may be entered directly or quoted.
3. Optional entry properties accept a JSON object, or `-` to keep the existing
   properties. Ordinary rotation creation needs no JSON editing. For example:
   `{"world":{"sprint":"stamina"},"preview_image":"arena.jpg"}`.
   Advanced game-specific rules should originate in the upstream client editor.
   On .20 the native CLI validates the private unsaved candidate; .13 retains
   conservative local validation because its CLI lacks playlist commands.
   A `null` value removes an optional property from the draft, for example
   `{"preview_image":null}`; no `null` placeholder is written into the entry.
4. Add at least three distinct games. Edit/remove entries, change voting time,
   rename the rotation or preview it. Weights show relative weight share, **not**
   exact ballot inclusion probability: upstream excludes repeats and the last game.
5. Choose Validate, then Save and answer `yes`. A failed validation writes nothing.
6. Return with `back`, choose Activate, select the file and confirm. Activation is
   saved as a pending override. Use Configuration 7 to validate/generate TOML
   and request reload, or restart. Switching from a single map/variant to a
   playlist can require an idle restart. This menu never forces a match restart.

Example editor output (abbreviated):

```text
Community | voting 25s | 3 games
  1 | Guardian | Slayer           | weight 3 | 50.0% weight share
  2 | Valhalla | Capture the Flag | weight 2 | 33.3% weight share
  3 | The Pit  | Slayer           | weight 1 | 16.7% weight share
> 7
Native playlist show validated the staged candidate. ...
Confirm: save community.playlist.json ... type yes ...
> yes
Playlist saved atomically. Active .20 rotations update from the next vote after reload.
```

Files live in `/home/container/server/playlists/`. Import means upload a JSON file
there using File Manager/SFTP, then choose **Import uploaded playlist** to validate
and copy it to a new filename. Arbitrary paths and URLs are never accepted.
Unknown fields already present in a file survive edits and copies; preserving a
field is not a promise that the installed engine understands it.

The local validator checks version 2, structure/name, duration, entry count,
installed references, duplicate definitions, weights, optional field shapes,
known sprint limits, Forge editing exclusion, saved-file references, and image
signature/size/count. Explicit Workshop references are limited to 23 distinct
maps and 16 packages. It cannot fully verify embedded saved-map dependencies,
mod map-ID collisions, aliases for identical games or every engine-specific
rule/option key. The running engine remains authoritative. On .20 the filesystem
backend invokes `dedicated playlist show --config <private config> <candidate>`
against installed assets before every save/copy/restore and activation check.
Failure writes no active file. Actual successful engine validation still needs
the owned-assets Wings run. No native command is called on .13.

Playlist option 10 uses `dedicated playlist new` for a comma-separated map/mode
cross-product in private staging; preview/edit its draft and confirm Save before
it reaches active storage. The Python editor retains incremental editing,
unknown fields, atomic writes, conflict checks and backups. Native `playlist
list` exists, but local bounded listing is retained for offline file workflows.

Map and mode pickers use the running server's documented JSON `entries` inventory,
preferring each entry's `reference`. They do not claim every map/mode pairing is
compatible: the engine checks that combination. On 0.9.13, restart after content
uploads before validating playlists that refer to the new content.

## Persistent configuration and authority

Manager settings and selected playlist are saved in `server/.manager/overrides.json`.
This is wrapper state, **not an invented upstream configuration format**.
`configure.py` validates it on every launch and writes its values into the existing
managed `[[server]]` block. The remainder of `dedicated.toml` stays administrator
controlled; `[rcon]` password/address continue to synchronize from Startup.

Precedence for the managed server is:

1. An explicit manager playlist/setting override.
2. Existing Startup variables and their generated server/default values.
3. Administrator-controlled upstream defaults and upstream fallback behavior.

Upstream's per-server settings take precedence over environment-supplied defaults.
An activated playlist therefore survives a stale Startup `PLAYLIST`, `MAP` or
`GAME_TYPE`. The menu makes this explicit. Updating Startup alone does not clear a
manager override. Configuration option 3 clears all manager overrides with a
backup; after restart, Startup/manual settings regain authority. Existing
installations with no manager state retain their previous configuration flow.

Guided persistent settings include server/community name, player limits, ping
limit, anti-cheat, VPN blocking, visibility, voting, team-changing policy,
voice/team voice, text chat, mod sharing and sharing rate (Mbit/s; zero unlimited).
New keys include welcome, friendly_fire, independent voice scopes, load_timeout,
trust_player_games and camera. The menu saves **pending** state; Configuration 7
or startup generates TOML. Apply validates before atomic replacement, requests
RCON reload and prints its actual reply. Immediate settings, next-game settings
and idle-restart settings are distinguished in [CONFIGURATION.md](CONFIGURATION.md#0920-persistent-settings-and-reload).
A rejection is never called applied; saved files can still be picked up by
upstream auto-reload independently. Live `servername`/`maxping` actions affect admission/status until
restart and do not rewrite files. `nextmap` waits for the next lobby. Join/RCON
passwords, allocation ports, networking and game paths are **static** and belong
in Startup or the appropriate administrator-controlled file.
Camera values are first_person/player_choice/third_person, from the next
multiplayer game after reload. Campaign co-op/Firefight, vehicles and modes with
fixed third-person cameras retain their behavior. Mods still require restart.
See [CAPABILITIES.md](CAPABILITIES.md) for exact gates.

## Votes, players and transition outcomes

Voting checks the current phase, known counts, voting policy and an existing
moderation vote. Playlist voting queries the **running** `nextmap` rotation;
merely saving an activation does not load it. The engine checks additional rules
such as team eligibility, active ballots and target/admin eligibility. Its errors
are ordinary operation failures, never bridge crashes. Refresh to see tallies.

Player selection favors stable IDs from a fresh `players` reply. The interface
shows IDs only in privileged player/moderation operations. Scores, ping and life
state depend on upstream telemetry; missing fields read `-`, not zero. Removal,
bans/unbans, team changes, announcements, admin and VPN changes ask confirmation.
Shared ban/admin/VPN changes may affect all servers using that ban list. Mutes
last until unmute/restart unless a duration is supplied through raw RCON.

Game changes print **request accepted**, never immediate completion. The manager
lazily starts `dedicated rcon --json --watch` to observe supported `control`
events through the existing local WebSocket CLI. Status/refresh reports observed
completion or failure events. Events are best effort, without replay or command
correlation IDs; another privileged RCON tool can also generate them. A failed
watcher is not automatically reconnected and does not prevent commands. When no
event is available, exact requested map/mode names are compared with refreshed
status. A match means **observed in status**, not proof of this request's success.
An unmatched request stays pending/unknown: inspect game logs; never assume success
or automatically repeat a disruptive command. Queueing `nextmap` is separately
reported as a next-game request and can be inspected without ending the match.

## Mods and vote artwork

Upload compatible mod packages into `server/content/Mods/<folder>/`, preserving
their metadata and map layout. The image contains no Steam/SteamCMD downloader;
the manager never downloads untrusted URLs or requests Steam credentials. Mod
metadata is shown as installed, so version information is available only when
the package provides it. Manual package replacement stays in File Manager/SFTP.

Enable/disable changes only the documented `content/disabled-mods.json`
`packages` list, preserving unrelated properties and backing up the old file.
**Restart required**, including after replacing a mod. A switch describes the
desired next-start state, not what a running game has loaded. Validate affected
playlists, and keep a copy of mod folders before manually replacing/removing them.
This manager does not delete mod files. Nested Workshop package folders are
discovered from their package metadata/layout. Explicit Workshop references to
recognized disabled packages fail playlist validation. Dependencies hidden in
saved variants still require engine validation; do not infer missing metadata
or a compatible version.

Put custom PNG/JPEG vote artwork in `content/Images`, at most 4 MiB each and 32
distinct images per playlist. Select by filename through `preview_image` in the
entry's optional properties. Replacement requires playlist reselect/restart
upstream; with 0.9.13 use restart. Signature checks do not fully decode the image.

## Diagnostics, security and rollback

Diagnostics reports presence checks for `halo3.dll`, `shared.map` and Wine's
`system.reg`; these are not full engine/prefix integrity tests. Live map/mode,
player count and round phase come from RCON. The image build version is labeled
separately because upstream AUTO_UPDATE can change the runtime executable.
Diagnostics 7 runs the actual executable's --version, compares its image pin,
lists capabilities and warns about detected mismatch. .20 clients must match
the server exactly; individual client versions are not exposed by documented
RCON. Automatic updates stay disabled by default. Recent
error excerpts exclude chat/moderation/authentication lines and redact known
credentials and common identifiers. Full original game output still streams to
the Console as before. No diagnostic report is automatically uploaded or sent.

Treat Console/File Manager/SFTP access as privileged. Panel authorizes viewers;
Wings submits their input to the container; Python validates menu values and calls
fixed argv subprocesses; local RCON authenticates against container-local files.
Persistent operations stay within playlists, content switches and manager state.
No menu executes a shell. Do not enter passwords in Console: Panel may retain or
echo submitted input even when the manager does not print it. Change secrets in
Startup. Keep the persistent volume and its backups private.

Atomic replacements use same-directory temporary files, fsync and rename, with
restricted new-file permissions. Existing playlists are backed up before changes
or deletion in `playlists/.backups/<id>.json`; use Playlist option 9 to restore a
validated backup. An edit also checks the opened file's hash, refusing to overwrite
an intervening SFTP edit. Static symlink/path escapes are rejected. Concurrent
privileged external directory replacement is outside this path-checking boundary;
avoid concurrent SFTP edits during an operation.

Manager state, mod switches and generated TOML have `.backups` beside their
respective storage areas. To roll back settings, use Configuration option 3 or,
while stopped, restore the desired JSON backup using File Manager. To roll back
the image, first clear manager overrides and restart once with this image to
regenerate the managed block from Startup, then select the previous working image.
Keep `server/`, `.wine-prefix/` and `.cache/reclaimer/` intact. Prefer restoring
pre-upgrade TOML and overrides while stopped; the older wrapper rejects new
.20 keys in override JSON. Also restore any .20-only administrator TOML fields
and use .13 clients for the rollback image. Exact original SHA/image digest are
recorded in [UPSTREAM-0.9.20.md](UPSTREAM-0.9.20.md#preserved-rollback).

See [CAPABILITIES.md](CAPABILITIES.md) for version evidence and
[WINGS-VALIDATION.md](WINGS-VALIDATION.md) for the required live regression run.

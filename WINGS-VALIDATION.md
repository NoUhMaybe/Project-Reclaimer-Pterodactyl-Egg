# Live Wings acceptance checklist

Automated tests use mock services and temporary files. They do not establish Halo
gameplay, WAN connectivity, multi-client correctness or actual mod compatibility.
Run this checklist on a separately approved test deployment before production.
The current candidate pins 0.9.21. Use a validated build from the reviewed
source or the matching published release image described in [RELEASING.md](RELEASING.md),
and match 0.9.21 clients. Gameplay tests below remain unperformed until operator
approval. The older .20 image procedure below is retained as historical context;
it does not select the current .21 candidate.

## Historical isolated 0.9.20 image procedure

Publishing a test image does not authorize deployment. The operator selects it
manually on a separate Pterodactyl server; do not change the working server.

1. Record that test server's current image and back up its persistent files.
   Preserve the known .13 manager image `console-manager-pr5-test.1`, digest
   `sha256:abaf6ca10fe1c622586242a25feb7b0e83df4049e88acda0a337362b93b568ee`.
   Record pre-upgrade TOML, overrides, bans, playlist/mod state and Startup values.
2. Stop only the separate test server. In the Panel's server administration Startup
   settings, find **Docker Image Configuration** and enter the full published
   `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:console-manager-pr5-reclaimer-0.9.20-test.N`
   reference in the custom image field. Save only that test server's settings;
   keep its Nest/Egg and the egg's default image unchanged.
   For reproducible testing, use the reported `@sha256:...` image digest instead
   when the Panel accepts digest references.
3. Upload your own Halo 3 assets to the test server's `server/game/` and configure
   its own allocation and RCON credentials through its existing Startup settings.
   Keep game/client versions matched to upstream **0.9.20**. Never copy credentials
   or alter allocations on the working production server as part of this task.
4. Start the test server and follow every checklist section below: asset/startup
   validation; `menu`; all eight categories; `exit` and raw `status`/`players`;
   playlist creation/save/activation, reload and restart; voting/map changes; moderation;
   content/mod inspection; graceful Stop/Restart; WAN and multiplayer gameplay.
5. To roll back, stop the test server, restore its pre-upgrade TOML/overrides and
   configuration, select the original image by digest and match .13 clients.
   New .20-only override keys are rejected by the older wrapper. Alternatively
   reset overrides on .20 and restart once to regenerate the managed block before
   switching, then restore any .20-only administrator TOML fields while stopped.
   Preserve uploaded assets, persistent prefix and backups.

The manual publisher is `.github/workflows/publish.yml`, dispatched from
`feature/console-manager-upstream-0.9.20` with `source_sha=<full upgrade PR head SHA>`,
`test_tag=console-manager-pr5-reclaimer-0.9.20-test.N`, `reclaimer_version=0.9.20` and
`tag_latest=false`. It requires passing CI for that exact commit, rejects existing
tags and forks, builds/tests without package-write credentials, publishes only two
experimental tags, and independently pulls the result without Docker credentials.
Publication proof (digest, source SHA and unchanged existing-tag digests) is attached
to the Actions run. No GitHub Release, main merge, release tag or deployment occurs.

## Prepare and record baseline

- Back up the persistent volume and record the currently working wrapper image,
  upstream executable version, Startup values, allocation and UID/GID. Keep all
  passwords out of reports. Preserve the existing working image as rollback.
- Confirm the current installation's Halo 3 match, two or more clients including
  a WAN client, raw RCON, game logs and graceful Stop/Start. These are mandatory
  regressions; a manager feature is not accepted if any fail.
- Use owned game assets and version-matched clients. The default pin remains
  0.9.21 on this branch; the existing .13 image stays available for rollback.
- After separate deployment approval, build a local test tag from this branch
  without pushing it. Use a test allocation/server, not the production match.

## Dedicated 0.9.21 upgrade acceptance record

Record pass/fail and redacted evidence for each item. These are pending live
checks, not automated-test claims. Test migration with a **copy** of the original
.13 wrapper's TOML, version-1 overrides, version-2 playlists and mod switches;
compare unmanaged settings and data before/after two restarts.

1. [ ] Fresh startup under Wings' assigned non-root UID reaches a playable .21 server.
2. [ ] Persistent prefix initializes with correct ownership, then survives recreation.
3. [ ] Owned Halo 3 assets validate; existing assets and content remain intact.
4. [ ] All eight menu categories, back/cancel/refresh/help and exit work via input field.
5. [ ] Raw quoted RCON commands work after exit; game logs continue in menus.
6. [ ] Incremental and native bulk playlist creation, staged validation, save,
   duplicate/restore and activation succeed; invalid candidates preserve files.
7. [ ] Apply/reload prints actual server result and reload events. Test welcome
   immediately, game settings next game, idle restart separately, and a rejected
   candidate. Existing ballots/matches retain their current state.
8. [ ] Native content search and manual mod metadata/enable/disable work;
   restart loads desired state without modifying uploaded packages.
9. [ ] Test each camera policy from next multiplayer game after reload; verify
   vehicle, fixed-camera modes and campaign/Firefight exceptions where available.
10. [ ] Stable-ID moderation, admins add/list/remove and kick pardon affect only
    consenting test players; restore ban/admin/VPN state afterwards.
11. [ ] Map-only/mode-only/load and next-game override work, including failed transition.
12. [ ] Playlist and moderation voting obey prerequisites and show correct tallies.
13. [ ] Stop/Restart from menus/prompts/slow CLI works; unexpected child exit exits container.
14. [ ] LAN and WAN clients connect with unchanged allocation/network behavior.
15. [ ] Multiple simultaneous clients join and play.
16. [ ] Full match completes, ballot/rotation advances and another match runs.
17. [ ] Diagnostics actual binary/pin are .20; matching clients work. Document
    wrong-version rejection without pretending to detect each client's version.
18. [ ] Restore pre-upgrade configuration and the .13 rollback digest; confirm
    .13 client/RCON/multiplayer/Stop behavior, then retain the evidence.

## Console and lifecycle

- [ ] First startup as the Wings-assigned non-root UID initializes a persistent
  Wine prefix, validates assets and reaches the same playable state as baseline.
- [ ] Second startup reuses the Wine prefix, configuration and assets.
- [ ] `menu`, `manager`, `console help` display the eight categories through the
  ordinary Console input field without a TTY or any additional UI.
- [ ] Invalid numbers, malformed quotes and empty states show readable errors.
- [ ] `back`, `cancel`, `help`, `refresh` and `0` work; `exit` during a pending
  confirmation returns to RCON and leaves the server playing.
- [ ] `players`, `status`, `load "The Pit" "Capture the Flag"`, and the menu's
  `rcon <command>` escape preserve argument grouping. Confirm the actual game state.
- [ ] Game output continues while menus are open; logs never repaint the menu.
- [ ] Panel Stop/Restart and direct `stop` work while at root, inside a prompt,
  and during a deliberately unavailable/slow RCON request.
- [ ] SIGINT/SIGTERM stop the upstream process group gracefully within the existing
  escalation budget; the container exits with the child and no auxiliary client
  keeps it falsely running. Check unexpected upstream exit behavior too.
- [ ] With RCON disabled, local file menus remain usable and live operations
  explain how to enable RCON without crashing the server.

## Games, votes and players

- [ ] Status/player tables agree with the actual map, mode, round and client count.
- [ ] Map-only, mode-only and combined changes require confirmation; cancelled
  operations do nothing. Observe accepted -> control completed/failed, or an
  explicitly limited status observation. Test one invalid/missing map outcome.
- [ ] `nextmap` queues without ending the game; inspection reports the actual
  override, and the configured rotation resumes after that one game.
- [ ] Endround/endgame affect the intended round/game and preserve next-match play.
- [ ] Vote view shows ballot choices/counts. Start/pass/cancel a playlist ballot;
  exercise endround/endgame/shuffle/kick votes and prerequisite errors.
- [ ] Players are selected by ID; test say/tell, kick, temporary ban, permanent
  ban, bans/unban, mute/unmute, team movement, shuffle/teamcount and VPN allowances
  using consenting test players. Restore all moderation changes afterwards.
- [ ] Admin management and pardon are available on .20; confirm actual shared
  scope and kick pardon behavior. They remain unavailable on the .13 rollback.

## Files, persistence and mods

- [ ] Create three games, edit/remove/re-add an entry, set weights and duration,
  preview, validate and save a version-2 playlist entirely through console input.
- [ ] Invalid references, duplicates, unsupported Forge sessions and unsafe paths
  write nothing. Advanced rules/dependencies receive actual engine validation.
- [ ] Duplicate/import a file, preserve existing extra fields, cancel deletion,
  then delete a nonactive test file and restore its backup.
- [ ] Edit the opened file via SFTP before saving; confirm a conflict leaves that
  external edit intact. Check atomic-write failure handling on a disposable volume.
- [ ] Activate a playlist while a different Startup PLAYLIST/MAP/GAME_TYPE is set.
  Confirm saving alone does not end a match. Apply/reload and observe documented
  next-vote/idle timing, or restart and verify the selected playlist is loaded;
  restart again and ensure it is not overwritten by Startup defaults.
- [ ] Reset overrides and restart; verify authority returns to Startup/manual defaults.
- [ ] Persistent settings survive restart and do not overwrite unmanaged TOML.
  Secret settings never appear in manager output; RCON remains container loopback.
- [ ] Upload compatible saved maps/modes and a manual mod package using File
  Manager/SFTP. Restart, inspect its real metadata/maps, and validate dependencies.
- [ ] Disable/enable the mod with confirmation and backup. Confirm only the next
  startup changes loaded content; test a playlist that references a disabled mod.
- [ ] Use a PNG/JPEG vote image, verify actual artwork in a ballot, and reject a
  missing/oversized image. Verify next-vote/reselect timing on .20; restart on .13.
- [ ] Confirm WAN clients and multiple players still join and finish matches after
  all changes. Restore the known working image/configuration and verify rollback.

Record pass/fail, versions, commit SHA, map/mode, client count and redacted
symptoms for each failed item. Do not include credentials, IPs or full player IDs.

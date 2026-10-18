# Live Wings acceptance checklist

Automated tests use mock services and temporary files. They do not establish Halo
gameplay, WAN connectivity, multi-client correctness or actual mod compatibility.
Run this checklist on a separately approved test deployment before production.
Do not publish an image, deploy, merge or tag a release as part of code review.

## Select the isolated PR #5 image on a separate test server

Publishing a test image does not authorize deployment. The operator selects it
manually on a separate Pterodactyl server; do not change the working server.

1. Record that test server's current image and back up its persistent files.
   `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.0-dev.4` is a previously
   published rollback candidate; prefer the exact image that worked on your server.
2. Stop only the separate test server. In the Panel's server administration Startup
   settings, find **Docker Image Configuration** and enter the full published
   `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:console-manager-pr5-test.N`
   reference in the custom image field. Save only that test server's settings;
   keep its Nest/Egg and the egg's default image unchanged.
   For reproducible testing, use the reported `@sha256:...` image digest instead
   when the Panel accepts digest references.
3. Upload your own Halo 3 assets to the test server's `server/game/` and configure
   its own allocation and RCON credentials through its existing Startup settings.
   Keep game/client versions matched to upstream **0.9.13**. Never copy credentials
   or alter allocations on the working production server as part of this task.
4. Start the test server and follow every checklist section below: asset/startup
   validation; `menu`; all eight categories; `exit` and raw `status`/`players`;
   playlist creation/save/activation and restart; voting/map changes; moderation;
   content/mod inspection; graceful Stop/Restart; WAN and multiplayer gameplay.
5. To roll back that test server, first reset manager overrides and restart once
   with the test image (or restore its pre-test configuration backup while stopped).
   Stop it, restore its previous Docker image tag/digest and backed-up configuration,
   and start it again. Preserve its uploaded game assets and persistent Wine prefix.

The manual publisher is `.github/workflows/publish.yml`, dispatched from
`feature/console-manager` with `source_sha=<full current PR #5 SHA>`,
`test_tag=console-manager-pr5-test.N`, `reclaimer_version=0.9.13` and
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
  0.9.13; do not silently upgrade players or servers to newer documentation.
- After separate deployment approval, build a local test tag from this branch
  without pushing it. Use a test allocation/server, not the production match.

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
- [ ] Admin management and pardon are unavailable on 0.9.13. Do not count gated
  screens as successful tests of newer engine operations.

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
  Confirm no running match ends. Restart and verify the selected playlist is loaded;
  restart again and ensure it is not overwritten by Startup defaults.
- [ ] Reset overrides and restart; verify authority returns to Startup/manual defaults.
- [ ] Persistent settings survive restart and do not overwrite unmanaged TOML.
  Secret settings never appear in manager output; RCON remains container loopback.
- [ ] Upload compatible saved maps/modes and a manual mod package using File
  Manager/SFTP. Restart, inspect its real metadata/maps, and validate dependencies.
- [ ] Disable/enable the mod with confirmation and backup. Confirm only the next
  startup changes loaded content; test a playlist that references a disabled mod.
- [ ] Use a PNG/JPEG vote image, verify actual artwork in a ballot, and reject a
  missing/oversized image. Restart after replacing it on 0.9.13.
- [ ] Confirm WAN clients and multiple players still join and finish matches after
  all changes. Restore the known working image/configuration and verify rollback.

Record pass/fail, versions, commit SHA, map/mode, client count and redacted
symptoms for each failed item. Do not include credentials, IPs or full player IDs.

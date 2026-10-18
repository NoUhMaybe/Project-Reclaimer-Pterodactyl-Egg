# 0.9.20 upgrade compatibility assessment

Research completed October 18, 2026 before implementation. Official latest
resolves to [v0.9.20](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.20),
published `2026-10-18T14:21:51Z`. The dedicated image is publicly available for
Linux amd64. [CAPABILITIES.md](CAPABILITIES.md) records per-version evidence and
the explicit 0.9.14 evidence gap.

| Contract | 0.9.13 versus 0.9.20 result |
| --- | --- |
| Upstream manifest | .13: `sha256:a3686b0eaca372bf4607dcf72b4a6fe5a587ece4d7793173e784292f8fcf941b`; .20: `sha256:975b4a772da6cc3c358ec7dd6abccbe31a6fca8e9e1c9ff5f7eb2ee6661efb07` |
| Architecture | Both linux/amd64 |
| Image config | Both User root, WorkingDir /server, Entrypoint ["/usr/bin/tini","--","reclaimer-entrypoint"], Cmd ["start"], StopSignal SIGINT |
| Environment | Same upstream HOME /home/reclaimer, USER reclaimer, WINEPREFIX /home/reclaimer/.wine, WINEARCH win64, WINEDEBUG -all; no new wrapper variable required |
| Entrypoint scripts | Extracted from both image layers; byte-identical. Prefix preparation, owner checks, root-only UID remapping and Xvfb/Wine startup contract unchanged |
| Writable executable | Bundled /opt/reclaimer/project-reclaimer.exe; writable /server/.reclaimer/project-reclaimer.exe (per-instance subfolder with ONLY). Changed bundled hash resets this copy at normal startup; no uploaded assets replaced |
| Persistent layout | Existing /server, /cache and Wine-prefix symlinks retained, all writable data under /home/container. No migration/deletion of assets, mods, bans or playlists |
| Supervision | Existing bridge/process groups/stdin worker/log inheritance and SIGINT escalation retained; native helper is bounded and closed during cleanup |
| RCON | Protocol 1, local credentials, structured command/args and JSON replies compatible; actual .13/.20 CLI tested against loopback fixture |
| Configuration | TOML managed block and manager JSON v1 retained. New .20 fields parse in actual binary. Apply validates before atomic replacement, then independently requests RCON reload |
| Playlist/content CLI | Actual .20 help confirms new/show/list/content/reload syntax; no content/playlist JSON flag. Native operations require owned assets and fail closed without them |
| Clients | Exact Project Reclaimer version matching required; documented RCON does not expose individual client versions |
| Updates | Startup default remains false; explicit existing choice preserved. Pin does not prove a binary changed by operator-enabled updates |

The metadata/entrypoint audit supports retaining the wrapper design. Automated
Linux tests cover missing assets, configuration, non-root filesystem access,
persistent Wine prefix and real .20 execution. They do not establish successful
Halo startup or gameplay without owned assets. Live reload/mod/camera/WAN and
multiple-player effects await the separately approved [Wings test](WINGS-VALIDATION.md).

## Preserved rollback

- Original branch: feature/console-manager (PR #5 remains unmerged).
- Original source: `0111dfdd7626467624177df17a70b4b000d9d5f8`.
- Original image: `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:console-manager-pr5-test.1`.
- Original digest: `sha256:abaf6ca10fe1c622586242a25feb7b0e83df4049e88acda0a337362b93b568ee`.

Before approved deployment, back up TOML, manager overrides, playlists, mod
switches, bans and Startup values. To revert, stop the test server, restore its
pre-upgrade configuration (including overrides and TOML), select the original
image by digest and match .13 clients. New .20-only override keys are rejected
by the old wrapper; restoring only the image is insufficient. Alternatively
reset overrides on the new image and restart once to regenerate its managed
block before switching; also remove/restore administrator-added .20 TOML fields
while stopped. Preserve assets and the persistent Wine prefix. This task does
not deploy or upgrade any server.

# 0.9.21 upgrade compatibility assessment

Checked October 20, 2026. The official [latest release](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/latest)
resolves to [v0.9.21](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/tag/v0.9.21),
published `2026-10-19T13:07:38Z`, with no prerelease flag. The egg remains the
unpublished v0.1.2 candidate; its upstream server and required client are 0.9.21.

| Contract | 0.9.20 to 0.9.21 result |
| --- | --- |
| Public linux/amd64 manifest | .21: `sha256:886f512c45ef052e56e0dff9d14732ac4332b92a8bd4e8c2bc4c71f659317ae9`; previous .20: `sha256:975b4a772da6cc3c358ec7dd6abccbe31a6fca8e9e1c9ff5f7eb2ee6661efb07` |
| Image configuration | Same User root, WorkingDir /server, Entrypoint `["/usr/bin/tini","--","reclaimer-entrypoint"]`, Cmd `["start"]`, StopSignal SIGINT, environment, ports and healthcheck |
| Filesystem layers | Every layer is identical except the bundled executable layer. Upstream entrypoint, UID handling, Wine preparation and filesystem layout are retained |
| Bundled executable layer | `sha256:17b3d4f0a49a7d03199243f62b99e8902a26ec7d5034bb8774d9d40c5ea7733e`, downloaded and digest verified before reading its executable |
| Bundled executable SHA256 | `c288e36a69f59c4cd54fe21332ecd9c53257c36be1d633e46b4b07c773ac0760`; actual --version confirms 0.9.21 |
| Windows release executable SHA256 | `f7c2c29a6eb82077cdbe2bf75e09cfb779326de469348556fa7232ae1e9712ab`, verified against the official SHA256SUMS.txt |
| Local real-binary checks | Both .21 executables pass version, structured RCON arguments against a loopback fixture, playlist/content/reload help, configuration parsing, invalid camera rejection and native validation failing safely without assets |
| Console and lifecycle | Existing line-oriented bridge, menu/raw RCON return, logs, child supervision and graceful Stop are retained |
| Persistence | Existing assets, mods, playlists, bans, manager JSON v1, TOML and Wine-prefix locations are retained; no migration or asset download is added |
| Updates and clients | Automatic updates remain disabled by default; existing explicit choices are preserved. Clients must match the actual server executable exactly |

The versioned [RCON reference](https://github.com/ProjectReclaimer/project-reclaimer-releases/releases/download/v0.9.21/RCON.md)
retains protocol 1 and structured command/args. The .21 release repairs ODST
map/mode/load/nextmap and endgame behavior and moderation state across games;
those operations continue through the existing RCON backend. New ODST campaign
modifiers and Firefight options remain administrator configuration, separate from
the guided Halo 3 asset preflight. No additional UI or process architecture is needed.

CI checks the actual bundled .21 executable under Wine in Test F, plus the
existing Linux lifecycle and non-root filesystem/prefix tests. Windows CI retains
the .13/.20 real-CLI regressions and adds .21. These checks do not establish Halo
gameplay, positive native validation with owned assets, WAN/multiple-player
connectivity or live reload effects. Complete [Wings validation](WINGS-VALIDATION.md)
on a separate authorized server before deployment.

Back up the current image selection, TOML, overrides, bans, playlists and mod state
before an upgrade. To roll back, restore the matching pre-upgrade image and
configuration and match its client version. Existing release tags and images are
preserved; the earlier .13 rollback identity remains recorded in
[UPSTREAM-0.9.20.md](UPSTREAM-0.9.20.md#preserved-rollback).

> **2026-10-11 live-testing update:** The historical notes below describe
> development-stage assumptions and failures and may contain superseded
> "not tested" statements. Current verified status: `v0.1.0-dev.3`
> succeeded on a real Wings node with LAN gameplay, a complete Guardian
> Slayer match, local RCON via the Pterodactyl Console, and graceful
> Stop/Start. Still unverified: WAN, multiple simultaneous clients, public
> server listing, independent fresh install. See [README.md](README.md)
> and [CONFIGURATION.md](CONFIGURATION.md) for current operation.
>
> For the current non-root Wine-prefix ownership fix, use
> `WINEPREFIX=/home/container/.wine-prefix` and ensure the directory owner
> matches the Wings container UID/GID. The old `/home/reclaimer/.wine`
> symlink ownership failure was fixed in `v0.1.0-dev.2`.
> Local-only RCON (TCP 127.0.0.1 inside the container) and stdin bridging
> were introduced in `v0.1.0-dev.3`. The appearance of
> `X connection to :0 broken` on graceful shutdown was observed alongside
> `All servers stopped` and is not by itself proof of a crash.

# Troubleshooting

## Console manager (this branch)

The operator reports the existing server working with WAN, multiple players,
interactive RCON and graceful shutdown. Older test notes below are historical;
they do not supersede that baseline or establish this branch's live behavior.
Complete [WINGS-VALIDATION.md](WINGS-VALIDATION.md) before accepting the manager.

| Symptom | Action |
| --- | --- |
| `menu` is treated as an unknown RCON command | The running wrapper image predates the manager. Build/test this branch under a separate tag after deployment approval; editing the egg alone does not update an image. |
| RCON-disabled message | Set Enable RCON and an 8-128 character password in Startup; restart. Persistent/native file validation can work with assets, but live inventories/Apply need RCON. |
| Authentication failure or timeout | Check startup, loopback RCON and synchronized configuration. Commands are not automatically retried because their outcome may be unknown. No password should be pasted into Console. |
| Save rejects a map/mode after upload | 0.9.13 inventories describe content loaded at startup. Restart after uploads, use the listed exact reference and refresh. Engine-specific compatibility still needs verification. |
| Active rotation still shows the old playlist | Activation is pending. Use Configuration 7 to generate/validate TOML and request reload, or restart. Content-type changes can idle-restart; inspect `nextmap` and server reply. |
| Startup PLAYLIST/settings seem ignored | Explicit manager overrides win. Configuration option 1 shows them; option 3 resets all manager settings/playlist authority for next start. |
| File changed since opened | An SFTP/File Manager edit intervened. Reopen the playlist before saving; the manager refuses to overwrite that edit. |
| Invalid path or symlinked storage | Use simple filenames inside playlists and real persistent storage directories. The manager refuses traversal and symlinks; no arbitrary file access is available. |
| Command accepted but map did not change | Refresh status, inspect next-game override and game logs. Acceptance differs from observed completion/failure. Events may be missed and are not replayed. |
| `startvote playlist` fails | The running server needs a valid loaded rotation and eligible lobby/player state. A pending activation is insufficient. Read the upstream prerequisite error. |
| Admins/pardon/reload unavailable | They need .16/.18 respectively. This upgrade pins .20; Diagnostics 7 checks actual binary, pin and gates. The original .13 image intentionally gates them. |
| Native validator rejects a candidate | Check owned game assets, installed content and upstream configuration. Candidate errors are sanitized because TOML can contain secrets. No failed candidate overwrites active files. |
| Saved setting has no live effect | Edits remain pending until Apply/reload or startup. Read the actual reload reply: immediate, next game/vote or idle restart. Mods need restart. A failed reload is unconfirmed even though files remain saved. |
| .20 client cannot join / binary differs from pin | Exact versions must match. Check Diagnostics 7 and client version manually. Individual client versions are not exposed by RCON. Keep AUTO_UPDATE off for pinned testing. |
| Camera seems unchanged | After reload, test the next on-foot multiplayer game. Vehicles, modes with fixed third-person cameras, campaign co-op and Firefight retain their own behavior. |
| Rollback image rejects overrides | Restore pre-upgrade overrides AND TOML, then use .13 clients. New .20 keys are not accepted by the older wrapper. See UPSTREAM-0.9.20.md. |
| Mod disabled on disk but still running | Mod switches require restart. Validate affected playlists before restarting; the switch describes next-start state. |
| Need to restore a playlist | Playlist option 9 validates/restores a selected `playlists/.backups` file, backing up an existing target first. |
| Need to restore settings or image | Follow [rollback](CONSOLE-MANAGER.md#diagnostics-security-and-rollback); reset overrides and regenerate managed TOML before returning to an earlier image. |
| Prompt changed while another admin was viewing | The container has one shared stdin session. Coordinate console use; `exit` discards the shared unfinished draft. |

Automated checks are `python -m unittest discover -s tests -v`. POSIX supervisor
checks are Linux-only, pure Python logic runs on Windows, and the optional
`RECLAIMER_TEST_BINARY` test exercises the real official CLI against a local fake
WebSocket server without Halo assets. CI also runs shell syntax, ShellCheck,
Docker build and runtime A/B/C/E/F. F verifies the actual bundled .20 binary
checksum/version and CLI under Wine without assets. None substitute for Wings.

## Verified upstream image metadata

Originally fetched for .13 on 2026-10-11, rechecked for .20 on 2026-10-18
and .21 on 2026-10-20
using the plain registry HTTP API (anonymous token + manifest + config blob; no `docker
pull` or local Docker daemon needed — see `tests/test_dockerfile.py` for a
repeatable version of this check, run automatically against the live
registry in CI):

```
image:       ghcr.io/projectreclaimer/project-reclaimer-dedicated:0.9.21
User:        root
WorkingDir:  /server
Entrypoint:  ["/usr/bin/tini", "--", "reclaimer-entrypoint"]
Cmd:         ["start"]
Env:         HOME=/home/reclaimer USER=reclaimer WINEPREFIX=/home/reclaimer/.wine
             WINEARCH=win64 WINEDEBUG=-all WINEDLLOVERRIDES=mscoree,mshtml=
ExposedPorts: 49175/tcp, 49176/udp, 49177/udp
StopSignal:  SIGINT
Healthcheck: CMD dedicated status (interval 30s, timeout 30s, start-period 180s, retries 3)
```

Build history confirms: `useradd --create-home --uid 1000 --user-group
--shell /usr/sbin/nologin reclaimer`, then `mkdir -p /server /cache
/opt/reclaimer && chown reclaimer:reclaimer /server /cache`; the entrypoint
script is installed at `/usr/local/bin/reclaimer-entrypoint` with `dedicated`
and `project-reclaimer` as symlinks to it; the Wine prefix is initialized
once at build time (`reclaimer-entrypoint prepare-prefix`, run as the
`reclaimer` user, UID 1000) before the final image reverts to `USER root`.

### `/home/reclaimer` permissions (and the symlink-validation regression this caused)

CI run `38167643842` failed Tests A and C with:

```
ERROR: /home/reclaimer/.wine is not the symlink this image's Dockerfile is supposed to create.
```

despite the Dockerfile's `RUN ... && ln -s /home/container/.wine-prefix
/home/reclaimer/.wine` succeeding at build time (confirmed: the image built
fine, and this exact `RUN` step runs as root, which can always create the
symlink regardless of any later permission concern). The real cause was
confirmed by downloading the specific upstream layer that runs `useradd
--create-home` (`docker/<repo>/blobs/sha256:07807a687f...`, found by
matching layer sizes against the config's build `history`, exactly as
described above) and inspecting it directly:

```
$ tar -tzvf useradd-layer.tar.gz
drwxr-xr-x  0 0      0           0 ... home/
drwx------  0 1000   1000        0 ... home/reclaimer/
-rw-r--r--  0 1000   1000      220 ... home/reclaimer/.bash_logout
...
```

`/home/reclaimer` is mode **0700** (owner-only — not the traditional 0755),
owned by UID 1000. `rm -rf`/`ln -s` at build time runs as root, which
bypasses all permission checks (`CAP_DAC_OVERRIDE`), so the symlink is
created successfully regardless. But at *runtime*, Wings (and Tests A/C,
deliberately) run as a UID that is neither 1000 nor root — and the kernel
denies that UID even *traversal* into a 0700 directory it doesn't own.
`entrypoint.sh`'s `[ -L "$path" ]` check calls `lstat()` on
`/home/reclaimer/.wine`, which fails with `EACCES` before it can even see
the symlink entry; bash's `-L` test (correctly, per POSIX) reports **false**
on any `lstat()` failure, which is indistinguishable, from the test's
boolean result alone, from the symlink not existing at all. `/server` and
`/cache` never had this problem because their parent, `/`, is a normal
`755 root:root` directory.

This also meant `reclaimer-entrypoint`'s own `check_prefix_owner()` and
`prepare-prefix` would have hit the identical `EACCES` the moment anything
tried to actually resolve `$WINEPREFIX` under a non-root, non-1000 UID —
this was never just our own validation check being overly strict.

**Fix:** the Dockerfile now also runs `chmod 755 /home/reclaimer` in the
same build-time `RUN` step that creates the symlinks. This only grants
traversal/read to other UIDs — nothing needs to be *written* directly
under `/home/reclaimer`, since Wine always resolves through the symlink to
`/home/container/.wine-prefix` (Wings-owned, already writable) for actual
I/O. The `[ -L path ]` check itself was correct all along and was not
weakened or removed; see `tests/test_dockerfile.py`'s
`test_home_reclaimer_permissions_are_relaxed` for a static regression
guard, and the new `tests/test-runtime-e-wine-prefix.sh` for a live one
that actually runs `reclaimer-entrypoint prepare-prefix` under a non-root
UID end to end (not just the symlink check in isolation).

The actual `reclaimer-entrypoint` script was also extracted from its own
image layer and read directly (not reproduced verbatim here for
cleanliness; its logic is summarized in README.md "How upstream's internals
were verified" and drove every design decision in `Dockerfile` and
`docker/entrypoint.sh`). Key confirmed behaviors that are NOT obvious from
the docs alone:

- `reclaimer-entrypoint start`, when NOT running as root (always true under
  Wings — see below), skips upstream's own `PUID`/`PGID`/privilege-drop
  logic entirely and proceeds directly, as whatever UID it was started
  with. This confirmed PUID/PGID are inert under Pterodactyl.
- It refuses to start if the Wine prefix (`$WINEPREFIX`) is not owned by
  the UID it is currently running as ("the Wine prefix ... belongs to
  another user"). Since the prefix upstream bakes into the image belongs to
  UID 1000, and Wings' assigned UID is normally something else entirely
  (see below), this would fail on a real Wings node if the image were used
  unmodified — which is why this egg's Dockerfile discards that baked
  prefix and the entrypoint re-initializes one for whatever UID Wings
  actually assigns, on each server's own first start.
- If `dedicated.toml` does not exist, `reclaimer-entrypoint start` creates
  one itself (`dedicated init .`) before this egg's own `configure.py` ever
  runs — in practice `configure.py` always runs first (see
  `docker/entrypoint.sh`), so this upstream behavior is pre-empted and
  never actually triggers, but it means the image is self-healing even if
  `configure.py` were ever skipped.
- On missing/invalid game assets, upstream's own `start()` loops forever
  (retrying `dedicated check` every 15 seconds with actionable messages),
  rather than exiting. This egg's `docker/validate-assets.sh` deliberately
  pre-empts that with its own fail-fast, nonzero-exit check instead (see
  `docker/entrypoint.sh` for the rationale) — upstream's own loop remains
  as an inert fallback that should never actually trigger in practice.

Separately, confirmed directly from the `pterodactyl/wings` source
(`develop` branch, `environment/docker/container.go`, function `Create()`):
Wings always creates server containers with an explicit `conf.User =
"<uid>:<gid>"`, taken from a "pterodactyl" system user Wings itself manages
on the host (`config/config.go`, `EnsurePterodactylUser`). This is **not**
guaranteed to be UID 988 — that is simply a common real-world result, not a
fixed value; it is whatever UID `useradd --system` happens to allocate on a
given machine, and can differ between Wings nodes (including the two nodes
described for this deployment). Confirm the actual value on your own node(s)
with `id pterodactyl` on the Wings host if you need to reason about exact
file ownership outside the container.

## What has and has not been tested

Be precise about this before relying on the egg in production.

### Verified

- `egg-project-reclaimer.json` is valid JSON and structurally matches the
  documented PTDL_v2 fields, including that the install script embedded in
  it is byte-for-byte identical to `scripts/install.sh` (`tests/test_egg.py`,
  run via `python3 -m unittest discover -s tests -v`, also run in CI).
- `docker/configure.py`'s `dedicated.toml` generation/patching logic is
  correct, idempotent (including full `main()` end-to-end runs, not just
  the internal patch function), preserves hand-edited content outside its
  managed block, correctly escapes special characters (quotes, backslashes)
  in server names, truncates overlong names, and rejects invalid/out-of-range
  ports (`tests/test_config.py`).
- The Dockerfile's `ENTRYPOINT` correctly names the real
  `reclaimer-entrypoint` program (not just an inherited, nameless `CMD`),
  the build-time symlinks for `/server`, `/cache`, and the Wine prefix are
  present, and the entrypoint calls `reclaimer-entrypoint prepare-prefix`
  and honors Wings' `$STARTUP` variable (`tests/test_dockerfile.py`, static
  checks).
- **The upstream image's actual `Entrypoint`, `Cmd`, `WorkingDir`, and
  `WINEPREFIX` env var were confirmed live against the real,
  currently-published `ghcr.io/projectreclaimer/project-reclaimer-dedicated:0.9.13`
  image** (`tests/test_dockerfile.py`'s `UpstreamImageLiveTests`, which ran
  successfully against the live registry during development of this egg,
  and re-runs automatically in CI on every push to catch a future upstream
  change before it silently breaks container startup).
- The install script fails fast (`set -euo pipefail`) and does not
  overwrite `bans.json` on reinstall.

### NOT verified (requires a real Docker host / Wings node / game files)

1. **The Dockerfile builds successfully in real CI** (confirmed: GitHub
   Actions runs `38166409350` and `38167643842` both built the image; see
   below for what each of those runs then found and fixed at runtime).
   Before using this in production, still run it yourself:
   ```bash
   docker build -t project-reclaimer-pterodactyl:test .
   ```
   and work through `tests/test-runtime.sh` (Tests A/B/C) against the
   result. CI (`.github/workflows/validate.yml`) does this on every push,
   but a failure there due to the base image being rate-limited from
   GitHub's runners is a known possibility, not necessarily a Dockerfile
   bug — check the error message. The build and runtime-test steps are
   separate jobs (`docker-build` and `docker-runtime-tests`), specifically
   so a Dockerfile/pull problem and a runtime test failure are never
   conflated into one ambiguous result.

   The first real CI run against this repository (GitHub Actions run
   `38166409350`) did build successfully and Test A's own assertions did
   pass, but its cleanup trap then failed with "Permission denied" trying
   to remove files the container had written as root inside its
   bind-mounted temp directory, using the unprivileged runner's own UID —
   and because the three runtime tests were invoked as separate sequential
   `run:` lines, that one failure aborted the whole step before Tests B
   and C ever got to execute. Fixed: `tests/lib/cleanup.sh`'s `safe_rm_rf`
   removes files via a throwaway root container when a plain host-side
   `rm -rf` fails (root inside a standard container can always remove
   files regardless of which UID wrote them); Tests A and B now also run
   the container under test as the calling user's own UID so this
   fallback is rarely needed for them in the first place; and CI now
   invokes `tests/test-runtime.sh` (which runs A, then B, then C,
   unconditionally) instead of three independent steps that could abort
   the run partway through. While fixing this, a related, previously
   unexercised bug in Test C was also found and fixed: it asserted a
   specific non-root UID could write into the bind mount without first
   making that UID actually own it (Wings always chowns a server's real
   volume before starting its container; the test now primes the same
   ownership itself, via the same throwaway-root-container technique,
   before asserting anything about permissions).

   A second real CI run (`38167643842`) then built successfully and passed
   Test B, but Tests A and C both failed with "ERROR: /home/reclaimer/.wine
   is not the symlink this image's Dockerfile is supposed to create." —
   the `/home/reclaimer` permissions bug described in full under "Verified
   upstream image metadata" above, now fixed (`chmod 755
   /home/reclaimer`), with a new regression test
   (`tests/test-runtime-e-wine-prefix.sh`) that actually runs
   `reclaimer-entrypoint prepare-prefix` under a non-root UID end to end,
   not just the symlink check in isolation. This fix has been committed
   but **not yet re-verified against a real Docker daemon or a third CI
   run** — see below.

2. **Non-root execution of the symlink/filesystem setup itself has now
   been exercised in real CI (`38167643842`, with a confirmed root cause
   and fix — see above), and the `prepare-prefix` codepath specifically
   has been reasoned through in detail against the actual extracted
   upstream script, but a real end-to-end `prepare-prefix` run under a
   non-root UID has not yet been confirmed to pass.** That is exactly what
   the new `tests/test-runtime-e-wine-prefix.sh` checks, but it has not
   yet been run against a real Docker daemon (none was available while
   writing it). Run `tests/test-runtime-c-nonroot-fs.sh` and
   `tests/test-runtime-e-wine-prefix.sh` (both automated, no game assets
   needed) and, ideally, `tests/test-runtime-d-full-startup.sh` (manual,
   real assets) on a real Docker host before production use.

3. **No verified "server is ready" console string exists.** Neither the
   available Project Reclaimer documentation nor the extracted
   `reclaimer-entrypoint` script (which simply `exec`s into the Wine
   process once `dedicated check` passes, without printing its own
   "ready" marker) provides a literal, guaranteed log line equivalent to
   (for example) Minecraft's `"Done ("`. Rather than invent one,
   `egg-project-reclaimer.json`'s `config.startup.done` is left as `{}`
   (empty), so Wings falls back to its own process-based heuristic
   instead of a true readiness string. **Action required:** once you have
   a real server running, capture its console output around the point
   players can actually join (this will be the Windows game executable's
   own stdout, forwarded through Wine), look for a stable, repeatable
   line, and add it to the egg's Startup Configuration in the Panel
   (Process Management → Startup Configuration).

4. **The default pinned upstream version (`RECLAIMER_VERSION=0.9.21` in the
   Dockerfile) has been confirmed to exist** via a live registry query (see
   "Verified upstream image metadata" above). It was the official latest release
   on October 20, 2026. Run `tests/test_dockerfile.py` (or pull that exact tag)
   before building; review any future version change separately. The .21 image
   retains every .20 filesystem layer except the executable; the current assessment
   is in [UPSTREAM-0.9.21.md](UPSTREAM-0.9.21.md), with earlier rollback identities
   preserved in [UPSTREAM-0.9.20.md](UPSTREAM-0.9.20.md).

5. **End-to-end gameplay has not been tested**: no client connected, no
   match was played, server-browser visibility from another network was
   not confirmed, RCON was not exercised, and graceful shutdown timing
   under real game load was not measured. This remains Test D
   (`tests/test-runtime-d-full-startup.sh`), to be done by someone with a
   Docker host, a Wings node, and legally obtained Halo 3 files — see that
   script for the exact manual checklist.

## The Startup Command field

By design (see README "How upstream's internals were verified"): this
egg's compatibility image preserves and directly invokes upstream's real
`reclaimer-entrypoint start` program, now honoring Pterodactyl's standard
`$STARTUP` mechanism the way the official custom-image guide's example
entrypoint does. There is, however, only one verified-correct value for it
(`reclaimer-entrypoint start`, the egg's default) — changing it to anything
else requires knowing upstream's other subcommands (`prepare-prefix`,
or running `dedicated`/`project-reclaimer` directly), which are internal
implementation details, not a general-purpose shell command field. Most
admins should never need to change this field at all.

## Common failure scenarios

| Symptom | Likely cause | What to check / do |
| --- | --- | --- |
| Container exits immediately with "ERROR: ... is not the symlink this image's Dockerfile is supposed to create" | Historically (fixed, see "Verified upstream image metadata" → `/home/reclaimer` permissions): `/home/reclaimer` being mode 0700 denied any non-root, non-UID-1000 process even traversal, which looks identical to the symlink not existing. If this recurs: the image was built from an older/modified Dockerfile missing the `chmod 755 /home/reclaimer` fix, or upstream changed its own `/server`/`/cache`/`/home/reclaimer` layout | Rebuild from the current Dockerfile; run `tests/test-runtime-c-nonroot-fs.sh` or `-e-wine-prefix.sh` to confirm a non-root UID can actually reach these paths; if upstream genuinely changed its layout, `tests/test_dockerfile.py`'s live tests will also start failing in CI and point at what changed |
| Container exits immediately with "the Wine prefix ... belongs to another user" | `reclaimer-entrypoint prepare-prefix` did not run, or `/home/container` is not actually writable by the UID Wings assigned (unexpected; check Wings itself) | Confirm `docker/entrypoint.sh` step 5 ran and succeeded in the log before this; if it's missing entirely, the image may not have rebuilt correctly |
| Console shows "Required game assets are missing" and the server does not start | `game/halo3/halo3.dll` or `game/halo3/maps/shared.map` not uploaded | Upload them per INSTALL.md step 4; this is a deliberate hard failure, not a bug |
| Console shows Wine errors (missing DLL, crash) | Runtime dependency missing inside the *runtime* Docker image, or corrupted/incomplete asset upload | Confirm the upload matches upstream's expected layout exactly (case-sensitive paths under `game/halo3/...`); re-run `dedicated init --from` and re-upload if unsure |
| Incorrect Docker permissions / "permission denied" writing files | Should not happen: `/server`, `/cache`, and the Wine prefix are symlinked onto `/home/container` at build time, which Wings always makes writable by whatever UID it assigns at runtime (see "Verified upstream image metadata"). If it does happen, it indicates either a Wings misconfiguration (confirm with `id pterodactyl` on the Wings host and check `/var/lib/pterodactyl/volumes/<server-uuid>` ownership matches) or a path this wrapper did not account for | Check container logs for the exact failing path; may require extending `docker/entrypoint.sh`/`Dockerfile` with an additional symlink |
| Game port binds but shows "Address already in use" | Another server/process on the same Wings node is using that port | Pterodactyl allocations are unique per node; this should not happen unless an allocation was manually duplicated outside the Panel |
| Server browser never lists the server | `SERVER_PUBLIC` is `false` (hidden), the UDP port is not actually reachable from the internet (check the node's upstream firewall/security group, not just Wings), or `public_address` detection failed outbound | Confirm `SERVER_PUBLIC=true`; from another network run the client's server-status check against `<public IP>:<port>`; check container logs for "Hole punching ready" or an ipify detection failure |
| LAN connectivity works but WAN fails | Port not open at the Wings node's own host firewall / cloud security group (Wings publishing the Docker port is necessary but not sufficient — the host's own firewall still applies) | Open the UDP+TCP port at the OS firewall level on the Wings node itself, not just in Docker |
| Process exits immediately on every start, repeated restarts | Likely one of the Wine-prefix/symlink failures above; also check `dedicated.toml` for a syntax error if you hand-edited content outside the managed block | Check the full container log from the very first lines; validate your manual TOML edits upstream with `dedicated check` if you have access to a Windows/Linux copy of the binary outside Docker |
| RCON connection refused | `RCON_ENABLED=false`, password blank, server still starting, or attempting access from outside container loopback | Enable RCON in Startup and restart; use the existing Pterodactyl Console bridge inside the container. Public TCP access is not required. |
| Changes to `dedicated.toml` lost after restart | You edited inside the `# >>> PTERODACTYL MANAGED SERVER BLOCK >>> ... <<<` markers | That block is intentionally regenerated every start from egg variables; edit anything outside it instead, or use the corresponding egg variable |
| Broken/corrupted `dedicated.toml` after a manual edit | A stray marker comment, or unbalanced quotes in a hand-edited section | `configure.py` only ever replaces text between exact marker lines; if you deleted one marker but not the other, delete both manually and restart — a fresh managed block will be appended |
| Server stays "Starting" for 10–60+ seconds on its very first boot only | Expected: the Wine prefix is being initialized fresh for this server (see CONFIGURATION.md "First boot and the Wine prefix") | Wait; subsequent restarts should be much faster. If it never progresses past this, check the log for a Wine/Xvfb error from `reclaimer-entrypoint prepare-prefix` |
| Repeated startup failures after many restarts | Wings' own crash-detection may apply its usual backoff/restart limits regardless of this egg | Check Wings' own logs (`journalctl -u wings`) in addition to the container console |

## Where commands run

- **Your own development/publishing machine (not a Wings node):**
  `docker build`, `git tag vX.Y.Z && git push origin vX.Y.Z` (triggers
  `.github/workflows/publish.yml`), `python3 -m unittest discover`,
  `shellcheck`.
- **Docker host (one of the two Wings VMs, e.g. the Proxmox-hosted Ubuntu
  VM):** `docker pull`, `docker logs <container>`,
  `docker inspect`, host firewall commands (`ufw`, `iptables`).
- **Wings VM, outside any container:** Wings' own logs
  (`journalctl -u wings`), the Panel's assigned storage path under
  `/var/lib/pterodactyl/volumes/<server-uuid>` (this is the same directory
  mounted as `/home/container` inside the container), `id pterodactyl` (to
  check the actual UID/GID Wings assigns on this specific node).
- **Inside the running game container:** anything invoked via the Panel's
  console, or `docker exec -it <container> bash` if you need to poke
  around directly (e.g. to inspect `/home/container/server/dedicated.toml`
  or re-run `/pterodactyl/validate-assets.sh /home/container/server` by
  hand).

## Reporting problems

If you confirm a real upstream crash/bug while testing against the real
game, Project Reclaimer's own
[Discord](https://discord.gg/Y8t7HexMEy) is the right place, with the
server's `data/<server>/server.log`. For problems with this egg/wrapper
specifically (not upstream Project Reclaimer itself), open an issue against
this repository with full container logs from the very first line.

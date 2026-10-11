# Troubleshooting

## What has and has not been tested

Be precise about this before relying on the egg in production. This egg was
built in an environment **without Docker, without a Pterodactyl
Panel/Wings install, and without network access to pull the private
upstream image**. The following reflects exactly that.

### Verified (static analysis / unit tests, see `tests/`)

- `egg-project-reclaimer.json` is valid JSON and structurally matches the
  documented PTDL_v2 fields (`tests/test_egg.py`, also run in CI).
- `docker/configure.py`'s `dedicated.toml` generation/patching logic is
  correct, idempotent, preserves hand-edited content outside its managed
  block, correctly escapes special characters (quotes, backslashes) in
  server names, truncates overlong names, and rejects invalid ports
  (`tests/test_config.py`, also run end-to-end manually; see its output in
  the project's implementation history).
- The install script fails fast (`set -euo pipefail`) and does not
  overwrite `bans.json` on reinstall.

### NOT verified (requires a real Docker host / Wings node / game files)

1. **The Dockerfile has never been built.** No Docker engine was available.
   Before using this in production, run:
   ```bash
   docker build -t project-reclaimer-pterodactyl:test .
   ```
   and fix anything that surfaces. CI (`.github/workflows/validate.yml`)
   will attempt this build on every push, but a failure there due to the
   base image being private/rate-limited from GitHub's runners is a known
   possibility, not necessarily a Dockerfile bug — check the error message.

2. **The "inherit upstream's CMD" mechanism is unverified against the real
   image.** This egg's entrypoint relies on Docker's standard layering
   behavior (a child Dockerfile that sets `ENTRYPOINT` without setting
   `CMD` inherits the parent's `CMD` as `"$@"`). This is a documented,
   reliable Docker mechanic, but it has not been exercised against the
   actual `ghcr.io/projectreclaimer/project-reclaimer-dedicated` image
   because that image's contents could not be pulled/inspected here. It is
   possible the upstream image's own `ENTRYPOINT` performs required setup
   (e.g. starting Xvfb, initializing a Wine prefix, chowning files) that
   this wrapper's replacement of `ENTRYPOINT` discards. **Run
   `tests/test-runtime.sh` against the built image on a real Docker host
   before production use**, and if the container exits immediately or
   fails to start Wine/the game process, inspect the upstream image's
   layers (`docker history`, `docker inspect --format '{{json .Config}}'`)
   to confirm what its original `ENTRYPOINT`/`CMD` actually did, and adjust
   `docker/entrypoint.sh` accordingly.

3. **Non-root execution under Wings is unverified.** Wings always runs
   containers as the UID/GID that owns the mounted server volume, never as
   root, regardless of the image's own `USER`/default user. If upstream's
   real entrypoint assumes it starts as root (common for images that
   support `PUID`/`PGID` remapping via a root-to-user privilege drop), it
   may fail under Wings' enforced non-root execution. This wrapper sets
   `PUID`/`PGID` to the container's actual running UID/GID as a mitigation
   (making any internal chown/privilege-drop a no-op), but this has not
   been exercised against the real image.

4. **No verified "server is ready" console string exists.** The available
   Project Reclaimer documentation does not include a literal, guaranteed
   log line equivalent to (for example) Minecraft's `"Done ("`. Rather than
   invent one, `egg-project-reclaimer.json`'s `config.startup.done` is left
   as `{}` (empty), so Wings falls back to its own process-based "is it
   still running" heuristic instead of a true readiness string. **Action
   required:** once you have a real server running, capture its console
   output around the point players can actually join, look for a stable,
   repeatable line, and add it to the egg's Startup Configuration in the
   Panel (Process Management → Startup Configuration).

5. **The default pinned upstream version (`RECLAIMER_VERSION=0.9.13` in the
   Dockerfile) was not confirmed to exist via a live registry query.** It
   was taken from the most recent version number mentioned in the upstream
   documentation at the time this was written. Run
   `docker pull ghcr.io/projectreclaimer/project-reclaimer-dedicated:0.9.13`
   (or check the project's Discord/release notes) before building, and
   update the Dockerfile's default `ARG` if it has since moved on.

6. **End-to-end gameplay has not been tested**: no client connected, no
   match was played, server-browser visibility from another network was
   not confirmed, RCON was not exercised, and graceful shutdown timing
   under real game load was not measured. All of section 13
   ("Testing Requirements") under "Runtime validation" in the original
   brief remains to be done by someone with a Docker host, a Wings node,
   and legally obtained Halo 3 files.

## The Startup Command field does nothing

By design (see README "Architecture decision"): this egg's compatibility
image preserves the upstream image's own `CMD` and executes it directly.
Upstream's command does not read Pterodactyl's `STARTUP` environment
variable (it wasn't built for Pterodactyl), so changing the egg's Startup
Command field in the Panel has no effect on what actually runs. It is set
to a self-documenting placeholder rather than something that looks
functional but isn't.

## Common failure scenarios

| Symptom | Likely cause | What to check / do |
| --- | --- | --- |
| Container exits immediately after start | Upstream's real entrypoint logic was not preserved correctly (see unverified item 2 above) | `docker logs` the container; compare against `docker history ghcr.io/projectreclaimer/project-reclaimer-dedicated:<tag>` to see what the original image actually ran |
| Console shows "Required game assets are missing" and the server does not start | `game/halo3/halo3.dll` or `game/halo3/maps/shared.map` not uploaded | Upload them per INSTALL.md step 4; this is a deliberate hard failure, not a bug |
| Console shows Wine errors (missing DLL, crash) | Runtime dependency missing inside the *runtime* Docker image, or corrupted/incomplete asset upload | Confirm the upload matches upstream's expected layout exactly (case-sensitive paths under `game/halo3/...`); re-run `dedicated init --from` and re-upload if unsure |
| Incorrect Docker permissions / "permission denied" writing files | Wings chowns `/home/container` to the enforced container UID before start; our symlinks point *inside* that tree, so this should not happen — if it does, it indicates the upstream entrypoint is trying to write somewhere else (e.g. directly to `/cache` before our symlink exists, or to a path we didn't adapt) | Check container logs for the exact failing path; may require extending `docker/entrypoint.sh` with an additional symlink |
| Game port binds but shows "Address already in use" | Another server/process on the same Wings node is using that port | Pterodactyl allocations are unique per node; this should not happen unless an allocation was manually duplicated outside the Panel |
| Server browser never lists the server | `SERVER_PUBLIC` is `false` (hidden), the UDP port is not actually reachable from the internet (check the node's upstream firewall/security group, not just Wings), or `public_address` detection failed outbound | Confirm `SERVER_PUBLIC=true`; from another network run the client's server-status check against `<public IP>:<port>`; check container logs for "Hole punching ready" or an ipify detection failure |
| LAN connectivity works but WAN fails | Port not open at the Wings node's own host firewall / cloud security group (Wings publishing the Docker port is necessary but not sufficient — the host's own firewall still applies) | Open the UDP+TCP port at the OS firewall level on the Wings node itself, not just in Docker |
| Process exits immediately on every start, repeated restarts | Likely item 2 or 3 above; also check `dedicated.toml` for a syntax error if you hand-edited content outside the managed block | Check the full container log from the very first lines; validate your manual TOML edits upstream with `dedicated check` if you have access to a Windows/Linux copy of the binary outside Docker |
| RCON connection refused | `RCON_ENABLED=false` or `RCON_PASSWORD` blank (disables it by design); or connecting to `127.0.0.1` from outside the node | Set both variables; connect to the node's public IP/allocation port, or use an SSH tunnel as described in CONFIGURATION.md |
| Changes to `dedicated.toml` lost after restart | You edited inside the `# >>> PTERODACTYL MANAGED SERVER BLOCK >>> ... <<<` markers | That block is intentionally regenerated every start from egg variables; edit anything outside it instead, or use the corresponding egg variable |
| Broken/corrupted `dedicated.toml` after a manual edit | A stray marker comment, or unbalanced quotes in a hand-edited section | `configure.py` only ever replaces text between exact marker lines; if you deleted one marker but not the other, delete both manually and restart — a fresh managed block will be appended |

## Where commands run

- **Docker host (one of the two Wings VMs, e.g. the Proxmox-hosted Ubuntu
  VM):** `docker build`, `docker pull`, `docker logs <container>`,
  `docker inspect`, host firewall commands (`ufw`, `iptables`).
- **Wings VM, outside any container:** Wings' own logs
  (`journalctl -u wings`), the Panel's assigned storage path under
  `/var/lib/pterodactyl/volumes/<server-uuid>` (this is the same directory
  mounted as `/home/container` inside the container).
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

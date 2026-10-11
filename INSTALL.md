# Installation Guide

## 1. Build and publish the Docker image

The egg references `ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:latest`.
**Nothing has been published there yet** (see TROUBLESHOOTING.md) — build
your own copy first, either to publish to that same registry (if you have
access) or to point the egg's Docker Image field at your own registry.

```bash
git clone <this repository>
cd Project-Reclaimer-Pterodactyl-Egg
docker build -t project-reclaimer-pterodactyl:local .
```

Verify the upstream base image tag first (also re-checked automatically by
`tests/test_dockerfile.py`):

```bash
docker pull ghcr.io/projectreclaimer/project-reclaimer-dedicated:0.9.13
```

If that tag no longer exists, pass a current one:
`--build-arg RECLAIMER_VERSION=<version>`.

To publish to GHCR under this repository's own name, push a version tag
(`git tag v0.1.0 && git push origin v0.1.0`) or run
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) manually
from the Actions tab — see README.md "Publishing to GHCR" for exactly what
that workflow does and when it does (and does not) run.

## 2. Import the egg into Pterodactyl Panel

1. In the Admin area, go to **Nests** and either pick an existing Nest or
   create a new one (e.g. "Game Servers").
2. Open the Nest, click **Import Egg**, and upload
   [`egg-project-reclaimer.json`](egg-project-reclaimer.json).
3. Open the imported egg and edit its **Docker Images** field to whichever
   image you built/published in step 1.
4. Review the **Variables** tab — defaults are sensible for a small
   open server, but confirm nothing conflicts with your setup.

## 3. Create a server

1. Create a new server using the Project Reclaimer egg.
2. Assign **one primary network allocation**. That single port is used for
   both the game (UDP) and, if enabled, RCON (TCP) — no additional
   allocations are required (see [CONFIGURATION.md](CONFIGURATION.md#networking)).
   Wings publishing this port through Docker is **not** the same as it being
   reachable from the internet: also open the same UDP+TCP port number at
   the Wings node's own OS firewall (e.g. `sudo ufw allow 49176` on Ubuntu)
   and in any upstream cloud/provider security group, or players on the
   public internet will not be able to join even though the server runs fine.
3. Set resource limits (see README.md "Resource recommendations"); 2 vCPU /
   3 GB RAM / 10 GB storage is a reasonable starting point for a single
   standard server, subject to how many maps you upload.
4. Set the egg variables (Server Name, Max Players, Playlist, etc.) — see
   [CONFIGURATION.md](CONFIGURATION.md) for the full reference.
5. Click **Create**. The install container will run
   [`scripts/install.sh`](scripts/install.sh), creating the persistent
   directory skeleton under the server's file manager (`game/`, `content/`,
   `playlists/`, `data/`, `bans.json`).

## 4. Upload your Halo 3 game assets

Project Reclaimer and this egg **do not include or download any Halo 3
files**. You need your own copy of Halo 3 from Halo: The Master Chief
Collection (Steam), installed on a Windows PC.

### Recommended: use `dedicated init --from` once, then upload the result

On the Windows PC with the game installed:

```powershell
.\project-reclaimer.exe dedicated init C:\reclaimer-upload --from
```

This copies exactly the files a server needs (including `shared.map`,
`campaign.map`, and `040_voi.map` for Forge's campaign vehicles/AI) into
`C:\reclaimer-upload\game`. Add `--maps "Guardian,Valhalla"` to copy only
specific maps, or `--maps campaign` to include the full campaign for
campaign co-op.

Then upload the resulting `game/` folder's **contents** into this server's
`game/` folder via SFTP (credentials are on the server's Panel page) or the
Pterodactyl File Manager, preserving the folder structure:

```
game/halo3/halo3.dll
game/halo3/maps/shared.map
game/halo3/maps/<MapName>.map   (one per map you host)
game/halo3/maps/campaign.map    (optional)
game/halo3/maps/040_voi.map     (optional)
```

### Manual alternative

If you cannot run `dedicated init`, copy the equivalent files by hand from
your MCC installation's `halo3` folder, preserving the same paths.

### Validation

The container validates required files (`halo3.dll`, `shared.map`) on every
start and **refuses to start** with a clear console error if they are
missing. It will start (with a warning) if only optional files
(`campaign.map`, `040_voi.map`, or additional maps) are missing, but
features depending on them will not work until you upload them.

## 5. Set a playlist or map, then start

- To run a playlist, upload your `.playlist.json` file into this server's
  `playlists/` folder and set the **Playlist** variable to its path, e.g.
  `playlists/community.playlist.json`.
- To run a single map/game type instead, leave Playlist blank and set
  **Map** / **Game Type** (e.g. `Guardian` / `Slayer`).
- Leaving all three blank uses upstream's own default (Slayer on Guardian).

Click **Start**. The very first start takes longer than usual (roughly
10–60 seconds) while a Wine prefix is initialized for this server — see
CONFIGURATION.md "First boot and the Wine prefix"; this is expected, not a
hang. Watch the console for asset-validation and startup messages. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) if it does not come up cleanly —
in particular, note that **automatic "server is ready" detection in the
Panel UI has not been verified** (see that document); rely on the console
output itself to confirm the server is actually up.

## 6. Connect with a Halo 3 client

Open Project Reclaimer's client, open the **Server Browser**, and look for
your server's name (public servers appear automatically within about a
minute of starting, via the project's public master servers). Alternatively
use **Direct Connect** with the node's public IP/DNS name and the port you
assigned.

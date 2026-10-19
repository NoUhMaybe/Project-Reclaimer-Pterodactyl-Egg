# Installation Guide

## 1. Obtain the published Docker image

Open the [latest published stable release](https://github.com/NoUhMaybe/Project-Reclaimer-Pterodactyl-Egg/releases/latest)
and use its validated `egg-project-reclaimer.json` attachment when available.
Source-code archives are not the standalone egg attachment. If an attachment is
missing, report it or use the JSON from that exact release tag; do not substitute
a development egg. The older v0.1.0 release currently lacks its promised attachment.

This maintenance branch prepares **egg v0.1.1**, selecting
`ghcr.io/nouhmaybe/project-reclaimer-pterodactyl:v0.1.1`, with **server and client
0.9.20**, on **linux/amd64**. Its previous tag/image are already published and
refer to older source, while its GitHub Release was deleted. Do not treat those
identifiers as the corrected release. Complete [RELEASING.md](RELEASING.md)
before using a newly released candidate. No local Docker build is required for
a validated published image.

Advanced users can build an image with `docker build -t project-reclaimer-pterodactyl:local .`.
The upstream base image remains pinned to 0.9.20. Use exact version-matched
0.9.20 clients, and back up the existing image selection and configuration before
an approved upgrade test.
See [the publishing workflow](.github/workflows/publish.yml) for tagged releases.

## 2. Import the egg into Pterodactyl Panel

1. In the Admin area, go to **Nests** and either pick an existing Nest or
   create a new one (e.g. "Game Servers").
2. Open the Nest, click **Import Egg**, and upload
   [`egg-project-reclaimer.json`](egg-project-reclaimer.json).
3. Confirm **Docker Images** matches the validated release's immutable version
   reference. Do not leave a stale development tag selected.
4. Review the **Variables** tab — defaults are sensible for a small
   open server, but confirm nothing conflicts with your setup.

## 3. Create a server

1. Create a new server using the Project Reclaimer egg.
2. Assign **one primary network allocation**. That single port is used for
   both the game (UDP) and, if enabled, RCON (TCP) — no additional
   allocations are required (see [CONFIGURATION.md](CONFIGURATION.md#networking)).
   Wings publishing this port through Docker is **not** the same as it being
   reachable from the internet: allow **UDP** on the Wings node's own OS firewall
   (e.g. `sudo ufw allow 49176/udp` on Ubuntu), and forward UDP on the router
   and in any upstream cloud/provider security group, or players on the
   public internet will not be able to join even though the server runs fine.
3. Set resource limits (see README.md "Resource recommendations"); 2 vCPU /
   3 GB RAM / 10 GB storage is a reasonable starting point for a single
   standard server, subject to how many maps you upload.
4. Set the egg variables (Server Name, Max Players, Playlist, etc.) — see
   [CONFIGURATION.md](CONFIGURATION.md) for the full reference.
5. Click **Create**. The install container will run
   [`scripts/install.sh`](scripts/install.sh), creating the persistent
   directory skeleton under the server's file manager (`server/game/`, `server/content/`,
   `server/playlists/`, `server/data/`, `server/bans.json`).

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
`server/game/` folder via SFTP (credentials are on the server's Panel page) or the
Pterodactyl File Manager, preserving the folder structure:

```
server/game/halo3/halo3.dll
server/game/halo3/maps/shared.map
server/game/halo3/maps/<MapName>.map   (one per map you host)
server/game/halo3/maps/campaign.map    (optional)
server/game/halo3/maps/040_voi.map     (optional)
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
  `server/playlists/` folder and set the **Playlist** variable to its path, e.g.
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

Use a Project Reclaimer client matching the server's exact version (0.9.20 for
this branch), open the **Server Browser**, and look for
your server's name (public servers appear automatically within about a
minute of starting, via the project's public master servers). Alternatively
use **Direct Connect** with the node's public IP/DNS name and the port you
assigned.

## 7. Interactive web-console commands

The manager is included when building the wrapper from this branch; existing
published tags keep their original behavior until a separately approved image
publication/deployment. In the Console command field submit `menu`, then select
a number. `exit` returns to ordinary RCON and keeps the game running. `stop`
and Panel Stop retain graceful shutdown. No extra port or Panel modification is
needed. Follow [CONSOLE-MANAGER.md](CONSOLE-MANAGER.md) to create a rotation and
[WINGS-VALIDATION.md](WINGS-VALIDATION.md) before accepting the new image.

The manager's playlist activation is authoritative over Startup defaults. Use
Configuration option 7 to validate/generate TOML and request reload, or restart.
Option 3 resets that authority. New in .20 support: native playlist new/show,
native content discovery, admin/pardon, welcome/voice scopes, reload and camera
policy. Native validation requires installed owned game assets; activation from
a single map to a playlist can require an idle restart. Follow
[the upgrade checklist and rollback procedure](WINGS-VALIDATION.md).

To administer the live server from the Pterodactyl Console tab, set
**Enable RCON** to `true` and set a strong **RCON Password** (8–128 characters)
under Startup, then restart the server. RCON binds to `127.0.0.1` **inside
the container only**; do not forward the TCP game allocation to the internet.

Run `help`, `maps`, `modes`, `players`, `load Valhalla Slayer`,
`load "The Pit" "Capture the Flag"`, `nextmap Guardian Slayer`,
or `help nextmap` in the Pterodactyl Console command field.
The bridge runs the upstream `dedicated rcon` CLI and returns its output.
RCON map-changing commands can **queue** a game for the next lobby rather
than immediately loading it. `startvote playlist` requires an active playlist.

The normal Stop and Start buttons were verified on Wings with `v0.1.0-dev.3`.
Only administrators with console access should have command privileges.

## Panel export for a community catalog contribution

The release JSON is generated from repository source; it is not a Panel export.
After importing the corrected release into a test Nest, review its image,
Startup, Variables and install script, save it, then use the egg's **Export**
action in Panel. Compare that exported file against the release JSON, ignoring
only export metadata. Use the actual Panel export for the catalog requirement.

## Verified deployment and remaining limitations

On one Ubuntu Wings node, the image has started under a non-root UID, loaded
Halo 3 assets, hosted a complete Guardian Slayer match including next-round
rotation, and accepted interactive RCON commands. Stop and restart were
also verified with the `dev.3` console bridge. The operator subsequently reports
WAN connectivity and multiple simultaneous players working on the current
installation. This manager branch still needs its own live regression run.
A fresh import/install on a separate server and public browser discovery remain
separate checks.

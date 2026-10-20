# Existing bridge and manager boundaries

## Launch and supervision

```text
tini (PID 1)
  entrypoint.sh (setup, then exec Python)
    console_bridge.py (supervisor + stdin selector)
      reclaimer-entrypoint start (existing separate process group/session)
        upstream Wine/Xvfb/dedicated supervisor and game processes
      dedicated rcon <split command args> (one bounded request at a time)
      dedicated rcon --json --watch (lazy optional control-event observer)
      dedicated playlist/content (bounded native filesystem helper, private staging)
```

The upstream program owns its internal Wine/game supervision; this change does
not replace that architecture. `entrypoint.sh` still maps Startup variables,
creates persistent directories, invokes `configure.py`, validates uploaded
assets and prepares the per-UID Wine prefix before its final exec. Added image
integration consists of copying `manager/`, recording the upstream build tag and
creating the documented Images directory. The egg startup, stop signal and
published image selection are unchanged.

The game child inherits the bridge's stdout/stderr directly, and receives
`DEVNULL` stdin. Wings stdin belongs to the existing bridge. Its selector drains
bytes and splits complete lines without Python text-buffer/readline starvation
when several lines arrive together. A bounded serial worker handles prompts and
RCON/file operations; it never blocks the supervision loop waiting for input or
RCON. Input is bounded to 64 KiB per line, with 32 queued lines. Stop/quit/Ctrl+C
bypass the worker queue.

SIGINT and SIGTERM still request **SIGINT to the child process group**. The
existing escalation remains 15 seconds, SIGTERM, 5 seconds, SIGKILL. Signals do not
depend on menu state or RCON availability. Child exit codes propagate; input and
event workers are daemon threads, so they cannot keep a dead game container
running. Auxiliary RCON/native clients are killed during bridge cleanup. EOF unregisters
stdin; it does not terminate the game. Menus repaint only on operator actions.

## Independent backends

| Responsibility | Modules |
| --- | --- |
| Input/session/navigation | `session.py`, `parsing.py`, `menus.py` |
| Domain prompts | `playlist_ui.py`, `players_ui.py`, `administration_ui.py` |
| RCON subprocess transport/credentials | `rcon_client.py` |
| Runtime semantics/version gates | `commands.py`, `capabilities.py` |
| Optional control observation | `events.py`, via documented existing CLI |
| Persistent JSON/content/mod/config operations | `playlists.py`, `content.py`, `configuration.py`, `filesystem.py`, `native.py` |
| Presentation and read-only health | `formatting.py`, `diagnostics.py` |
| Process ownership/signal escalation | Existing `console_bridge.py` |

Persistent backends import no RCON client. The controller injects installed
references into playlist validation; backend tests use fixed inventories. No
filesystem action is encoded as an RCON command. The optional native playlist
validator (0.9.15+) is a fixed local CLI invocation, separate from RCON. On .20
it validates unsaved candidates before every save/copy/restore, using installed
game/content paths and private outputs under `.manager/staging`. Native bulk
creation becomes an in-memory draft until confirmed Save. No filesystem RCON
command is used. Native content has text output; structured map/mode pickers
continue to use RCON's documented entries/reference schema.

Explicit configuration Apply renders a private candidate beside dedicated.toml
(preserving relative paths), validates it with the native CLI, then atomically
replaces the managed TOML with backup and a digest check for intervening edits.
The controller then independently requests RCON reload, retaining the actual
server reply and optional reload control events. Failed validation leaves TOML
intact; failed reload leaves saved files and reports an unconfirmed live state.
Native staging strips Startup defaults and disables updates. JSON overrides
remain version 1; no persistent layout migration is needed.

## Storage and trust

Wings owns `/home/container` for its assigned non-root UID/GID. Build-time
symlinks remain `/server -> /home/container/server`,
`/cache -> /home/container/.cache/reclaimer`, and
`/home/reclaimer/.wine -> /home/container/.wine-prefix`. The manager uses the real
persistent paths, and rejects additional symlinked storage areas.

Game assets remain `server/game/`; content remains `server/content/{Maps,Game
Modes,Mods,Images}`; playlists remain `server/playlists/`; upstream logs/instance
files remain `server/data/`. New manager authority is `server/.manager/overrides.json`.
Backups stay next to each bounded storage area under `.backups/`. No draft files
are shared between processes.

RCON stays loopback-only inside the container. The local CLI discovers its
credentials/host key from upstream files; they are not passed as argv flags.
The actual 0.9.13, 0.9.20 and 0.9.21 CLIs were tested against a fake WebSocket endpoint: each sends its
argv as `command` plus structured `args`, so the original bridge's `shlex.split`
approach is retained. Never join tokens into one CLI argument: the CLI treats
that as a command name. There is no shell interpolation in menu operations.

Panel/Wings console authorization is the privilege boundary. Pterodactyl does
not identify individual stdin submitters to the bridge. File Manager/SFTP users
can also modify persistent configuration; hash checks protect ordinary intervening
playlist edits, but the wrapper is not an isolation boundary against a malicious
privileged user replacing directories during a filesystem operation.

The existing Startup `eval` substitution is unchanged and remains privileged
Panel configuration, outside menu input handling. No new general shell executor,
network service or automatic Workshop installer is added. The isolated .20
publication uses the existing guarded manual workflow; it does not deploy.

The .13/.20 upstream entrypoint scripts are byte-identical, and .21 retains
all .20 filesystem layers except the bundled executable. The metadata and layout
contracts are unchanged. See [the current audit](UPSTREAM-0.9.21.md) and
[capability matrix](CAPABILITIES.md).

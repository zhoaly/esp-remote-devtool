# Server deployment: Ubuntu, macOS and Windows

The service host runs Python 3.10+; compiler toolchains run in **Linux Docker
containers**. Ubuntu uses Docker Engine. macOS and Windows use Docker Desktop
(Windows must select Linux containers). Apple Silicon uses ARM64 images by
default; pin image versions that provide the desired architecture.

## Install and run

From the repository root, use the same commands in PowerShell, Bash or zsh:

```text
python server/manage.py install
python server/manage.py doctor
python server/manage.py start
```

Use `python3` instead of `python` on hosts that name Python that way. The launcher
automatically uses `server/.venv` after installation. Do not copy a virtual
environment between operating systems; install a fresh one on each host.
`install --dev` installs the test dependencies too. The existing `.sh` launchers
and new `.ps1` launchers are thin wrappers around this entry point.

Optionally copy `server/.env.example` to `server/.env` and edit it. Configuration
precedence is explicit command-line paths, existing environment, then `.env`.
Values are parsed as dotenv data, never executed as shell commands. Relative
workspace configuration paths resolve against `ESP_SERVER_BASE_DIR`, not the
shell's working directory. Prefer absolute paths in background-service configs.

`start` verifies that a Linux Docker engine is available, runs Alembic migrations,
then supervises the API and independent FIFO worker. A child failure stops its
siblings and returns a failure status to the OS service manager. A second server
or worker for the same data directory is rejected by file locks.

```text
python server/manage.py stop
```

Stop requests allow active builds to stop and clean up their named containers;
queued jobs stay queued. A restarted worker marks jobs left running after an
unclean shutdown as interrupted and removes their old containers. `api` and
`worker` commands are available for separate service managers; run `migrate`
while all service processes are stopped before using them. `start
--skip-docker-check` permits API-only testing without a working compiler engine;
submitted builds will fail until Docker is available.

`doctor` reports Python/dependency versions, architecture, data-directory write
access and Docker engine OS/resources. It does not pull compiler images or
claim that a real firmware build has passed. Verify the chosen ESP-IDF image and
Emscripten image with real projects when commissioning a new host.

## Storage and migration

`ESP_SERVER_DATA_DIR` defaults to `ESP_SERVER_BASE_DIR/data`. Use **local,
non-synced storage** for SQLite, uploads, workspaces, logs and compiler caches.
Do not actively run SQLite WAL files from OneDrive, iCloud, SMB or a shared
network directory. The code and static assets may live separately from data.
SQLite WAL, foreign keys and the existing busy timeout remain enabled.

New managed file paths are stored relative to the data root. Existing absolute
paths from the current OS remain readable. To move existing data across hosts:

1. Stop the old API and worker, including old systemd units or OS startup jobs.
2. Back up and copy the entire data directory after shutdown. Keep a backup of
   the old code and database for rollback: old code cannot read new relative paths.
3. Install dependencies on the destination and set `ESP_SERVER_DATA_DIR` there.
4. Preview conversion using the old **data** directory, not the old server root:

```text
python server/manage.py relocate-data --old-root /home/zhaoly/repos/esp-remote-devtool/server/data
python server/manage.py relocate-data --old-root /home/zhaoly/repos/esp-remote-devtool/server/data --apply
```

Windows source roots such as `C:\ESP\server\data` are accepted on a Mac/Linux
host too. Quote paths containing spaces. Repeat `--old-root` for multiple old
roots. Apply mode creates `server.db.before-relocate-*.bak` using SQLite's backup
API, then updates paths transactionally. Dry-run mode does not commit changes.
Stop all standalone API/worker processes first. The tool refuses active worker
locks and running job records; resolve an unclean shutdown on the original host
before moving. It converts managed paths only: update external workspace entries
in `config/workspaces.json` and `LVGL_*_DIR` settings for the destination.

After migration, check historical logs/downloads, previews and existing OTA
firmware, then test a new ESP and LVGL build. Configure
`ESP_OTA_PUBLIC_BASE_URL` to the stable URL reachable by your ESP devices; a
Tailscale-only address is usable only by clients with a route to it. Existing
public APIs remain `/api/v2`; no frontend or Local Agent upgrade is required
solely for these server portability changes.

## Docker paths, permissions and proxies

Host processes invoke the Docker CLI directly with argument lists and CSV-encoded
bind mounts, including Windows drive letters, spaces, Unicode and commas. The
Bash, `nproc` and other Linux commands in build instructions run **inside the
compiler container**. Docker must run on this host/context and must be able to
share the configured project and cache directories; an arbitrary remote Docker
context cannot mount this host's paths.

On Linux, build containers use the server user's UID:GID so output remains
writable. On macOS/Windows the container image's default user is used, with Docker
Desktop handling file sharing. `ESP_DOCKER_USER` can explicitly override this.
Keep `ESP_DOCKER_PLATFORM` unset for native execution or select `linux/amd64` /
`linux/arm64` deliberately; emulation is not a guaranteed substitute for a
compatible toolchain image. Set `ESP_DOCKER_EXECUTABLE` to an absolute CLI path
when a background service has a minimal PATH.

Configure Docker Engine/Desktop's pull proxy independently from compiler
container traffic. The latter can use `ESP_BUILD_HTTP_PROXY`,
`ESP_BUILD_HTTPS_PROXY`, `ESP_BUILD_ALL_PROXY` and `ESP_BUILD_NO_PROXY`.
`127.0.0.1` inside a container is that container. On Desktop use a reachable host
endpoint such as `host.docker.internal:7890`; on Linux explicitly configure a
reachable proxy address. Do not assume that a proxy listening only on the host's
loopback interface is accessible through its LAN/gateway address. Proxy values
are redacted from command headers, but build tools may print their own settings.

The allowed ESP-IDF image list, disabled-by-default custom images, ESP/LVGL build
timeouts and job retention settings retain their existing meanings. Terminal
record retention defaults to 100 per kind; queued/running jobs and builds
referenced by live OTA releases are protected.

## Background startup

Generate configurations **on the target host**, after installation. Generation
does not install or start a service. Put persistent settings in `.env`; generated
configs pin the Python executable, source/data directories and Docker CLI, and
read the selected `.env` when starting. Do not run the new supervisor alongside
the old migration/API/worker systemd units. Disable those units before switching.

### Ubuntu (systemd user unit)

```sh
python3 server/manage.py service-config --target systemd --output "$HOME/.config/systemd/user/esp-remote.service"
systemctl --user daemon-reload
systemctl --user enable --now esp-remote.service
```

The user needs Docker access. A user unit runs after login unless lingering is
enabled by the administrator. For a system-wide deployment, adapt the generated
unit with the appropriate `User`, install target and local security policy. The
existing `install_systemd.sh` remains a Linux-specific alternative for separate
API/worker services. Use the generated single-supervisor unit for the common
cross-platform startup flow.

### macOS (launchd user agent)

```sh
python3 server/manage.py service-config --target launchd --output "$HOME/Library/LaunchAgents/net.zlyhub.esp-remote.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/net.zlyhub.esp-remote.plist"
```

Docker Desktop must finish starting and have access to shared folders. Launchd
restarts the service if Docker is not ready initially. Logs go to the configured
data `logs` directory. A LaunchAgent runs in the logged-in user session; boot
before login requires a separately designed LaunchDaemon/container-engine setup.
For a persistent stop, `launchctl bootout` the plist; its KeepAlive setting would
restart a process stopped only through `manage.py stop`. Verify AC power,
system sleep, closed-lid behavior and recovery after a real reboot before using
a laptop for continuous service.

### Windows (Task Scheduler at user logon)

```powershell
python server/manage.py service-config --target windows --output "$env:TEMP/esp-remote-task.xml"
schtasks /Create /TN ESPRemoteBuild /XML "$env:TEMP/esp-remote-task.xml" /F
schtasks /Run /TN ESPRemoteBuild
```

The generated task runs in the current interactive user context, retries failures
and has no execution time limit. It is a logon task, not a native Windows SCM
service or a guarantee of operation before login. Docker Desktop must use that
user's running Linux engine. Configure durable settings in `.env`, and use
`manage.py stop` for a graceful manual stop. Review the generated task before
registering it; generate it again after relocating Python or the source tree.

## HTTPS reverse proxy

The Caddy Compose project publishes 80/443 and reaches the host API through
`host.docker.internal`; it no longer requires host networking. On Linux,
`host-gateway` supplies that name. Keep the API bound to an address reachable
from the Docker gateway (default `ESP_SERVER_HOST=0.0.0.0`). Override
`ESP_PUBLIC_HOST` and `ESP_CADDY_UPSTREAM` in `.env` when needed.

```sh
cd server
docker compose -f compose.https.yaml up -d
```

The domain's A/AAAA record and incoming ports must reach this host. Certificates
persist in Docker volumes. `ESP_SERVER_IPV6_PROXY=1` optionally starts the
existing IPv6-only TCP forwarder alongside the IPv4 API; do not enable it when
the API already occupies the same IPv6 address/port.

## Verification

```text
python server/manage.py install --dev
```

Set `PYTHONPATH=server` in the current shell, then run:

```text
python -m pytest -q server/tests_py
python -m ruff check server/app server/manage.py server/tests_py server/migrations
```

Use the installed venv interpreter (Windows `server/.venv/Scripts/python.exe`,
Ubuntu/macOS `server/.venv/bin/python`) for these commands. CI runs the server
suite on Ubuntu, macOS and Windows with Python 3.10 and 3.14. Set
`ESP_TEST_DOCKER=1` to additionally run real Linux-container tests for Unicode /
space / comma bind paths and timeout cleanup. These pull a small test image and
do not compile ESP firmware. Real ESP-IDF/LVGL builds remain deployment acceptance
checks against the selected compiler versions and project sources.

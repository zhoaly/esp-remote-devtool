# Architecture

The repository has two runtime components:

- `server/`: a FastAPI API and independent worker running on Ubuntu, macOS or Windows. The API validates requests and persists jobs; the worker performs ESP-IDF or LVGL builds in Linux Docker containers and records artifacts. Host orchestration and firmware packaging use Python; Bash is only required inside compiler images.
- `local-agent/`: a Windows FastAPI helper that compresses the local ESP-IDF workspace, uploads it to the server, enumerates COM ports, downloads firmware packages, and flashes devices with `esptool`.

The web UI is served by the remote server. It talks to the Windows agent on `127.0.0.1` for local-only operations and to `/api/v2` for job polling, incremental logs, OTA releases, and artifact download.

## Server layers

```text
API / Worker -> Services -> Repository / Builders -> Domain / Core
```

- `app/core`: environment configuration, paths, logging, and common errors.
- `app/domain`: job enums, validation schemas, and transition rules.
- `app/storage`: SQLAlchemy models, repositories, SQLite setup, and Alembic migrations.
- `app/services`: submissions, jobs, retention, workspaces, OTA, and worker orchestration.
- `app/builders`: secure extraction, process control, and ESP/LVGL build implementations.
- `app/api/v2`: thin HTTP routers; they do not access the database, filesystem, or subprocesses directly.

SQLite runs in WAL mode with foreign keys and a busy timeout. Queued jobs survive restarts. When a worker starts, any job left in `running` is changed to `interrupted`; retry always creates a new job linked through `retry_of_job_id`.

`manage.py start` supervises separate API/worker processes and optionally the IPv6
proxy. Children observe a shutdown marker and parent liveness, so normal stops
work on Windows without Unix signals. The worker uses a cross-platform file lock.
Build processes use POSIX process groups or Windows process-tree termination;
named Docker containers are removed on failure, cancellation and timeout.

Managed database paths are relative to `ESP_SERVER_DATA_DIR` (default:
`server/data`). Native legacy absolute paths remain readable. `relocate-data`
converts old Linux/Windows data roots after a stopped-data copy and backs up the
database before committing. Explicit external workspaces remain host-specific
and must be configured on each host. API routes and response formats are unchanged.

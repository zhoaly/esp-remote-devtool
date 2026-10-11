# Architecture

The repository has two runtime components:

- `server/`: a FastAPI API and independent worker running on Linux. The API validates requests and persists jobs; the worker performs ESP-IDF or LVGL Docker builds and records artifacts.
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

# ESP Remote Build Flash 0.2.0

A web-based ESP-IDF remote build and local flash tool.

## Features

- Upload a local ESP-IDF project from Windows through a local agent
- Persist build jobs in SQLite and execute them through an independent FIFO worker
- Build ESP-IDF and LVGL projects remotely inside Docker
- Cancel, retry, and recover queued jobs across API or worker restarts
- Package merged firmware and related flashing artifacts
- Download remote build artifacts and inspect build logs
- Enumerate local COM ports on Windows
- Flash ESP32 and ESP32-S3 devices through a local serial port

## Repository Layout

```text
server/       Linux remote build service and web UI
local-agent/  Windows upload and flash helper
docs/         Deployment, usage, and troubleshooting notes
release/      Release output placeholder
```

## Architecture

The browser talks to the remote API for job management and to the local Windows agent for local filesystem access and serial flashing. The API writes jobs to SQLite; an independent worker claims and runs them. All public server endpoints use `/api/v2`.

## Quick Start

### Server

```bash
cd server
./install_server.sh
cp .env.example .env
./start_server.sh
```

`start_server.sh` runs `alembic upgrade head`, then starts both the API and worker. Python 3.10 or newer is required for the server.

### Local Agent

```powershell
cd local-agent
.\install_agent.ps1
copy config.example.json config.json
.\start_agent.ps1
```

## Security Notes

- Do not commit `.env`, `config.json`, uploaded project archives, firmware archives, runtime logs, or merged firmware binaries.
- Server runtime data lives under `server/data/` and is excluded by `.gitignore`.
- Local build outputs and packaged executables are excluded by `.gitignore`.

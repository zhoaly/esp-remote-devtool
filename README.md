# ESP Remote Build Flash

A web-based ESP-IDF remote build and local flash tool.

## Features

- Upload a local ESP-IDF project from Windows through a local agent
- Build the project remotely inside an ESP-IDF Docker environment
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

The browser talks to the remote server for job management and to the local Windows agent for local filesystem access and serial flashing. The remote server never reads the Windows filesystem directly.

## Quick Start

### Server

```bash
cd server
./install_server.sh
cp .env.example .env
./start_server.sh
```

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

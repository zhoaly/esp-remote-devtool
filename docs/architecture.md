# Architecture

The repository has two runtime components:

- `server/`: a FastAPI service running on Linux that receives zipped ESP-IDF projects, builds them inside Docker, packages merged firmware, and exposes logs and artifacts over HTTP.
- `local-agent/`: a Windows FastAPI helper that compresses the local ESP-IDF workspace, uploads it to the server, enumerates COM ports, downloads firmware packages, and flashes devices with `esptool`.

The web UI is served by the remote server. It talks to the Windows agent on `127.0.0.1` for local-only operations and to the remote server for build job polling and artifact download.

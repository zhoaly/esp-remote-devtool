# Server Deploy

1. Copy the `server/` directory to the Linux host.
2. Install Docker and Python 3.10 or newer.
3. Run `./install_server.sh`.
4. Copy `.env.example` to `.env` and adjust values if needed.
5. Start the API and worker with `./start_server.sh`, or install the migration/API/worker systemd units with `./install_systemd.sh`.

The startup path always runs `alembic upgrade head` before either process starts. Runtime state is stored in `server/data/server.db`; SQLite WAL, foreign keys, and a 30-second busy timeout are enabled automatically.

For a 0.2.0 upgrade, stop the old service and back up `server/data/` first. V2 starts with an empty database and intentionally does not import or delete old JSON records, logs, uploads, or artifacts. Deploy the server, Web assets, and Local Agent in the same maintenance window because V1 server APIs are not retained.

For dual-stack access on hosts where the app is bound to IPv4, keep
`ESP_SERVER_HOST=0.0.0.0` and set `ESP_SERVER_IPV6_PROXY=1` in `.env`. The
startup script will run the main server on IPv4 and a local IPv6-only TCP proxy
on the same port.

To control the ESP-IDF versions shown on the build page, set
`ESP_ALLOWED_IDF_IMAGES` to a comma-separated list of Docker images. Keep
`ESP_ALLOW_CUSTOM_IDF_IMAGE=1` only if users may type a custom image name. It is disabled by default.

For OTA releases, set `ESP_OTA_PUBLIC_BASE_URL` to a stable externally
reachable origin, preferably a DDNS hostname instead of a raw IPv6 address:

```bash
ESP_OTA_PUBLIC_BASE_URL=http://zlyhub.serveblog.net:8000
```

The UI copies `ota check <latest-manifest-url>`. The latest manifest URL should
point to `/api/v2/ota/latest?...`, and the manifest JSON returned by that endpoint
contains a `url` field pointing to `/api/v2/ota/firmware/<release>`.

Build timeouts default to 3600 seconds for ESP and 1800 seconds for LVGL. Override them with `ESP_BUILD_TIMEOUT_SECONDS` and `LVGL_BUILD_TIMEOUT_SECONDS`. Cancellation sends SIGTERM to the complete build process group, waits up to 10 seconds, then sends SIGKILL and removes the named Docker container.

Runtime data is stored under `server/data/` and is intentionally excluded from Git. Terminal job retention defaults to the latest 100 records per build kind; queued and running jobs are never pruned, and a job referenced by a live OTA release is protected until that release is deleted.

## HTTPS reverse proxy

The included Caddy deployment terminates HTTPS for `zlyhub.top` and proxies to
the existing application on `127.0.0.1:8000`. The domain's A or AAAA record must
point to the server, and public ports 80 and 443 must reach the server.

```bash
cd server
docker compose -f compose.https.yaml up -d
```

Caddy stores certificates in persistent Docker volumes and automatically
redirects HTTP requests to HTTPS.

# Server Deploy

1. Copy the `server/` directory to the Linux host.
2. Install Docker and Python 3.
3. Run `./install_server.sh`.
4. Copy `.env.example` to `.env` and adjust values if needed.
5. Start the service with `./start_server.sh` or install systemd with `./install_systemd.sh`.

For dual-stack access on hosts where the app is bound to IPv4, keep
`ESP_SERVER_HOST=0.0.0.0` and set `ESP_SERVER_IPV6_PROXY=1` in `.env`. The
startup script will run the main server on IPv4 and a local IPv6-only TCP proxy
on the same port.

To control the ESP-IDF versions shown on the build page, set
`ESP_ALLOWED_IDF_IMAGES` to a comma-separated list of Docker images. Keep
`ESP_ALLOW_CUSTOM_IDF_IMAGE=1` if users may type a custom image name.

For OTA releases, set `ESP_OTA_PUBLIC_BASE_URL` to a stable externally
reachable origin, preferably a DDNS hostname instead of a raw IPv6 address:

```bash
ESP_OTA_PUBLIC_BASE_URL=http://zlyhub.serveblog.net:8000
```

The UI copies `ota check <latest-manifest-url>`. The latest manifest URL should
point to `/api/ota/latest?...`, and the manifest JSON returned by that endpoint
contains a `url` field pointing to `/api/ota/firmware/<release>/app.bin`.

Runtime data is stored under `server/data/` and is intentionally excluded from Git.

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

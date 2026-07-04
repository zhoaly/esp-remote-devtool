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

Runtime data is stored under `server/data/` and is intentionally excluded from Git.

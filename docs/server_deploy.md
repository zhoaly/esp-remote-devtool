# Server Deploy

1. Copy the `server/` directory to the Linux host.
2. Install Docker and Python 3.
3. Run `./install_server.sh`.
4. Copy `.env.example` to `.env` and adjust values if needed.
5. Start the service with `./start_server.sh` or install systemd with `./install_systemd.sh`.

Runtime data is stored under `server/data/` and is intentionally excluded from Git.

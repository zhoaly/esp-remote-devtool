# Troubleshooting

- If upload fails, confirm that the Windows agent is running and that `remote_build_url` points to the correct server.
- If the server build fails immediately, inspect `server/data/logs/<job>.log`.
- Run `python server/manage.py doctor` first for dependency, data-directory and Linux Docker checks (use `python3` on macOS/Ubuntu when needed).
- If the API is available but jobs stay queued, inspect supervisor/worker logs and verify that one worker owns the configured data directory's `worker.lock`.
- If startup reports a missing table, stop all service processes and run `python server/manage.py migrate`, or start them through `manage.py start`, which migrates before launching either process.
- Jobs left running by an abnormal worker stop become `interrupted` at the next worker start and must be retried explicitly.
- If Docker build fails, verify the ESP-IDF image tag and that Docker can run as the current user.
- A ready Docker engine does not prove image pulls work: check pull proxy, DNS and credential helper availability. The Python Docker runner adds Docker Desktop's helper directory to PATH; external shell commands may still need the application's `Contents/Resources/bin` directory on macOS.
- `stat: illegal option -- c` or `wait: -n: invalid option` means an old host-side shell workflow is still being invoked. Use the new Python launcher/builders, not a cached copy of the legacy scripts.
- If historical files disappear after moving hosts, preview `manage.py relocate-data --old-root <previous-data-directory>` before applying its backed-up path conversion. Also update externally configured workspaces.
- If flashing fails, confirm the COM port and that the board is not busy in another tool.
- If no serial ports are listed, reconnect the device and install the correct USB serial driver.

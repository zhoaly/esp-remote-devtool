# Troubleshooting

- If upload fails, confirm that the Windows agent is running and that `remote_build_url` points to the correct server.
- If the server build fails immediately, inspect `server/data/logs/<job>.log`.
- If the API is available but jobs stay queued, check `esp-remote-worker.service` and verify that only one worker owns `server/data/worker.lock`.
- If startup reports a missing table, run `server/.venv/bin/python -m alembic -c server/alembic.ini upgrade head` from the repository root or use `server/start_server.sh`.
- Jobs left running by an abnormal worker stop become `interrupted` at the next worker start and must be retried explicitly.
- If Docker build fails, verify the ESP-IDF image tag and that Docker can run as the current user.
- If flashing fails, confirm the COM port and that the board is not busy in another tool.
- If no serial ports are listed, reconnect the device and install the correct USB serial driver.

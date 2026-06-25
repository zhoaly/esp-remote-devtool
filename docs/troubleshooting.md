# Troubleshooting

- If upload fails, confirm that the Windows agent is running and that `remote_build_url` points to the correct server.
- If the server build fails immediately, inspect `server/data/logs/<job>.log`.
- If Docker build fails, verify the ESP-IDF image tag and that Docker can run as the current user.
- If flashing fails, confirm the COM port and that the board is not busy in another tool.
- If no serial ports are listed, reconnect the device and install the correct USB serial driver.

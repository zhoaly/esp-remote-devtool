# Local Agent Deploy

1. Open PowerShell in `local-agent/`.
2. Run `.\install_agent.ps1`.
3. Copy `config.example.json` to `config.json` and set `remote_build_url`.
4. Start the agent with `.\start_agent.ps1`.

The agent listens on `127.0.0.1:8765` by default and should run on the same Windows machine that has the ESP board connected.

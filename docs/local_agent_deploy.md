# Local Agent Deploy

## Recommended Windows installation

1. Run `release/ESPRemoteBuildAgentSetup-0.1.0-x64.exe`.
2. Keep **Start with Windows** unchecked unless the workstation should always expose
   the local Agent.
3. Launch **ESP Remote Build Agent** from the desktop or Start menu.
4. On first launch, enter the remote build upload URL in the settings window.

The application runs in the Windows notification area without a console window.
Right-click its icon to open the ESP tools, edit settings, inspect logs, restart the
Agent, or exit.

Runtime configuration and logs are stored under:

```text
%LOCALAPPDATA%\ESPRemoteBuildAgent\
```

The Agent listens on `127.0.0.1:8765`. If the tray icon reports a startup error,
check that another process is not already using that port.

## Source development

1. Open PowerShell in `local-agent/`.
2. Run `.\install_agent.ps1`.
3. Copy `config.example.json` to `config.json` and set `remote_build_url`.
4. Start the console Agent with `.\start_agent.ps1`.

The source workflow continues to read `local-agent/config.json`. Settings saved by
the packaged tray application take precedence from LocalAppData.

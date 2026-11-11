# Local Agent Deploy

## Recommended Windows installation

1. Run `release/ESPRemoteBuildAgentSetup-0.2.0-x64.exe`.
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

For V2, `remote_build_url` must end with `/api/v2/builds/esp/upload`. The Agent derives the LVGL upload and server information URLs from the same origin.

## Use several build servers

In `%LOCALAPPDATA%\ESPRemoteBuildAgent\config.json`, set `remote_build_servers` to a JSON
object mapping each browser origin to its V2 ESP upload URL. Use the scheme, host, and
port as shown in the browser address bar, without a path or trailing slash. Register
each IP address or DNS name you use to open a server. The Agent allows those origins
and routes ESP and LVGL local-path uploads to the server for the current tab.

`remote_build_url` is the default for command-line requests without an Origin header
and the server opened by the tray shortcut. Once a server map is configured, browser
build requests must come from a mapped origin or the default server's origin. The
legacy `allowed_origins` setting alone does not route uploads.

After editing the JSON, choose **重试 / 重启 Agent** from the tray. To check the destination
without uploading a project, run the following with the origin you want to verify:

```powershell
curl.exe -H "Origin: https://another-server.example" http://127.0.0.1:8765/
```

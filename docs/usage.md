# Usage

1. Start the Linux build server.
2. Start the Windows local agent.
3. Open the ESP toolset at `http://your-server:8000/tools/esp`.
4. Enter the local ESP-IDF project path.
5. Trigger remote build.
6. Wait for the job to finish and inspect logs if needed.
7. Refresh COM ports and flash the packaged firmware.

## ESP page defaults

Open `/tools/esp/settings` to configure the initial values used by the remote compile, local flash, and OTA release pages. These preferences are stored in the current browser, so they can include workstation-specific values such as a Windows project path or preferred COM port without changing the remote server configuration.

Use **Restore factory defaults** on the settings page to clear the saved browser preferences.

Open `/tools/lvgl/settings` to configure the LVGL simulator build defaults, including the source mode, local upload mode, project path, UI-package entry fields, project name, and preview dimensions. Remote workspace metadata continues to override the project name, dimensions, and LVGL version when that source mode is selected.

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found. Run install_agent.ps1 first."
}

& $PythonExe -m pip install pyinstaller
& $PythonExe -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --name ESPRemoteBuildAgent `
    (Join-Path $ProjectRoot "src\\agent_main.py")

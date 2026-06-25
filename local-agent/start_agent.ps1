$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

& $PythonExe (Join-Path $ProjectRoot "src\\agent_main.py")

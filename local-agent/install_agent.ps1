$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"

python -m venv (Join-Path $ProjectRoot ".venv")
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host "Local agent environment installed at $ProjectRoot"

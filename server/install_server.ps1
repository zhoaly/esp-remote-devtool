$ErrorActionPreference = 'Stop'
$pythonBin = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonBin)) { $pythonBin = 'python' }
& $pythonBin (Join-Path $PSScriptRoot 'manage.py') install @args
exit $LASTEXITCODE

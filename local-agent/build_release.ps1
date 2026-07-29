param(
    [switch]$SkipInstaller,
    [switch]$SkipTests,
    [switch]$UseExistingEnvironment,
    [switch]$UseExistingBundle
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ProjectRoot
$BuildVenv = Join-Path $ProjectRoot ".build-venv"
$BootstrapPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Version = (Get-Content -Raw -LiteralPath (Join-Path $RepositoryRoot "VERSION")).Trim()
$AssetsDir = Join-Path $ProjectRoot "assets"
$VersionFile = Join-Path $ProjectRoot "build\version_info.txt"
$SpecFile = Join-Path $ProjectRoot "packaging\ESPRemoteBuildAgent.spec"
$ReleaseDir = Join-Path $RepositoryRoot "release"
$AgentExe = Join-Path $ProjectRoot "dist\ESPRemoteBuildAgent\ESPRemoteBuildAgent.exe"

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "The release build requires 64-bit Windows."
}

if (-not $UseExistingBundle) {
    if (-not (Test-Path -LiteralPath $BootstrapPython)) {
        $BootstrapPython = (Get-Command python -ErrorAction Stop).Source
    }

    if ($UseExistingEnvironment) {
        $BuildPython = $BootstrapPython
    }
    else {
        $BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
        if (Test-Path -LiteralPath $BuildVenv) {
            $resolvedBuildVenv = (Resolve-Path -LiteralPath $BuildVenv).Path
            $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
            if (-not $resolvedBuildVenv.StartsWith($resolvedProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove build environment outside the local-agent directory: $resolvedBuildVenv"
            }
            Remove-Item -Recurse -Force -LiteralPath $resolvedBuildVenv
        }
        & $BootstrapPython -m venv $BuildVenv
        & $BuildPython -m pip install --upgrade pip
    }

    & $BuildPython -m pip install `
        -r (Join-Path $ProjectRoot "requirements.txt") `
        -r (Join-Path $ProjectRoot "requirements-build.txt")

    if (-not $SkipTests) {
        & $BuildPython -m unittest discover `
            -s (Join-Path $ProjectRoot "tests") `
            -p "test_*.py" `
            -v
    }

    & $BuildPython (Join-Path $ProjectRoot "packaging\generate_build_assets.py") `
        --version $Version `
        --assets-dir $AssetsDir `
        --version-file $VersionFile

    Push-Location $ProjectRoot
    try {
        & $BuildPython -m PyInstaller --clean --noconfirm $SpecFile
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $AgentExe)) {
    throw "PyInstaller did not produce the expected executable: $AgentExe"
}

$selfTest = Start-Process `
    -FilePath $AgentExe `
    -ArgumentList "--self-test" `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
if ($selfTest.ExitCode -ne 0) {
    throw "Packaged agent self-test failed with exit code $($selfTest.ExitCode)."
}

if ($SkipInstaller) {
    Write-Host "Application bundle created at $AgentExe"
    exit 0
}

$isccCandidates = @()
if ($env:INNO_SETUP_COMPILER) {
    $isccCandidates += $env:INNO_SETUP_COMPILER
}
$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCommand) {
    $isccCandidates += $isccCommand.Source
}
if ($env:LOCALAPPDATA) {
    $isccCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
}
if (${env:ProgramFiles(x86)}) {
    $isccCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
}
if ($env:ProgramFiles) {
    $isccCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
}
$IsccExe = $isccCandidates | Where-Object {
    $_ -and (Test-Path -LiteralPath $_)
} | Select-Object -First 1

if (-not $IsccExe) {
    throw "Inno Setup compiler was not found. Install Inno Setup 6 or set INNO_SETUP_COMPILER to ISCC.exe."
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$SetupName = "ESPRemoteBuildAgentSetup-$Version-x64"
$SetupExe = Join-Path $ReleaseDir "$SetupName.exe"
$ChecksumFile = "$SetupExe.sha256"
if (Test-Path -LiteralPath $SetupExe) {
    Remove-Item -Force -LiteralPath $SetupExe
}
if (Test-Path -LiteralPath $ChecksumFile) {
    Remove-Item -Force -LiteralPath $ChecksumFile
}

& $IsccExe `
    "/DAppVersion=$Version" `
    "/DOutputBaseFilename=$SetupName" `
    (Join-Path $ProjectRoot "installer\ESPRemoteBuildAgent.iss")

if (-not (Test-Path -LiteralPath $SetupExe)) {
    throw "Inno Setup did not produce the expected installer: $SetupExe"
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SetupExe).Hash.ToLowerInvariant()
Set-Content `
    -LiteralPath $ChecksumFile `
    -Value "$hash *$SetupName.exe" `
    -Encoding ascii

Write-Host "Installer: $SetupExe"
Write-Host "SHA-256:  $ChecksumFile"

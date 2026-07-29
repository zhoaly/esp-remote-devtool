# Release Build

## Windows Local Agent

Run the full release build from PowerShell:

```powershell
cd local-agent
.\build_release.ps1
```

The script creates a clean Python build environment, installs the pinned runtime
and build dependencies, runs the tests, generates application icons and version
metadata, builds the PyInstaller `onedir` application, runs the frozen self-test,
and invokes Inno Setup.

The public release files are:

```text
release/ESPRemoteBuildAgentSetup-<version>-x64.exe
release/ESPRemoteBuildAgentSetup-<version>-x64.exe.sha256
```

Requirements:

- 64-bit Windows 10 or Windows 11
- Python 3.14
- Inno Setup 6 (`ISCC.exe`), either on `PATH`, in its default install directory,
  or referenced by `INNO_SETUP_COMPILER`

Useful build switches:

```powershell
# Build only the PyInstaller application directory
.\build_release.ps1 -SkipInstaller

# Reuse the existing development virtual environment
.\build_release.ps1 -UseExistingEnvironment

# Repackage an already verified dist directory
.\build_release.ps1 -UseExistingBundle
```

The current installer is unsigned. Windows SmartScreen can warn until the release
is signed with a trusted code-signing certificate.

## Server package

Run `server/make_release.sh`.

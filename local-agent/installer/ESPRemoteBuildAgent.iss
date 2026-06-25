#define AppName "ESP Remote Build Agent"
#define AppVersion "0.1.0"
#define AppPublisher "zhoaly"
#define AppExeName "ESPRemoteBuildAgent.exe"

[Setup]
AppId={{8A9D219F-4F3B-4F87-A4A4-1FE9B9F0B8AB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\ESPRemoteBuildAgent
DefaultGroupName={#AppName}
OutputDir=..\release
OutputBaseFilename=ESPRemoteBuildAgentSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

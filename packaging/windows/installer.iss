#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef AppSource
  #error AppSource is required
#endif
#ifndef OutputDirectory
  #error OutputDirectory is required
#endif

#define AppName "Comic Sequence Studio"
#define AppExe "Comic-Sequence-Studio.exe"
#define ProjectUrl "https://github.com/a18714466979-cmd/Comic-Sequence-Studio"

[Setup]
AppId={{DB866465-3034-46A5-9E90-6FC8857FA624}
AppName={#AppName}
AppVersion={#AppVersion}
AppSupportURL={#ProjectUrl}
AppUpdatesURL={#ProjectUrl}/releases
DefaultDirName={localappdata}\Programs\Comic-Sequence-Studio
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir={#OutputDirectory}
OutputBaseFilename=Comic-Sequence-Studio-{#AppVersion}-Windows-x64-Setup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Inno Setup script for the Anonymizer Windows installer.
; Compile with: ISCC.exe scripts\anonymizer-installer.iss
; (run from the repo root, or adjust the relative paths below if not).
;
; NOTE: written to match scripts\build_windows.ps1's PyInstaller output
; (dist\Anonymizer\Anonymizer.exe) but not verified on an actual Windows
; machine — no Windows environment was available to test the compile step.

#define MyAppName "Anonymizer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Lernsachen.blog"
#define MyAppURL "https://lernsachen.blog"
#define MyAppExeName "Anonymizer.exe"

[Setup]
AppId={{B1E9F6B4-9C6E-4B5A-9C7A-ANONYMIZERAPP}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Anonymizer-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Anonymizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; Inno Setup script: wraps desktop\dist\Stemmer\ into a per-user installer.
; Built by build_windows.ps1:  iscc /DAppVersion=0.1.0 stemmer.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8F4A6C2E-5B1D-4E7A-9C3F-2D6B8E1A4F70}
AppName=Stemmer
AppVersion={#AppVersion}
AppPublisher=Alfathony
AppPublisherURL=https://github.com/alfathony/stemmer
AppSupportURL=https://github.com/alfathony/stemmer/issues
DefaultDirName={autopf}\Stemmer
DefaultGroupName=Stemmer
DisableProgramGroupPage=yes
; Per-user install by default: no admin prompt. Users can still pick all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=Stemmer-{#AppVersion}-windows-x64-setup
SetupIconFile=..\icon\Stemmer.ico
UninstallDisplayIcon={app}\Stemmer.exe
LicenseFile=..\..\LICENSE
; ultra64 runs out of memory on ~1 GB of PyTorch files; max is close in size.
Compression=lzma2/max
SolidCompression=yes
; Compress in a separate 64-bit process instead of the 32-bit compiler.
LZMAUseSeparateProcess=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Stemmer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Stemmer"; Filename: "{app}\Stemmer.exe"
Name: "{autodesktop}\Stemmer"; Filename: "{app}\Stemmer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Stemmer.exe"; Description: "{cm:LaunchProgram,Stemmer}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Working files and the log; songs the user exported elsewhere are untouched.
Type: filesandordirs; Name: "{userappdata}\Stemmer"

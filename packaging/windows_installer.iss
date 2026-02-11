; Inno Setup Script for Disease2Gene Windows Installer
; Build with: iscc windows_installer.iss
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; Prerequisites:
;   1. Build the EXE first:  python -m PyInstaller Disease2Gene.spec
;   2. The dist\Disease2Gene.exe must exist

[Setup]
AppName=Disease2Gene
AppVersion=1.0.0
AppVerName=Disease2Gene 1.0.0
AppPublisher=ResearchShop
AppPublisherURL=https://researchshop.pl
AppSupportURL=https://github.com/michaluppal/RS_SOFTWAREX/issues
AppUpdatesURL=https://github.com/michaluppal/RS_SOFTWAREX/releases
DefaultDirName={autopf}\Disease2Gene
DefaultGroupName=Disease2Gene
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Disease2Gene_Setup_1.0.0
SetupIconFile=Disease2Gene.ico
UninstallDisplayIcon={app}\Disease2Gene.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Disease2Gene.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Disease2Gene"; Filename: "{app}\Disease2Gene.exe"
Name: "{group}\Uninstall Disease2Gene"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Disease2Gene"; Filename: "{app}\Disease2Gene.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Disease2Gene.exe"; Description: "{cm:LaunchProgram,Disease2Gene}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

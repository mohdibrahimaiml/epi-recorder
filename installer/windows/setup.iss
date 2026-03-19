; EPI Recorder — Windows Installer
; Built with Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
;
; This installer writes file associations to HKLM (system-wide).
; Unlike pip install + HKCU, HKLM associations:
;   - Survive UserChoice resets
;   - Apply to all users on the machine
;   - Persist across Windows updates
;   - Are respected exactly like Docker / VS Code associations
;
; Build:
;   1. pyinstaller epi.spec --clean          <- builds dist/epi/
;   2. Open this file in Inno Setup Compiler <- builds Output/epi-setup-X.Y.Z.exe

#define MyAppName "EPI Recorder"
#define MyAppVersion "2.8.5"
#define MyAppPublisher "EPI Labs"
#define MyAppURL "https://epilabs.org"
#define MyAppExeName "epi.exe"
#define MyAppDescription "Verifiable execution evidence for AI systems"

[Setup]
AppId={{B4F2A1C7-3E9D-4F8A-B2C1-7E5D9F4A3B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\EPI Labs\EPI Recorder
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output
OutputDir=Output
OutputBaseFilename=epi-setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; Require admin so we can write to HKLM — this is what makes file
; association work permanently, exactly like Docker and VS Code
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; Appearance
WizardStyle=modern
DisableDirPage=no
DisableProgramGroupPage=yes
SetupIconFile=..\..\epi_core\assets\epi.ico
; Uninstall
UninstallDisplayIcon={app}\epi.ico
UninstallDisplayName={#MyAppName}
; Version info embedded in the installer exe
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
; Architecture
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath";     Description: "Add epi to system PATH (recommended)";  GroupDescription: "Additional options:"; Flags: checked
Name: "desktopicon";   Description: "Create desktop shortcut (EPI Viewer)";   GroupDescription: "Additional options:"; Flags: unchecked

[Files]
; The entire PyInstaller bundle
Source: "..\..\dist\epi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\epi_core\assets\epi.ico"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; ─── HKLM file association (system-wide, permanent, UserChoice-proof) ───

; 1. Map .epi extension → our ProgID
Root: HKLM; Subkey: "Software\Classes\.epi";                              ValueType: string; ValueName: "";        ValueData: "EPIRecorder.File";     Flags: uninsdeletevalue
Root: HKLM; Subkey: "Software\Classes\.epi\OpenWithProgids";              ValueType: none;   ValueName: "EPIRecorder.File"; ValueData: "";           Flags: uninsdeletevalue

; 2. ProgID metadata
Root: HKLM; Subkey: "Software\Classes\EPIRecorder.File";                  ValueType: string; ValueName: "";        ValueData: "EPI Recording File";   Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\EPIRecorder.File";                  ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "EPI Recording File"

; 3. Open command — the key line that makes double-click work
Root: HKLM; Subkey: "Software\Classes\EPIRecorder.File\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" view ""%1"""

; 4. Icon shown in Explorer
Root: HKLM; Subkey: "Software\Classes\EPIRecorder.File\DefaultIcon";      ValueType: string; ValueName: "";        ValueData: """{app}\epi.ico"""

; 5. Register as a capable application so Windows knows about us
Root: HKLM; Subkey: "Software\Classes\EPIRecorder.File\shell\open";       ValueType: string; ValueName: "FriendlyAppName"; ValueData: "EPI Viewer"

; 6. Register in "Open with" → "Recommended Programs"
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName";        ValueData: "{#MyAppName}"
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{#MyAppDescription}"
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".epi"; ValueData: "EPIRecorder.File"
Root: HKLM; Subkey: "Software\RegisteredApplications";                    ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\{#MyAppPublisher}\{#MyAppName}\Capabilities"

; ─── PATH entry (if task selected) ───
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}'); Tasks: addtopath

[Icons]
Name: "{group}\EPI Recorder";        Filename: "{app}\{#MyAppExeName}"; Parameters: "--help"
Name: "{group}\Uninstall EPI";       Filename: "{uninstallexe}"
Name: "{commondesktop}\EPI Viewer";  Filename: "{app}\{#MyAppExeName}"; Parameters: "view"; Tasks: desktopicon

[Run]
; Notify Windows shell to refresh file type icons immediately after install
Filename: "{app}\{#MyAppExeName}"; Parameters: "associate --system --force --elevated"; WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Registering .epi file type..."

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "unassociate"; WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; RunOnceId: "UnregisterFileType"

[Code]
// Helper: check if a path is already in the system PATH variable
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKLM,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

// After install completes, notify the shell of changed file associations
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then begin
    // SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0)
    // Inno Setup doesn't expose this directly, but epi associate (in [Run]) does it.
  end;
end;

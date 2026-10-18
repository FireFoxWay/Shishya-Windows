; Shishya for Windows - the installer.
;
; Built by windows\build.ps1, which passes AppDir (the finished app folder),
; OutDir and AppVersion. Per-user and without administrator rights, on
; purpose: the sandbox is an AppContainer, which is per-user anyway, and the
; installer has to change the access lists on its own folders so the clone
; can read them - which it may do in the user's own LocalAppData without
; elevation, and could not in Program Files without it.
;
; What uninstalling removes: the program, its shortcuts, and the clone's
; AppContainer profile. What it keeps: %LOCALAPPDATA%\Shishya\Data - the shop's
; books, the lessons and the ledger are the person's, not the program's.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppDir
  #error AppDir must be set: run windows\build.ps1
#endif
#ifndef OutDir
  #define OutDir "."
#endif

[Setup]
AppId={{5B1F3A7E-6C2D-4E8B-9A41-7D3C2B9E0F11}
AppName=Shishya
AppVersion={#AppVersion}
AppVerName=Shishya {#AppVersion}
AppPublisher=Shishya
AppComments=An apprentice that watches you do a job once, writes down what it learned, and does that job - sandboxed, on this laptop.
DefaultDirName={localappdata}\Programs\Shishya
DefaultGroupName=Shishya
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutDir}
OutputBaseFilename=Shishya-Setup-{#AppVersion}
SetupIconFile={#AppDir}\windows\shishya.ico
UninstallDisplayIcon={app}\Shishya.exe
UninstallDisplayName=Shishya
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put Shishya on the desktop"; GroupDescription: "Shortcuts:"
Name: "path"; Description: "Add the shishya terminal command to PATH"; GroupDescription: "Terminal:"; Flags: unchecked

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The AppUserModelID matches what the panel window declares, so the running
; window groups under this shortcut's name and icon on the taskbar.
;
; IconFilename names the .ico itself rather than leaving the shortcut to take
; the exe's icon. Windows caches a shortcut's picture by the file it points
; at; after the icon was redrawn (the i-matra of "shi" had been on the wrong side)
; reinstalling kept showing the old one, because the exe's path had not
; changed. The [Run] entry below refreshes that cache as well.
Name: "{autoprograms}\Shishya"; Filename: "{app}\Shishya.exe"; WorkingDir: "{app}"; IconFilename: "{app}\windows\shishya.ico"; AppUserModelID: "Shishya.Panel"; Comment: "The control panel and the clone's sandbox"
Name: "{userdesktop}\Shishya"; Filename: "{app}\Shishya.exe"; WorkingDir: "{app}"; IconFilename: "{app}\windows\shishya.ico"; AppUserModelID: "Shishya.Panel"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: path; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Refresh this user's icon cache, so an upgrade's new icon shows at once in
; Start, on the desktop and on the taskbar instead of after a sign-out.
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden waituntilterminated skipifdoesntexist
Filename: "{app}\Shishya.exe"; Description: "Start Shishya"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop anything of the clone's still running, then remove its AppContainer
; profile - and with it the container's private storage.
Filename: "{app}\runtime\python.exe"; Parameters: "-I ""{app}\host\winbox.py"" delete_container"; Flags: runhidden; RunOnceId: "RemoveSandbox"

[Code]
function NeedsAddPath(Dir: string): Boolean;
var
  Current: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Current) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Current) + ';') = 0;
end;

function OllamaPresent: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
         or FileExists(ExpandConstant('{commonpf}\Ollama\ollama.exe'));
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and not OllamaPresent then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'One more thing: Shishya answers with a model that runs on this computer, ' +
      'through Ollama, which is not installed. Get it from ollama.com, then add a ' +
      'model from the Models app on the clone''s screen. Everything else works without it.';
end;

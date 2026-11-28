[Setup]
AppId={{B5CF5A95-A196-49BD-969D-031B243623DB}
AppName=UltraBar Studio
AppVersion=0.52.47
AppPublisher=UltraBar Studio
DefaultDirName={localappdata}\Programs\UltraBar Studio
DefaultGroupName=UltraBar Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=release
OutputBaseFilename=UltraBarStudio-Setup-0.52.47
SetupIconFile=assets\studio.ico
UninstallDisplayIcon={app}\UltraBar Studio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\UltraBar Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\UltraBar Studio"; Filename: "{app}\UltraBar Studio.exe"
Name: "{autodesktop}\UltraBar Studio"; Filename: "{app}\UltraBar Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UltraBar Studio.exe"; Description: "Start UltraBar Studio"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "UltraBar Studio"; Flags: uninsdeletevalue

[Code]
function InitializeSetup(): Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  if not Result then
    Result := RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    MsgBox('Microsoft Edge WebView2 Runtime must be installed first. Download it from https://developer.microsoft.com/microsoft-edge/webview2 and then run setup again.', mbError, MB_OK);
end;


procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer;
    AdbPath, Command: String;
begin
  if CurStep <> ssInstall then Exit;
  AdbPath := ExpandConstant('{app}\_internal\platform-tools\adb.exe');
  if not FileExists(AdbPath) then Exit;
  { Stop only ADB from this installation after Restart Manager closes Studio. }
  StringChangeEx(AdbPath, #39, #39#39, True);
  Command := '$target = ' + #39 + AdbPath + #39 + '; ' +
    'foreach ($process in Get-Process -Name adb -ErrorAction SilentlyContinue) { ' +
    '  try { $path = $process.Path } catch { continue }; ' +
    '  if ($path -ne $target) { continue }; ' +
    '  try { if (!$process.HasExited) { $process.Kill() }; ' +
    '        if (!$process.WaitForExit(3000)) { exit 1 } } ' +
    '  catch { if (!$process.HasExited) { exit 1 } } ' +
    '}; exit 0';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoLogo -NoProfile -NonInteractive -Command "' + Command + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
    Log('Could not stop the bundled ADB process. Setup will check for files still in use.');
end;

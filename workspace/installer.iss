[Setup]
AppId={{B5CF5A95-A196-49BD-969D-031B243623DB}
AppName=UltraBar Studio
AppVersion=0.45.0
AppPublisher=UltraBar Studio
DefaultDirName={localappdata}\Programs\UltraBar Studio
DefaultGroupName=UltraBar Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=release
OutputBaseFilename=UltraBarStudio-Setup-0.45.0
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
var Locator, Services, Processes, Process: Variant;
    I, Code: Integer;
    AdbPath, ProcessPath: String;
begin
  if CurStep <> ssInstall then Exit;
  AdbPath := ExpandConstant('{app}\_internal\platform-tools\adb.exe');
  if not FileExists(AdbPath) then Exit;
  { Stop only ADB from this installation after Restart Manager closes Studio. }
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Processes := Services.ExecQuery('SELECT * FROM Win32_Process WHERE Name = ''adb.exe''');
    for I := 0 to Processes.Count - 1 do begin
      Process := Processes.ItemIndex(I);
      if not VarIsNull(Process.ExecutablePath) then begin
        ProcessPath := Process.ExecutablePath;
        if CompareText(ProcessPath, AdbPath) = 0 then begin
          Code := Process.Terminate(0);
          if Code <> 0 then
            RaiseException('Could not close the Studio ADB background process. Close Studio and retry installation.');
          Log('Closed ADB from this Studio installation.');
        end;
      end;
    end;
    Sleep(500);
  except
    RaiseException('Could not release Studio background files. Close Studio and its bundled adb.exe, then retry. ' + GetExceptionMessage);
  end;
end;

[Setup]
AppId={{B5CF5A95-A196-49BD-969D-031B243623DB}
AppName=UltraBar Studio
AppVersion=0.15.0
AppPublisher=UltraBar Studio
DefaultDirName={localappdata}\Programs\UltraBar Studio
DefaultGroupName=UltraBar Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=release
OutputBaseFilename=UltraBarStudio-Setup-0.15.0
SetupIconFile=assets\studio.ico
UninstallDisplayIcon={app}\UltraBar Studio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
AppMutex=Local\UltraBarStudio.Desktop

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

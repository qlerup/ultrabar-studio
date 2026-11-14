# Native build tools write progress to stderr; check their exit codes explicitly.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
$studioPython = Join-Path $PSScriptRoot '.venv-build/Scripts/python.exe'
$studioCompiler = Join-Path $PSScriptRoot 'build-tools/InnoSetup/ISCC.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Opret .venv-build og installer requirements-build.txt først.' }
if (-not (Test-Path -LiteralPath $studioCompiler)) { throw 'Inno Setup-kompileren mangler i build-tools/InnoSetup.' }
& $studioPython -m unittest test_server test_hardware test_discovery test_previews test_editor test_native_widgets test_updates
if ($LASTEXITCODE -ne 0) { throw 'Tests fejlede.' }
& $studioPython ../native-widgets/build.py
if ($LASTEXITCODE -ne 0) { throw 'Native widget build failed.' }
& $studioPython -m PyInstaller --noconfirm 'UltraBar Studio.spec'
if ($LASTEXITCODE -ne 0) { throw 'App-build fejlede.' }
& $studioCompiler installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer-build fejlede.' }
Get-FileHash 'release/UltraBarStudio-Setup-0.15.0.exe' -Algorithm SHA256


# Native build tools write progress to stderr; check their exit codes explicitly.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
$studioPython = Join-Path $PSScriptRoot '.venv-build/Scripts/python.exe'
$studioCompiler = Join-Path $PSScriptRoot 'build-tools/InnoSetup/ISCC.exe'
if (-not (Test-Path -LiteralPath $studioPython)) { throw 'Create .venv-build and install requirements-build.txt first.' }
if (-not (Test-Path -LiteralPath $studioCompiler)) { throw 'The Inno Setup compiler is missing from build-tools/InnoSetup.' }
& $studioPython -m unittest test_store_cancel test_studio_contract test_studio_integrations test_bambu_upgrade test_bambu test_bambu_contract test_server test_hardware test_discovery test_previews test_editor test_vivo test_store_activation test_app_settings test_app_settings_contract test_widget_images test_library_icons test_native_widgets test_updates test_store test_screen_sync test_local_packages test_package_stats test_settings test_deferred_apps
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $studioPython verify_tray.py
if ($LASTEXITCODE -ne 0) { throw 'Native tray checks failed.' }
& $studioPython verify_folder_dialog.py
if ($LASTEXITCODE -ne 0) { throw 'Native folder chooser checks failed.' }
& $studioPython ../native-widgets/build.py
if ($LASTEXITCODE -ne 0) { throw 'Native widget build failed.' }
& $studioPython -m PyInstaller --noconfirm 'UltraBar Studio.spec'
if ($LASTEXITCODE -ne 0) { throw 'App build failed.' }
& $studioCompiler installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
& $studioPython make_update_feed.py
if ($LASTEXITCODE -ne 0) { throw 'Update feed build failed.' }
Get-FileHash 'release/UltraBarStudio-Setup-0.52.12.exe' -Algorithm SHA256


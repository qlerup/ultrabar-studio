# UltraBar Studio

Windows companion for UltraBar X / CoreBAR: device overview, profile and action
editing, native hardware widgets, saved previews and manual update checks.

[Download the latest Windows installer](https://github.com/qlerup/ultrabar-studio/releases/latest)

## Licensing

Source available for inspection, **not open source**. Unmodified official binary
releases may be installed and used. Modifications, derivative works and
redistribution of Studio require written permission. See [LICENSE](../LICENSE).
Third-party components keep their own licenses.

## Development

The application lives in `workspace/`; native widget Java source is in
`native-widgets/`. Python 3.12, Windows and Microsoft Edge WebView2 are required
for the desktop app. Run these commands from `workspace/`:

```powershell
python -m venv .venv-build
.venv-build/Scripts/python -m pip install -r requirements-build.txt
.venv-build/Scripts/python -m unittest test_server test_hardware test_discovery test_previews test_editor test_native_widgets test_updates
.venv-build/Scripts/python desktop.py
```

To connect a device, place the official Android platform-tools under
`tools/platform-tools/` at repository root. Tools and private device data are
not committed. Browser tests additionally require Playwright and installed Edge:
`python -m pip install playwright`, then run `test_design_browser test_onboarding`.
The browser tests use synthetic profiles and do not require a real device.

For installer builds, install Inno Setup's compiler under
`workspace/build-tools/InnoSetup/`, JDK on PATH, Android platform 35 at
`tools/android-sdk/android-35/`, and D8 at `tools/android-sdk/android-15/lib/d8.jar`.
Then run `workspace/Build-Installer.ps1`. The build verifies native Java tests,
runs backend tests, packages the app and creates the Windows installer.

Packaged user data lives in `%LOCALAPPDATA%/UltraBar Studio`; installing a new
version does not reset profiles, drafts or settings. Development data lives in
`workspace/data/`. Do not commit this data, signing keys or device credentials.

## Updates and future store

The app checks this repository's latest stable release only when requested.
It opens the download page in the system browser; installer execution is manual.

The planned community store uses a separate, owner-reviewed catalog and
prebuilt release assets. See [store architecture](../docs/store-architecture.md).
The store installer and plugin runtime are **not implemented in 0.14**.

See [workspace notes](../workspace/README.md) for history and tested device limits.

# UltraBar Studio — 0.29 Windows

## 0.29 update

Studio stays maximized when the title bar is dragged or double-clicked, and when Windows requests Move, Size or Restore. Minimize and Close remain available. A native Windows message hook prevents drag-to-restore, and a UI-thread state guard maximizes any programmatically restored window. Native regression checks cover title-bar operations, system commands, direct state changes and minimize/restore.

## 0.28 update

Store installation supports private, device-specific setup for the reviewed Vivo Screen Sync Core app. It discovers online VivoCubes, keeps credentials out of the package and PC files, preserves existing Android app settings, and leaves first activation to the user. Requires the separately approved Store listing and existing root ADB/Studio bridge authorization. The new setup path still requires physical owner testing before package approval.

## 0.27 update

- Deploy displays a modal with live backend stages and elapsed time, including wake, runtime preparation, sending, verification and restart. Errors and results stay visible until closed.

## 0.26 update

- Studio stays maximized: resizing and the restore button are disabled, and OS restore requests maximize the window again. Minimize and close remain available.

## 0.25 update

- Deploy wakes Core and waits for Awake / display ON before preparing or sending settings. A wake failure stops deployment without changing the profile.
- Uses Android KEYCODE_WAKEUP rather than a power toggle, so an already-awake screen stays on.
- Verified on physical Core from Dozing/OFF to Awake/ON, followed by a successful LineOS home restart.

## 0.24 update

- System Monitor is one Store widget with a per-block Show selector for CPU, RAM or GPU. Each block keeps its own choice. Removed the former built-in CPU/RAM/GPU templates; existing layouts remain editable.
- Adding Store cards no longer adds duplicate templates to the library. Multiple cards on the bar remain supported.

- Drive widgets are now distributed as one Studio Drive Usage Store package. Install once, add multiple cards and choose a drive in each card?s settings.
- Removed built-in Disk usage / per-drive shortcuts from the library. Existing placed disk widgets remain editable and deployable; updates never remove user layouts.

## 0.23 update

- Widget library separates UltraBarX built-ins, Studio widgets, Store packages and existing items of unknown origin. Store widgets already on the bar no longer create duplicate library entries.

- Store packages use responsive app cards with verified PNG app icons, titles, descriptions and installation controls. Studio applies one consistent rounded icon mask to square source images.
- New store submissions require icon.png: static PNG at 256x256 or 512x512, maximum 256 KiB. The bot checks actual image decoding, dimensions, byte size/hash and published icon bytes.
- Icons are downloaded only from official versioned store assets through the protected local API, verified and cached. Legacy entries without icon metadata show a fallback initial.
- Updated contributor instructions and Clock & Date icon; widget functionality and existing settings are unchanged.

## 0.22 update

- Opening Connect device/Manage connection starts discovery automatically. Find devices remains available for rescans.
- Discovered devices form a selectable list; selection alone never connects. A separate Connect button uses the selected Core address.
- Manual IP/port and Connect are in a collapsed Manual connection disclosure below the list. It starts collapsed each time the dialog opens.
- Closing the dialog invalidates in-flight scan results. Empty/error states keep rescan and manual options available.
- Browser tests cover automatic scan, reopen, multiple devices, selected-target connection, no connection on selection, manual fallback, rescan/error handling and narrow layouts.

## 0.21 update

- Save & install update saves the active dirty draft, aborts on save failure, queues the verified installer, closes the desktop and starts setup after backend shutdown. Active store installs block the handoff.
- Removed the installer's startup AppMutex blockade. Interactive setup can use Windows Restart Manager to offer closing an older running Studio.
- Just before replacing files, setup stops only adb.exe processes whose executable path matches this installation's bundled ADB. Other Android SDK installations are not targeted. Program replacement leaves saved data untouched.
- Automated tests cover save failure, explicit confirmation and deferred installer handoff. Installer compiles; a complete native upgrade has not been run against the user's installation.

## 0.20 update

- Integrated corebar-widget packages install locally into the left library; right-panel settings are saved in the draft, and existing verified Deploy sends the shared renderer/settings to Core.
- Clock/date renderer with 12/24-hour time, optional seconds/date, name and colors. Uses Core clock/locale; preview uses PC clock. The existing root-enabled ARM32 CB01 / LineOS 1.0.8-1.0.9 integration is required. Runtime restoration after Core restart requires Studio connection.
- Package provenance/version survives in saved native widget settings. Removing a package from the library preserves placed widgets and drafts. Remove a card and Deploy to remove it from Core.
- Supported declarative widget kinds: clock, cpu, memory, gpu and disk. New custom executable code/data sources are not loaded from store packages.
- Browser drag/settings/save, package integrity/local-only installation and Java compilation checks pass. Clock rendering on physical Core still awaits owner testing.

## 0.19 update

- Download Studio updates directly in the app with progress, exact size and GitHub SHA-256 verification, and an explicit Start installation button.
- The existing installer AppId and installation directory are retained. It updates program files; persistent data in `%LOCALAPPDATA%/UltraBar Studio` is separate and is not removed or replaced. Save unsaved drafts before starting installation and close Studio when requested.
- Versions through 0.18 still open GitHub: install 0.19 manually once to gain the integrated downloader. Installer execution is user-initiated, not silent.

## 0.18 update

- App & Plugin Store with search, type/installed filters, explicit install confirmation, job status and independent catalog refresh. Only main-branch approved entries from qlerup/ultrabar-store can be installed.
- CoreBAR APKs: bounded download, exact hash/size, metadata and permission checks, APK v2 signing-identity check, model/API/ABI checks, device identity recheck and fixed ADB install/update. Android verifies signatures. Existing apps are never silently uninstalled or downgraded.
- Studio plugins: validated declarative JSON presets only; install/remove on this PC and expose presets in the widget library. No remote scripts or arbitrary executable plugin loading.
- Widget dragging uses pointer events, an insert marker and edge scrolling across the scaled preview. Browser drag/add tests pass; a separate Windows UI test launch was blocked by the environment, so packaged WebView dragging still needs user confirmation.
- Studio Clock and Iris Presets are submitted separately for owner approval. Their APK/JSON review assets alone do not publish them in the approved store catalog.
- Native renderer package installation and executable plugin APIs remain unsupported.

## 0.17 update

- Studio starts maximized on every launch, retaining the normal Windows title bar and window controls.

## 0.16 update

- First-use setup now explains how to unlock Android Developer options before enabling ADB WiFi, including Build number, seven taps, optional PIN and the already-enabled case.
- Android activation reference: https://developer.android.com/studio/debug/dev-options

## 0.15 update

- Collapsible widget library: UltraBarX built-in widgets, Studio & App Store extensions, and separately listed installed apps whose installation source is not tracked.
- Search expands matching groups temporarily and restores disclosure choices when cleared. Click-to-add and drag/drop remain available.
- Short public README with current features, tested compatibility and planned store capabilities.

## 0.14 update

- Fixed native widget deploy on LineOS 1.0.9. Exact active-package version checking supports 1.0.8 and 1.0.9; hidden factory APKs cannot bypass it. Verified renderer attachment for three existing widgets on a real 1.0.9 device without changing its profile.

- Manual Check for updates in the top bar, available without a connected device. Stable GitHub releases are checked with a 10-second timeout; errors and missing installers are explicit. Downloads open in your system browser; installation remains manual.
- One workspace navigation: Device overview and Design & actions live in the sidebar (top navigation on narrow windows).
- Public source and releases: https://github.com/qlerup/ultrabar-studio
- Installer: `release/UltraBarStudio-Setup-0.14.0.exe`.

## 0.13 update

- CoreBAR stays centered in the hardware viewport when space permits, including asymmetric layouts. Other modules retain their saved order; narrow windows keep horizontal scrolling.
- Flat workspace sections, fine separators, underlined tabs and precise corners replace rounded nested panels throughout Studio.
- Installer: `release/UltraBarStudio-Setup-0.13.0.exe`.

## 0.12 update

- Graphite and iris visual design across the workspace, editor and dialogs. Adaptive navigation and editor columns, sticky connection toolbar, scalable cards and a 640 x 520 minimum desktop window.
- Responsive browser checks cover overview, editor and connection access at 390, 640, 850, 1024, 1440 and 1920 pixels.
- Installer: `release/UltraBarStudio-Setup-0.12.0.exe`.

## 0.11 update

- Connection status and the Connect device / Manage connection button now live in the top bar. Discovery, manual IP entry and connection help open in a modal dialog.
- First launch shows the CoreBAR touchscreen setup guide. Dismissal is remembered in the local `setup-seen` marker, independently of the desktop webview port. Reopen the guide from the connection dialog at any time.
- Live hardware polling updates the top-bar connection indicator on disconnect and recovery. Existing profiles, backups and device settings are preserved.
- Installer: `release/UltraBarStudio-Setup-0.11.0.exe`.
- Browser regression: `.venv-build/Scripts/python -m unittest test_onboarding` (requires Playwright and installed Edge). Checks first launch, persisted dismissal, discovery, connection errors, keyboard dismissal and narrow layouts without connecting to hardware.

## 0.9 update

- Original Studio hardware widgets now render as child views inside LineOS's existing scrolling cards. No replacement home, dashboard activity, accessibility service or overlay window.
- Disk usage has a per-widget drive selector: C:, D:, or All drives. All drives shows separate labelled rows, two at a time; larger drive sets switch to the next pair every six seconds. CPU, RAM and NVIDIA GPU cards share the Studio design. Background, text and accent colors are configurable per card, with a preview before deploying. Individual drive shortcuts appear in the widget library.
- Supported integration: root-enabled ARM32 CB01 with LineOS 1.0.8. A pinned Frida 16.7.19 runtime loads a small Java renderer into the running home process. The original APK and default home selection remain unchanged. Runtime listens only on device loopback, requires a random authentication token, and is reached over ADB forwarding.
- Keep Studio running and connected for live data and attachment after a Core/LineOS restart. Visible rendered cards explicitly show PC offline after ten seconds without updates. After a Core restart, connect Studio and open Core home to activate rendering again.
- Removing Studio cards and deploying restores the original widget-only layout. Pre-deploy XML and rollback drafts remain available. No firmware partition writes or re-signing of vendor APKs.
- Development found and removed an unsafe ART heap scan and an early process attachment. The current integration traverses actual view roots and waits for the HomeActivity window before attaching.

Installer: `release/UltraBarStudio-Setup-0.9.0.exe`.

## 0.8 update

- Design & actions editor: drag native widgets onto Core, reorder cards, edit names/colors/icon sizes, and configure supported module actions.
- Drafts stay on this PC until Deploy. Deployment backs up the original XML, checks for device-side changes, sends settings once and verifies readback. LineOS home restarts to load the layout; Android is not rebooted.
- Draft & recovery tools can load the previous deployment into a draft for review and redeployment. Existing module input records are retained with empty action lists when clearing them.
- Website and local .exe buttons are registered on this PC and require Studio to remain connected. No command-line arguments or arbitrary remote commands are accepted.
- Native Core widgets support CPU, RAM and combined fixed-drive usage. GPU and individual-drive measurements are visible in Studio only. The experimental accessibility overlay was removed because it lagged behind native cards during scrolling; old overlay drafts cannot be redeployed. True GPU/per-drive home widgets remain unimplemented.
- Existing Core profiles and unsupported widgets are preserved. Creating/deleting profiles, new VivoCube artwork and custom album/player deployment are not supported.
- Installed data remains in `%LOCALAPPDATA%/UltraBar Studio`: backups, drafts, hardware arrangements and PC action registrations. Reinstalling does not reset it.
- Regression tests cover drafts, conflicts, backup ordering, ambiguous deployment replies, rejected overlays, PC action validation and native metric responses. Live checks use Core 10.10.0.181; user layout restored after temporary deployment checks.

Latest installer: `release/UltraBarStudio-Setup-0.8.0.exe`.

Earlier version notes below describe the capabilities at those releases.

## 0.7 update

- Previews are snapshots fetched at connection, manual refresh, or a detected saved-configuration/package change. Status polling checks only metadata; no periodic screenshot or artwork transfer.
- VivoCube previews read serial-specific TGZ artwork from CoreBAR. The supported single-button default layout uses an LVGL RGB565 big-endian image with alpha. Verified against the installed VS Code artwork.
- The second cube displays factory artwork on the physical device, as confirmed by the owner. CoreBAR has no saved package for it, and the image is not available in the inspected local files. This cube still cannot be previewed. We do not substitute another cube's picture.
- Unsupported composite layouts report an explicit error. Saved default artwork is not a framebuffer or an active-layer readback. Physical navigation and animation do not trigger preview capture; use Refresh previews.
- Tested image decoding, invalid input, package limits, serial isolation, real artwork retrieval, no capture during unchanged polling, change-triggered capture and manual refresh.

Latest installer: `release/UltraBarStudio-Setup-0.7.0.exe`.

## 0.6 update

- Actual CoreBAR screenshot appears inside its hardware card and in the larger screen panel. It refreshes every five seconds while the window is visible, with pause and manual refresh controls.
- Screen-off state comes from the device, not image brightness. Failed capture clears both previews; old connection responses are discarded.
- VivoCube screen preview remains unavailable. The inspected QLink VivoCube protocol exposes power state and active layer/widget IDs, but no framebuffer capture. VivoCube is not an Android display on CoreBAR. No simulated image is presented as a live preview.
- Verified real 1424x280 capture, pause, capture failure/recovery, narrow layout and screen-off reporting.

Latest installer: `release/UltraBarStudio-Setup-0.6.0.exe`.

## 0.5 update

- Added an English Setup guide beside the connection controls, in the first-use screen and after connection errors.
- CoreBAR steps: swipe down, press and hold the gear icon, open System > Advanced > Developer options, scroll to Debugging and enable ADB WiFi. Menu path confirmed by the device owner.
- The guide hands off to Find devices and includes manual connection and troubleshooting instructions.
- Checked desktop and narrow-window layout, close/Escape behavior, focus restoration and real device-discovery handoff.

Latest installer: `release/UltraBarStudio-Setup-0.5.0.exe`.

## 0.4 update

- Drag any cube or CoreBAR to match the physical arrangement, including cubes on both sides of Core. Edge scrolling supports long rows; Escape cancels a drag. Alt+Left/Right provides keyboard reordering.
- Layouts save automatically to `layouts.json` in the app's user-data directory, keyed by CoreBAR serial number. They survive polling, restart and IP changes. Temporarily absent modules keep their remembered positions. New modules appear at the end. No configuration is written to the hardware.
- Saving errors restore the last layout and show an error. Polls do not replace DOM nodes during a drag.
- Device discovery runs on launch and can be repeated with Find devices. It uses the official UDP `discovery.ultrabar` request on port 5319. Since broadcast does not return results on the tested network, a bounded fallback probes the nearest /24 on active default-route adapters (maximum four adapters, 254 addresses each). No firewall rules are changed.
- Discovery identifies the device without knowing its IP. Select a result to connect. WiFi ADB must still be enabled; advertised TCP 7431 is CoreBridge, not the ADB port. The initial connection uses ADB 5555, with manual entry available for other ports. Discovery announcements are hints, not trusted credentials.
- Tested real UDP discovery, mouse drag, order persistence after page restart, layout save failure, keyboard move, status refresh during drag and existing live status/error recovery.

Latest installer: `release/UltraBarStudio-Setup-0.4.0.exe`.

## 0.3 update

The application and installer now use English. Hardware status refreshes automatically every five seconds while the window is visible and no manual operation is running. Overlapping polls are suppressed; late replies from a previous connection are discarded. Bringing the window back refreshes status immediately.

The prior version only queried status on Connect/Refresh and could leave an old offline reading visible indefinitely. A fresh query on September 17 confirmed all six modules online, including both KnobKeys. This does not establish why CoreBAR had reported one offline earlier: its endpoint status is based on recently received traffic.

Status errors replace previous online/offline indicators with Unknown and retry automatically. The selected module's detail line updates along with its indicator. Polling does not create profile backups or reload the displayed action editor. Tested offline → online, connection loss → unknown → recovery, and the actual six-module device response.

Latest installer: `release/UltraBarStudio-Setup-0.3.0.exe`. Earlier version notes below describe the original 0.2 packaging.

## Historical Windows packaging notes (0.2)

The original Windows installer installed Studio for the current Windows user,
with a Start menu shortcut and optional desktop shortcut. Python, ADB and runtime
libraries were bundled. Setup checked for Microsoft Edge WebView2 Runtime.
Studio opened its own window, started a private loopback server on an available
port and stopped that server when the window closed.

Backups, the remembered IP address and logs are stored in
`%LOCALAPPDATA%/UltraBar Studio`, separately from installed program files. They
survive updates and uninstalling. The app and installer were not code-signed.

### Hardware preview

The module list comes from authenticated CoreBridge request `30730` (runtime
supervisor), independently of profile actions. Names and types come from Core's
endpoint registry. New runtime modules without known metadata appear as unknown;
old registry entries without runtime membership are excluded.

The initial test reported six modules: two VivoCubes, two KnobKeys, one DotKey and
one SenseCube. Five were online and one KnobKey was offline. The preview shows
reported state and its read timestamp. Positions are schematic rather than a
verified physical order. Cube images are illustrations rather than live video.

In the original version, Connect and Refresh triggered status reads. Failed
requests displayed an error rather than presenting saved configuration as live
hardware. The previously approved diagnostic credential was read through ADB and
used only in memory. It was excluded from the package and logs, and the server
certificate was matched exactly before authentication.

### Build the installer

Create `.venv-build`, install `requirements-build.txt` and place the Inno Setup 6
compiler in `build-tools/InnoSetup`. Run `Build-Installer.ps1`. Builds include code,
static assets, the public certificate and ADB. Private `data/` and user profiles
are excluded.

Original packaging validation covered eight backend tests, browser flows with six
runtime modules, responsive layouts, error responses, packaged WebView startup,
live device reads, normal shutdown, installation and the Start menu shortcut.
`--smoke-test --live-test` tests the packaged app against the current device and
writes PASS/FAIL to its user data directory. See newer release notes above for
subsequent functionality and validation.

Updates use the same AppId. To roll back, reinstall an earlier version while
retaining the data directory. The original read-only release did not modify
Core firmware or profiles.

### Local development

From this directory, run `python -m pip install -r requirements.txt`, followed by
`python server.py`. Open http://127.0.0.1:8741 and select **Connect**. Alternatively,
use `Start-Studio.ps1`. Development requires Python, ADB at
`../tools/platform-tools/adb.exe` and WiFi ADB enabled on Core. Enter the current
local address in Studio. The tested CB01 allowed reading its profile file over
ADB; other firmware may restrict access.

### Original read-only feature scope

- Read LineOS profiles and configured modules. The saved configuration alone was
  not a live inventory of physically connected modules.
- Read saved inputs and actions, with unknown fields available in the saved-data view.
- Refresh manually and display the timestamp of the last successful read.
- Fetch a screenshot on request, without remote control or continuous streaming.
- Save the original profile XML in `data/backups/<sha256>.xml`, once per distinct
  file content. Backups were downloadable; automatic restore was not implemented.
- Run on loopback with session-token and Host validation. Browser assets loaded locally.
- Keep private backups local; `data/` is excluded from Git.

The original roadmap covered draft editing, validation, verified deployment with
backups and readback, clearing removed actions, PC actions, widgets and reconnect.
These historical limitations describe the initial release; newer releases are
covered above. A protocol acknowledgement alone does not prove that a runtime
reloaded an action: deployment requires readback and physical input testing.

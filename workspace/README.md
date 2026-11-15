# UltraBar Studio — 0.46.0 Windows

## 0.46 update (under review)

Adds the Bambu Liquid native widget and a fixed companion IPC contract. Each
placed card can choose its primary/secondary reading, expanded size (2–5 slots),
detail fields, controls visibility and liquid/reduced motion. Tapping grows a
native presentation from the actual card position, including real slot gaps and
host corner radius. Neighboring cards move left and/or right; closing restores the
existing layout without changing profile positions. The animation runs on Core.

Install/deploy Bambu Panel on Core first and enter printer credentials there.
The native card receives sanitised state only; controls remain gated by the app's
explicit enable switch, fresh status and printer capabilities. Unsupported or
offline readings stay unavailable. Studio must reconnect to restore native cards
after a Core/LineOS restart, as with the existing native runtime.

New package support requires reviewed Studio 0.46 and Store contract changes;
current released Studio versions do not understand the new Bambu kind. Renderer
preview screenshots use sample data and are separate from real-printer testing.

## 0.45 update

Android app packages can declare settings API 1. Studio builds typed controls from
reviewed descriptors, reads current device values, and saves edits with the draft.
Deploy transfers validated values as the app UID and waits for a matching durable
confirmation. Missing/stale/rejected/mismatched replies stop deployment with the
draft and backup preserved. App settings apply across profiles; removing an app
from the layout does not apply its stored settings in the background.

Supported controls: booleans, bounded integers/numbers, text, HTTP(S) URLs and
choices. Descriptors must match the APK asset and protected fixed receiver, and
require Studio 0.45.0+. No contributor commands, arbitrary transports or secret
fields are supported. Existing widgets retain their native runtime settings.
Legacy Screen Sync controls remain supported until its library package is updated.

Requirements, example and submission checklist:
https://github.com/qlerup/ultrabar-store/blob/main/APP-SETTINGS.md .

## 0.44 update

Studio now includes separate **Open website** and **Launch PC app** widgets in
its library. Drag either onto Core, enter the URL or browse for an executable,
and choose Apply settings. Existing shortcuts can be selected and edited in the
same settings panel. The combined Website or PC program button has been removed.

Each shortcut has its own purple library icon and a visible preview card. Upload
a PNG, JPG or WebP picture (up to 2 MB), or use the program's automatically
extracted Windows icon. Pictures are normalized, saved with local Studio data,
and transferred to Core with byte-for-byte verification before the layout is sent.
If a program icon is unavailable, Studio shows its default app picture.

Unfinished shortcuts can be saved as drafts; Deploy asks you to finish their
settings first. Shortcuts open on the PC and require Studio to remain running.
Browser regression checks cover drag-only placement, URL validation, picker
cancellation, uploaded pictures, automatic program icons, editing, Undo and reload.

## 0.43.1 update

Calculator, Alarmclock, Space Dodger, AuroraSniper, White Noise, StellarRing and
ScreensaverFlip now appear in the UltraBarX library section alongside built-in
widgets. Classification uses their known package IDs; Store package provenance
still takes priority, and unrelated apps remain in Other apps & widgets on Core.

Clicking a widget-library item no longer adds it to the draft. Drag and drop is
required to place it on the Core bar or in Background apps. Library guidance and
tooltips now describe these destinations. Browser checks verify clicks do not
add widgets/apps, leave a clean draft clean, and both drag destinations still work.

## 0.43 update

Module action setup now unfolds in three numbered panels: choose a press or gesture,
choose what happens, then enter only the settings needed for that action. Website
and PC program actions use inline URL/path fields; program browsing supports
cancellation. Core app launch and saved PC controls have their own selectors.
Changes are assigned only with Add action or Update action, then use the existing
Save draft and Deploy workflow. Existing assignments remain available for editing,
reordering, removal and Undo. Switching devices/profiles resets the composer;
background status polling preserves unfinished fields. PC action saves lock the
selection until completion to prevent assignment to a different input.

The widget library now shows verified Store package icons and real Core app/Clock
icons instead of generic glyphs. Core icons are read through a temporary local ADB
forward, validated as bounded PNGs, cached by device and never taken from arbitrary
URLs in app metadata. Unavailable icons retain a usable initial. The app catalog
accepts both application and packageName identifiers, fixing empty catalogs and
missing friendly app names on supported Core firmware.

Offline browser checks cover progressive disclosure, URL validation, program picker
cancellation, saved PC controls, Core app launch, editing, Undo, profile/device
isolation, a delayed save, and desktop/mobile layouts. Core Clock and Calculator
icon retrieval was also verified read-only on the connected device. No module
assignments or profiles were deployed during these checks.

## 0.42.3 update

Fixed Screen Sync setup failing certificate verification when Windows files contain
CRLF line endings. Setup now transfers file bytes through raw ADB exec-in, then
applies ownership, permissions, atomic rename and SELinux labels in a separate
command. Config, certificate and preferences still require exact readback before
the service is started; verification is not relaxed.

Reproduced the line-ending corruption with a harmless scratch file on CB01.
Verified the corrected setup on the connected Core using its saved Follow Core
and 1000 ms wake delay settings. Setup files/preferences passed byte-for-byte
verification and Android reported the Screen Sync foreground service running.
No profiles or button assignments were deployed during this verification.

## 0.42.2 update

App placement is controlled by dragging into Background apps or onto the Core bar.
The redundant Move onto bar and Run in background settings buttons are removed.
The empty-background hint now describes dragging from the library or the bar.
Browser acceptance covers dragging between both areas, saved background settings
and Undo restoring the prior background placement and settings.

## 0.42.1 update

Selected Core layout widgets keep their lavender selection border while hovered.
The selection rule now takes precedence over the general button hover styling.
Browser acceptance verifies the selected border with the pointer over the widget
and after moving it away, using reduced motion to check final colors without
transition timing affecting the result.

## 0.42 update

Module actions now uses the same visual device strip, live status, saved artwork and desk order as Device overview. Select a module to reveal its input selector and action editor. Matching devices are distinguished by their serial suffix; offline modules and saved modules absent from live hardware can still be configured. Selecting CoreBAR opens Core layout. Device selection alone does not change the draft.

KnobKey rotation inputs are available alongside button presses. Assignments remain separate for each physical module and use the existing draft, Undo, save and Deploy workflow. Live status refresh preserves the selected module and input.

Device overview no longer repeats the Home screen widgets list or the Modules/configuration inspector. Hardware previews, connection status, profile summary and backup download remain available. Edit layouts and module actions in Design & actions.

Browser acceptance checks cover device selection, two independent KnobKeys, offline configuration, DotKey presses, VivoCube presses, SenseCube taps, KnobKey rotation, persisted draft assignments and desktop/mobile layouts. No physical-device assignment changes were performed for these checks.

## 0.41 update

Studio automatically checks for updates at startup. A newer release highlights the top-bar button with its version number and opens the update dialog once. The notice waits until other open dialogs close, and the button stays highlighted after dismissal. Offline checks do not interrupt startup; manual checking remains available. Download and installation still require user action.

The built-in Clock now appears only once in the widget library, even when profiles already contain a Clock. Existing cards and separately installed Store clocks are preserved.

On wide screens, Widget library and Widget settings match the height of the central CoreBAR panel. Smaller screens retain their responsive layout.

## 0.40 update

SenseCube's hardware preview now includes the original-style vertical division on its front face.

Install from folder now opens a manual-app dialog. Browse for a package folder or paste its full path and choose Check folder. Required files, format, icon, checksums and Studio compatibility are validated; APK metadata, permissions and signing identity are also checked for Core apps. Device-specific compatibility remains a Deploy check and is clearly labelled. Invalid or unchecked folders cannot be added.

Add manual app registers a local Store card without installing anything. Install on that card separately adds it to the library. Registration retains a verified copy, so the original folder can move or change without changing the reviewed package. Manual cards persist across restarts and remain available when the catalog is offline. Local packages are marked Manual app / Not Store reviewed.

The native folder chooser now runs through an owned WinForms dialog on the Studio UI thread, disposes resources and restores the owner on cancellation, close or failure. Isolated native checks cover Cancel, Close, reopening and continued WebView responsiveness without controlling installed Studio. Browser tests cover the popup, cancellation, validation, explicit add followed by separate installation and narrow layouts.

## 0.39 update

Fixed a deployment regression for older profiles containing app placeholders whose Android APK is no longer installed. Those visible placeholders are preserved and no longer block Deploy. Explicit background apps still require setup; a missing package now gives an actionable library message instead of incorrectly reporting a WiFi ADB failure. APKs staged in Store retain their normal signature and device checks.

Removed the separate CoreBAR screen section from Device overview. The CoreBAR preview remains in the hardware overview alongside the other devices, with capture status below that overview. Refresh previews still updates the artwork; clicking CoreBAR refreshes its screen preview directly. Profiles, widgets and backups are unchanged.

## 0.38 update

All Store Core apps, including local APK packages, now install into the PC library without a CoreBAR connection. Add an app to the layout, or to the Background apps area above the Core preview, then Deploy. Deploy verifies cached APK checksums, metadata, signer and device compatibility, installs the required apps and performs supported setup before sending the layout. Library removal preserves existing draft dependencies and does not uninstall Android apps.

Background apps apply to the whole device and take no space on Core's home bar. Drag Core apps into the area, select a chip to configure it, or move it back onto the bar. Changes support Undo, draft save, deploy and recovery. Removing a background app stops it at the next successful deployment, unless it is still placed on the visible bar; it remains installed on Android.

Vivo Screen Sync offers Follow Core / Always on and a 0–3000 ms wake delay in 250 ms steps. Deploy writes only these preferences while preserving other app preferences, configures online VivoCubes using the existing approved bridge credential, and starts its foreground service without opening its settings screen. Root WiFi ADB and an online VivoCube are still required at deployment. Other background apps offer Launch after Deploy and rely on their own Android background support. Offline tests cover installation, drag/drop, settings, persistence, dependency verification and hidden apps staying out of the LineOS widget payload; physical-device service startup remains to be verified.

## 0.37 update

Deployment now uses a styled Studio dialog with an indeterminate progress indicator, readable status and elapsed time. Success and errors have distinct titles, icons and actions. The result remains visible until closed; Escape stays blocked during deployment. Layouts adapt to narrow windows and respect reduced motion. Offline browser checks exercise running, failure, retry and success without sending settings to hardware.

## 0.36 update

The update dialog displays release notes from the latest public GitHub Release, including when that version is already installed. Notes are displayed as text; embedded HTML and scripts are never executed.

Studio reconnects to the last successfully saved CoreBAR address at launch, including after restarting Windows. If CoreBAR or the network is offline, startup retries every 15 seconds. Opening Manage connection / Connect device stops these retries so you can choose a different device. A failed connection never replaces the saved address. If CoreBAR's IP address changes, select it again through Connect device.

Settings in the sidebar includes Start with Windows (off by default), saved immediately for the current Windows user in installed builds. Uninstall removes Studio's login startup entry. Startup registration follows the [Windows per-user Run key](https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys). The development server shows this setting as unavailable.

## Independence, testing and responsibility

Studio is independently developed and is not made in collaboration with, affiliated with or endorsed by the UltraBarX / CoreBAR team. It is under active development. Use it and any third-party packages at your own risk. The software is provided as is, without warranty; to the extent permitted by law, the authors and contributors are not liable for resulting loss or damage. Non-excludable legal rights remain unaffected. See [LICENSE](../LICENSE) and the [project README](../.github/README.md).

The Windows installer is currently unsigned and may trigger an unrecognized-app or unknown-publisher SmartScreen warning. A reputation warning alone is not a malware detection or a guarantee of safety. Use official GitHub Releases and their checksums; see the project README for details.

## 0.35 update

Removed the forced-maximized window policy and its native move/resize interception. Studio starts maximized but now has normal Windows move, resize, maximize, restore and minimize controls. Tray reopening preserves the previous normal size or maximized state instead of forcing maximization. Closing still hides Studio in the notification area; Exit still shuts down completely.

## 0.34 update

Closing the Studio window keeps it running in the Windows notification area. Double-click the tray icon or choose Open Studio to reopen maximized. Exit fully stops Studio; update installation also exits fully before launching Setup. Opening the shortcut while Studio is already running restores the existing window. PC actions and native widget metrics continue in background threads. Normal minimize remains available.

Store cards show cached GitHub Downloads and Open issues badges. Downloads count fetches of the currently published package artifact, including repeat and automated downloads; they are not unique users/installations or lifetime totals across every release. Issue counts exclude pull requests. Counts load asynchronously for visible cards, normally refresh on a 15-minute cache, and respect rate-limit cooldown. Unavailable counts display a dash or last known value rather than a false zero. No GitHub login or user telemetry is required.

## 0.33 update

Studio has a new desktop/window/sidebar icon. Store cards automatically resolve the package's source repository and provide Repository, Issues and Pull requests links in the system browser. Links are derived from validated GitHub source references rather than arbitrary client URLs; new install records retain source references for delisted packages. Local development packages are not presented as verified GitHub publishers.

## 0.32 update

Install from folder previews and installs local development packages without Store publication or a catalog connection. Widget/preset packages use separate local library IDs and an explicit Local development label. They can be edited and deployed like Store widgets. Local APKs require complete Android metadata and a signed non-debuggable APK; installation uses the same device, compatibility and Android identity checks. Folder contents are snapshotted before confirmation and are never executed as setup/build scripts.

## 0.31 update

Store now reads the generated catalog feed. Package PRs change only their own folder; GitHub assembles and publishes the approved list after merge, preventing shared catalog-array conflicts between independent package updates. The last successful feed remains available if validation or publication fails. This is a one-time client feed migration; supported package updates continue independently of Studio.

## 0.30 update

Store package cards now identify the uploader with their GitHub account. Publisher declarations are checked against the package source owner, and new installations retain the attribution if a package is later delisted. Existing catalog entries can derive attribution from their GitHub source URL. Store submissions now require a registered owner repository and verified publisher rather than a first-party exemption.

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

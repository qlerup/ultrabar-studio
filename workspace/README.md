# UltraBar Studio — 0.19 Windows

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

## Windows-installation

Kør `release/UltraBarStudio-Setup-0.2.0.exe`. Appen installeres for den aktuelle Windows-bruger og får en Start-menu-genvej samt en almindelig afinstallation under Installerede apps. En skrivebordsgenvej kan vælges i installationsguiden.

Programmet har sit eget vindue. Python, ADB og programafhængigheder følger med. Microsoft Edge WebView2 Runtime skal være installeret; det kontrollerer installationsprogrammet. Ingen browser skal åbnes og ingen server skal startes manuelt. Appen starter en privat loopback-server på en ledig port og lukker den sammen med vinduet.

Backups, husket IP-adresse og log gemmes i `%LOCALAPPDATA%/UltraBar Studio`, separat fra installationsmappen. De bevares ved opdatering og afinstallation. Installer og app er endnu ikke kodesigneret.

## Hardware-preview

Modullisten kommer fra den autentificerede CoreBridge-forespørgsel `30730` (runtime supervisor). Den er uafhængig af profilernes actions. Modulnavn og type slås op i CoreBARs endpoint-register. Nye runtime-moduler uden kendt type vises som ukendte; gamle registreringer uden runtime-status indsættes ikke i previewet.

CoreBAR rapporterede ved testen seks moduler: to VivoCube, to KnobKey, én DotKey og én SenseCube. Fem var online, én KnobKey offline. Previewet gengiver den rapporterede status og viser et aflæsningstidspunkt. Placering er skematisk, ikke en konstateret fysisk rækkefølge. Cube-skærmene er illustrationer, ikke live-video.

Status læses ved Forbind og Opdater. Hvis statusforespørgslen fejler, vises en fejl i stedet for at udgive gemte konfigurationer for at være forbundne moduler. Den tidligere godkendte diagnosticeringsklients credential læses via ADB og bruges kun i hukommelsen; det pakkes ikke med appen eller gemmes i loggen. Certifikatet matches præcist før autentifikation.

## Byg installationsprogrammet

Opret `.venv-build`, installer `requirements-build.txt`, og placer Inno Setup 6-kompileren i `build-tools/InnoSetup`. Kør `Build-Installer.ps1`. Bygningen inkluderer kun kode, statiske assets, certifikat og ADB — aldrig `data/` eller brugerens profiler.

Valideret: otte backend-tests, browserflow med seks runtime-moduler, responsive layouts, fejlsvar, native pakket WebView-opstart, live enhedslæsning, normal lukning, installation og Start-menu-genvej. `--smoke-test --live-test` tester den pakkede app mod den aktuelle enhed og skriver PASS/FAIL i brugerens datamappe.

Opdatering: kør en nyere installer med samme AppId. Tilbageførsel: afinstaller programmet og geninstaller tidligere version; behold datamappen. Ingen ændringer er foretaget i CoreBARs firmware eller profiler.

## Lokal udvikling

Vores egen lokale brugerflade til UltraBar X. Læsning af den rigtige enhed, profiloverblik, modul-actions, widgets, skærmbillede og automatisk backup. Ingen simulerede enheder eller demo-profiler.

## Start

Fra denne mappe: `python -m pip install -r requirements.txt`, derefter `python server.py`.
Åbn http://127.0.0.1:8741 og tryk **Forbind**. Alternativt start serveren med `Start-Studio.ps1`.

Kræver Python, den eksisterende `../tools/platform-tools/adb.exe` og WiFi ADB på CoreBAR. Den aktuelle adresse er 10.10.0.181:5555 og kan ændres i appen. Den testede CB01 tillader læsning af appens profilfil via ADB; andre firmwareversioner kan nægte denne adgang.

## Funktioner og grænser

- Læser profiler fra LineOS på enheden og viser konfigurerede moduler. Listen er **ikke** en livefortegnelse over alle fysisk tilsluttede moduler.
- Inputs og actions læses fra den gemte konfiguration. Ukendte felter kan ses under **Vis gemte data**.
- Opdatering er manuel; tidsstemplet angiver seneste vellykkede læsning.
- Henter et skærmbillede efter klik. Ingen fjernbetjening eller kontinuerlig streaming.
- Gemmer den originale profil-XML i `data/backups/<sha256>.xml`, med én fil pr. forskelligt indhold. Backup kan downloades. Automatisk gendannelse er ikke implementeret.
- Ingen ændringer af profiler, firmware, widgets eller actions på enheden i denne version. Redigering/deploy og PC-action execution er ikke implementeret.
- Kører kun på loopback. API kræver sessionstoken og korrekt Host. Ingen eksterne biblioteker indlæses i browseren.
- Backups indeholder privat konfiguration og skal holdes lokale. `data/` er ignoreret af Git.

## Næste trin

1. Lokal editor med kladder og validering for én understøttet action-type ad gangen.
2. CoreBridge-parring og verificeret deploy med ændringskontrol, backup og readback.
3. Eksplicit tømning af fjernede actions for at undgå den verificerede LineOS-fejl med gamle scenes i hukommelsen.
4. PC-actions, widgeteditor og automatisk genforbindelse.

En vellykket protokolkvittering beviser ikke, at en action er genindlæst i runtime. Deploy skal testes både med readback og fysisk input.

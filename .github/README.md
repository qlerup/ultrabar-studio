# UltraBar Studio

[![Downloads](https://raw.githubusercontent.com/qlerup/ultrabar-studio/stats/downloads.svg?v=2)](https://github.com/qlerup/ultrabar-studio/releases)

<img width="2541" height="861" alt="image" src="https://github.com/user-attachments/assets/2ab39753-689d-447c-9a8f-55cf33a46535" />

<img width="2538" height="1197" alt="image" src="https://github.com/user-attachments/assets/899e67e1-70bd-42a8-b0b1-1819f296e1c6" />

<img width="2551" height="1141" alt="image" src="https://github.com/user-attachments/assets/9eab287b-4ec9-40e5-bb7f-439abccb715f" />


A community-built Windows companion for UltraBar X / CoreBAR. Independent of the official UltraBarX software.

[Latest release](https://github.com/qlerup/ultrabar-studio/releases/latest)

- See connected modules, status and saved screen previews.
- Arrange your desk layout around a centered CoreBAR.
- Edit profiles, widgets and button actions, then deploy to Core.
- Drag separate website and PC app widgets onto Core; upload a picture or use the program icon automatically.
- Add live CPU, RAM, GPU and disk widgets where supported.
- Browse collapsible libraries for **UltraBarX**, **Studio & App Store** and **Installed apps**.
- Save local drafts and backups, and download verified Studio updates in the app. The installer replaces program files and keeps saved data.

Native Studio widgets currently require a root-enabled ARM32 CB01 running LineOS 1.0.8 or 1.0.9, with Studio connected. GPU readings depend on available sensors. Other firmware has not been verified.

## App & Plugin Store

Studio 0.20 supports integrated widget packages: install once, drag from **Studio & App Store**, configure in the right panel, then **Deploy** to activate on Core. Packages use the shared clock/date and hardware-widget runtime. Standalone APK installation remains available as a separate app type; arbitrary executable plugins are not supported.

[Submit your widget](https://github.com/qlerup/ultrabar-store/blob/main/CONTRIBUTING.md). GitHub checks the submission and explains errors in the PR. The owner reviews and merges approved catalog entries; new packages appear without a Studio update.

Developers can submit their own supported apps, widgets and presets so other users can install them through the Store. Keep the source in your own repository, publish a release and submit a Store PR. New packages require maintainer acceptance; eligible updates to registered packages can auto-merge after checks. [Read the submission guide](https://github.com/qlerup/ultrabar-store/blob/main/SUBMIT-A-PACKAGE.md). Use **Install from folder** in Studio to test locally before submitting.

## Windows security warning

Studio's Windows installer and executable are currently not code-signed. Windows may show an **unrecognized app**, **unknown publisher** or **Windows protected your PC** warning because the file or publisher does not have an established reputation. That reputation warning alone does not mean malware has been detected; it is also not a guarantee that software is safe or free of defects. See [Microsoft's SmartScreen explanation](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation).

Download Studio only from this repository's official [Releases](https://github.com/qlerup/ultrabar-studio/releases). Each release includes a SHA-256 checksum file. Verify the source and decide whether you trust the download before running it.

## Independence and use at your own risk

UltraBar Studio is an independent community project. It is **not developed in collaboration with, affiliated with, endorsed by or supported by the team behind UltraBarX / CoreBAR**. Product names and trademarks belong to their respective owners.

Studio is actively under development and is available for testing. You use Studio and third-party packages **at your own risk**. The software is provided **as is**, without warranties, including warranties of fitness, reliability or compatibility. You are responsible for your device configuration, backups and any changes you deploy.

To the maximum extent permitted by applicable law, the authors and contributors accept no liability for loss of data, device malfunction, damage, interruption or other losses arising from use of Studio or installed packages. This does not exclude rights or liability that cannot lawfully be excluded. See [LICENSE](../LICENSE).

## License

Proprietary source-available software, not open source. You may use unmodified official releases. Modifying, redistributing or building derivative versions requires written permission. See [LICENSE](../LICENSE). Third-party components retain their own licenses.

Bug reports and feedback are welcome in [Issues](https://github.com/qlerup/ultrabar-studio/issues).

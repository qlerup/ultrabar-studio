# Test a package locally before submitting it

1. Open UltraBar Studio 0.40+ and select **App & Plugin Store > Install from folder**.
2. In the popup, use **Browse** or paste an absolute folder path and choose **Check
   folder**. Review the package and the file, integrity and Studio compatibility checks.
3. Select **Add manual app**, widget or preset. This creates a local Store card;
   nothing is installed by checking or adding the folder.
4. Select **Install** on the manual card to add the package to your library.
5. Add an app/widget to the Core layout, or put a Core app in **Background apps**,
   then Deploy. Core apps are installed and checked against the device during Deploy;
   adding the manual card or installing into the library does not require Core.
6. After editing your package, open **Install from folder** again to check and add the
   new build. Local packages are not submitted to GitHub or the public Store.

## Folder contents

All local packages require a square static icon.png (256x256 or 512x512, at most
256 KiB). Supply exactly the payload for the selected package type:

- Integrated widget: widget.json, icon.png, optionally manifest.json.
- Presets: plugin.json, icon.png, optionally manifest.json.
- Standalone Core app: app.apk, icon.png and manifest.json.

For JSON packages without a manifest, Studio derives a local ID/name from the
folder, uses version 1.0.0 and the currently supported CB01/ARM32/LineOS defaults.
Use a manifest for stable identity/version and your actual compatibility. The
same format as a Store submission is accepted. Declared artifact/icon hashes and
sizes must match the local files; update them when changing the package. Download
URLs and publisher claims are not used to install or endorse a local package.
No GitHub release, repository.json or network download is required for local testing.

APKs must already be compiled and signed. manifest.json must declare the Android
package ID, versionCode, minimum SDK, signer SHA-256, exact permissions and supported
hardware/firmware. The same non-debuggable APK requirement applies as in Store.
Studio does not compile Android source or run package-supplied commands/scripts.

Local widgets/presets get a separate local.* library identity, so they do not replace
Store templates. Removing a local library package keeps existing placed blocks;
remove blocks and Deploy to remove them from Core. Local APKs use their declared
Android package ID: installing a matching signed APK updates that Android app and
preserves its data. A different signing key is rejected by Android. No automatic
uninstall or downgrade is performed. Remove APKs through Core settings.

The preview uses a bounded snapshot and expires after ten minutes. Adding the package
retains that verified snapshot for the manual Store card, including across restarts.
Changing or moving the source folder does not change what Install applies; check and
add the folder again to load new content. Manual cards are available offline. A folder
picker is available in the desktop app; the browser-only development server can accept
a folder path accessible to that server. Local testing does not replace
Store review, licensing checks or testing on physical hardware.

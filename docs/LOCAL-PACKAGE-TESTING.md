# Test a package locally before submitting it

1. Open UltraBar Studio 0.32+ and select **App & Plugin Store > Install from folder**.
2. Select the directory containing your package. Review the name, type and permissions.
3. Select **Install**. Nothing is installed merely by choosing the folder.
4. Widgets/presets appear in the library. Drag a block onto Core, edit its settings
   and Deploy. APKs require a connected Core and appear in its Android app list.
5. After editing your package, choose **Install from folder** again to snapshot and
   install the new build. Local packages are not submitted to GitHub or Store.

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

The preview uses a bounded snapshot and expires after ten minutes. Changing files
after preview does not change what Install applies; select the folder again to
load new content. A folder picker is available in the desktop app; the browser-only
development server has no native folder picker. Local testing does not replace
Store review, licensing checks or testing on physical hardware.

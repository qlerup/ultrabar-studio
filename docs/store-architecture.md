# Independent store delivery (planned; not an installed feature)

## Decisions

Studio remains proprietary/source available. Third-party apps retain their own
licenses and are submitted to `qlerup/ultrabar-store` through pull requests.
qlerup reviews and approves entries before publication. No Studio executable
release is needed to add packages using an already supported installation type.
A new installation type, permission or host API can require a Studio update.

The store repository publishes a versioned catalog. Application binaries are
prebuilt, signed GitHub Release assets, not compiled on users' computers.
A catalog entry pins an exact version, asset URL, byte length and SHA-256.
APK entries additionally pin Android package ID, versionCode and signer
certificate SHA-256. Never use a moving `latest` URL for installation assets.

## Existing implementations inspected

* `screen-sync/AndroidManifest.xml` and `screen-sync/provision.py`: Vivo Screen
  Sync is an Android APK (`dk.ultrabarx.screensync`), installed with `adb install
  -r`. Current version is 0.4-test, versionCode 4, minSdk 26, targetSdk 28.
  It is debuggable and testsigned. Provisioning uses `run-as` and injects the
  already-authorized CoreBridge credential into app-private storage, then starts
  its activity. Current provisioner contains fixed device serials/IP. This is a
  local test artifact, not a store-ready release. Removing debuggable also removes
  the current `run-as` provisioning path; a secure pairing interface must be
  implemented before a production release. Do not publish its signing key,
  credentials, provisioned files or a falsely labelled production APK.
* `workspace/native_widgets.py` and `native-widgets/src`: CPU/RAM/disk widgets
  run as LineOS child views using `studio-widgets.dex`, a pinned Frida 16.7.19
  runtime and host-supplied metrics. Supported target is root-enabled CB01,
  ARM32, LineOS 1.0.8. They are not independent Android APKs and need Studio
  connected. DEX/runtime replacement is privileged and not a generic plugin API.
* `pc-hardware/README.md`: the old accessibility overlay experiment is retired.
  It must not be bundled or used as the store's widget installation mechanism.

## Package families

### corebar-app / android-apk

Publish a release-signed APK as a GitHub Release asset alongside the catalog
manifest. Studio verifies download hash/size, APK package ID, versionCode,
signing identity, device API/ABI and declared permissions. The user chooses the
connected Core and approves installation. Studio invokes a fixed argument-list
ADB installer (`install -r`), never scripts provided by the package. Verify the
installed package/version after completion. Updating an existing package must
preserve its signer. Never silently uninstall to resolve a signing conflict or
use downgrade flags. Application-specific pairing follows a reviewed host API.
Installation does not automatically grant root or expose shared credentials.

### corebar-widget / studio-native-v1

Initially first-party-only until a supported renderer contract exists. Package
contains the compiled DEX and declarative widget metadata, with explicit model,
LineOS, ABI, runtime and minimum Studio API requirements. It is distinct from an
APK. Install must back up the previous renderer, detach it safely, swap validated
files atomically, reconnect and roll back on failed health checks. Widgets are
activated through the existing draft/deploy flow, never by overwriting profiles.

### studio-plugin / studio-plugin-v1

A versioned ZIP with manifest and payload. Start with declarative actions and
widget templates supported by an explicit host API. Executable extensions need
an out-of-process host and a reviewed permissions protocol; do not import
arbitrary Python or inject JavaScript into the privileged Studio UI. A ZIP alone
does not make a runnable plugin. This runtime still needs implementation.

## Catalog and author workflow

1. Author submits source/build instructions, manifest, license, screenshots,
   compatibility information and permission rationale in a pull request.
2. Tests validate metadata; no privileged jobs run on untrusted PR code.
3. qlerup reviews the source and requested capabilities, then merges.
4. A trusted release pipeline builds and signs the app using protected signing
   credentials (never in Git). Retain and back up each APK signing key.
5. Publish immutable versioned release assets, then merge the catalog entry
   containing the actual checksums and signer identity. Do not add dummy hashes.
6. Studio refreshes the remote catalog on demand and compares package versions
   with its local installation registry independently of Studio's version.

## Download/install requirements for implementation

Use a trusted catalog origin, bounded HTTPS downloads, repository/asset allowlist,
verified hash/length and an explicit supported catalog/host API version. Recheck
the Core identity immediately before installation. Serialize installs per device.
Store state by device serial and package ID, not IP address. ZIP extraction must
reject absolute/traversal paths, symlinks, duplicate entries and decompression
bombs. Stage in a temporary directory, verify before activation and atomically
record successful installation. Failures must leave a recoverable previous state.

Show actual permissions and compatibility before Install. Support cancellation,
clear offline/errors, installed/updatable states and package-specific uninstall.
APK data backup/restore is not universally available; do not claim rollback can
restore application data. Revocations disable new installs; never remove an
installed app silently. Catalog signature and key-rotation design should be
completed before enabling executable community packages.

## Next milestones

1. Production-sign and implement secure pairing for Vivo Screen Sync; remove
   fixed serials and targets and test install/update/uninstall on a test Core.
2. Implement catalog fetch, store UI and verified Android APK installer.
3. Stabilize native widget host API and separate renderer delivery.
4. Implement declarative Studio plugins, then a constrained executable plugin host.

No store installation endpoint is enabled by the 0.14 release. This document
is an implementation plan based on inspected code, not a claim of runtime support.

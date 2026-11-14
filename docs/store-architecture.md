# Store delivery and integrated widgets

Studio 0.20 reads the owner-reviewed main-branch catalog in qlerup/ultrabar-store.
Opening the store, Refresh and a visible one-minute timer fetch new entries.
Installing rechecks the selected ID/version/hash against that catalog. Downloads
are bounded and pinned to versioned official GitHub release assets by SHA-256
and byte size. Package updates do not silently change placed widgets or drafts.

## Integrated corebar-widget packages

The package is declarative JSON: widgetApi 1, runtime studio-native-v1 and a
list of widget definitions with stable IDs, kind, name and default settings.
Supported kinds are clock, cpu, memory, gpu and disk. Clock adds hourFormat,
showSeconds and showDate. Names and colors are editable in the existing panel;
disk uses the existing drive selector. No submitted code is executed.

Install validates and records the package locally without ADB writes. Templates
appear under Studio & App Store. Drag creates an independently editable native
widget instance retaining package ID/version/key. Draft save validates settings.
The existing verified Deploy flow checks Core compatibility, backs up settings,
transfers the shared renderer, writes the layout and verifies readback.

The renderer is shipped with Studio, not replaced by downloaded packages.
Additional packages using supported kinds/defaults need no Studio update.
A new renderer or data source requires a host API enhancement first. This is
not an arbitrary executable plugin platform.

Native integration requires root-enabled ARM32 CB01 and LineOS 1.0.8 or 1.0.9.
Clock uses Core time/locale; preview uses PC time/locale. Hardware metrics need
Studio connected. Studio must reconnect to restore rendering after Core restart.
Removing a library package preserves placed cards. Remove a card and Deploy to
remove it from Core. No destructive package-uninstall action changes profiles.

## Other package types

corebar-app installs a standalone APK using fixed ADB install -r arguments.
The app checks metadata, permissions, signer identity, device identity/API/ABI,
size and hash. Android verifies the cryptographic signature. No silent uninstall
or downgrade is used. These apps are separate from integrated widget packages.

studio-plugin is the legacy declarative preset format (pluginApi 1). Executable
Windows plugins, arbitrary renderer DEX packages, custom remote scripts and ZIP
extraction are not supported. APK submissions currently require manual review;
the new contributor bot only accepts integrated corebar-widget submissions.

## Review and publication

See https://github.com/qlerup/ultrabar-store/blob/main/CONTRIBUTING.md for exact
files and UI steps. Contributors fork, commit package/source/license/docs and
open a PR. The owner publishes exact reviewed JSON bytes as a versioned release
asset, then adds a matching manifest/catalog entry in that PR. Publication of a
review asset alone does not make a package visible in Studio.

GitHub Actions runs the main-branch validator against PR data, never contributor
code. Checkout credentials are not persisted. The comment step alone receives
the token used to update one PR comment. Checks cover required files, metadata,
compatibility, supported fields, immutable source reference, unique IDs, local
hash/size and equality with the published artifact. New commits rerun checks;
workflow_dispatch accepts a PR number for manual reruns. Ready for approval is
reported only when publication checks pass. Human review and merge remain final.
The bot cannot prove license ownership, visual quality or physical Core behavior.

## Compatibility and persistence

Package/host versions are explicit. Downloads with unsupported host versions or
capabilities fail before installation. User drafts, backups and package records
stay in Studio's data directory, separate from installer program files. Existing
clock/settings formats require no migration. Clock hardware rendering still
needs owner testing; automated checks use isolated data and mocked device writes.

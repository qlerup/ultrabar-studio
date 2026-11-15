# Bambu Liquid native integration

Requires Studio 0.46, root-enabled CB01 / LineOS 1.0.9 and the reviewed Bambu Panel
companion APK (`dk.ultrabar.bambu`). Earlier LineOS 1.0.8 has not been tested with
this renderer, even though the existing native host supports it.

Each placed JSON widget uses `kind=bambu`. Studio stores primary/secondary
reading, expandedSlots 2–5, showJob/showTemperatures/showLayers/showRemaining,
showControls and liquidMotion in that widget's native params. Typed contract
validation runs before save/deploy. No executable package fields, credentials,
arbitrary IPC endpoints or installation commands are accepted.

The trusted renderer polls one fixed ContentProvider off the UI thread, once per
second with at most one request in flight. Its cache expires visibly, and printer
state freshness and action authorization remain enforced in the companion. The
companion alone stores encrypted printer credentials. Missing companion blocks
Deploy with setup instructions; missing state renders as unavailable. The
companion is installed by the existing reviewed APK path, not arbitrary code
loaded into the system launcher.

Tap opens a native temporary presentation anchored to the actual source card.
Width includes 2/3/4/5 measured card widths plus the actual intervening gaps. The
available row positions determine expansion to the left, right or both. Neighbor
item views translate outward in the same animation, leaving the normal gap at
each edge; their exact translations and source opacity are restored on close.
No RecyclerView adapter model or saved profile position is changed. A
bounded spring changes the outline and an edge wave settles into place while
content fades in. Content stays at its final layout width, avoiding per-frame
text reflow. Controls cannot receive taps while animating. Outside tap, collapse
and Back remove the layer. No profile width/order is written. Android reduced
motion and the per-widget preference disable the spring/wave.

## Validation

- 158 Studio regression/browser tests passed, including native/package/settings paths.
- Offline browser: two independently configured cards; Save, reload, Undo and
  narrow layout. Browser screenshots use sample data; no ADB writes.
- Java geometry checks: spring endpoints, bounded overshoot, 2–5 widths and edge
  clamps. Existing drive paging tests also pass.
- Native build succeeds with Android SDK 35 / D8 minimum API 26.
- Physical CB01 / Android 10 / active LineOS 1.0.9: temporary expansion in the
  real launcher at widths 542, 823, 1104 and 1385 px; 20px gaps and the host's
  60px corner radius preserved; launcher UID IPC accepted;
  Back/reduced motion tested. No saved profiles or layouts were changed.
- Separate Android preview APK exercises the same native renderer with clearly
  labelled sample data; it is not shipped as the production companion.

The opt-in physical probe is `native-widgets/tests/host_probe.py`. It requires
the existing trusted Studio runtime/token, explicit ADB target and installed
companion; removes its temporary layer, ADB forward and review DEX in finally.
It does not provide printer credentials, modify the saved layout or control a
real printer. Do not run it as an unattended install step.

Real printer tests, the full Store install→drag→Deploy flow, updates and removal
remain release acceptance checks. The runtime PR and matching Store contract
must land before the new JSON widget is publishable. Existing released Studio
versions reject the new kind; do not lower its declared minimum Studio version.

## Review and rollout

No known build/contract blockers remain in these isolated checks. Release blockers
are the untested real-printer/full-deployment flows and pending companion/Store
review. Important follow-up: verify representative old/new Bambu firmware and
selected-profile persistence during a same-signer upgrade. Optional future work:
camera, AMS cards and model-specific artwork, through separately reviewed APIs.

Ship matching Studio/runtime/Store contracts together. Keep app controls off until
the physical state is checked. Closing the expansion restores the existing home
view; remove placed widgets and Deploy to stop using them. The companion retains
private data until forgotten/uninstalled. Forward fixes preserve Android signer,
package ID and increasing versionCode. Preserve existing drafts and backups.

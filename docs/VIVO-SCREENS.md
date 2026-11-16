# VivoCube screen pictures

Choose Module actions, select the VivoCube, then use Vivo screen picture.
Upload a static PNG/JPG/WebP up to 2 MB, or choose Use action icon. Adding a
website action supplies a default globe; a PC program supplies its executable
icon where available. A custom uploaded picture is preserved when editing actions.

This editor creates one full-screen button, using the selected Cube's existing
button ID or 101 for a new Cube. The image is shared across profiles and press
variants. Existing multi-button layouts must not be replaced while other button
actions remain assigned. Clear screen & actions asks for confirmation, clears
that Cube's actions across profiles, and prepares a blank screen for Deploy.
Other modules are preserved. Undo and local draft saving support these changes.

Deploy backs up original Core preferences and cached Vivo archives, preserves
existing gateway/network configuration, registers the picture button on Core,
then uploads the actual RGB565/alpha artwork package through Core's vendor
service. Core's module supervisor briefly rebuilds its endpoint registration.
Studio requires firmware acknowledgement and matching cached bytes; it never
blindly retries a timed-out upload. Partial changes may already have occurred
when an error is reported. Your draft/backups remain available; reconnect and
review before retrying. The saved-image preview is not a live camera of the Cube.

Backups and image cache are local Studio data under %LOCALAPPDATA%/UltraBar Studio.
Keep Studio running for website/PC program actions. These changes do not require
an update to the separate Vivo Screen Sync APK.

Studio automatically rounds the corners of uploaded pictures and action icons.
The preview uses the same renderer as the normal/pressed device artwork. Original
uploads are retained; Deploy again to apply rounded corners to existing pictures.

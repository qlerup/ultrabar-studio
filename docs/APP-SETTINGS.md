# Studio app settings API 1

The normative specification, complete Android example, required files and contributor
checklist are maintained in the Store repository:
https://github.com/qlerup/ultrabar-store/blob/main/APP-SETTINGS.md .

Requires Studio 0.45.0 and root-enabled Core ADB with su support. Generic transport
reads/writes only with the registered ordinary app UID, never as root in an app's
mutable data directory. Request bytes are verified before notifying the protected
receiver. Responses must have the current revision and valid full saved values.

Settings are global per app and are stored locally with drafts and pre-deploy
backups. Read current values before changing an existing installation. Changes may
already have occurred when a later Deploy stage fails; read back before retrying.
Restoring a backup prepares a draft, and applying it requires a new Deploy.

Settings API 1 does not provision bridge credentials or execute contributor code.
Existing packages without the descriptor keep their existing controls. JSON native
widgets continue using widgetApi 1 and their existing per-block settings.

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
widgets continue using widgetApi 1 and per-block values. From Studio 0.49.0 they
may own their settings UI and connection panels through a declarative `studio`
descriptor; see [Studio panels](STUDIO-PANELS.md). Both mechanisms use the shared
field renderer while retaining their separate setting scopes and transports.

## Runtime and installation ownership

Install a Core app into the Studio library, add it to the layout or background apps, and use Deploy to install it on the connected Core.

| Package | App and widget responsibilities | Studio responsibilities today |
| --- | --- | --- |
| Bambu Printer Panel | Core APK owns printer setup, credential storage, LAN telemetry and controls for the selected printer. | Install the APK and optionally relay supported display settings. |
| Bambu home widget and legacy widget | The data-only package declares the model choices, artwork and per-card settings. Existing cards can follow separate printers. | The current connector owns the PC's saved printer profiles, streams telemetry to Core and relays printer actions. |
| Vivo Screen Sync | Core APK runs screen sync and persists its mode and wake delay. | Verify the first-party signing identity and provision the approved Core bridge credential. Some older deployments also use a dedicated settings path. |
| Clock & Date | Package declares time format and date preferences. Core supplies its local time. | Install and restore the shared native card host and relay layout settings. |
| Drive Usage and System Monitor | Packages declare which readings and formatting to show. | Sample the Windows machine and relay those measurements to Core's native card host. |

Third-party apps can use the standard signed APK workflow without a Studio code
change. Apps should hold their own secrets, do protocol work in their own process
and save their own preferences. For PC readings, Studio remains a transport for
data produced on the PC. Native cards use the supported declarative renderers;
the Store does not load contributor code into Core's privileged launcher.

The standalone Bambu panel has its own app storage. A future migration of
existing Bambu cards must preserve their per-printer bindings, saved layouts and
explicit certificate trust, including deployments where the PC can reach a
printer but Core cannot. Installing the panel does not perform that migration.

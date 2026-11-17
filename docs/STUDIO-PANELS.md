# App-owned Studio panels (API 1)

Requires Studio 0.49.0. A native widget may declare a `studio` object in its
reviewed `widget.json`. The app package owns its labels, help, field order,
defaults and supported options. Studio renders the descriptor with shared controls.
Changing those descriptions requires an app update, not a Studio UI patch.

```json
{
  "id": "clock",
  "name": "Clock",
  "kind": "clock",
  "studio": {
    "api": 1,
    "settings": {
      "api": 1,
      "fields": [
        {"key": "showSeconds", "label": "Show seconds", "type": "boolean", "default": true}
      ]
    },
    "help": "These display settings apply to this widget."
  }
}
```

The descriptor is part of the checksum-verified package. It is not copied into
layout drafts or sent to Core. Only widget setting values and opaque connection
IDs belong in a draft. Existing packages receive compatibility descriptors;
existing placed widgets retain IDs, settings and connection selections.

`settings` reuses the declarative field types from Android settings API 1, with
keys constrained to the selected native renderer. `expandedSlots` is an integer,
not a string choice. Disk widgets may declare `sources: {"drive": "pc.drives"}`;
the common renderer then includes current drives and the saved drive selection.
The runtime continues validating actual setting values before deployment.

An optional `connection` describes the connection picker and manager: `provider`,
`key`, `label`, `title`, `manageLabel`, `itemLabel`, `setupHelp`, and `fields`.
The initial trusted provider is `bambu-lan`, with key `printerId`. It requires
name, host, serial, secret code and controls fields. The package can label these
fields but cannot change a secret into a public field or replace the transport.

The common manager lists, discovers, probes, saves, removes and reconnects through
`/api/studio/integrations/<package>/<widget>/<operation>`. Only `list` uses GET;
the other operations use POST. `list`, `discover` and mutations return `items`;
`probe` returns a certificate `pin`. Remove/reconnect receive an `id` object.
The server resolves the installed package and widget before invoking a trusted
adapter. Package data cannot supply executable code, endpoint URLs or commands.

Studio owns polling, error reporting and cleanup. Open connection managers refresh
every two seconds after the previous request finishes; typing and focus survive
status updates. Closing the manager stops polling. Certificate approval precedes
credential authentication. Bambu keeps its existing Windows DPAPI storage,
redaction, protocol checks and connection lifecycle.

The provider registry is the extension point for another device protocol. A new
adapter is reviewed and shipped with Studio; an app package selects a supported
provider and supplies its declarative panel. Downloaded Python/JavaScript plugins
are not executed. A genuinely new native renderer or protocol needs Studio support.

Android `corebar-app` settings remain global per app and use the existing protected
receiver/read/apply protocol. They share the field renderer but do not become
per-widget values. Vivo Screen Sync therefore needs no schema or APK migration.

Validation covers descriptors, installed-package authorization, provider dispatch,
legacy package loading, Store persistence, per-widget values, secret isolation,
generated fields, live status, focus preservation and dialog cleanup. Tests use
offline fixtures; they do not establish physical printer/Core acceptance.

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

## Package-defined settings in Studio 0.52.18

A widget installed in Studio can set `widgets[].studio.api` to `2`. Declare the
editor controls in `studio.settings.fields`. Each field supplies its own key,
label, type and default. The same Studio version reads added fields, choices
and defaults when the package is updated. Values belong to each placed card.
Use a stable package ID, widget ID and field key across releases.

For example, a package can declare a color as
`{"key":"plate","label":"Plate color","type":"color","default":"#353839"}`
and set `plateColorSetting` to `plate` in its split-flap presentation preset.
A choice field can select a package-defined presentation through
`presentation.source`. A printer presentation preset can specify
`minTemperatureRows` from 1 to 3. The existing Core layout applies these values
on Deploy. Publish changes to the widget JSON through the existing Store listing.

Supported field types are boolean, integer, number, string, URL, choice and
color. New field keys are stored under `packageSettings`, separately from the
card identity and transport settings. A field supplies configuration. A feature
that uses it also needs a renderer, presentation or device capability that
consumes its value. Declare `compatibility.minStudioVersion` of at least
`0.52.18` for panel API 2.

### Shared widget layouts

Panel API 2 accepts a `layout` object with a `large` and a `small` array. Each array declares up to 32 layers drawn in order. Use coordinates on a 260 by 240 canvas for large cards and 130 by 120 for small cards. Each layer declares an `op` and a `box` containing x, y, width and height. Supported operations are text, rect, bar, image and time. Bind a color to a field with `$fieldName`, text to a value with `@fieldName`, and visibility with `when`. For example, `{"op":"rect","box":[4,4,50,20],"color":"$plateColor"}` draws a plate in the selected color. Time layers continue ticking locally on Core. Studio previews the installed layout and Deploy supplies the same graphics to the home card. Keep the widget ID stable when changing layouts.

# Bambu printers in Studio

Studio 0.48 owns printer setup and Bambu LAN connections on the PC. Core is the
display and input surface, using the same metrics channel as CPU and drive cards.
The Bambu Android app is not required for these widgets.

## Setup

1. Install the **Bambu** widget package from Store and drag it onto Core.
2. In widget settings, choose **Manage printers → Add printer**. Enter a name,
   private IPv4 address, serial number and eight-character LAN access code.
   **Search local network** can fill the address and serial; it never reads codes.
3. Choose **Check connection**. Compare the displayed SHA-256 fingerprint with a
   trusted connection to the printer, then **Trust certificate & save**. The
   certificate probe sends no MQTT credentials.
4. Select the printer in each widget's **Printer** dropdown, then Save and Deploy.
   Different widgets can monitor different printers simultaneously, or different
   readings from the same printer. Up to 16 connections can be saved.
5. Keep Studio running. Core shows offline status when samples expire. A failed
   printer connection requires **Reconnect** in Manage printers.

The PC needs LAN access to each printer on TLS MQTT port 8883. Compatible firmware
may require LAN mode and Developer Mode for controls. Studio does not change
printer modes. Cloud login, camera, uploads, job starts, heating and AMS operations
are not implemented.

Connections save immediately, independently of the layout draft. Widget printer
selections use the normal draft, Undo, Save and Deploy workflow. Only opaque IDs
belong to drafts. A blank code retains the saved code only when address and serial
are unchanged. Removing a connection keeps its widgets; select another printer
before deploying them again.

## Storage and transport

`data/bambu-connections.json` uses Windows DPAPI bound to the current Windows user.
Addresses, serials, access codes and approved certificate pins are encrypted;
none are stored in layout drafts, exports or backups. The UI receives connection
metadata without codes or pins. Re-enter connections on a new Windows account.

Studio merges partial reports and normalizes legacy/packed multi-extruder
temperatures. Only bounded, whitelisted telemetry is sent through the existing
`ultrabar-studio-metrics.json` channel. Core receives neither addresses nor printer
credentials. Each card reads its own printer ID. The editor preview uses sample data.

Pause/resume/stop/light default off per connection. Controls also require fresh
state, compatible firmware and the widget's own controls switch. Stop asks for
confirmation on Core. Short-lived actions travel through the trusted native runtime;
Studio checks widget/printer identity, age and duplicate IDs. There is no persistent
or offline command queue and no replay. MQTT PUBACK is not success: corresponding
printer telemetry must confirm the action within 12 seconds. Check the physical
printer after a timeout before retrying.

Native liquid expansion, 2–5 slots, neighbor movement, reduced motion and saved
layout restoration are retained.

## Updating from the Core app

The original `studio.bambu` identity is retained. Version 2.0.1 appears as **Update**
for the installed 1.x app. Studio 0.48.1 preserves placed widget IDs, names, colors,
readings and display preferences, removes obsolete companion dependencies and
background settings, and keeps the original saved draft recoverable until Save.
Configure printer connections in Studio, select each card's printer, Save and Deploy.
The briefly published duplicate `studio.bambu.widget` is consolidated into the
original identity on a successful update; failed updates preserve existing records.
Core credentials are not extracted or deleted. Uninstall the old APK separately
when it is no longer needed.

## Validation and physical acceptance

Tests cover Windows DPAPI save/reload/edit/removal, independent printer connections,
MQTT framing bounds, actual local TLS/MQTT sessions against an ephemeral fake
printer, certificate changes before credentials, stale reports, signed-command
gates, action routing and duplicate rejection. Browser tests cover setup, approval,
two independent selections, draft persistence, Undo and desktop/mobile forms.
Native Java/D8 builds and geometry tests validate the renderer.

Real H2D/H3C firmware, the physical Core action path, discovery on the owner's LAN
and the complete Store install → Deploy flow still need physical acceptance.
Synthetic tests do not claim those devices have been tested.

Run `python -m unittest test_bambu test_bambu_browser test_bambu_contract
test_native_widgets` from workspace. TLS tests use Git for Windows OpenSSL for
temporary certificates and skip when unavailable. No test accesses real printers.
Build with `python native-widgets/build.py` and `ULTRABAR_ANDROID_SDK` set to the SDK.

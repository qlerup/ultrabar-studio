"""One-time deployment of reviewed Core-side screensaver services."""
import base64
import hashlib
import json
import re
import subprocess
import time
import zipfile

import bridge

MARKER = 'assets/core-screensaver.json'
CLASS = '.CoreScreensaverService'
PACKAGE = r'[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+'
COMPONENT = re.compile(r'(' + PACKAGE + r')/\1\.CoreScreensaverService')
LEGACY_ID = 'qlerup.core.flip-clock-hd'
STATE = 'ultrabar_core_screensaver_v1'


def candidate(server, path, entry):
    try:
        with zipfile.ZipFile(path) as apk:
            item = apk.getinfo(MARKER)
            marker = apk.read(item) if item.file_size <= 256 else b''
    except (KeyError, zipfile.BadZipFile):
        return None
    from store import StoreError, ASSET_PREFIX
    package = entry['android']['packageId']
    if (not COMPONENT.fullmatch(package + '/' + package + CLASS)
            or not entry.get('settings') or entry.get('original_id') is not None
            or entry.get('publisher') != 'qlerup'
            or not entry.get('source', '').startswith('https://github.com/qlerup/')
            or not entry['artifact']['url'].startswith(ASSET_PREFIX)):
        raise StoreError('Automatic Core screensaver setup requires a reviewed first-party Store app.')
    try:
        descriptor = json.loads(marker)
        if not isinstance(descriptor, dict) or type(descriptor.get('api')) is not int or descriptor != {'api': 1}:
            raise ValueError()
        aapt = str(server.ROOT / 'assets/android/aapt.exe')

        def dump(kind, *arguments):
            result = subprocess.run([aapt, 'dump', kind, str(path), *arguments],
                                    capture_output=True, check=True, timeout=15,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return result.stdout.decode('utf-8', errors='replace')

        lines = dump('xmltree', 'AndroidManifest.xml').splitlines()
        for index, line in enumerate(lines):
            start = re.match(r'( +)E: service\b', line)
            if not start:
                continue
            depth = len(start[1])
            end = next((i for i in range(index + 1, len(lines))
                        if len(lines[i]) - len(lines[i].lstrip()) <= depth), len(lines))
            service = '\n'.join(lines[index + 1:end])
            if not re.search(r'android:name\([^)]*\)="(?:' + re.escape(package) + r')?\.CoreScreensaverService"', service):
                continue
            if ('"android.permission.BIND_ACCESSIBILITY_SERVICE"' not in service
                    or '"android.accessibilityservice.AccessibilityService"' not in service
                    or not re.search(r'android:exported[^=]*=\(type 0x12\)0xffffffff\b', service)):
                raise ValueError()
            metadata = re.search(r'android:name[^=]*="android.accessibilityservice"[^\n]*\n'
                                 r'\s*A: android:resource[^=]*=@(0x[0-9a-f]+)', service)
            resources = dump('resources')
            if not metadata or not re.search(r'\b' + metadata[1] + ' ' + re.escape(package)
                                             + r':xml/core_screensaver:', resources):
                raise ValueError()
            break
        else:
            raise ValueError()
        config = dump('xmltree', 'res/xml/core_screensaver.xml')
        if not re.search(r'android:canRetrieveWindowContent\([^)]*\)=\(type 0x12\)0x0\b', config):
            raise ValueError()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise StoreError('The app does not implement the supported Core screensaver contract.') from exc
    return package + '/' + package + CLASS


def state_path(server, device):
    digest = hashlib.sha256(device.encode()).hexdigest()
    return server.DATA_DIR / 'store' / 'screensavers' / (digest + '.json')


def read_state(raw, legacy_path):
    if raw in ('', 'null'):
        try:
            state = json.loads(legacy_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
    else:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,8192}={0,2}', raw):
            raise ValueError('Invalid Core screensaver state.')
        state = json.loads(base64.urlsafe_b64decode(raw))
    if not isinstance(state, dict) or type(state.get('previous', {}).get('featureEnabled')) is not bool:
        raise ValueError('Invalid screensaver backup.')
    if 'components' in state:
        if not isinstance(state['components'], list) or any(not COMPONENT.fullmatch(x) for x in state['components']):
            raise ValueError('Invalid screensaver service.')
        if state.get('accessibility') not in ('0', '1', 'null') or not isinstance(state.get('configured'), dict):
            raise ValueError('Invalid screensaver backup.')
    return state



def activate(server, target, device, component):
    from store import StoreError

    def shell(*args):
        return server.adb('-s', target, 'shell', *args)

    try:
        state = read_state(shell('settings', 'get', 'secure', STATE), state_path(server, device))
        if shell('getprop', 'ro.serialno') != device or not state or component not in state.get('components', []):
            raise ValueError('Core screensaver setup changed.')
        raw = shell('settings', 'get', 'secure', 'enabled_accessibility_services')
        enabled = [] if raw in ('', 'null') else raw.split(':')
        if any(not re.fullmatch(r'[a-zA-Z0-9_.$]+/[a-zA-Z0-9_.$]+', item) for item in enabled):
            raise ValueError('Unexpected accessibility component.')
        peers = [item for item in enabled if item not in state['components']]
        updated = list(dict.fromkeys(peers + [component]))
        if enabled != updated:
            shell('settings', 'put', 'secure', 'enabled_accessibility_services', ':'.join(updated))
        if shell('settings', 'get', 'secure', 'accessibility_enabled') != '1':
            shell('settings', 'put', 'secure', 'accessibility_enabled', '1')
        package = component.split('/', 1)[0]
        for _ in range(12):
            services = shell('dumpsys', 'activity', 'services', package)
            if re.search(r'ServiceRecord\{[^}\r\n]*\b' + re.escape(package + '/' + CLASS) + r'\}', services):
                raw = base64.urlsafe_b64encode(json.dumps(dict(state, components=[component]),
                                                         separators=(',', ':')).encode()).decode()
                shell('settings', 'put', 'secure', STATE, raw)
                state_path(server, device).unlink(missing_ok=True)
                return
            time.sleep(.25)
        raise ValueError('The screensaver service did not bind.')
    except Exception as exc:
        raise StoreError('Android did not start the Core screensaver service. Reconnect and retry Deploy.') from exc


def reconcile(server, target, device, component):
    from store import StoreError
    path = state_path(server, device)

    def shell(*args):
        return server.adb('-s', target, 'shell', *args)

    def save_state(value):
        raw = base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode()
        shell('settings', 'put', 'secure', STATE, raw)
        if shell('settings', 'get', 'secure', STATE) != raw:
            raise ValueError('Core did not save its screensaver state.')

    def set_native(config):
        try:
            bridge.screensaver(target, server.adb, server.ROOT, config)
        except Exception:
            pass  # Read back even when the response from LineOS was lost.
        actual = bridge.screensaver(target, server.adb, server.ROOT)
        if any(actual.get(key) != config.get(key) for key in ('featureEnabled', 'uri', 'ver', 'lockTime')):
            raise ValueError('LineOS did not retain the selected configuration.')

    try:
        state = read_state(shell('settings', 'get', 'secure', STATE), path)
        if component is None and state is None:
            return
        if component is not None and not COMPONENT.fullmatch(component):
            raise ValueError('Invalid screensaver service.')
        if shell('getprop', 'ro.serialno') != device or shell('id', '-u') != '0':
            raise ValueError('Core identity or root-enabled WiFi ADB changed.')
        native = bridge.screensaver(target, server.adb, server.ROOT)
        if type(native.get('featureEnabled')) is not bool:
            raise ValueError('Invalid LineOS screensaver state.')
        raw = shell('settings', 'get', 'secure', 'enabled_accessibility_services')
        enabled = [] if raw in ('', 'null') else raw.split(':')
        if any(not re.fullmatch(r'[a-zA-Z0-9_.$]+/[a-zA-Z0-9_.$]+', value) for value in enabled):
            raise ValueError('Unexpected accessibility component.')
        flag = shell('settings', 'get', 'secure', 'accessibility_enabled')
        legacy = state is not None and 'components' not in state
        previous = state['previous'] if state else native
        if legacy and native.get('uri') == 'ultra-flip-hd' and native.get('ver', 0) < 2:
            if native.get('lockTime') != state.get('appliedLockTime'):
                previous = dict(previous, lockTime=native['lockTime'])
            native_choice = previous
        else:
            native_choice = native
        managed = state['components'] if state and not legacy else []
        baseline = state['accessibility'] if state and not legacy else flag
        peers = [service for service in enabled if service not in managed]

        if component is not None:
            configured = dict(native_choice, featureEnabled=False)
            pending = dict(previous=previous, configured=configured, accessibility=baseline,
                           components=sorted(set(managed + [component])))
            save_state(pending)
            if configured != native:
                set_native(configured)
            return

        if enabled != peers:
            if peers:
                shell('settings', 'put', 'secure', 'enabled_accessibility_services', ':'.join(peers))
            else:
                shell('settings', 'delete', 'secure', 'enabled_accessibility_services')
                if baseline == 'null':
                    shell('settings', 'delete', 'secure', 'accessibility_enabled')
                elif baseline != flag:
                    shell('settings', 'put', 'secure', 'accessibility_enabled', baseline)
        if legacy and native_choice != native:
            set_native(native_choice)
        elif not legacy:
            configured = state['configured']
            if all(native.get(key) == configured.get(key) for key in ('featureEnabled', 'uri', 'ver')):
                set_native(dict(native, featureEnabled=previous['featureEnabled']))
        shell('settings', 'delete', 'secure', STATE)
        path.unlink(missing_ok=True)
    except Exception as exc:
        raise StoreError('Core screensaver setup could not be verified. Check WiFi ADB and retry Deploy.') from exc

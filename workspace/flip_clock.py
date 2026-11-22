"""Select the reviewed Flip Clock HD app through LineOS's screensaver setting."""
import hashlib
import json

import bridge

PACKAGE_ID = 'dk.qlerup.flipclock'
STORE_ID = 'qlerup.core.flip-clock-hd'
SIGNER = 'a2ffc4fd3545404750bd482b0332a30727e581dc70fd4f0cc6d34b22837f1fc8'
HOST = 'ultra-flip-hd'


def applies(entry):
    return entry.get('original_id', entry.get('id')) == STORE_ID


def validate_identity(entry):
    from store import StoreError
    android = entry.get('android', {})
    if (entry.get('type') != 'corebar-app' or android.get('packageId') != PACKAGE_ID
            or android.get('signerSha256') != SIGNER):
        raise StoreError('Flip Clock HD requires its approved Android identity and signing key.')


def placed(profiles, background):
    return any(app['id'] == PACKAGE_ID for app in background) or any(
        widget.get('type') == 'APPS' and widget.get('id') == PACKAGE_ID
        for profile in profiles for widget in profile.get('homeData', []))


def changed_settings(current, enabled, previous=None):
    if enabled:
        return dict(current, uri=HOST, featureEnabled=True)
    if previous is None or current.get('uri') != HOST:
        return current
    restored = dict(current)
    if 'uri' in previous:
        restored['uri'] = previous['uri']
    else:
        restored.pop('uri', None)
    if current.get('featureEnabled') is True:
        restored['featureEnabled'] = previous['featureEnabled']
    return restored


def reconcile(server, target, device, enabled):
    from editor import atomic_json
    from store import StoreError
    name = hashlib.sha256(device.encode()).hexdigest()
    path = server.DATA_DIR / 'store' / 'screensavers' / (name + '.json')
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(previous, dict) or type(previous.get('featureEnabled')) is not bool:
            raise ValueError('Invalid screensaver backup')
    except FileNotFoundError:
        previous = None
    except (OSError, ValueError) as exc:
        raise StoreError('Flip Clock HD could not read the saved screensaver choice.') from exc

    if not enabled and previous is None:
        return
    if server.adb('-s', target, 'shell', 'getprop', 'ro.serialno') != device:
        raise StoreError('Core changed before applying the screensaver. Reconnect and retry Deploy.')
    if enabled:
        result = server.adb('-s', target, 'shell', 'cmd', 'package', 'resolve-activity',
                            '--brief', '-a', 'android.intent.action.VIEW', '-d',
                            'screensaver://' + HOST + '/start')
        if PACKAGE_ID + '/.ClockActivity' not in result:
            raise StoreError('Flip Clock HD did not register as a screensaver. Install the package and retry Deploy.')

    try:
        current = bridge.screensaver(target, server.adb, server.ROOT)
        if type(current.get('featureEnabled')) is not bool:
            raise ValueError('Invalid LineOS screensaver state')
        if enabled and current.get('uri') != HOST:
            atomic_json(path, current)
        updated = changed_settings(current, enabled, previous)
        if updated != current:
            try:
                bridge.screensaver(target, server.adb, server.ROOT, updated)
            except Exception:
                # A missing acknowledgement can still mean LineOS saved the change.
                pass
            actual = bridge.screensaver(target, server.adb, server.ROOT)
            if any(actual.get(field) != updated.get(field) for field in ('uri', 'featureEnabled', 'lockTime')):
                raise ValueError('LineOS did not retain its screensaver setting')
        if not enabled:
            path.unlink(missing_ok=True)
    except Exception as exc:
        raise StoreError('Could not verify the Core screensaver choice. Retry Deploy on the same Core.') from exc

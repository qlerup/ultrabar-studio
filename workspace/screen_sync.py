"""Fixed, first-party Screen Sync setup. No package-supplied commands or scripts."""
import json
import re
import xml.etree.ElementTree as ET

PACKAGE_ID = 'dk.ultrabarx.screensync'
SIGNER = '6b663d4525f5a8f192df55e4548582e96c52188809cc76123e2e7dbd44ebff1f'


def applies(entry):
    return entry.get('id') == 'studio.vivo.screensync'


def prepare(server, target, entry):
    from store import StoreError
    android = entry.get('android', {})
    if entry.get('type') != 'corebar-app' or android.get('packageId') != PACKAGE_ID or android.get('signerSha256') != SIGNER:
        raise StoreError('Screen Sync requires its approved Android identity and signing key.')
    if server.adb('-s', target, 'shell', 'id', '-u') != '0':
        raise StoreError('Screen Sync setup requires root-enabled WiFi ADB on Core.')
    snapshot = server.read_snapshot(target)
    devices = snapshot.get('hardware', {}).get('devices', [])
    serials = sorted({d['serial'] for d in devices if d.get('type') == 'VIVO_CUBE' and d.get('online') is True and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(d.get('serial', '')))})
    if not serials:
        raise StoreError('Connect your VivoCubes to Core and retry. No online VivoCube was found.')
    try:
        raw = server.adb('-s', target, 'exec-out', 'cat', '/data/user/0/com.ultrabar.hub/shared_prefs/my_prefs.xml', binary=True)
        config = json.loads(ET.fromstring(raw).find("./string[@name='config']").text)
        token = next(x['code'] for x in config.get('authorizationCodes', []) if x.get('clientId') == 'ultrabarx-profile-inspection')
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise ValueError()
    except Exception:
        raise StoreError('Core has no existing approved Studio bridge credential. Screen Sync setup cannot continue.') from None
    # Only returned in memory; never written to a PC file, command argument or log.
    return json.dumps(dict(token=token, serials=serials)).encode(), (server.ROOT/'assets/corebridge.crt').read_bytes()


def configure(server, target, prepared):
    from store import StoreError
    dump = server.adb('-s', target, 'shell', 'dumpsys', 'package', PACKAGE_ID).split('Hidden system packages:', 1)[0]
    match = re.search(r'^\s*userId=(\d+)\s*$', dump, re.M)
    if not match:
        raise StoreError('Screen Sync installed, but its app storage owner could not be verified. Retry setup.')
    uid = match.group(1)
    base = '/data/user/0/' + PACKAGE_ID + '/files'
    server.adb('-s', target, 'shell', 'am', 'force-stop', PACKAGE_ID)
    server.adb('-s', target, 'shell', f'mkdir -p {base} && chown {uid}:{uid} {base} && chmod 700 {base}')
    for name, raw in zip(('config.json', 'server.crt'), prepared):
        path = base + '/' + name
        server.adb('-s', target, 'shell', f'umask 077; cat > {path}.tmp && chown {uid}:{uid} {path}.tmp && chmod 600 {path}.tmp && mv {path}.tmp {path} && restorecon {path}', input_data=raw)
        if server.adb('-s', target, 'exec-out', 'cat', path, binary=True) != raw:
            raise StoreError('Screen Sync installed, but setup could not be verified. Retry installation from Store.')
    server.adb('-s', target, 'shell', 'am', 'start', '-n', PACKAGE_ID+'/.MainActivity')

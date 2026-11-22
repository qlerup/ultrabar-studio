"""Fixed, first-party Screen Sync setup. No package-supplied commands or scripts."""
import json
import re
import xml.etree.ElementTree as ET
from contextlib import contextmanager

PACKAGE_ID = 'dk.ultrabarx.screensync'
SIGNER = '6b663d4525f5a8f192df55e4548582e96c52188809cc76123e2e7dbd44ebff1f'


def applies(entry):
    return entry.get('original_id', entry.get('id')) == 'studio.vivo.screensync'


def validate_identity(entry):
    from store import StoreError
    android = entry.get('android', {})
    if entry.get('type') != 'corebar-app' or android.get('packageId') != PACKAGE_ID or android.get('signerSha256') != SIGNER:
        raise StoreError('Screen Sync requires its approved Android identity and signing key.')


def prepare(server, target, entry):
    from store import StoreError
    validate_identity(entry)
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


def validate_settings(settings):
    from store import StoreError
    if not isinstance(settings,dict) or set(settings)-{'enabled','wakeDelayMs'} or type(settings.get('enabled',True)) is not bool or type(settings.get('wakeDelayMs',1000)) is not int or not 0<=settings.get('wakeDelayMs',1000)<=3000 or settings.get('wakeDelayMs',1000)%250:
        raise StoreError('Choose Follow Core or Always on, and a wake delay from 0 to 3000 ms in steps of 250.')


def start_sync(server,target,enabled=None):
    from store import StoreError
    args=['-s',target,'shell','am','start-foreground-service','-n',PACKAGE_ID+'/.SyncService']
    if enabled is not None:args.extend(('-a','enable' if enabled else 'disable'))
    result=server.adb(*args)
    if re.search(r'error|exception',result,re.I):raise StoreError('Screen Sync could not start in the background. Check Core and retry Deploy.')


@contextmanager
def pause_for_artwork(server,target):
    # The Cube's config download must not overlap Screen Sync's property commands.
    # In particular, installing/configuring Sync starts an immediate sync pass.
    services=server.adb('-s',target,'shell','dumpsys','activity','services',PACKAGE_ID)
    running=bool(re.search(r'ServiceRecord\{[^}\r\n]*\b'+re.escape(PACKAGE_ID)+r'/\.SyncService\}',services))
    if not running:
        yield
        return
    server.adb('-s',target,'shell','am','force-stop',PACKAGE_ID)
    try:
        yield
    finally:
        # No enable/disable action: restore the persisted mode and wake delay.
        # Also restore after a rejected/ambiguous artwork transfer.
        start_sync(server,target)


def write_private_file(server, target, path, uid, raw):
    # Keep binary stdin out of shell-v2 CR handling. Finish metadata in a separate
    # command: exec-in may terminate a shell command chain when stdin closes.
    server.adb('-s', target, 'exec-in', f'umask 077; cat > {path}.tmp', input_data=raw)
    server.adb('-s', target, 'shell', f'chown {uid}:{uid} {path}.tmp && chmod 600 {path}.tmp && mv {path}.tmp {path} && restorecon {path}')
    return server.adb('-s', target, 'exec-out', 'cat', path, binary=True) == raw


def configure(server, target, prepared, settings=None, background=False, *, launch=True):
    from store import StoreError
    dump = server.adb('-s', target, 'shell', 'dumpsys', 'package', PACKAGE_ID).split('Hidden system packages:', 1)[0]
    match = re.search(r'^\s*userId=(\d+)\s*$', dump, re.M)
    if not match:
        raise StoreError('Screen Sync installed, but its app storage owner could not be verified. Retry setup.')
    uid = match.group(1)
    base = '/data/user/0/' + PACKAGE_ID + '/files'
    server.adb('-s', target, 'shell', 'am', 'force-stop', PACKAGE_ID)
    server.adb('-s', target, 'shell', f'mkdir -p {base} && chown {uid}:{uid} {base} && chmod 700 {base}')
    # ADB shell input removes CR bytes on this firmware; exec-in preserves file bytes.
    for name, raw in zip(('config.json', 'server.crt'), prepared):
        path = base + '/' + name
        if not write_private_file(server, target, path, uid, raw):
            raise StoreError('Screen Sync installed, but setup could not be verified. Check the connection and retry Deploy.')
    if not launch:
        # Packages with the settings API start their own service on confirmed apply.
        return
    if settings is not None or background:
        settings=settings or {}
        validate_settings(settings)
        prefs='/data/user/0/'+PACKAGE_ID+'/shared_prefs'
        path=prefs+'/sync.xml'
        raw=server.adb('-s',target,'shell',f'if [ -f {path} ]; then cat {path}; else printf "<map />"; fi')
        try:
            root=ET.fromstring(raw)
            if root.tag!='map':raise ValueError()
        except (ET.ParseError,ValueError) as exc:raise StoreError('Could not read Screen Sync preferences. Existing settings were preserved.') from exc
        for key,tag,value in [('enabled','boolean',str(settings.get('enabled',True)).lower()),('wakeDelayMs','int',str(settings.get('wakeDelayMs',1000)))]:
            for old in list(root):
                if old.get('name')==key:root.remove(old)
            ET.SubElement(root,tag,name=key,value=value)
        data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        server.adb('-s',target,'shell',f'mkdir -p {prefs} && chown {uid}:{uid} {prefs} && chmod 700 {prefs}')
        if not write_private_file(server,target,path,uid,data):raise StoreError('Screen Sync preferences could not be verified. Retry Deploy.')
        start_sync(server,target,settings.get('enabled',True))
    else:
        server.adb('-s', target, 'shell', 'am', 'start', '-n', PACKAGE_ID+'/.MainActivity')

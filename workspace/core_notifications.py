"""Install Studio's built-in notification provider on Core and test its banner."""
import hashlib
import re

PACKAGE = 'dk.ultrabarx.notifications'
AUTHORITY = 'content://' + PACKAGE
APK_NAME = 'core-notifications.apk'
TEST_SOUNDS = ('silent', 'complete', 'error')
APK_PATH = re.compile(r'(/data/app/[a-zA-Z0-9_./=~+\-]+/base\.apk)')
DIGEST = re.compile(r'^([a-f0-9]{64})\s')


def installed_digest(server, target):
    packages = server.adb('-s', target, 'shell', 'pm', 'list', 'packages', '-f', PACKAGE)
    for line in packages.splitlines():
        path, _, package = line.removeprefix('package:').rpartition('=')
        if package == PACKAGE:
            if not APK_PATH.fullmatch(path):
                raise server.DeviceError('Could not verify the installed Core Notifications package.')
            result = server.adb('-s', target, 'shell', 'sha256sum', path)
            match = DIGEST.match(result)
            if not match:
                raise server.DeviceError('Could not verify the installed Core Notifications APK.')
            return match[1]
    return None


def call(server, target, method, *options):
    result = server.adb('-s', target, 'shell', 'content', 'call',
                        '--uri', AUTHORITY, '--method', method, *options)
    match = re.fullmatch(r'Result: Bundle\[\{status=([a-z_]+)\}\]', result)
    return match[1] if match else None


def bundled_digest(server, apk):
    try:
        return hashlib.sha256(apk.read_bytes()).hexdigest()
    except OSError as error:
        raise server.DeviceError('Studio is missing the built-in Core Notifications APK. Reinstall Studio.') from error


def provision(server, target):
    apk = server.ROOT / 'assets' / APK_NAME
    expected = bundled_digest(server, apk)
    if installed_digest(server, target) != expected:
        result = server.adb('-s', target, 'install', '-r', str(apk))
        if 'Success' not in result.splitlines() or installed_digest(server, target) != expected:
            raise server.DeviceError('Could not install the bundled Core Notifications APK.')
    if call(server, target, 'status.v1') != 'ready':
        server.adb('-s', target, 'shell', 'appops', 'set', PACKAGE, 'SYSTEM_ALERT_WINDOW', 'allow')
        if call(server, target, 'status.v1') != 'ready':
            raise server.DeviceError('Core did not grant the built-in notification banner permission.')


def test_banner(server, target, sound='silent'):
    if installed_digest(server, target) != bundled_digest(server, server.ROOT / 'assets' / APK_NAME):
        raise server.DeviceError('Deploy to Core before sending a test notification.')
    status = call(server, target, 'test.v1', '--arg', sound)
    if status == 'accepted':
        return
    messages = {
        'busy': 'Wait a few seconds before sending another notification.',
        'screen_off': 'Wake the Core screen and try again.',
    }
    raise server.DeviceError(messages.get(status, 'Core Notifications is unavailable. Deploy to Core and try again.'))

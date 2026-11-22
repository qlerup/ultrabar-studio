"""Studio-managed PC Standby pairing and its isolated, loopback-only presence API."""
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from screen_sync import write_private_file

PACKAGE_ID = 'dk.qlerup.corestandby'
STORE_ID = 'qlerup.core.pc-standby'
SIGNER = 'd336c808d454d6d9737e9663a1514da3c21ae572f605916cc3972ce49290c8ea'
CORE_PORT = 'tcp:47431'
MIN_VERSION = 110
BASE = '/data/user/0/' + PACKAGE_ID
KEY_PATH = BASE + '/files/studio-key'
HEX_KEY = re.compile(r'[a-f0-9]{64}')
PING = re.compile(r'/pc-standby/([a-f0-9]{32})/([a-f0-9]{64})')


def applies(entry):
    return entry.get('original_id', entry.get('id')) == STORE_ID


def validate_identity(entry):
    from store import StoreError
    android = entry.get('android', {})
    if entry.get('type') != 'corebar-app' or android.get('packageId') != PACKAGE_ID or android.get('signerSha256') != SIGNER:
        raise StoreError('PC Standby requires its approved Android identity and signing key.')


def placed(profiles, background):
    return any(app['id'] == PACKAGE_ID for app in background) or any(
        widget.get('type') == 'APPS' and widget.get('id') == PACKAGE_ID
        for profile in profiles for widget in profile.get('homeData', []))


class PresenceHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(2)
        super().setup()

    def log_message(self, *args):
        pass

    def do_GET(self):
        reply = self.server.reply(self.path)
        self.send_response(200 if reply else 404)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(reply)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if reply:
            self.wfile.write(reply)


class Standby:
    def __init__(self, server):
        self.server = server
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.http = None
        self.worker = None

    @property
    def path(self):
        return self.server.DATA_DIR / 'store/pc-standby.json'

    def pairs(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError('Invalid PC Standby settings')
        for device, item in data.items():
            if (not device or not isinstance(item, dict)
                    or not isinstance(item.get('key'), str) or not HEX_KEY.fullmatch(item['key'])
                    or self.server.validate_target(item.get('target')) != item['target']):
                raise ValueError('Invalid PC Standby settings')
        return data

    def reply(self, path):
        match = PING.fullmatch(path)
        if not match:
            return b''
        pairing, nonce = match.groups()
        try:
            with self.lock:
                pairs = self.pairs()
        except (ValueError, OSError):
            return b''
        for item in pairs.values():
            key = bytes.fromhex(item['key'])
            if hmac.compare_digest(hashlib.sha256(key).hexdigest()[:32], pairing):
                return hmac.digest(key, bytes.fromhex(nonce), 'sha256')
        return b''

    def start(self):
        with self.lock:
            if self.http is not None:
                return
            self.http = ThreadingHTTPServer(('127.0.0.1', 0), PresenceHandler)
            self.http.reply = self.reply
            threading.Thread(target=self.http.serve_forever, daemon=True, name='PCStandbyAPI').start()
            self.worker = threading.Thread(target=self.reconnect, daemon=True, name='PCStandbyReconnect')
            self.worker.start()

    def close(self):
        self.stop.set()
        if self.http is not None:
            self.http.shutdown()
            self.http.server_close()

    @property
    def local_port(self):
        return 'tcp:' + str(self.http.server_port)

    def reconnect(self):
        server = self.server
        while not self.stop.wait(5):
            try:
                with self.lock:
                    pairs = self.pairs()
            except (OSError, ValueError):
                logging.warning('PC Standby pairings could not be read')
                continue
            for device, item in pairs.items():
                if self.stop.is_set():
                    return
                snapshot = server.connection.get('snapshot') or {}
                target = (server.connection.get('target') if snapshot.get('device_id') == device else None) or item['target']
                try:
                    self.restore_route(target, device, item['key'])
                except server.DeviceError:
                    pass  # A shut-down or disconnected Core is expected.

    def restore_route(self, target, device, key):
        adb = self.server.adb
        try:
            identity = adb('-s', target, 'shell', 'getprop', 'ro.serialno')
        except self.server.DeviceError:
            adb('connect', target)
            identity = adb('-s', target, 'shell', 'getprop', 'ro.serialno')
        if identity != device:
            return
        digest = hashlib.sha256(bytes.fromhex(key)).hexdigest()
        stored = adb('-s', target, 'shell',
                     f'if [ -f {KEY_PATH} ]; then sha256sum {KEY_PATH}; fi')
        if stored.split()[:1] != [digest]:
            return  # A later Deploy from a different PC owns this Core.
        with self.lock:
            if self.pairs().get(device, {}).get('key') != key:
                return
            routes = adb('-s', target, 'reverse', '--list')
            if not any(row.split()[-2:] == [CORE_PORT, self.local_port] for row in routes.splitlines()):
                adb('-s', target, 'reverse', CORE_PORT, self.local_port)

    def broadcast(self, target, action):
        from store import StoreError
        result = self.server.adb('-s', target, 'shell', 'am', 'broadcast', '--include-stopped-packages',
                                 '-n', PACKAGE_ID + '/.StudioReceiver', '-a', PACKAGE_ID + '.' + action)
        if not re.search(r'(?m)^Broadcast completed: result=1\s*$', result):
            raise StoreError('Core did not confirm PC Standby setup. Check WiFi ADB and retry Deploy.')

    def reconcile(self, target, device, enabled):
        from editor import atomic_json
        from store import StoreError
        server = self.server
        with self.lock:
            pairs = self.pairs()
            current = pairs.get(device)
            if not enabled and current is None:
                return
            if (server.adb('-s', target, 'shell', 'getprop', 'ro.serialno') != device
                    or server.adb('-s', target, 'shell', 'id', '-u') != '0'):
                raise StoreError('PC Standby requires the selected Core with root-enabled WiFi ADB.')
            if not enabled:
                stored = server.adb('-s', target, 'shell',
                                    f'if [ -f {KEY_PATH} ]; then sha256sum {KEY_PATH}; fi')
                digest = hashlib.sha256(bytes.fromhex(current['key'])).hexdigest()
                if stored.split()[:1] == [digest]:
                    self.broadcast(target, 'DISABLE')
                del pairs[device]
                atomic_json(self.path, pairs)
                if self.http is not None:
                    routes = server.adb('-s', target, 'reverse', '--list')
                    if any(row.split()[-2:] == [CORE_PORT, self.local_port] for row in routes.splitlines()):
                        server.adb('-s', target, 'reverse', '--remove', CORE_PORT)
                return
            dump = server.adb('-s', target, 'shell', 'dumpsys', 'package', PACKAGE_ID)
            version = re.search(r'\bversionCode=(\d+)', dump)
            uid = re.search(r'^\s*userId=(\d+)\s*$', dump, re.M)
            if not version or int(version.group(1)) < MIN_VERSION or uid is None:
                raise StoreError('Update PC Standby from the Store, then Deploy to enable Studio monitoring.')
            self.start()
            key = current['key'] if current else secrets.token_hex(32)
            pairs[device] = dict(target=target, key=key)
            server.adb('-s', target, 'shell', 'am', 'force-stop', PACKAGE_ID)
            server.adb('-s', target, 'shell', 'cmd', 'appops', 'set', PACKAGE_ID, 'WRITE_SETTINGS', 'allow')
            server.adb('-s', target, 'shell', 'dpm', 'set-active-admin', PACKAGE_ID + '/.StandbyAdmin')
            owner = uid.group(1)
            base = BASE + '/files'
            server.adb('-s', target, 'shell', f'mkdir -p {base} && chown {owner}:{owner} {base} && chmod 700 {base} && restorecon {base}')
            if not write_private_file(server, target, KEY_PATH, owner, bytes.fromhex(key)):
                raise StoreError('Core did not retain the PC Standby pairing. Retry Deploy.')
            atomic_json(self.path, pairs)
            server.adb('-s', target, 'reverse', CORE_PORT, self.local_port)
            self.broadcast(target, 'ENABLE')
        # The app must be able to call the real endpoint and take over the timeout.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = server.adb('-s', target, 'shell',
                                f'if [ -f {BASE}/shared_prefs/standby.xml ]; then '
                                f'grep studioConnected {BASE}/shared_prefs/standby.xml || true; fi')
            if 'value="true"' in status:
                return
            time.sleep(0.25)
        raise StoreError('PC Standby started, but Core could not confirm a reply from Studio. Retry Deploy.')

"""UltraBar Studio: local, read-only starting point for our own workspace."""
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
import secrets
import subprocess
import threading
import xml.etree.ElementTree as ET

from flask import Flask, jsonify, request, send_file
import updates
import webbrowser

ROOT = Path(__file__).resolve().parent
PACKAGED = getattr(sys, 'frozen', False)
ADB = ROOT / 'platform-tools' / 'adb.exe' if PACKAGED else ROOT.parent / 'tools' / 'platform-tools' / 'adb.exe'
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'UltraBar Studio' if PACKAGED else ROOT / 'data'
PREFERENCES = '/data/user/0/com.ultrabar.launch/shared_prefs/my_preferences.xml'
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 3*1024*1024
app.config['ALLOWED_HOSTS'] = {'127.0.0.1:8741', 'localhost:8741'}
SESSION_TOKEN = secrets.token_urlsafe(32)
device_lock = threading.Lock()
connection = {'target': None, 'snapshot': None}
discovery_lock = threading.Lock()


class DeviceError(Exception):
    pass


def adb(*args, binary=False, input_data=None):
    try:
        result = subprocess.run([str(ADB), *args], capture_output=True, timeout=15, input=input_data,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise DeviceError('The device is not responding. Check WiFi ADB and the IP address.') from exc
    except OSError as exc:
        raise DeviceError('ADB could not start. Check the application installation.') from exc
    if result.returncode:
        # Do not leak device file contents or command output into errors.
        raise DeviceError('Could not read the device. Check the connection and WiFi ADB.')
    return result.stdout if binary else result.stdout.decode('utf-8', errors='replace').strip()


def validate_target(value):
    if not isinstance(value, str):
        raise ValueError('Enter an IPv4 address and optional port, e.g. 10.10.0.181:5555.')
    host, separator, port = value.strip().partition(':')
    address = ipaddress.IPv4Address(host)
    port = int(port) if separator else 5555
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError('Use a local network address for your UltraBar X.')
    if not 1 <= port <= 65535:
        raise ValueError('The port must be between 1 and 65535.')
    return f'{address}:{port}'


def parse_profiles(raw):
    try:
        root = ET.fromstring(raw)
        entry = root.find("./string[@name='app_data']")
        data = json.loads(entry.text) if entry is not None else None
        if not isinstance(data, dict) or not isinstance(data.get('profiles'), list):
            raise ValueError()
        for profile in data['profiles']:
            if not isinstance(profile, dict) or not isinstance(profile.get('module', []), list):
                raise ValueError()
        return data
    except (ET.ParseError, ValueError, TypeError) as exc:
        raise DeviceError('Could not read the profile format. No settings have been changed.') from exc


def read_snapshot(target):
    model = adb('-s', target, 'shell', 'getprop', 'ro.product.model')
    if model != 'CB01':
        raise DeviceError('The connected device is not the expected CoreBAR (CB01).')
    device_id = adb('-s', target, 'shell', 'getprop', 'ro.serialno') or target
    raw = adb('-s', target, 'exec-out', 'cat', PREFERENCES, binary=True)
    data = parse_profiles(raw)
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = {'target': target, 'model': model, 'read_at': datetime.now(timezone.utc).isoformat(),
                'sha256': digest, 'profiles': data['profiles'], 'device_id': device_id,
                'layout_order': read_layouts().get(device_id, [])}
    # Content-addressed backups: repeated refreshes do not create duplicate files.
    directory = DATA_DIR / 'backups'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{digest}.xml'
    if not path.exists():
        temp = path.with_suffix('.tmp')
        temp.write_bytes(raw)
        temp.replace(path)
    snapshot['backup'] = path.name
    from hardware import inventory
    snapshot['hardware'] = inventory(data, target, adb, ROOT)
    from previews import revision
    snapshot['preview_revision'] = revision(data, target, adb)
    return snapshot


def read_layouts():
    try:
        data = json.loads((DATA_DIR / 'layouts.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise DeviceError('Could not read saved layouts. Your existing file has been preserved.') from exc


@app.post('/api/layout')
def save_layout():
    data = request.get_json(silent=True)
    order = data.get('order') if isinstance(data, dict) else None
    if (not isinstance(order, list) or not 1 <= len(order) <= 128
            or any(not isinstance(key, str) or not re.fullmatch(r'core|[0-9A-Fa-f]{16}', key) for key in order)
            or len(set(order)) != len(order) or order.count('core') != 1):
        return jsonify(error='Invalid layout order.'), 400
    with device_lock:
        current = connection['snapshot']
        if not current or data.get('device_id') != current.get('device_id'):
            return jsonify(error='The connected device changed. Reconnect before saving the layout.'), 409
        layouts = read_layouts()
        layouts[current['device_id']] = order
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / 'layouts.json'
        try:
            path.with_suffix('.tmp').write_text(json.dumps(layouts, indent=2), encoding='utf-8')
            path.with_suffix('.tmp').replace(path)
        except OSError as exc:
            raise DeviceError('Could not save the layout. Please try again.') from exc
        current['layout_order'] = order
    return jsonify(order=order)


@app.before_request
def protect_local_api():
    if request.host not in app.config['ALLOWED_HOSTS']:
        return jsonify(error='Unknown host.'), 403
    if request.path.startswith('/api/') and not secrets.compare_digest(
            request.headers.get('X-Studio-Token', ''), SESSION_TOKEN):
        return jsonify(error='Reload the app to connect.'), 403


@app.after_request
def response_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.errorhandler(DeviceError)
def device_error(error):
    return jsonify(error=str(error)), 502


@app.get('/')
def index():
    html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
    return html.replace('__SESSION_TOKEN__', SESSION_TOKEN).replace('__APP_VERSION__', updates.VERSION)


@app.get('/api/updates')
def check_updates():
    try:
        return jsonify(updates.check_latest())
    except updates.UpdateError as exc:
        return jsonify(error=str(exc)), 502


@app.post('/api/updates/open')
def open_updates():
    # Open only the fixed release page in the system browser, outside the app.
    if not webbrowser.open(updates.RELEASES_URL + '/latest'):
        return jsonify(error='Could not open your browser. Visit ' + updates.RELEASES_URL), 502
    return jsonify(ok=True)


@app.get('/api/preferences')
def preferences():
    try:
        data = json.loads((DATA_DIR / 'preferences.json').read_text())
        return jsonify(target=validate_target(data.get('target')), setup_seen=(DATA_DIR / 'setup-seen').exists())
    except (OSError, ValueError, TypeError, AttributeError):
        return jsonify(target='', setup_seen=(DATA_DIR / 'setup-seen').exists())


@app.post('/api/setup-seen')
def setup_seen():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'setup-seen').touch()
    return jsonify(ok=True)


@app.get('/api/discover')
def discover_devices():
    from discovery import discover
    if not discovery_lock.acquire(blocking=False):
        return jsonify(error='A device search is already running.'), 409
    try:
        return jsonify(devices=discover())
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise DeviceError('Device search could not complete. You can still enter the IP address manually.') from exc
    finally:
        discovery_lock.release()


@app.post('/api/connect')
def connect():
    body = request.get_json(silent=True)
    try:
        target = validate_target(body.get('target') if isinstance(body, dict) else None)
    except ValueError:
        return jsonify(error='Enter a valid local IPv4 address and port.'), 400
    with device_lock:
        result = adb('connect', target)
        if 'connected to ' not in result.lower():
            raise DeviceError('Connection refused. Enable WiFi ADB and check the port.')
        snapshot = read_snapshot(target)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings_file = DATA_DIR / 'preferences.json'
        settings_file.with_suffix('.tmp').write_text(json.dumps({'target': target}))
        settings_file.with_suffix('.tmp').replace(settings_file)
        connection.update(target=target, snapshot=snapshot)
    return jsonify(snapshot)


@app.post('/api/refresh')
def refresh():
    with device_lock:
        if not connection['target']:
            return jsonify(error='Connect to a device first.'), 409
        snapshot = read_snapshot(connection['target'])
        connection['snapshot'] = snapshot
    return jsonify(snapshot)


@app.get('/api/screen')
def screen():
    with device_lock:
        if not connection['target']:
            return jsonify(error='Connect to a device first.'), 409
        data = adb('-s', connection['target'], 'exec-out', 'screencap', '-p', binary=True)
        try:
            power = adb('-s', connection['target'], 'shell', 'dumpsys', 'power')
            match = re.search(r'Display Power: state=(\w+)', power)
            screen_state = match.group(1) if match else 'UNKNOWN'
        except DeviceError:
            screen_state = 'UNKNOWN'
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise DeviceError('Could not capture the screen.')
    response = app.response_class(data, mimetype='image/png')
    response.headers['X-Core-Screen-State'] = screen_state
    return response


@app.get('/api/hardware')
def hardware_status():
    from hardware import inventory
    with device_lock:
        target = connection['target']
        if not target:
            return jsonify(error='Connect to a device first.'), 409
        # Refresh metadata as well, so newly attached modules acquire their type.
        # No profile backup or profile reload is needed for status polling.
        raw = adb('-s', target, 'exec-out', 'cat', PREFERENCES, binary=True)
        data = parse_profiles(raw)
        result = inventory(data, target, adb, ROOT)
        from previews import revision
        preview_revision = revision(data, target, adb)
        connection['snapshot']['hardware'] = result
    return jsonify(target=target, hardware=result, preview_revision=preview_revision)


@app.get('/api/cube-previews')
def saved_cube_previews():
    from previews import cube_previews
    with device_lock:
        current = connection['snapshot']
        if not current:
            return jsonify(error='Connect to a device first.'), 409
        result = cube_previews(current['hardware']['devices'], connection['target'], adb)
    return jsonify(previews=result)


@app.get('/api/backup')
def backup():
    with device_lock:
        snapshot = connection['snapshot']
        if snapshot is None:
            return jsonify(error='Load a profile first.'), 409
        path = DATA_DIR / 'backups' / snapshot['backup']
    return send_file(path, as_attachment=True, download_name='ultrabar-profil-backup.xml')


from editor import register_editor
register_editor(sys.modules[__name__])
from pc import register_pc
register_pc(sys.modules[__name__])
from native_widgets import NativeWidgets
native_widgets = NativeWidgets(sys.modules[__name__])

from store import register_store
register_store(sys.modules[__name__])

if __name__ == '__main__':
    from waitress import serve
    print('UltraBar Studio: http://127.0.0.1:8741', flush=True)
    serve(app, host='127.0.0.1', port=8741, threads=4)

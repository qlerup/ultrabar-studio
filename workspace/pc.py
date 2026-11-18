"""Studio PC actions and real Windows telemetry for the connected CoreBAR."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit
import uuid
import webbrowser

from flask import jsonify, request, Response
import bridge
import widget_images
from editor import atomic_json, EditError


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in
        ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]


class Metrics:
    def __init__(self):
        self.previous = None
        self.value = {}
        self.last = 0
        self.lock = threading.Lock()

    def sample(self):
        with self.lock:
            if time.monotonic()-self.last < 3:
                return self.value
            result = dict(cpu=None, memory=None, disks=[], gpu=None, sampled_at=time.time())
            if os.name == 'nt':
                kernel = ctypes.windll.kernel32
                idle, system, user = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
                if kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(system), ctypes.byref(user)):
                    now = (idle.value, system.value+user.value)
                    if self.previous:
                        total = now[1]-self.previous[1]
                        if total > 0:
                            result['cpu'] = round(100*(1-(now[0]-self.previous[0])/total), 1)
                    self.previous = now
                memory = MemoryStatus()
                memory.length = ctypes.sizeof(memory)
                if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
                    result.update(memory=memory.load, memory_total_gb=round(memory.total/1024**3, 1),
                                  memory_used_gb=round((memory.total-memory.available)/1024**3, 1))
                mask = kernel.GetLogicalDrives()
                for i in range(26):
                    drive = chr(65+i)+':\\'
                    if mask & (1 << i) and kernel.GetDriveTypeW(ctypes.c_wchar_p(drive)) == 3:
                        try:
                            disk = shutil.disk_usage(drive)
                            result['disks'].append(dict(name=drive, total_gb=round(disk.total/1024**3, 1), used_gb=round(disk.used/1024**3, 1), percent=round(disk.used/disk.total*100, 1)))
                        except OSError:
                            pass
            # NVIDIA telemetry is optional. Unavailable sensors stay unavailable, never zero.
            smi = shutil.which('nvidia-smi')
            if smi:
                try:
                    output = subprocess.run([smi, '--query-gpu=name,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if output.returncode == 0:
                        parts = [x.strip() for x in output.stdout.splitlines()[0].split(',')]
                        result['gpu'] = dict(name=parts[0], usage=float(parts[1]), memory_used_mb=float(parts[2]), memory_total_mb=float(parts[3]))
                except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                    pass
            self.value, self.last = result, time.monotonic()
            return result


def validate_action(data):
    if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 100:
        raise EditError('Give the action a name of 1–100 characters.')
    target = data.get('target')
    if not isinstance(target, str) or not target.strip() or len(target) > 2048 or any(ord(c)<32 for c in target):
        raise EditError('Enter a valid website or program path.')
    target = target.strip()
    if data.get('kind') == 'url':
        try:
            url = urlsplit(target)
            valid = url.scheme in ('http', 'https') and url.hostname and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid:
            raise EditError('Use a complete http:// or https:// website URL without embedded credentials.')
    elif data.get('kind') == 'program':
        path = Path(target)
        if not path.is_absolute() or path.suffix.lower() != '.exe' or not path.is_file() or target.startswith('\\\\'):
            raise EditError('Choose an existing local .exe file using its full path. Arguments are not supported.')
        target = str(path.resolve())
    else:
        raise EditError('Unsupported PC action.')
    return dict(id=uuid.uuid4().hex, name=data['name'].strip(), kind=data['kind'], target=target)


class Companion:
    def __init__(self, server):
        self.server = server
        self.metrics = Metrics()
        self.stop = threading.Event()
        self.thread = None
        self.target = None
        self.device_id = None
        self.status = 'PC companion disconnected'
        self.seen = {}
        self.guard = threading.Lock()

    def actions(self):
        path = self.server.DATA_DIR / 'pc-actions.json'
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise EditError('Could not read saved PC actions.')
        return data

    def start(self, target, device_id):
        with self.guard:
            if self.thread and self.thread.is_alive():
                if self.target == target and self.device_id == device_id:
                    return
                self.stop.set()
                self.thread.join(5)
                if self.thread.is_alive():
                    raise EditError('Previous PC connection is closing. Try again in a moment.')
            self.target, self.device_id = target, device_id
            self.stop = threading.Event()
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def handle(self, frame):
        if frame.get('act') != 1000000 or frame.get('code') is not None or not isinstance(frame.get('id'), str):
            return None
        data = frame.get('data')
        if not isinstance(data, dict):
            return None
        kind = data.get('type')
        payload = None
        if kind in ('CPU', 'MEMORY', 'STORAGE'):
            metrics = self.metrics.sample()
            if kind == 'STORAGE':
                total = sum(d['total_gb'] for d in metrics['disks'])
                if total:
                    payload = round(100*sum(d['used_gb'] for d in metrics['disks'])/total)
            else:
                value = metrics.get(kind.lower())
                if value is not None:
                    payload = round(value)
            if payload is None:
                return None
        elif kind == 'PC_CONTROL':
            pc = data.get('payload')
            if not isinstance(pc, dict) or pc.get('action') != 'studioAction' or not isinstance(pc.get('params'), dict):
                return None  # Original desktop-client actions are deliberately not executed twice.
            action = next((a for a in self.actions() if a['id'] == pc['params'].get('id') and a.get('device_id') == self.device_id), None)
            if action is None:
                return None
            if frame['id'] not in self.seen:
                self.seen[frame['id']] = time.monotonic()
                self.seen = {key: stamp for key, stamp in self.seen.items() if time.monotonic()-stamp < 300}
                validate_action(action)  # Check the local path still exists at execution time.
                if action['kind'] == 'url':
                    if not webbrowser.open(action['target']):
                        raise OSError('Browser could not start')
                else:
                    subprocess.Popen([action['target']], shell=False, cwd=str(Path(action['target']).parent))
                self.status = 'Connected · last action: '+action['name']
            payload = True
        else:
            return None
        return dict(id=frame['id'], act=1000000, code=200, data=dict(type=kind, payload=payload))

    def run(self):
        self.metrics.sample()
        while not self.stop.is_set():
            try:
                with bridge.Stream(self.target, self.server.adb, self.server.ROOT) as stream:
                    self.status = 'Connected · PC actions and hardware readings ready'
                    heartbeat = time.monotonic()
                    while not self.stop.is_set():
                        if time.monotonic()-heartbeat >= 10:
                            stream.send(dict(id=uuid.uuid4().hex, act=20, data=None))
                            heartbeat = time.monotonic()
                        try:
                            frame = stream.receive(1)
                        except socket.timeout:
                            continue
                        try:
                            response = self.handle(frame)
                            if response:
                                stream.send(response)
                        except (OSError, ValueError):
                            self.status = 'Connected · a PC action failed; check its program path or default browser'
            except Exception:
                self.status = 'PC connection lost · reconnecting'
                self.stop.wait(3)
        self.status = 'PC companion disconnected'

def register_pc(server):
    companion = Companion(server)
    server.companion = companion

    @server.app.get('/api/pc')
    def pc_status():
        device_id = (server.connection['snapshot'] or {}).get('device_id')
        return jsonify(status=companion.status, native_status=server.native_widgets.status, native_error=server.native_widgets.last_error, metrics=companion.metrics.sample(), actions=[a for a in companion.actions() if a.get('device_id') == device_id])

    @server.app.post('/api/pc/connect')
    def pc_connect():
        with server.device_lock:
            snapshot = server.connection['snapshot']
            if not snapshot:
                raise EditError('Connect to CoreBAR first.')
            companion.start(server.connection['target'], snapshot['device_id'])
            from editor import core_widget_layouts, saved_compact_profiles
            compact_profiles = core_widget_layouts(saved_compact_profiles(server, snapshot))
            server.native_widgets.prepare(snapshot['profiles'], server.connection['target'], compact_profiles)
            server.native_widgets.configure(snapshot['profiles'], server.connection['target'], compact_profiles)
        return jsonify(status=companion.status)

    @server.app.post('/api/pc/actions')
    def pc_action():
        data = request.get_json(silent=True)
        action = validate_action(data)
        with server.device_lock:
            snapshot = server.connection['snapshot']
            if not snapshot or data.get('device_id') != snapshot['device_id']:
                return jsonify(error='The connected device changed.'), 409
            action['device_id'] = snapshot['device_id']
            actions = companion.actions()
            actions.append(action)
            atomic_json(server.DATA_DIR / 'pc-actions.json', actions)
            companion.start(server.connection['target'], snapshot['device_id'])
        return jsonify(action=action, actions=[a for a in actions if a.get('device_id') == snapshot['device_id']])

    @server.app.get('/api/pc/widget-icons/<kind>')
    def shortcut_default_icon(kind):
        try:raw=widget_images.default_png(kind)
        except ValueError as exc:raise EditError(str(exc)) from exc
        return Response(raw,mimetype='image/png',headers={'X-Content-Type-Options':'nosniff'})

    @server.app.get('/api/pc/images/<digest>')
    def shortcut_picture(digest):
        try:raw=widget_images.read_picture(server,digest)
        except (OSError,ValueError) as exc:raise EditError('This widget picture is unavailable. Upload it again.') from exc
        return Response(raw,mimetype='image/png',headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=3600'})

    @server.app.post('/api/pc/images')
    def upload_shortcut_picture():
        upload=request.files.get('image')
        if upload is None:raise EditError('Choose a PNG, JPG or WebP picture up to 2 MB.')
        try:image=widget_images.store_picture(server,upload.read(widget_images.MAX_UPLOAD+1))
        except (OSError,ValueError) as exc:raise EditError('Choose a valid static PNG, JPG or WebP picture up to 2 MB.') from exc
        return jsonify(image=image)

    @server.app.post('/api/pc/default-image')
    def default_shortcut_picture():
        data=request.get_json(silent=True) or {}
        try:image=widget_images.store_picture(server,widget_images.default_png(data.get('kind')),source='default')
        except ValueError as exc:raise EditError(str(exc)) from exc
        return jsonify(image=image)

    @server.app.post('/api/pc/program-icon')
    def shortcut_program_icon():
        data=request.get_json(silent=True) or {}
        action=validate_action(dict(name='Program icon',kind='program',target=data.get('target')))
        raw=widget_images.program_png(action['target'])
        image=widget_images.store_picture(server,raw or widget_images.default_png('program'),source='program' if raw else 'default')
        return jsonify(image=image)

    @server.app.post('/api/pc/browse')
    def browse_program():
        picker = getattr(server, 'program_picker', None)
        if picker is None:
            raise EditError('Program browsing is available in the Windows app. Enter the full .exe path here.')
        selected = picker()
        return jsonify(path=selected[0] if selected else None)

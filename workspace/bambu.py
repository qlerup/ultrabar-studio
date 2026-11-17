"""Studio owns Bambu LAN connections. Only sanitized telemetry reaches Core."""
import base64
import ctypes
import hashlib
import ipaddress
import json
import math
import os
import re
import select
import socket
import ssl
import struct
import threading
import time
import uuid
from flask import jsonify, request
from editor import EditError, atomic_json

MAX_PACKET = 262144
ACTIONS = ('pause', 'resume', 'stop', 'light_on', 'light_off')
READINGS = ('gcode_state', 'subtask_name', 'mc_percent', 'mc_remaining_time', 'layer_num',
            'total_layer_num', 'nozzle_temper', 'nozzle_target_temper', 'bed_temper',
            'bed_target_temper', 'chamber_temper', 'chamber_target_temper')


def private_host(value):
    try:
        address = ipaddress.IPv4Address(value)
        if any(address in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')) and int(str(address).split('.')[-1]) not in (0, 255):
            return str(address)
    except (ValueError, TypeError):
        pass
    raise EditError('Enter a private LAN IPv4 address for the printer.')


def announcement(raw, sender):
    if len(raw) > 8192:
        return None
    try:
        host = private_host(sender)
        lines = raw.decode('utf-8').splitlines()
        if len(lines) > 64 or not lines or not (lines[0] == 'NOTIFY * HTTP/1.1' or lines[0].startswith('HTTP/1.1 200')):
            return None
        headers = {}
        for line in lines[1:]:
            key, sep, value = line.partition(':')
            if not sep:
                continue
            key, value = key.strip().lower(), value.strip()
            if key in headers and headers[key] != value:
                return None
            headers[key] = value
        kind = 'urn:bambulab-com:device:3dprinter:1'
        if kind not in (headers.get('nt'), headers.get('st')) or not re.fullmatch('[A-Za-z0-9]{6,32}', headers.get('usn', '')):
            return None
        name = headers.get('devname.bambu.com', 'Bambu Lab')
        if not 1 <= len(name) <= 48 or any(ord(c) < 32 for c in name):
            name = 'Bambu Lab'
        return dict(host=host, serial=headers['usn'], name=name)
    except (ValueError, UnicodeError):
        return None


def discover():
    sockets, found = [], {}
    query = b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1990\r\nMAN: "ssdp:discover"\r\nMX: 3\r\nST: urn:bambulab-com:device:3dprinter:1\r\n\r\n'
    try:
        for port in (0, 1990, 2021):
            stream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                stream.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                stream.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                stream.bind(('', port))
                if port:
                    stream.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton('239.255.255.250')+socket.inet_aton('0.0.0.0'))
                sockets.append(stream)
            except OSError:
                stream.close()  # Another app may own the announcement ports; direct replies still work.
        if not sockets:
            raise EditError('Could not search this network. Enter the printer IP and serial manually.')
        for host, port in (('239.255.255.250', 1990), ('239.255.255.250', 2021), ('255.255.255.255', 2021)):
            sockets[0].sendto(query, (host, port))
        until = time.monotonic()+8
        while time.monotonic() < until and len(found) < 32:
            ready, _, _ = select.select(sockets, [], [], min(.25, max(0, until-time.monotonic())))
            for stream in ready:
                raw, peer = stream.recvfrom(8193)
                printer = announcement(raw, peer[0])
                if printer:
                    found[printer['serial']] = printer
        return list(found.values())
    except OSError as exc:
        raise EditError('Network search failed. Check network access or enter the printer IP and serial manually.') from exc
    finally:
        for stream in sockets:
            stream.close()


def protect(raw, decrypt=False):
    """Windows user-bound DPAPI; never fall back to plaintext storage."""
    if os.name != 'nt':
        raise EditError('Saved printer connections require Windows credential protection.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise EditError('Windows could not unlock the saved printer connections.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(result.data)


def tls(host, pin=None):
    # Bambu uses self-signed certificates. A probe sends no MQTT credentials;
    # every authenticated connection checks the explicitly approved leaf pin.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    raw = socket.create_connection((private_host(host), 8883), timeout=6)
    try:
        stream = context.wrap_socket(raw, server_hostname=host)
        actual = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
        if pin is not None and actual != pin:
            stream.close()
            raise EditError('The printer certificate changed. Check the printer before approving it again.')
        return stream, actual
    except Exception:
        raw.close()
        raise


def utf(value):
    raw = value.encode('utf-8')
    return struct.pack('!H', len(raw)) + raw


def write(stream, header, body=b''):
    size = len(body)
    if size > MAX_PACKET:
        raise ValueError('MQTT packet too large')
    length = bytearray()
    while True:
        digit, size = size % 128, size // 128
        length.append(digit | (128 if size else 0))
        if not size:
            break
    stream.sendall(bytes([header]) + length + body)


def exact(stream, count):
    result = bytearray()
    while len(result) < count:
        part = stream.recv(count - len(result))
        if not part:
            raise OSError('MQTT disconnected')
        result.extend(part)
    return bytes(result)


def read(stream):
    header, size, multiplier = exact(stream, 1)[0], 0, 1
    for _ in range(4):
        digit = exact(stream, 1)[0]
        size += (digit & 127) * multiplier
        if size > MAX_PACKET:
            raise ValueError('MQTT packet too large')
        if not digit & 128:
            return header, exact(stream, size)
        multiplier *= 128
    raise ValueError('Invalid MQTT length')


def command(action, sequence):
    message = dict(sequence_id=str(sequence))
    if action == 'pushall':
        return dict(pushing=dict(message, command='pushall'))
    if action in ('light_on', 'light_off'):
        return dict(system=dict(message, command='ledctrl', led_node='chamber_light',
                                led_mode='on' if action == 'light_on' else 'off',
                                led_on_time=500, led_off_time=500, loop_times=0, interval_time=0))
    if action not in ACTIONS:
        raise ValueError('Unsupported printer command')
    return dict(print=dict(message, command=action, param=''))


class State:
    def __init__(self):
        self.data, self.report_at, self.state_at = {}, 0, 0

    def accept(self, root, now):
        patch = root.get('print')
        if not isinstance(patch, dict) or patch.get('command') != 'push_status':
            return False
        def merge(target, value):
            for key, item in value.items():
                if isinstance(item, dict) and isinstance(target.get(key), dict):
                    merge(target[key], item)
                else:
                    target[key] = item
        # Keep only fields used by this integration; reports may contain large
        # unrelated camera/AMS/job structures or ever-changing vendor keys.
        allowed = set(READINGS) | {'fun', 'lights_report'}
        merge(self.data, {key: value for key, value in patch.items() if key in allowed})
        self.report_at = now
        if 'gcode_state' in patch:
            self.state_at = now
        device = patch.get('device', {})
        if isinstance(device, dict):
            for part, prefix in (('bed', 'bed'), ('ctc', 'chamber')):
                info = device.get(part, {})
                info = info.get('info', {}) if isinstance(info, dict) else {}
                packed = info.get('temp', device.get('bed_temp') if part == 'bed' else None) if isinstance(info, dict) else None
                if type(packed) is int:
                    self.data[prefix+'_temper'], self.data[prefix+'_target_temper'] = packed & 65535, (packed >> 16) & 65535
            extruder = device.get('extruder', {})
            if isinstance(extruder, dict):
                if type(extruder.get('state')) is int:
                    self.data['active_tool'] = (extruder['state'] >> 4) & 15
                nozzles = self.data.setdefault('tools', {})
                info = extruder.get('info', [])
                for item in info[:16] if isinstance(info, list) else []:
                    if isinstance(item, dict) and type(item.get('id')) is int and 0 <= item['id'] <= 15 and type(item.get('temp')) is int:
                        nozzles[item['id']] = (item['temp'] & 65535, (item['temp'] >> 16) & 65535)
                active = nozzles.get(self.data.get('active_tool', 0))
                if active:
                    self.data['nozzle_temper'], self.data['nozzle_target_temper'] = active
        return True

    def fresh(self, now):
        return self.report_at > 0 and 0 <= now - self.report_at < 30

    def light(self):
        lights = self.data.get('lights_report', [])
        for item in lights if isinstance(lights, list) else []:
            if isinstance(item, dict) and item.get('node') == 'chamber_light' and item.get('mode') in ('on', 'off'):
                return item['mode']

    def print_control_reason(self, now):
        if not self.fresh(now):
            return 'Waiting for live printer status'
        try:
            value = self.data.get('fun', '0')
            flags = value if type(value) is int else int(value, 16) if isinstance(value, str) else None
            if flags is None or flags < 0:
                return 'Waiting for printer control status'
            if flags & 0x20000000:
                return 'Print controls need LAN Only + Developer Mode'
        except ValueError:
            return 'Waiting for printer control status'
        if not self.state_at or now - self.state_at >= 30:
            return 'Waiting for current print state'
        return ''

    def allows(self, action, now):
        if not self.fresh(now):
            return False
        # ledctrl is a system command; the signature flag restricts print commands.
        if action in ('light_on', 'light_off'):
            return self.light() is not None
        if self.print_control_reason(now):
            return False
        return self.data.get('gcode_state') in {'pause': ('RUNNING',), 'resume': ('PAUSE',), 'stop': ('RUNNING', 'PAUSE', 'PREPARE')}.get(action, ())

    def confirmed(self, action, patch):
        if action in ('light_on', 'light_off'):
            return 'lights_report' in patch and self.light() == ('on' if action == 'light_on' else 'off')
        return patch.get('gcode_state') in {'pause': ('PAUSE',), 'resume': ('RUNNING',), 'stop': ('IDLE', 'FINISH', 'FAILED')}.get(action, ())


class Link:
    def __init__(self, profile):
        self.profile = profile
        self.lock = threading.RLock()
        self.state = State()
        self.connected = False
        self.closed = threading.Event()
        self.stream = None
        self.status = 'Connecting'
        self.detail = 'Waiting for printer status'
        self.queued = self.pending = None
        self.packet_id = self.sequence = 1

    def start(self):
        threading.Thread(target=self.run, daemon=True, name='StudioBambu').start()

    def close(self):
        self.closed.set()
        with self.lock:
            self.connected = False
            self.queued = self.pending = None
        if self.stream:
            try:
                self.stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.stream.close()

    def request(self, action):
        with self.lock:
            if self.closed.is_set() or not self.connected or not self.profile['controls'] or self.queued or self.pending or not self.state.allows(action, time.monotonic()):
                return False
            self.queued = (action, time.monotonic())
            return True

    def snapshot(self):
        with self.lock:
            fresh = self.connected and self.state.fresh(time.monotonic()) and not self.closed.is_set()
            data = {key: self.state.data[key] for key in READINGS if key in self.state.data and isinstance(self.state.data[key], (str, int, float)) and not isinstance(self.state.data[key], bool)}
            # Bound arbitrary printer strings before they reach Core's metrics file.
            data = {k: v[:256] if isinstance(v, str) else v for k, v in data.items() if not isinstance(v, float) or math.isfinite(v)}
            tools = self.state.data.get('tools', {})
            ordered_tools = sorted(tools.items())
            summary = '  ·  '.join(f'T{i} {v[0]} / {v[1]}°' for i, v in ordered_tools if len(tools) <= 2 or i == self.state.data.get('active_tool', 0))
            data.update(name=self.profile['name'], connection=self.status, detail=self.detail, fresh=fresh,
                        controls=self.profile['controls'], busy=bool(self.queued or self.pending), light=self.state.light(),
                        nozzles=summary, nozzle_readings=[{'tool': tool, 'temperature': reading[0]} for tool, reading in ordered_tools])
            data['control_reason'] = ('Enable controls in Studio' if not self.profile['controls'] else
                                      'Waiting for live printer status' if not fresh else
                                      'Waiting for printer confirmation' if self.queued or self.pending else
                                      self.state.print_control_reason(time.monotonic()))
            data['print_controls_available'] = fresh and self.profile['controls'] and not self.state.print_control_reason(time.monotonic())
            for action in ACTIONS:
                data['can_'+action] = fresh and self.profile['controls'] and not (self.queued or self.pending) and self.state.allows(action, time.monotonic())
            return data

    def publish(self, action):
        self.sequence += 1
        self.packet_id = self.packet_id % 65535 + 1
        write(self.stream, 0x32, utf('device/'+self.profile['serial']+'/request') + struct.pack('!H', self.packet_id) + json.dumps(command(action, self.sequence)).encode())

    def run(self):
        try:
            stream, _ = tls(self.profile['host'], self.profile['pin'])
            self.stream = stream
            if self.closed.is_set():
                return
            stream.settimeout(6)
            write(stream, 0x10, utf('MQTT') + b'\x04\xc2\x00\x1e' + utf('studio-'+uuid.uuid4().hex[:12]) + utf('bblp') + utf(self.profile['code']))
            if read(stream) != (0x20, b'\x00\x00'):
                raise ValueError('Login rejected')
            write(stream, 0x82, b'\x00\x01' + utf('device/'+self.profile['serial']+'/report') + b'\x01')
            header, body = read(stream)
            if header != 0x90 or body not in (b'\x00\x01\x00', b'\x00\x01\x01'):
                raise ValueError('Subscription rejected')
            with self.lock:
                self.connected, self.status = True, 'Connected'
            self.publish('pushall')
            received = ping = refresh = time.monotonic()
            while not self.closed.is_set():
                now = time.monotonic()
                with self.lock:
                    if self.pending and now >= self.pending[1]:
                        self.pending = None
                        self.detail = 'No confirmation. Check the printer before retrying.'
                    if self.queued:
                        action, queued_at = self.queued
                        self.queued = None
                        if now - queued_at < 3 and self.profile['controls'] and self.state.allows(action, now):
                            self.pending = (action, now + 12)
                            self.publish(action)
                            self.detail = 'Command sent; waiting for printer confirmation'
                if now - received > 45:
                    raise OSError('Heartbeat timed out')
                if now - ping >= 10:
                    write(stream, 0xc0)
                    ping = now
                if now - refresh >= 15:
                    self.publish('pushall')
                    refresh = now
                if not stream.pending() and not select.select([stream], [], [], .25)[0]:
                    continue
                header, body = read(stream)
                received = time.monotonic()
                if header >> 4 == 3:
                    qos = (header >> 1) & 3
                    if header & 1 or qos > 1 or len(body) < 2:
                        raise ValueError('Unsupported report')
                    length = struct.unpack('!H', body[:2])[0]
                    offset = 2 + length
                    if not length or offset + (2 if qos else 0) > len(body):
                        raise ValueError('Invalid report')
                    topic = body[2:offset].decode('utf-8')
                    if qos:
                        packet = body[offset:offset+2]
                        if packet == b'\x00\x00':
                            raise ValueError('Invalid packet id')
                        write(stream, 0x40, packet)
                        offset += 2
                    if topic != 'device/'+self.profile['serial']+'/report':
                        continue
                    try:
                        root = json.loads(body[offset:])
                    except (ValueError, UnicodeError):
                        continue
                    with self.lock:
                        if isinstance(root, dict) and self.state.accept(root, received) and self.pending and self.state.confirmed(self.pending[0], root['print']):
                            self.pending = None
                            self.detail = 'Confirmed by printer'
                elif not ((header == 0xd0 and not body) or (header == 0x40 and len(body) == 2)):
                    raise ValueError('Unexpected MQTT packet')
        except (OSError, ValueError, TypeError, RecursionError, EditError):
            with self.lock:
                self.status = 'Disconnected'
                self.detail = 'Check IP, access code, certificate and LAN mode, then reconnect in Studio.'
        finally:
            with self.lock:
                self.connected = False
                self.queued = self.pending = None
                self.state = State()
            if self.stream:
                self.stream.close()


class Printers:
    def __init__(self, server):
        self.server = server
        self.lock = threading.RLock()
        self.links = {}
        self.active = set()

    def read(self):
        path = self.server.DATA_DIR / 'bambu-connections.json'
        if not path.exists():
            return []
        try:
            values = json.loads(protect(base64.b64decode(json.loads(path.read_text())['protected']), True))
            if not isinstance(values, list) or len(values) > 16 or any(not isinstance(p, dict) or set(p) != {'id','name','host','serial','code','pin','controls'} for p in values):
                raise ValueError('Invalid saved connections')
            return values
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise EditError('Could not read saved printer connections. The file has been preserved.') from exc

    def store(self, profiles):
        encrypted = base64.b64encode(protect(json.dumps(profiles, allow_nan=False).encode())).decode()
        atomic_json(self.server.DATA_DIR / 'bambu-connections.json', dict(protected=encrypted))

    def listing(self):
        with self.lock:
            return [dict(id=p['id'], name=p['name'], host=p['host'], serial=p['serial'], controls=p['controls'],
                         status=self.links[p['id']].snapshot() if p['id'] in self.links else dict(connection='Not connected', fresh=False)) for p in self.read()]

    def validate(self, specs):
        printers = [s for s in specs.values() if s.get('kind') == 'bambu']
        if printers:
            with self.lock:
                available = {p['id'] for p in self.read()}
                if any(s.get('printerId') not in available for s in printers):
                    raise EditError('Choose a saved printer for each Bambu widget in Studio before deploying.')

    def configure(self, specs):
        with self.lock:
            wanted = {s.get('printerId') for s in specs.values() if s.get('kind') == 'bambu' and s.get('printerId')}
            profiles = {p['id']: p for p in self.read()} if wanted else {}
            self.active = wanted
            for key in list(self.links):
                if key not in wanted or key not in profiles:
                    self.links.pop(key).close()
            for key in wanted & profiles.keys():
                if key not in self.links:
                    link = self.links[key] = Link(profiles[key])
                    link.start()

    def sample(self):
        with self.lock:
            return {key: link.snapshot() for key, link in self.links.items()}

    def close(self):
        with self.lock:
            for link in self.links.values():
                link.close()
            self.links.clear()

    def save(self, body):
        if not isinstance(body, dict) or set(body) - {'id', 'name', 'host', 'serial', 'code', 'pin', 'controls'}:
            raise EditError('Invalid printer connection.')
        name, serial, code, pin = (body.get(k, '') for k in ('name', 'serial', 'code', 'pin'))
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48 or any(ord(c) < 32 for c in name):
            raise EditError('Give the printer a name of 1â€“48 characters.')
        if not isinstance(serial, str) or not re.fullmatch('[A-Za-z0-9]{6,32}', serial) or not isinstance(code, str) or not isinstance(pin, str) or not re.fullmatch('[a-f0-9]{64}', pin) or type(body.get('controls', False)) is not bool:
            raise EditError('Enter the serial number, LAN access code and approve the printer certificate.')
        host = private_host(body.get('host'))
        with self.lock:
            profiles = self.read()
            old = next((p for p in profiles if p['id'] == body.get('id')), None)
            if body.get('id') and old is None:
                raise EditError('This printer no longer exists. Refresh the printer list.')
            if not code and old and old['host'] == host and old['serial'] == serial:
                code = old['code']
            if not re.fullmatch('[A-Za-z0-9]{8}', code):
                raise EditError('Enter the 8-character LAN access code.')
            if any(p['serial'] == serial and p is not old for p in profiles):
                raise EditError('This printer is already saved. Edit its existing connection.')
            if old is None and len(profiles) >= 16:
                raise EditError('A maximum of 16 printers can be saved.')
            profile = dict(id=old['id'] if old else uuid.uuid4().hex, name=name.strip(), host=host, serial=serial, code=code, pin=pin, controls=body.get('controls', False))
            profiles = [profile if p is old else p for p in profiles] if old else profiles + [profile]
            self.store(profiles)
            if profile['id'] in self.links:
                self.links.pop(profile['id']).close()
            link = self.links[profile['id']] = Link(profile)
            link.start()
            return profile['id']

    def remove(self, key):
        with self.lock:
            profiles = self.read()
            if not any(p['id'] == key for p in profiles):
                raise EditError('Unknown printer.')
            self.store([p for p in profiles if p['id'] != key])
            if key in self.links:
                self.links.pop(key).close()


def register(server):
    server.bambu = Printers(server)

    @server.app.get('/api/bambu/printers', endpoint='bambu_list')
    def listing():
        return jsonify(printers=server.bambu.listing())

    @server.app.post('/api/bambu/probe', endpoint='bambu_probe')
    def probe():
        body = request.get_json(silent=True)
        host = private_host(body.get('host') if isinstance(body, dict) else None)
        try:
            stream, pin = tls(host)
            stream.close()
            return jsonify(pin=pin)
        except (OSError, ValueError) as exc:
            raise EditError('Could not read the printer certificate. Check IP, LAN mode and network access from this PC.') from exc

    @server.app.post('/api/bambu/discover', endpoint='bambu_discover')
    def search():
        return jsonify(printers=discover())

    @server.app.post('/api/bambu/printers', endpoint='bambu_save')
    def save():
        key = server.bambu.save(request.get_json(silent=True))
        return jsonify(id=key, printers=server.bambu.listing())

    @server.app.post('/api/bambu/printers/<key>/remove', endpoint='bambu_remove')
    def remove(key):
        server.bambu.remove(key)
        return jsonify(printers=server.bambu.listing())

    @server.app.post('/api/bambu/printers/<key>/reconnect', endpoint='bambu_reconnect')
    def reconnect(key):
        with server.bambu.lock:
            profile = next((p for p in server.bambu.read() if p['id'] == key), None)
            if profile is None:
                raise EditError('Unknown printer.')
            if key in server.bambu.links:
                server.bambu.links.pop(key).close()
            link = server.bambu.links[key] = Link(profile)
            link.start()
        return jsonify(printers=server.bambu.listing())

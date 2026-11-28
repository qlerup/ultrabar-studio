"""Read inventory and runtime online state. Never write module properties."""
from datetime import datetime, timezone
import logging
import re
import threading
import time
from copy import deepcopy

from bridge import PairingRequired, Stream

CAN_PRODUCTS = {
    268435456: ('EXT_SCREEN', 'External screen'),
    268435457: ('DOT_KEY', 'DotKey'),
    268435458: ('KNOB_KEY', 'KnobKey'),
    268435459: ('VIVO_CUBE', 'VivoCube'),
    268435460: ('SENSE_CUBE', 'SenseCube'),
    268435461: ('PC_BOOT_CARD', 'PC Boot card'),
}
LOG = logging.getLogger(__name__)
# CoreBAR searches the CAN bus every five seconds and ends a discovery session
# after one minute. Keep listening across those sweeps for late replies.
SCAN_WINDOW = 61
RECENT_SIGHTING = 35
EXPIRED_SIGHTING = 65
CAN_CAPTURE = 'timeout 11 candump can0; status=$?; [ "$status" = 124 ] || exit "$status"'
CAN_FRAME = re.compile(r'\s*<0x([0-9a-fA-F]+)> \[8\] ([0-9a-fA-F ]+)\s*')
MODULE_SERIAL = re.compile(r'[0-9A-F]{16}')
MANUALLY_REGISTERED_TYPES = {'DOT_KEY', 'KNOB_KEY', 'VIVO_CUBE', 'SENSE_CUBE'}


def crc8(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ (7 if value & 128 else 0)) & 255
    return value


def decode_can_modules(capture):
    """Read complete QuantumLink discovery replies and join announcements."""
    pending = {}
    for line in capture.splitlines():
        match = CAN_FRAME.fullmatch(line)
        if not match:
            continue
        address = int(match[1], 16)
        if not 0x400 < address <= 0x7ff:
            continue
        try:
            frame = bytes.fromhex(match[2])
        except ValueError:
            continue
        if len(frame) != 8:
            continue
        message = (frame[0] >> 4, frame[3])
        if (message in ((15, 8), (0, 9)) and frame[5] == 16 and crc8(frame[:7]) == frame[7]
                and (int.from_bytes(frame[:2], 'big') & 0xfff) == (address & 0x3ff)):
            pending[address] = (frame[6], [])
            continue
        if address not in pending:
            continue
        checksum, chunks = pending[address]
        chunks.append(frame)
        if len(chunks) < 2:
            continue
        del pending[address]
        for payload in (b''.join(chunks), b''.join(reversed(chunks))):
            product = CAN_PRODUCTS.get(int.from_bytes(payload[8:12], 'big'))
            serial = payload[:8]
            if product and any(serial) and crc8(payload) == checksum:
                yield dict(serial=serial.hex().upper(), type=product[0], name=product[1], interface='can',
                           net_id=int.from_bytes(payload[14:16], 'big'), work_mode=1)
                break


def observe_can(target, adb, on_device, cancelled, finished):
    # Some CoreBAR versions omit replies from the CoreBridge discovery stream.
    # The firmware's passive reader sees them without sending CAN frames.
    try:
        while not (cancelled.is_set() or finished.is_set()):
            capture = adb('-s', target, 'shell', '-tt', CAN_CAPTURE)
            for device in decode_can_modules(capture):
                on_device(device)
    except Exception:
        LOG.debug('Could not read CoreBAR CAN discovery replies.', exc_info=True)


def discover_attached(target, adb, root, on_device, cancelled):
    def collect(frame):
        module = frame.get('data')
        if frame.get('act') != 30102 or not isinstance(module, dict) or module.get('interfaceType') != 'can':
            return
        serial = module.get('serialNumber')
        if not isinstance(serial, str) or not serial:
            return
        product = module.get('productId')
        product_type, name = CAN_PRODUCTS.get(product if type(product) is int else None, ('UNKNOWN', 'Unknown module'))
        on_device(dict(serial=serial.upper(), type=product_type, name=name, interface='can',
                       net_id=module.get('netId'), work_mode=module.get('workMode')))

    with Stream(target, adb, root) as stream:
        try:
            stream.query(30100, 'can', timeout=2, on_event=collect)
            deadline = time.monotonic() + SCAN_WINDOW
            while not cancelled.is_set() and (remaining := deadline - time.monotonic()) > 0:
                try:
                    collect(stream.receive(min(remaining, 1)))
                except TimeoutError:
                    continue
        finally:
            try:
                stream.query(30101, None, timeout=2, on_event=collect)
            except (EOFError, OSError, ValueError):
                LOG.debug('Could not stop the CoreBAR module scan.')


class ModuleDiscovery:
    def __init__(self):
        self.lock = threading.Lock()
        self.device = None
        self.sightings = {}
        self.cancelled = threading.Event()
        self.search_finished = threading.Event()
        self.active_cancel = None
        self.running = False

    def start(self, device, target, adb, root):
        with self.lock:
            if device != self.device:
                self.device = device
                self.sightings.clear()
                self.cancelled.set()
                self.cancelled = threading.Event()
            if self.running:
                return
            if self.cancelled.is_set():
                self.cancelled = threading.Event()
            self.running = True
            self.active_cancel = self.cancelled
            self.search_finished.clear()
            threading.Thread(target=self.scan, args=(target, adb, root, self.cancelled), daemon=True).start()

    def stop(self):
        with self.lock:
            if not self.running:
                return True
            self.active_cancel.set()
        return self.search_finished.wait(10)

    def scan(self, target, adb, root, cancelled):
        def observe(device):
            with self.lock:
                if not cancelled.is_set():
                    self.sightings[device['serial']] = (time.monotonic(), device)

        finished = threading.Event()
        capture = threading.Thread(target=observe_can, args=(target, adb, observe, cancelled, finished), daemon=True)
        capture.start()
        try:
            discover_attached(target, adb, root, observe, cancelled)
        except Exception:
            LOG.debug('Could not scan for CoreBAR modules.', exc_info=True)
        finally:
            finished.set()
            self.search_finished.set()
            capture.join()
            with self.lock:
                self.running = False

    def recent(self, device):
        with self.lock:
            if device != self.device:
                return []
            now = time.monotonic()
            self.sightings = {serial: entry for serial, entry in self.sightings.items()
                              if now - entry[0] < EXPIRED_SIGHTING}
            return [dict(module, online=True if now - seen < RECENT_SIGHTING else None)
                    for seen, module in self.sightings.values()]

    def active(self, device):
        with self.lock:
            return self.device == device and self.running


def can_address(device):
    address = device.get('net_id')
    return (MODULE_SERIAL.fullmatch(device['serial']) and device['type'] in MANUALLY_REGISTERED_TYPES and device.get('interface') == 'can'
            and type(address) is int and 0 < address < 1023 and address & 127 != 127
            and type(device.get('work_mode')) is int and device['work_mode'] == 1)


def registered_endpoints(configuration):
    for gateway in ('canGateway', 'meshGateway'):
        yield from (configuration.get(gateway) or {}).get('endpoints') or ()


def register_can_modules(configuration, discovered, serials):
    updated = deepcopy(configuration)
    existing = list(registered_endpoints(updated))
    registered = {entry['serialNumber'].upper() for entry in existing if entry.get('serialNumber')}
    used_ids = {entry.get('netId') for entry in (updated.get('canGateway') or {}).get('endpoints') or ()}
    used_uids = {str(entry.get('uid')) for entry in existing}
    available = {d['serial']: d for d in discovered if d['online'] is True and can_address(d)}
    for serial in serials:
        if serial in registered:
            continue
        device = available.get(serial)
        if device is None:
            raise ValueError('Search again to confirm the selected module is connected to this CoreBAR.')
        if device['net_id'] in used_ids:
            raise ValueError('Another CAN module uses the same address. Check the connected modules before adding it.')
        uid = next(str(n) for n in range(1, len(used_uids)+2) if str(n) not in used_uids)
        if updated.get('canGateway') is None:
            updated['canGateway'] = {}
        if updated['canGateway'].get('endpoints') is None:
            updated['canGateway']['endpoints'] = []
        updated['canGateway']['endpoints'].append(dict(serialNumber=serial, uid=uid, name=device['name'],
            interfaceType='can', productId=device['type'], netId=device['net_id'], workMode=device['work_mode']))
        used_uids.add(uid)
        used_ids.add(device['net_id'])
        registered.add(serial)
    return updated


def read_online(target, adb, root):
    with Stream(target, adb, root) as stream:
        states = stream.query(30730, [], timeout=6)
    if not isinstance(states, list):
        raise ValueError('Invalid module state list')
    return {item['serialNo']: item['online'] for item in states
            if isinstance(item, dict) and isinstance(item.get('online'), bool) and 'serialNo' in item}


def inventory(data, target, adb, root, *, discovered=()):
    devices = []
    seen = set()
    configuration = data.get('configuration') or {}
    for item in registered_endpoints(configuration):
        serial = item.get('serialNumber')
        if not serial or serial in seen:
            continue
        seen.add(serial)
        devices.append({'serial': serial, 'type': item.get('productId', 'UNKNOWN') or 'UNKNOWN',
                        'name': item.get('name', 'Module'), 'interface': item.get('interfaceType'), 'online': None})
    registered = {device['serial'].upper() for device in devices}
    available = [dict(serial=d['serial'], name=d['name'], type=d['type'], online=d['online'])
                 for d in discovered if d['serial'] not in registered and can_address(d)]
    pairing_required = False
    try:
        states = read_online(target, adb, root)
        live = {device['serial']: device for device in devices}
        for serial, device in live.items():
            device['online'] = states.get(serial)
        devices = list(live.values())
        error = None
    except PairingRequired:
        pairing_required = True
        error = 'Approve Studio on CoreBAR to load connected modules.'
    except Exception:
        error = 'Could not read current module status from CoreBridge. Retrying automatically.'
    return {'devices': devices, 'available': available, 'status_error': error, 'pairing_required': pairing_required, 'layout': 'schematic',
            'checked_at': datetime.now(timezone.utc).isoformat()}

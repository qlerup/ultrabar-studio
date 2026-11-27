"""Read inventory and runtime online state. Never write module properties."""
from datetime import datetime, timezone
import logging
import re
import threading
import time

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
                yield dict(serial=serial.hex().upper(), type=product[0], name=product[1], interface='can')
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
        on_device({'serial': serial, 'type': product_type, 'name': name, 'interface': 'can'})

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
            self.running = True
            threading.Thread(target=self.scan, args=(target, adb, root, self.cancelled), daemon=True).start()

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
    for gateway in ('canGateway', 'meshGateway'):
        for item in (configuration.get(gateway) or {}).get('endpoints', []):
            serial = item.get('serialNumber')
            if not serial or serial in seen:
                continue
            seen.add(serial)
            devices.append({'serial': serial, 'type': item.get('productId', 'UNKNOWN'),
                            'name': item.get('name', 'Module'), 'interface': item.get('interfaceType'), 'online': None})
    pairing_required = False
    try:
        states = read_online(target, adb, root)
        metadata = {device['serial']: device for device in devices}
        live = {serial: dict(metadata.get(serial, {'serial': serial, 'type': 'UNKNOWN', 'name': 'Unknown module'}), online=online)
                for serial, online in states.items()}
        for device in discovered:
            serial = device['serial']
            registered = metadata.get(serial, {})
            runtime = live.get(serial, {})
            product, name = registered.get('type'), registered.get('name')
            live[serial] = dict(device, type=product if product not in (None, 'UNKNOWN') else device['type'],
                                name=name if name not in (None, 'Module') else device['name'],
                                online=runtime.get('online', device['online']))
        devices = list(live.values())
        error = None
    except PairingRequired:
        devices = []
        pairing_required = True
        error = 'Approve Studio on CoreBAR to load connected modules.'
    except Exception:
        devices = []
        error = 'Could not read current module status from CoreBridge. Retrying automatically.'
    return {'devices': devices, 'status_error': error, 'pairing_required': pairing_required, 'layout': 'schematic',
            'checked_at': datetime.now(timezone.utc).isoformat()}

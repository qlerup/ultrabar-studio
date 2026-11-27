"""Read inventory and runtime online state. Never write module properties."""
from datetime import datetime, timezone
import logging
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


def discover_attached(target, adb, root):
    devices = {}

    def collect(frame):
        module = frame.get('data')
        if frame.get('act') != 30102 or not isinstance(module, dict) or module.get('interfaceType') != 'can':
            return
        serial = module.get('serialNumber')
        if not isinstance(serial, str) or not serial:
            return
        product = module.get('productId')
        product_type, name = CAN_PRODUCTS.get(product if type(product) is int else None, ('UNKNOWN', 'Unknown module'))
        devices[serial] = {'serial': serial, 'type': product_type, 'name': name, 'interface': 'can', 'online': True}

    with Stream(target, adb, root) as stream:
        try:
            stream.query(30100, 'can', timeout=2, on_event=collect)
            deadline = time.monotonic() + 1.25
            while (remaining := deadline - time.monotonic()) > 0:
                try:
                    collect(stream.receive(remaining))
                except TimeoutError:
                    break
        finally:
            try:
                stream.query(30101, None, timeout=2, on_event=collect)
            except (EOFError, OSError, ValueError):
                LOG.debug('Could not stop the CoreBAR module scan.')
    return devices


def read_online(target, adb, root):
    with Stream(target, adb, root) as stream:
        states = stream.query(30730, [], timeout=6)
    if not isinstance(states, list):
        raise ValueError('Invalid module state list')
    return {item['serialNo']: item['online'] for item in states
            if isinstance(item, dict) and isinstance(item.get('online'), bool) and 'serialNo' in item}


def inventory(data, target, adb, root, *, discover=False):
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
        if discover:
            try:
                for serial, device in discover_attached(target, adb, root).items():
                    registered = metadata.get(serial, {})
                    if registered.get('type') not in (None, 'UNKNOWN'):
                        device['type'] = registered['type']
                    if registered.get('name') not in (None, 'Module'):
                        device['name'] = registered['name']
                    live[serial] = device
            except Exception:
                LOG.debug('Could not scan for CoreBAR modules.', exc_info=True)
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

"""Read inventory and runtime online state. Never write module properties."""
from datetime import datetime, timezone

from bridge import PairingRequired, Stream


def read_online(target, adb, root):
    with Stream(target, adb, root) as stream:
        states = stream.query(30730, [], timeout=6)
    if not isinstance(states, list):
        raise ValueError('Invalid module state list')
    return {item['serialNo']: item['online'] for item in states
            if isinstance(item, dict) and isinstance(item.get('online'), bool) and 'serialNo' in item}


def inventory(data, target, adb, root):
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
        # Membership comes exclusively from the live supervisor response, never
        # from profile actions or the stored endpoint registry.
        devices = [dict(metadata.get(serial, {'serial': serial, 'type': 'UNKNOWN', 'name': 'Unknown module'}), online=online)
                   for serial, online in states.items()]
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

"""Read inventory and runtime online state. Never write module properties."""
import json
import socket
import ssl
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def read_online(target, adb, root):
    raw = adb('-s', target, 'exec-out', 'cat', '/data/user/0/com.ultrabar.hub/shared_prefs/my_prefs.xml', binary=True)
    entry = ET.fromstring(raw).find("./string[@name='config']")
    config = json.loads(entry.text)
    # Reuse the user's already-approved diagnostic client, only in memory.
    token = next(item['code'] for item in config.get('authorizationCodes', [])
                 if item.get('clientId') == 'ultrabarx-profile-inspection')
    certificate = ssl.PEM_cert_to_DER_cert((root / 'assets' / 'corebridge.crt').read_text())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # Exact certificate pin checked before sending credentials.
    host = target.split(':')[0]
    with socket.create_connection((host, 7431), timeout=4) as tcp:
        with context.wrap_socket(tcp, server_hostname=host) as connection:
            if connection.getpeercert(binary_form=True) != certificate:
                raise ValueError('Certificate mismatch')
            connection.settimeout(6)
            with connection.makefile('rb') as reader:
                def query(action, data):
                    if action not in (100, 30730):
                        raise ValueError('Read-only protocol')
                    identity = str(uuid.uuid4())
                    connection.sendall((json.dumps({'id': identity, 'act': action, 'data': data})+'\n').encode())
                    deadline = time.monotonic() + 6
                    for _ in range(100):
                        connection.settimeout(max(0.01, deadline-time.monotonic()))
                        line = reader.readline(1024*1024)
                        if not line or len(line) >= 1024*1024:
                            raise ValueError('Invalid bridge response')
                        if not line.strip():
                            continue
                        reply = json.loads(line)
                        if reply.get('id') == identity:
                            if reply.get('code') != 200:
                                raise ValueError('Bridge request rejected')
                            return reply.get('data')
                        if time.monotonic() >= deadline:
                            raise TimeoutError()
                    raise ValueError('No matching reply')
                query(100, token)
                states = query(30730, [])
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
    try:
        states = read_online(target, adb, root)
        metadata = {device['serial']: device for device in devices}
        # Membership comes exclusively from the live supervisor response, never
        # from profile actions or the stored endpoint registry.
        devices = [dict(metadata.get(serial, {'serial': serial, 'type': 'UNKNOWN', 'name': 'Unknown module'}), online=online)
                   for serial, online in states.items()]
        error = None
    except Exception:
        devices = []
        error = 'Could not read current module status from CoreBridge. Retrying automatically.'
    return {'devices': devices, 'status_error': error, 'layout': 'schematic',
            'checked_at': datetime.now(timezone.utc).isoformat()}

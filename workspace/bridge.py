"""Pinned authenticated CoreBridge sessions; credentials only live in memory."""
import json
import socket
import ssl
import time
import uuid
import xml.etree.ElementTree as ET


CLIENT_ID = 'ultrabarx-profile-inspection'
PREFERENCES = '/data/user/0/com.ultrabar.hub/shared_prefs/my_prefs.xml'


class PairingRequired(Exception):
    pass


class BridgeRejected(ValueError):
    pass


def read_token(target, adb):
    raw = adb('-s', target, 'exec-out', 'cat', PREFERENCES, binary=True)
    if raw.startswith(b'cat:') and b'No such file or directory' in raw:
        raise PairingRequired()
    entry = ET.fromstring(raw).find("./string[@name='config']")
    config = json.loads(entry.text) if entry is not None else {}
    for client in config.get('authorizationCodes', []):
        if client.get('clientId') == CLIENT_ID and client.get('code'):
            return client['code']
    raise PairingRequired()


class Stream:
    def __init__(self, target, adb, root, *, pairing=False):
        token = None if pairing else read_token(target, adb)
        self.socket = None
        self.buffer = b''
        pin = ssl.PEM_cert_to_DER_cert((root / 'assets/corebridge.crt').read_text())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        host = target.split(':')[0]
        tcp = socket.create_connection((host, 7431), timeout=4)
        try:
            self.socket = context.wrap_socket(tcp, server_hostname=host)
            if self.socket.getpeercert(binary_form=True) != pin:
                raise ValueError('Certificate mismatch')
            if not pairing:
                try:
                    self.query(100, token)
                except BridgeRejected as exc:
                    raise PairingRequired() from exc
        except Exception:
            (self.socket or tcp).close()
            raise

    def send(self, frame):
        self.socket.settimeout(4)
        self.socket.sendall((json.dumps(frame)+'\n').encode())

    def receive(self, timeout=10):
        deadline = time.monotonic()+timeout
        while b'\n' not in self.buffer:
            self.socket.settimeout(max(.01, deadline-time.monotonic()))
            chunk = self.socket.recv(65536)
            if not chunk:
                raise EOFError('CoreBridge disconnected')
            self.buffer += chunk
            if len(self.buffer) > 4*1024*1024:
                raise ValueError('Bridge frame too large')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line) if line.strip() else {}

    def query(self, action, data, *, timeout=10, on_event=None):
        identity = str(uuid.uuid4())
        self.send(dict(id=identity, act=action, data=data))
        deadline = time.monotonic()+timeout
        for _ in range(128):
            reply = self.receive(max(.01, deadline-time.monotonic()))
            if reply.get('id') == identity:
                if reply.get('code') != 200:
                    raise BridgeRejected('CoreBridge rejected the request')
                result = reply.get('data')
                if action != 101 or not isinstance(result, dict) or result.get('state') != 0:
                    return result
            elif on_event is not None:
                on_event(reply)
            if time.monotonic() >= deadline:
                break
        raise TimeoutError('No matching response')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.socket.close()


def pair(target, adb, root):
    with Stream(target, adb, root, pairing=True) as stream:
        result = stream.query(101, {'id': CLIENT_ID, 'name': 'UltraBar Studio'}, timeout=18)
        if not isinstance(result, dict) or result.get('state') != 1:
            raise BridgeRejected('CoreBridge did not approve pairing')


def request(target, adb, root, action, data):
    if action not in (1000, 1108, 30300):
        raise ValueError('Unsupported Studio request')
    with Stream(target, adb, root) as stream:
        return stream.query(action, data)


def screensaver(target, adb, root, value=None):
    with Stream(target, adb, root) as stream:
        if value is None:
            return stream.query(30740, dict(type='BASE_SET'))
        return stream.query(30741, dict(type='BASE_SET', value=value))

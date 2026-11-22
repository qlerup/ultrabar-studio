"""Pinned authenticated CoreBridge sessions; credentials only live in memory."""
import json
import socket
import ssl
import time
import uuid
import xml.etree.ElementTree as ET


class Stream:
    def __init__(self, target, adb, root):
        self.socket = None
        self.buffer = b''
        raw = adb('-s', target, 'exec-out', 'cat', '/data/user/0/com.ultrabar.hub/shared_prefs/my_prefs.xml', binary=True)
        config = json.loads(ET.fromstring(raw).find("./string[@name='config']").text)
        token = next(x['code'] for x in config.get('authorizationCodes', []) if x.get('clientId') == 'ultrabarx-profile-inspection')
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
            self.query(100, token)
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

    def query(self, action, data):
        identity = str(uuid.uuid4())
        self.send(dict(id=identity, act=action, data=data))
        deadline = time.monotonic()+10
        for _ in range(128):
            reply = self.receive(max(.01, deadline-time.monotonic()))
            if reply.get('id') == identity:
                if reply.get('code') != 200:
                    raise ValueError('CoreBridge rejected the request')
                return reply.get('data')
            if time.monotonic() >= deadline:
                break
        raise TimeoutError('No matching response')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.socket.close()


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

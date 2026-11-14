"""Vendor UDP discovery, with a bounded local-subnet fallback for blocked broadcasts."""
import ipaddress
import json
import select
import socket
import subprocess
import time


def local_networks():
    script = "Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | ForEach-Object { $_.IPv4Address | Select-Object IPAddress,PrefixLength } | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, timeout=8,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise OSError('Network interfaces unavailable')
    rows = json.loads(result.stdout.decode('utf-8-sig') or '[]')
    if isinstance(rows, dict):
        rows = [rows]
    networks = []
    for row in rows:
        address = ipaddress.IPv4Address(row['IPAddress'])
        if address.is_private and not address.is_link_local and not address.is_loopback:
            # Never probe more than 254 hosts per adapter, even on large networks.
            prefix = max(24, int(row['PrefixLength']))
            networks.append((str(address), ipaddress.IPv4Network(f'{address}/{prefix}', strict=False)))
    return networks[:4]


def parse_announcement(raw, source):
    try:
        data = json.loads(raw)
        address = ipaddress.IPv4Address(source[0])
        if source[1] != 5319 or not address.is_private or data.get('name') != 'ultrabar' or data.get('tcpPort') != 7431:
            return None
        serial = data.get('serialNo')
        if not isinstance(serial, str) or not 1 <= len(serial) <= 80:
            return None
        return {'name': 'CoreBAR', 'ip': str(address), 'serial': serial,
                'target': f'{address}:5555', 'version': str(data.get('ver', ''))[:40]}
    except (ValueError, TypeError, AttributeError):
        return None


def discover():
    sockets, found = [], {}
    try:
        for address, network in local_networks():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((address, 0))
            sock.setblocking(False)
            destinations = [str(network.broadcast_address)] + [str(host) for host in network.hosts() if str(host) != address]
            for destination in destinations:
                try:
                    sock.sendto(b'discovery.ultrabar', (destination, 5319))
                except OSError:
                    continue
        deadline = time.monotonic() + 3
        while sockets and time.monotonic() < deadline:
            ready, _, _ = select.select(sockets, [], [], max(0, deadline-time.monotonic()))
            for sock in ready:
                try:
                    raw, source = sock.recvfrom(4096)
                    item = parse_announcement(raw, source)
                    if item:
                        found[item['serial']] = item
                except OSError:
                    continue
        return sorted(found.values(), key=lambda item: item['ip'])
    finally:
        for sock in sockets:
            sock.close()

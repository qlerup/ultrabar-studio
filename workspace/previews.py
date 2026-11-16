"""Read saved VivoCube artwork from CoreBAR, without modifying either device."""
import base64
import hashlib
import io
import json
import re
import struct
import tarfile
import zlib

PACKAGE_DIR = '/data/user/0/com.ultrabar.launch/cache/tgz'


def revision(data, target, adb):
    # File metadata and configuration only: never take periodic screenshots.
    listing = adb('-s', target, 'shell', f"stat -c '%n %s %Y' {PACKAGE_DIR}/*.tgz 2>/dev/null; true")
    content = json.dumps(data.get('profiles', []), sort_keys=True) + listing
    return hashlib.sha256(content.encode()).hexdigest()


def decode_image(data):
    if len(data) < 8:
        raise ValueError('Invalid image header')
    header, size = struct.unpack_from('<II', data)
    width, height = (header >> 10) & 2047, (header >> 21) & 2047
    if header & 31 != 5 or not 1 <= width <= 512 or not 1 <= height <= 512:
        raise ValueError('Unsupported image format')
    if size != width * height * 3 or len(data) != size + 8:
        raise ValueError('Invalid image length')
    # Cube assets use big-endian RGB565 followed by an 8-bit alpha channel.
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)  # PNG scanline filter
        for x in range(width):
            offset = 8 + (y * width + x) * 3
            color = int.from_bytes(data[offset:offset + 2], 'big')
            pixels.extend((((color >> 11) & 31) * 255 // 31,
                           ((color >> 5) & 63) * 255 // 63,
                           (color & 31) * 255 // 31, data[offset + 2]))
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(pixels))) + chunk(b'IEND', b''))


def package_image(raw):
    # Stream archive entries with strict decompressed limits; never extract files.
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r|gz') as archive:
        for index, member in enumerate(archive):
            total += member.size
            if index > 256 or total > 16 * 1024 * 1024:
                raise ValueError('Artwork package is too large')
            if member.isfile() and (member.name == 'config.json' or re.fullmatch(r'com_res\d+/default\.bin', member.name)):
                if member.size > 1024 * 1024:
                    raise ValueError('Artwork is too large')
                files[member.name] = archive.extractfile(member).read()
    config = json.loads(files['config.json'])
    layer = next(layer for layer in config['layers'] if layer['id'] == config['defaultLayer'])
    items = layer['items']
    # A composite needs its real placement rules; do not invent positions.
    if len(items) != 1 or items[0].get('type') != 1:
        raise ValueError('This saved layout is not supported yet')
    ident = items[0]['id']
    if type(ident) is not int:
        raise ValueError('Invalid widget ID')
    return decode_image(files[f'com_res{ident}/default.bin'])


def cube_previews(devices, target, adb):
    results = {}
    for device in devices:
        serial = device['serial']
        if device['type'] != 'VIVO_CUBE' or not re.fullmatch(r'[0-9A-Fa-f]{16}', serial):
            continue
        candidates=[]
        for name in dict.fromkeys((serial.upper(),serial.lower())):
            path=f'{PACKAGE_DIR}/{name}.tgz'
            try:
                meta=adb('-s',target,'shell','stat','-c','%s %Y',path).split()
                if len(meta)==2 and all(v.isdigit() for v in meta):candidates.append((int(meta[1]),int(meta[0]),path))
            except Exception:continue
        if not candidates:
            results[serial]={'error':'No saved artwork on CoreBAR'};continue
        _,size,path=max(candidates)
        try:
            if not 0 < size <= 8 * 1024 * 1024:
                raise ValueError('Invalid package size')
            raw = adb('-s', target, 'exec-out', 'cat', path, binary=True)
            image = package_image(raw)
            results[serial] = {'image': base64.b64encode(image).decode(), 'source': 'Saved default layout from CoreBAR'}
        except Exception:
            results[serial] = {'error': 'Saved artwork could not be decoded'}
    return results

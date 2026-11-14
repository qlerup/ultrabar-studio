import io
import json
import struct
import tarfile
import unittest
import zlib

from previews import decode_image, package_image, cube_previews, revision


class PreviewTests(unittest.TestCase):
    def image(self):
        return struct.pack('<II', 5 | (1 << 10) | (1 << 21), 3) + bytes([0xf8, 0, 255])

    def test_big_endian_rgb565_and_alpha(self):
        png = decode_image(self.image())
        offset = png.index(b'IDAT')
        size = struct.unpack('>I', png[offset-4:offset])[0]
        self.assertEqual(zlib.decompress(png[offset+4:offset+4+size]), bytes([0, 255, 0, 0, 255]))
        with self.assertRaises(ValueError):
            decode_image(self.image()[:-1])

    def test_package_selects_default_button_and_rejects_unknown_composites(self):
        def archive(items):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w:gz') as tar:
                for name, value in {'config.json': json.dumps({'defaultLayer': 1, 'layers': [{'id': 1, 'items': items}]}).encode(), 'com_res101/default.bin': self.image()}.items():
                    member = tarfile.TarInfo(name); member.size = len(value)
                    tar.addfile(member, io.BytesIO(value))
            return out.getvalue()
        self.assertEqual(package_image(archive([{'id': 101, 'type': 1}])), decode_image(self.image()))
        with self.assertRaises(ValueError):
            package_image(archive([{'id': 101, 'type': 1}, {'id': 102, 'type': 1}]))

    def test_missing_artwork_does_not_copy_another_cube(self):
        devices = [{'serial': '0000000000000001', 'type': 'VIVO_CUBE'}]
        result = cube_previews(devices, 'device', lambda *a, **kw: '')
        self.assertNotIn('image', result[devices[0]['serial']])

    def test_revision_changes_with_config_or_package_metadata(self):
        original = revision({'profiles': [1]}, 'device', lambda *a: 'package 123 1')
        self.assertEqual(original, revision({'profiles': [1]}, 'device', lambda *a: 'package 123 1'))
        self.assertNotEqual(original, revision({'profiles': [2]}, 'device', lambda *a: 'package 123 1'))
        self.assertNotEqual(original, revision({'profiles': [1]}, 'device', lambda *a: 'package 123 2'))


if __name__ == '__main__':
    unittest.main()

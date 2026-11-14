import json
import unittest
from discovery import parse_announcement


class DiscoveryTests(unittest.TestCase):
    def test_uses_packet_source_not_untrusted_advertised_ip(self):
        data = {'name': 'ultrabar', 'tcpPort': 7431, 'serialNo': 'core-1', 'ip': '8.8.8.8'}
        device = parse_announcement(json.dumps(data), ('10.10.0.181', 5319))
        self.assertEqual(device['target'], '10.10.0.181:5555')

    def test_ignores_invalid_or_unrelated_announcements(self):
        for value in ['not json', '{}', '[]', '{"name":"printer"}']:
            self.assertIsNone(parse_announcement(value, ('10.10.0.181', 5319)))

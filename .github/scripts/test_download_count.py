import unittest

from update_download_count import badge, installer_downloads


class CounterTests(unittest.TestCase):
    def test_only_installer_downloads_count(self):
        release = {"assets": [
            {"name": "UltraBarStudio-Setup-0.34.0.exe", "download_count": 7},
            {"name": "SHA256SUMS.txt", "download_count": 99},
            {"name": "studio-update.json", "download_count": 50},
        ]}
        self.assertEqual(installer_downloads(release), 7)
        self.assertIn("Downloads: 7", badge(7))

    def test_invalid_count_does_not_publish_a_false_value(self):
        with self.assertRaises(ValueError):
            installer_downloads({"assets": [
                {"name": "UltraBarStudio-Setup-1.0.0.exe", "download_count": -1}
            ]})

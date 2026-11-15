import unittest
from update_download_count import installer_downloads,badge


class CounterTests(unittest.TestCase):
    def test_installers_only_across_releases(self):
        releases=[dict(assets=[dict(name='UltraBarStudio-Setup-0.33.0.exe',download_count=10),dict(name='SHA256SUMS-0.33.0.txt',download_count=99),dict(name='source.zip',download_count=50)]),dict(assets=[dict(name='UltraBarStudio-Setup-0.34.0.exe',download_count=7)]),dict(draft=True,assets=[dict(name='UltraBarStudio-Setup-0.35.0.exe',download_count=100)])]
        self.assertEqual(installer_downloads(releases),17)
        self.assertIn('Installer downloads: 17',badge(17))
    def test_invalid_count_does_not_publish_a_false_value(self):
        with self.assertRaises(ValueError):installer_downloads([dict(assets=[dict(name='UltraBarStudio-Setup-1.0.0.exe',download_count=-1)])])

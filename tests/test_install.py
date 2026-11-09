from pathlib import Path
import tempfile
import unittest

from install_overlay import install


class TestInstaller(unittest.TestCase):
    def test_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            html = Path(folder)
            index = html / "index.html"
            index.write_text('<html><head></head><body><script src="config.js"></script></body></html>')
            install(html)
            once = index.read_text()
            self.assertIn('sonde-overlay.js', once)
            self.assertIn('sonde-overlay.css', once)
            self.assertTrue((html / 'sonde-overlay.js').exists())
            self.assertTrue((html / 'sonde-overlay.css').exists())
            self.assertEqual(len(list(html.glob('index.html.sonde1090.*.bak'))), 1)
            install(html)
            self.assertEqual(index.read_text(), once)
            self.assertEqual(len(list(html.glob('index.html.sonde1090.*.bak'))), 1)


if __name__ == "__main__":
    unittest.main()

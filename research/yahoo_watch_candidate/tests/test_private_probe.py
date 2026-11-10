from pathlib import Path
import tempfile
import unittest
from private_outbox_probe import run_probe,validate_private_directory

class Tests(unittest.TestCase):
    def test_concurrent_interrupt_restart(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_probe(Path(d),'test')
            self.assertTrue(r['passed']);self.assertEqual(r['reservations'],1)
            self.assertFalse(r['smtp_called']);self.assertFalse(r['production_db_touched'])
    def test_never_reuse_existing_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.v82-watch-synthetic-existing';p.mkdir(mode=0o700)
            sentinel=p/'do-not-touch';sentinel.write_text('original')
            with self.assertRaises(FileExistsError):run_probe(Path(d),'existing')
            self.assertEqual(sentinel.read_text(),'original')
    def test_reject_public_parent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'public_html';p.mkdir()
            with self.assertRaises(ValueError):run_probe(p,'test')
    def test_reject_symlink_root(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'real').mkdir(mode=0o700);(p/'alias').symlink_to(p/'real')
            with self.assertRaises(ValueError):validate_private_directory(p/'alias')
    def test_invalid_id(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):run_probe(Path(d),'../../other')

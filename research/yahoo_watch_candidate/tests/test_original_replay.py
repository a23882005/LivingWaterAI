from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
import unittest
from replay_original_technical import replay,APPROVED_SOURCE_COMMIT

class Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.q=self.root/'q.json';self.q.write_text('{}')
    def tearDown(self):self.t.cleanup()
    def test_wrong_commit_blocks(self):
        with patch('subprocess.check_output',return_value='wrong'):
            with self.assertRaisesRegex(ValueError,'COMMIT_MISMATCH'):replay(self.root,self.q,'x','VT','2026-11-10T00:00:00Z')
    def test_modified_original_blocks(self):
        with patch('subprocess.check_output',return_value=APPROVED_SOURCE_COMMIT),patch('subprocess.run',return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError,'SOURCE_MODIFIED'):replay(self.root,self.q,'x','VT','2026-11-10T00:00:00Z')
    def test_qualification_hash_blocks(self):
        with patch('subprocess.check_output',return_value=APPROVED_SOURCE_COMMIT),patch('subprocess.run',return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):replay(self.root,self.q,'x','VT','2026-11-10T00:00:00Z')

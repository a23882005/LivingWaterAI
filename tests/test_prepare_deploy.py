import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.prepare_deploy import prepare_index, stage

class TestPrepareDeploy(unittest.TestCase):
    def test_verified_current_source(self):
        from tempfile import TemporaryDirectory
        base = Path(__file__).resolve().parent.parent
        with TemporaryDirectory() as td:
            dest=Path(td)/"index.html"
            stage("123456",base/"V70_Live.html",dest)
            result=dest.read_text(encoding="utf-8")
            self.assertIn("LivingWaterAI V70.2 verified deployment run=123456", result)
            self.assertIn("投資戰情室 V70.2", result)
            self.assertEqual(result.count("</html>"),1)
    def test_bad_template_rejected(self):
        with self.assertRaises(ValueError):
            prepare_index("<!DOCTYPE html><html><body>V20</body></html>","123")
    def test_invalid_run_id_rejected(self):
        with self.assertRaises(ValueError):
            prepare_index("<!DOCTYPE html><html><title>投資戰情室 V70.2</title><body></body></html>","../../danger")

if __name__ == "__main__":
    unittest.main()

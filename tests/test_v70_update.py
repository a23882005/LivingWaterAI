import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("v70_update", BASE / "scripts" / "v70_update.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestV70Update(unittest.TestCase):
    def test_owner_source_files_present(self):
        p128 = (BASE / "p128.py").read_text(encoding="utf-8")
        html = (BASE / "V70_Live.html").read_text(encoding="utf-8")
        self.assertIn('INPUT_HTML = "V70_2.html"', p128)
        self.assertIn('OUTPUT_HTML = "V70_Live.html"', p128)
        self.assertIn('V70.2', html)
        self.assertIn("</html>", html)

    def test_missing_snapshot_blocks_publish(self):
        with self.assertRaises(ValueError):
            mod.manual_snapshot("", today=dt.date(2026,10,11))

    def test_approved_snapshot_validation(self):
        obj={"as_of":"2026-10-10","fed_current":4.25,
             "fed_target":3.5,"pmi":52.1,"cpi":2.6}
        snap=mod.manual_snapshot(json.dumps(obj),today=dt.date(2026,10,11))
        self.assertEqual(snap["pmi"],52.1)

    def test_stale_snapshot_blocks_publish(self):
        obj={"as_of":"2026-01-01","fed_current":4.25,
             "fed_target":3.5,"pmi":52.1,"cpi":2.6}
        with self.assertRaises(ValueError):
            mod.manual_snapshot(json.dumps(obj),today=dt.date(2026,10,11))

    def test_wrong_field_blocks_publish(self):
        obj={"as_of":"2026-10-10","fed_current":4.25,
             "fed_target":3.5,"pmi":520.1,"cpi":2.6}
        with self.assertRaises(ValueError):
            mod.manual_snapshot(json.dumps(obj),today=dt.date(2026,10,11))

    def test_replace_only_one_indicator(self):
        html = (BASE / "V70_Live.html").read_text(encoding="utf-8")
        updated, matched = mod.replace_value(html,"m07",18.5)
        self.assertTrue(matched)
        self.assertNotEqual(updated,html)
        self.assertIn("val: 18.5",updated)
        self.assertEqual(updated.count("</html>"),1)

    def test_bad_id_cannot_modify_html(self):
        html=(BASE / "V70_Live.html").read_text(encoding="utf-8")
        with self.assertRaises(RuntimeError):
            mod.replace_value(html,"not-an-indicator",12)

if __name__=="__main__":
    unittest.main()

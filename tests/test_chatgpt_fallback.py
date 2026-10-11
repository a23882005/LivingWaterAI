import datetime as dt
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from chatgpt_fallback import read_verified_fallback, make_manual_input

class TestChatGPTFallback(unittest.TestCase):
    def _make(self, path, fields, asof="2026-10-10T10:00:00+08:00"):
        path.write_text(json.dumps({"as_of": asof, "metrics": fields}), encoding="utf-8")

    def test_valid_sourced_macro_fallback(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            path=Path(td)/"snapshot.json"
            self._make(path,{"pmi":{"value":51.2,"data_date":"2026-10-01",
                        "source":"Institute for Supply Management",
                        "url":"https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"}})
            now=dt.datetime(2026,10,11,0,0,tzinfo=dt.timezone.utc)
            values,notes=read_verified_fallback(path,now=now)
            self.assertEqual(values["pmi"]["value"],51.2)
            self.assertEqual(notes,[])
            self.assertEqual(make_manual_input(values)["pmi"],51.2)

    def test_invalid_range_and_url_dropped_individually(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            path=Path(td)/"snapshot.json"
            self._make(path,{
              "cpi":{"value":99.0,"data_date":"2026-10-10","source":"Bad inflation","url":"https://example.org/cpi"},
              "pmi":{"value":49.0,"data_date":"2026-10-01","source":"ISM official","url":"http://example.org"},
              "vix":{"value":20.0,"data_date":"2026-10-09","source":"CBOE official","url":"https://www.cboe.com"}
            })
            vals,notes=read_verified_fallback(path,now=dt.datetime(2026,10,11,0,0,tzinfo=dt.timezone.utc))
            self.assertEqual(list(vals),["vix"])
            self.assertEqual(len(notes),2)

    def test_stale_snapshot_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            path=Path(td)/"snapshot.json"
            self._make(path,{"pmi":{"value":50.0,"data_date":"2026-09-30","source":"ISM official","url":"https://www.ismworld.org"}},asof="2026-10-01T10:00:00+08:00")
            vals,notes=read_verified_fallback(path,now=dt.datetime(2026,10,11,0,0,tzinfo=dt.timezone.utc))
            self.assertFalse(vals)
            self.assertTrue(notes)

    def test_no_file_rejected(self):
        vals,notes=read_verified_fallback(Path("/nonexistent/snapshot.json"))
        self.assertEqual(vals,{})
        self.assertTrue(notes)

if __name__ == "__main__":
    unittest.main()

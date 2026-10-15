# 最後修改日期時間（台灣）：2026/10/16 02:30｜版本：D009-v2｜檔案：test_d009_state.py
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro18_state import snapshot, recover, read_valid

IDS = ("m07","m01","m08","m02","m04","m05","m09","m10","m12",
       "m13","m14","m15","m16","m17","m18","m19","m20","s04")


def report(value):
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    items = {key: {"id": key, "value": value, "status": "OK",
                   "observation_date": today, "source_url": "https://example.org/verified"}
             for key in IDS}
    items["s03"] = dict(items["m07"], id="s03")
    return {"items": items, "independent_indicators": {"total": 18},
            "lei_history": [{"observation_date": (dt.date.fromisoformat(today)-dt.timedelta(days=62)).isoformat(), "value": value}, {"observation_date": (dt.date.fromisoformat(today)-dt.timedelta(days=31)).isoformat(), "value": value}, {"observation_date": today, "value": value}]}


class TestD009State(unittest.TestCase):
    def test_rotate_dedupe_and_recover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            for value in (1, 1, 2, 3, 4):
                source.write_text(json.dumps(report(value)), encoding="utf-8")
                snapshot(source, root)
            backups = list((root / "backups").glob("macro18_*.json"))
            self.assertEqual(len(backups), 3)
            output = root / "restored.json"
            recover(output, root)
            self.assertEqual(read_valid(output)["items"]["m07"]["value"], 4)
            self.assertEqual(read_valid(output)["items"]["m07"]["status"], "STALE")
            output.write_text("{invalid", encoding="utf-8")
            recover(output, root)
            self.assertEqual(read_valid(output)["items"]["m07"]["value"], 4)

    def test_corrupt_head_does_not_replace_three_valid_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            for value in (1, 2, 3):
                source.write_text(json.dumps(report(value)), encoding="utf-8")
                snapshot(source, root)
            corrupt = root / "backups" / "macro18_99999999T999999999999Z_corrupt.json"
            corrupt.write_text("{broken", encoding="utf-8")
            source.write_text(json.dumps(report(4)), encoding="utf-8")
            snapshot(source, root)
            valid = []
            for file in (root / "backups").glob("macro18_*.json"):
                try:
                    valid.append(read_valid(file)["items"]["m07"]["value"])
                except ValueError:
                    pass
            self.assertEqual(sorted(valid), [2, 3, 4])
            output = root / "recovered.json"
            recover(output, root)
            self.assertEqual(read_valid(output)["items"]["m07"]["value"], 4)

    def test_corrupt_report_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "invalid.json"
            source.write_text('{"items": {}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                snapshot(source, tmp)


if __name__ == "__main__":
    unittest.main()

"""Regression cases for role budgets, the six common periods, and sparse history."""
import sys
from datetime import date,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import equity_sleeve as calc
import family03_plans as plans


class ThreePlans(unittest.TestCase):
    def test_dates_are_intersected_across_all_six(self):
        portfolios=[plans.blank() for _ in range(3)]
        for p,k in zip(portfolios,("A","B","C")):
            p["layers"]["主軸"]={k:100}
        data={s:("USD",{(date(2024,1,1)+timedelta(days=i)).isoformat():100+i/100
                        for i in range(n,500)}) for n,s in enumerate(("VT","VOO","QQQ","A","B","C"))}
        rows=plans.six(portfolios,data,[],calc)
        self.assertEqual(len(rows),6)
        self.assertEqual({r["歷史試算"]["共同觀察筆數"] for r in rows},{495})
        del data["B"]
        self.assertTrue(all("B" in r["歷史試算"]["缺行情"] for r in plans.six(portfolios,data,[],calc)))
    def test_short_history_and_direct_exposure(self):
        prices={"短期":("USD",{"2026-01-05":100,"2026-01-06":90})}
        h=calc.simulate({"短期":100},prices)
        self.assertAlmostEqual(h["期間報酬率"],-.1)
        self.assertNotIn("年化報酬率",h)
        rows=calc.direct_exposures({"ZTS","PAWZ"},{"ZTS"},[])
        self.assertAlmostEqual(calc.exposure({"ZTS":5,"PAWZ":10},rows)["共同曝險"][0]["已知合計百分點"],5.999)
    def test_fx_uses_same_date_and_correct_direction(self):
        data={"TW":("TWD",{"a":300,"b":310}),"US":("USD",{"a":10,"b":11})}
        fx=lambda _:{"USDTWD":("TWD_PER_USD",{"a":30})}
        self.assertEqual(calc.common_currency(data,fx)["TW"],("USD",{"a":10}))
    def test_each_range_covers_each_allowed_percentage_once(self):
        for limit in range(101):
            self.assertEqual([v for a,b in plans.available_bands(limit).values() for v in range(a,b+1)],list(range(limit+1)))


    def test_progress_receipt_matrix_for_current_and_legacy_workbook_layouts(self):
        layouts = ("偏好年報酬", "主軸想占股票部位的哪個範圍？", None, " ")
        cases = (
            "latest", "older", "unsaved", "source changed", "duplicate", "wrong owner header",
            "wrong owner event", "invalid event", "invalid source revision", "wrong action",
        )
        errors = {
            "duplicate": (ValueError, "FAMILY03_DUPLICATE_PROGRESS_EVENT"),
            "wrong owner header": (PermissionError, "FAMILY03_PROGRESS_OWNER_MISMATCH"),
            "wrong owner event": (PermissionError, "FAMILY03_PROGRESS_OWNER_MISMATCH"),
            "invalid event": (ValueError, "FAMILY03_INVALID_PROGRESS_RECEIPT_REQUEST"),
            "invalid source revision": (ValueError, "FAMILY03_INVALID_PROGRESS_RECEIPT_REQUEST"),
            "wrong action": (ValueError, "FAMILY03_INVALID_PROGRESS_RECEIPT_REQUEST"),
        }
        first, latest = "a" * 64, "b" * 64
        reader = calc.reader_module()
        with TemporaryDirectory() as root:
            path = Path(root) / "mou_03_股票配置選擇進度.xlsx"
            for position in layouts:
                for case in cases:
                    with self.subTest(position=position, case=case):
                        book = Workbook()
                        main = book.active
                        main.title = "選擇進度"
                        main.append(["股票配置・選擇進度", "other" if case == "wrong owner header" else "mou"])
                        if position is not None:
                            main.append(["續選位置", position])
                        history = book.create_sheet("選擇歷程")
                        history.append(["事件識別", "家人"])
                        history.append([latest if case == "duplicate" else first, "mou"])
                        history.append([latest, "other" if case == "wrong owner event" else "mou"])
                        book.save(path)
                        before = path.read_bytes()
                        payload = {
                            "action": "other" if case == "wrong action" else "progress_receipt",
                            "event_id": {"older": first, "unsaved": "c" * 64, "source changed": "c" * 64,
                                         "invalid event": "bad"}.get(case, latest),
                            "source_revision": {"source changed": "d" * 64,
                                                "invalid source revision": "bad"}.get(case, sha256(before).hexdigest()),
                        }
                        if case in errors:
                            with self.assertRaisesRegex(*errors[case]):
                                plans.progress_receipt(path, "mou", payload, reader)
                        else:
                            result = plans.progress_receipt(path, "mou", payload, reader)
                            expected = {"unsaved": "FAMILY03_PROGRESS_NOT_SAVED",
                                        "source changed": "FAMILY03_PROGRESS_SOURCE_CHANGED"}
                            self.assertEqual(result["status"], expected.get(case, "FAMILY03_PROGRESS_EVENT_FOUND"))
                            if case in ("latest", "older"):
                                self.assertEqual(result["讀回時為最新作答"], case == "latest")
                                self.assertEqual(result.get("讀回時續選位置"), position.strip() or None
                                                 if position is not None else None)
                                self.assertEqual(result["事件序號"], 2 if case == "latest" else 1)
                            else:
                                self.assertNotIn("讀回時續選位置", result)
                                self.assertNotIn("讀回時為最新作答", result)
                        self.assertEqual(path.read_bytes(), before)

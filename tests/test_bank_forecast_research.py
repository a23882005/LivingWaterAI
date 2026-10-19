import importlib.util
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

MODULE = Path(__file__).parents[1] / "scripts/monthly_research/bank_forecast_research.py"
spec = importlib.util.spec_from_file_location("bank_forecast_research", MODULE)
bfr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bfr)


class BankForecastResearchTests(unittest.TestCase):
    def workbook(self, path):
        wb = Workbook()
        ws = wb.active
        ws.title = "五大機構來源"
        ws.append(["來源明細｜公開歷史目標"])
        ws.append([None])
        ws.append(["公開資料最遲可得日期", "機構", "年底目標點數", "預測截止日", "機構部門", "資料來源連結", "附註"])
        ws.append(["2025-12-16", "高盛", 7600, "2026-12-31", "Goldman Sachs", "https://example.com/a", None])
        ws.append(["2026-06-25", "高盛", 8000, "2026-12-31", "Goldman Sachs", "https://example.com/b", "目標修訂"])
        q = wb.create_sheet("季度回測資料")
        q.append(["季度回測資料｜標題"])
        q.append([None])
        q.append([None])
        q.append(["基準日", "實際交易日", "S&P500收盤點", "3M後交易日", "3M後收盤點", "3M價格報酬 (%)"])
        q.append(["2026-04-01", "2026-04-01", 7000, "2026-07-01", 7100, 1.428571])
        q.append(["2026-10-01", "2026-10-01", 7500, None, None, None])
        wb.save(path)

    def test_import_is_traceable_and_only_uses_available_forecast(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.xlsx"
            self.workbook(path)
            register = bfr.extract_register(path, "2026-10-19T00:00:00Z")
            observations = bfr.extract_quarterly_observations(path)
            comparison = bfr.build_comparison(register, observations)
            self.assertEqual(len(register), 2)
            self.assertEqual(len({r["forecast_id"] for r in register}), 2)
            self.assertTrue(all(r["publication_date"] == "" for r in register))
            self.assertTrue(all(r["verification_status"] == "RESEARCH_PIT_PENDING" for r in register))
            april = next(r for r in comparison if r["observation_date"] == "2026-04-01")
            self.assertEqual(april["forecast_value"], "7600")
            self.assertEqual(april["return_status"], "REALIZED")
            self.assertEqual(april["sp500_forward_end_date"], "2026-07-01")
            october = next(r for r in comparison if r["observation_date"] == "2026-10-01")
            self.assertEqual(october["forecast_value"], "8000")
            self.assertEqual(october["return_status"], "PENDING")
            repeated = bfr.merge_register(register, register)
            self.assertEqual(len(repeated), len(register))
            added = dict(register[0])
            added["forecast_id"] = "new-version"
            added["forecast_value"] = "8100"
            added["evidence_date"] = "2026-10-06"
            extended = bfr.merge_register(register, [added])
            self.assertEqual(len(extended), len(register) + 1)
            self.assertEqual(next(r for r in extended if r["forecast_id"] == register[0]["forecast_id"]), register[0])


if __name__ == "__main__":
    unittest.main()

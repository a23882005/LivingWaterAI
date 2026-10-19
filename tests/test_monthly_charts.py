import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from importlib.util import spec_from_file_location, module_from_spec

MODULE = Path(__file__).parents[1] / "scripts/monthly_research/build_monthly_charts.py"
spec = spec_from_file_location("build_monthly_charts", MODULE)
charts = module_from_spec(spec)
spec.loader.exec_module(charts)


class MonthlyResearchChartTests(unittest.TestCase):
    def test_missing_license_blocks_and_removes_stale_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "monthly"
            out.mkdir()
            for name in charts.CHARTS:
                (out / name).write_bytes(charts.PNG + b"old")
            status = charts.build(Path(tmp) / "missing.csv", out, Path(tmp) / "missing.json")
            self.assertEqual(status["status"], "BLOCKED")
            self.assertEqual(list(out.glob("*.png")), [])
            saved = json.loads((out / "monthly_chart_status.json").read_text())
            self.assertEqual(saved["status"], "BLOCKED")

    def test_authorized_real_month_rows_generate_exactly_seven_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "monthly.csv"
            months = ["2026-01", "2026-02", "2026-03", "2026-04"]
            fields = [
                "snapshot_month", "snapshot_date", "institution", "macro_score_status",
                "macro_slope_points_per_month", "macro_sp500_forward_3m_return_pct",
                "macro_return_status", "forecast_implied_return_pct",
            ]
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index, month in enumerate(months):
                    for institution in charts.INSTITUTIONS:
                        writer.writerow({
                            "snapshot_month": month,
                            "snapshot_date": month + "-05",
                            "institution": institution,
                            "macro_score_status": "FORMAL_VALID",
                            "macro_slope_points_per_month": str(index - 1),
                            "macro_sp500_forward_3m_return_pct": str(index + 2),
                            "macro_return_status": "REALIZED",
                            "forecast_implied_return_pct": str(index + 1),
                        })
            license_path = root / "license.json"
            license_path.write_text(json.dumps({
                "schema": charts.LICENSE_SCHEMA,
                "status": "AUTHORIZED",
                "benchmark": "S&P 500",
                "source_url": "https://data.example.com/sp500",
                "license_evidence_url": "https://data.example.com/license",
                "license_id": "public-display-123",
                "allowed_uses": [
                    "historical_index_values",
                    "derived_forward_3m_returns",
                    "public_static_charts",
                ],
            }), encoding="utf-8")
            out = root / "charts"
            status = charts.build(csv_path, out, license_path, today=date(2026, 5, 1))
            self.assertEqual(status["status"], "READY")
            self.assertEqual(status["eligible_months"], 4)
            self.assertEqual({p.name for p in out.glob("*.png")}, set(charts.CHARTS))
            for name in charts.CHARTS:
                self.assertEqual((out / name).read_bytes()[:8], charts.PNG)

    def test_canonical_html_source_switches_and_reverts(self):
        repo = Path(__file__).parents[1]
        source = repo / "系統工程" / "總經V70" / "V70-3-27.html"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "V70-3-27.html"
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            charts.sync_canonical_html(target, True)
            self.assertIn("真實月斜率（分數點／月）", target.read_text(encoding="utf-8"))
            charts.sync_canonical_html(target, False)
            restored = target.read_text(encoding="utf-8")
            self.assertIn("候選季度體質方向斜率", restored)
            self.assertNotIn("真實月斜率（分數點／月）", restored)

    def test_not_enough_common_months_remains_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "monthly.csv"
            fields = [
                "snapshot_month", "snapshot_date", "institution", "macro_score_status",
                "macro_slope_points_per_month", "macro_sp500_forward_3m_return_pct",
                "macro_return_status", "forecast_implied_return_pct",
            ]
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for institution in charts.INSTITUTIONS:
                    writer.writerow({
                        "snapshot_month": "2026-01", "snapshot_date": "2026-01-05",
                        "institution": institution, "macro_score_status": "FORMAL_VALID",
                        "macro_slope_points_per_month": "1", "macro_sp500_forward_3m_return_pct": "2",
                        "macro_return_status": "REALIZED", "forecast_implied_return_pct": "3",
                    })
            license_path = root / "license.json"
            license_path.write_text(json.dumps({
                "schema": charts.LICENSE_SCHEMA, "status": "AUTHORIZED",
                "benchmark": "S&P 500", "source_url": "https://data.example.com/sp500",
                "license_evidence_url": "https://data.example.com/license",
                "license_id": "public-display-123", "allowed_uses": [
                    "historical_index_values", "derived_forward_3m_returns", "public_static_charts",
                ],
            }), encoding="utf-8")
            status = charts.build(csv_path, root / "charts", license_path, today=date(2026, 5, 1))
            self.assertEqual(status["status"], "BLOCKED")
            self.assertEqual(status["eligible_months"], 1)


if __name__ == "__main__":
    unittest.main()

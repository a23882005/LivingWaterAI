import importlib.util
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_daily_v703_site", ROOT / "scripts" / "build_daily_v703_site.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ResearchChartMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_section = False
        self.images = []
        self.figures = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section" and attrs.get("id") == "v703-research-charts":
            self.in_section = True
        elif self.in_section and tag == "figure":
            self.figures += 1
        elif self.in_section and tag == "img":
            self.images.append(attrs.get("src"))

    def handle_endtag(self, tag):
        if tag == "section" and self.in_section:
            self.in_section = False


class V703ResearchChartsTests(unittest.TestCase):
    def test_html_references_exactly_seven_saved_charts(self):
        html = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        parser = ResearchChartMarkup()
        parser.feed(html)
        expected = {f"v70-research-charts/{name}" for name in builder.RESEARCH_CHARTS}
        self.assertEqual(parser.figures, 7)
        self.assertEqual(set(parser.images), expected)
        self.assertEqual(len(parser.images), len(expected))
        self.assertIn("兩者期間不同", html)
        self.assertTrue("候選季度體質方向斜率" in html or "真實月斜率（分數點／月）" in html)
        self.assertIn("七線總覽", html)
        self.assertIn("正式月度圖將在真實月度資料累積後另行替換", html)
        self.assertIn("macro_slope_candidate.png", parser.images[-2])
        self.assertIn("overview_7lines.png", parser.images[-1])

    def test_build_copies_verified_pngs_with_stable_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, monthly_ready = builder.copy_research_charts(tmp)
            self.assertFalse(monthly_ready)
            self.assertEqual({path.name for path in output.iterdir()}, set(builder.RESEARCH_CHARTS))
            for target, source in builder.RESEARCH_CHARTS.items():
                expected = (builder.Path(builder.__file__).resolve().parents[1]
                            / "experiments" / "macro-safety-monthly-research" / "charts" / source)
                self.assertEqual((output / target).read_bytes(), expected.read_bytes())

    def test_build_switches_only_when_all_seven_monthly_pngs_are_valid(self):
        signature = bytes([137]) + b"PNG" + bytes([13, 10, 26, 10])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quarterly, monthly = root / "quarterly", root / "monthly"
            quarterly.mkdir()
            monthly.mkdir()
            for output_name, source_name in builder.RESEARCH_CHARTS.items():
                (quarterly / source_name).write_bytes(signature + b"quarterly")
                (monthly / output_name).write_bytes(signature + output_name.encode())
            license_path = root / "license.json"
            license_info = {
                "schema": "V70.3/SP500-public-display-license-v1", "status": "AUTHORIZED",
                "benchmark": "S&P 500", "source_url": "https://data.example.com/sp500",
                "license_evidence_url": "https://data.example.com/license",
                "license_id": "test-license",
                "allowed_uses": ["historical_index_values", "derived_forward_3m_returns", "public_static_charts"],
                "valid_through": "2099-12-31",
            }
            license_path.write_text(json.dumps(license_info), encoding="utf-8")
            (monthly / "monthly_chart_status.json").write_text(json.dumps({
                "schema": "V70.3/monthly-research-chart-status-v1", "status": "READY",
                "charts": list(builder.RESEARCH_CHARTS), "license_id": "test-license",
                "benchmark_source_url": license_info["source_url"],
                "license_evidence_url": license_info["license_evidence_url"],
            }), encoding="utf-8")
            output, ready = builder.copy_research_charts(
                root / "out", quarterly, monthly, license_path
            )
            self.assertTrue(ready)
            for name in builder.RESEARCH_CHARTS:
                self.assertEqual((output / name).read_bytes(), (monthly / name).read_bytes())

            (monthly / "ubs.png").unlink()
            output, ready = builder.copy_research_charts(
                root / "out2", quarterly, monthly, license_path
            )
            self.assertFalse(ready)
            for name, source in builder.RESEARCH_CHARTS.items():
                self.assertEqual((output / name).read_bytes(), (quarterly / source).read_bytes())

    def test_monthly_markup_drops_quarterly_candidate_language(self):
        html = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        monthly = builder._monthly_chart_markup(html)
        self.assertIn("真實月斜率（分數點／月）", monthly)
        self.assertIn("具公開展示授權", monthly)
        self.assertNotIn("候選季度體質方向斜率", monthly)
        self.assertNotIn("正式月度圖將在真實月度資料累積後另行替換", monthly)

    def test_quarterly_markup_can_be_restored_after_monthly_mode(self):
        html = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        monthly = builder._monthly_chart_markup(html)
        quarterly = builder._quarterly_chart_markup(monthly)
        self.assertIn("候選季度體質方向斜率", quarterly)
        self.assertNotIn("真實月斜率（分數點／月）", quarterly)

    def test_deployment_upload_includes_chart_assets(self):
        workflow = (ROOT / ".github" / "workflows" / "v703-site-deploy-1100.yml").read_text(encoding="utf-8")
        self.assertIn("build/site/v70-research-charts/*", workflow)
        for name in builder.RESEARCH_CHARTS:
            self.assertIn(name, workflow)
        self.assertIn("HOSTINGER_RESEARCH_CHARTS_LIVE_PASS", workflow)
        self.assertIn("--html-template", workflow)
        self.assertIn('git add "系統工程/總經V70/V70-3-27.html"', workflow)


if __name__ == "__main__":
    unittest.main()

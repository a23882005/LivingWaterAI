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
        self.assertIn("候選季度體質方向斜率", html)
        self.assertNotIn("真實月斜率（分數點／月）", html)
        self.assertIn("七線總覽", html)
        self.assertIn("本頁研究圖固定呈現逐季資料", html)
        self.assertIn("macro_slope_candidate.png", parser.images[-2])
        self.assertIn("overview_7lines.png", parser.images[-1])

    def test_build_always_copies_quarterly_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "quarterly"
            monthly_dir = root / "monthly"
            source_dir.mkdir()
            monthly_dir.mkdir()
            original_dir = (Path(builder.__file__).resolve().parents[1]
                            / "experiments" / "macro-safety-monthly-research" / "charts")
            for target, source in builder.RESEARCH_CHARTS.items():
                (source_dir / source).write_bytes((original_dir / source).read_bytes())
            output, monthly_ready = builder.copy_research_charts(
                root / "out", source_dir, monthly_dir, root / "missing-license.json"
            )
            self.assertFalse(monthly_ready)
            self.assertEqual({path.name for path in output.iterdir()}, set(builder.RESEARCH_CHARTS))
            for target, source in builder.RESEARCH_CHARTS.items():
                self.assertEqual((output / target).read_bytes(), (source_dir / source).read_bytes())

    def test_monthly_assets_never_replace_quarterly_charts(self):
        signature = bytes([137]) + b"PNG" + bytes([13, 10, 26, 10])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quarterly, monthly = root / "quarterly", root / "monthly"
            quarterly.mkdir()
            monthly.mkdir()
            for output_name, source_name in builder.RESEARCH_CHARTS.items():
                (quarterly / source_name).write_bytes(signature + b"quarterly")
                (monthly / output_name).write_bytes(signature + b"monthly")
            output, monthly_ready = builder.copy_research_charts(
                root / "out", quarterly, monthly, root / "license.json"
            )
            self.assertFalse(monthly_ready)
            for output_name, source_name in builder.RESEARCH_CHARTS.items():
                self.assertEqual((output / output_name).read_bytes(),
                                 (quarterly / source_name).read_bytes())

    def test_quarterly_markup_keeps_quarterly_scope_explicit(self):
        html = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        quarterly = builder._quarterly_chart_markup(html)
        self.assertIn("候選季度體質方向斜率", quarterly)
        self.assertIn("本頁研究圖固定呈現逐季資料", quarterly)
        self.assertNotIn("真實月斜率（分數點／月）", quarterly)

    def test_deployment_upload_includes_chart_assets(self):
        workflow = (ROOT / ".github" / "workflows" / "v703-site-deploy-1100.yml").read_text(encoding="utf-8")
        self.assertIn("build/site/v70-research-charts/*", workflow)
        for name in builder.RESEARCH_CHARTS:
            self.assertIn(name, workflow)
        self.assertIn("HOSTINGER_RESEARCH_CHARTS_LIVE_PASS", workflow)
        self.assertIn('--html "系統工程/總經V70/V70-3-27.html"', workflow)
        self.assertNotIn("build_monthly_charts.py", workflow)
        self.assertIn('git add "系統工程/總經V70/V70-3-27.html"', workflow)


if __name__ == "__main__":
    unittest.main()

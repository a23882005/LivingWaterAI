import importlib.util
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_daily_v703_site", ROOT / "scripts" / "build_daily_v703_site.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ResearchChartMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_section = False
        self.images = []
        self.alts = []
        self.figures = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section" and attrs.get("id") == "v703-research-charts":
            self.in_section = True
        elif self.in_section and tag == "figure":
            self.figures += 1
        elif self.in_section and tag == "img":
            self.images.append(attrs.get("src"))
            self.alts.append(attrs.get("alt", ""))

    def handle_endtag(self, tag):
        if tag == "section" and self.in_section:
            self.in_section = False


class V703ResearchChartsTests(unittest.TestCase):
    def test_html_references_twelve_plots_and_overview_in_requested_order(self):
        page = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        parser = ResearchChartMarkup()
        parser.feed(page)
        self.assertTrue(page.lstrip().startswith("<!DOCTYPE html>"))
        self.assertNotIn("# 最後修改日期時間", page[:200])
        expected = [f"v70-research-charts/{name}" for name in builder.RESEARCH_CHARTS]
        self.assertEqual(parser.figures, 13)
        self.assertEqual(parser.images, expected)
        self.assertIn("完整逐季數值表（28 季）", page)
        self.assertIn("2026-10-01", page)
        self.assertIn("季度資料不插值成月資料", page)
        self.assertIn("動能上修／下修家數", page)
        self.assertTrue(all("後三個月實際報酬" in alt for alt in parser.alts))
        names = ("Macro-SaFe｜原始值", "高盛｜原始值", "美國銀行｜原始值", "摩根士丹利｜原始值", "瑞銀｜原始值", "摩根大通｜原始值")
        positions = [page.index(f"<figcaption class=\"text-sm font-semibold text-slate-100 mb-2\">{name}") for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_builder_copies_all_pngs_and_both_source_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, monthly_ready = builder.copy_research_charts(Path(tmp) / "out")
            self.assertFalse(monthly_ready)
            expected = set(builder.RESEARCH_CHARTS) | {builder.QUARTERLY_DATA, builder.QUARTERLY_CONSENSUS}
            self.assertEqual({p.name for p in output.iterdir()}, expected)
            for name in builder.RESEARCH_CHARTS:
                self.assertEqual((output / name).read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_markup_builds_full_quarter_table_with_na_and_preserves_no_monthly_interpolation(self):
        template = (ROOT / "系統工程" / "總經V70" / "V70-3-27.html").read_text(encoding="utf-8")
        rendered = builder._quarterly_chart_markup(template)
        self.assertEqual(rendered.count("<tbody>"), 1)
        self.assertIn(">NA</td>", rendered)
        self.assertIn("季度資料不插值成月資料", rendered)
        self.assertIn("後三個月報酬尚未成熟，保留 NA", rendered)
        self.assertNotIn("五家機構偏多／偏空與動能上修／下修家數</h3>", rendered)
        self.assertNotIn(">後三個月取價交易日</th>", rendered)
        self.assertNotIn(">報酬成熟狀態</th>", rendered)
        self.assertIn('position:sticky;left:0;z-index:30;box-sizing:border-box;width:8rem;min-width:8rem;max-width:8rem;background-color:#1e293b;white-space:normal', rendered)
        self.assertIn('position:sticky;left:8rem;z-index:30;box-sizing:border-box;width:6rem;min-width:6rem;max-width:6rem;background-color:#1e293b;white-space:normal', rendered)
        self.assertIn('position:sticky;left:0;z-index:20;box-sizing:border-box;width:8rem;min-width:8rem;max-width:8rem;background-color:#0f172a', rendered)
        self.assertIn('position:sticky;left:8rem;z-index:20;box-sizing:border-box;width:6rem;min-width:6rem;max-width:6rem;background-color:#0f172a', rendered)
        self.assertIn("grid-cols-1 2xl:grid-cols-2", rendered)

    def test_deployment_upload_and_live_verification_cover_full_set(self):
        workflow = (ROOT / ".github" / "workflows" / "v703-site-deploy-1100.yml").read_text(encoding="utf-8")
        self.assertIn("build/site/v70-research-charts/*", workflow)
        self.assertIn(builder.QUARTERLY_DATA, workflow)
        self.assertIn(builder.QUARTERLY_CONSENSUS, workflow)
        self.assertIn("HOSTINGER_RESEARCH_CHARTS_LIVE_PASS", workflow)
        self.assertIn('--html "系統工程/總經V70/V70-3-27.html"', workflow)


if __name__ == "__main__":
    unittest.main()

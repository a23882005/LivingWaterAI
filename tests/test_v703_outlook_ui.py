# 最後修改日期時間：2026/10/20 08:27（台灣時間）｜檔案名稱：test_v703_outlook_ui.py
"""Regression tests for V70-3-27 macro-health UI preparation.

Run: python -m unittest tests/test_v703_outlook_ui.py -v
This checks source invariants, not browser behavior or deployed output.
"""
from pathlib import Path
import re
import unittest

HTML = Path(__file__).resolve().parents[1] / "系統工程/總經V70/V70-3-27.html"


class V703OutlookUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_four_health_thresholds(self):
        s = self.source
        expected = (
            ('if (mSafe_final >= 70) zoneText = "🟢 體質良好 (≥70)"',),
            ('else if (mSafe_final >= 55) zoneText = "🟡 體質尚穩 (55–<70)"',),
            ('else if (mSafe_final >= 40) zoneText = "🟠 體質偏弱 (40–<55)"',),
            ('"🔴 體質不佳 (<40)" : "⚠ 資料不足（NA）"',),
        )
        for (fragment,) in expected:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, s)

    def test_missing_score_starts_as_na_and_four_bands_stay_visible(self):
        s = self.source
        self.assertIn('id="macro-safety-val">NA</div>', s)
        self.assertIn('id="macro-bar" style="width: 0%"', s)
        self.assertIn('id="macro-zone-text">⚠ 資料不足（NA）</div>', s)
        self.assertIn('"🔴 體質不佳 (<40)" : "⚠ 資料不足（NA）"', s)
        explainer = re.search(
            r'<div class="([^"]+)" aria-label="Macro-SaFe 體質分四段說明">',
            s,
        )
        self.assertIsNotNone(explainer)
        self.assertNotIn("hidden", explainer.group(1))
        for label in ("體質不佳｜停車", "體質偏弱｜防守", "體質尚穩｜穩健", "體質良好｜進攻"):
            with self.subTest(label=label):
                self.assertIn(label, s)

    def test_five_bank_outlook_is_display_only_and_source_scoped(self):
        s = self.source
        self.assertEqual(s.count('id="v703-wallstreet-observation"'), 1)
        self.assertEqual(s.count('id="v703-wallstreet-rows"'), 1)
        self.assertIn("華爾街五大機構 S&P 500 展望觀察", s)
        self.assertIn("公開數字／自寫摘要／來源連結；全文未授權", s)

    def test_original_data_and_risk_gates_remain(self):
        s = self.source
        self.assertEqual(s.count('id="v70-embedded-feed"'), 1)
        self.assertEqual(s.count('id="v703-wallstreet-rows"'), 1)
        self.assertIn("const mSafe_final = Math.min(mSafe_raw, capMin);", s)
        self.assertIn("v703CanPublishFormalAllocation", s)
        self.assertIn("calcAlloc(", s)

    def test_raw_data_panel_keeps_explanation_visible_when_values_are_missing(self):
        s = self.source
        self.assertIn('id="v703-raw-data-placeholder"', s)
        self.assertIn("圖表與季度／月度口徑說明仍可查看", s)
        self.assertIn("缺值維持 MISSING／NA，不補值", s)
        self.assertIn("if(entries.length===0)", s)
        self.assertIn("body.replaceChildren()", s)

    def test_raw_data_table_hides_method_column_and_keeps_source_column(self):
        s = self.source
        panel = re.search(r'<details id="v703-raw-data-panel".*?</details>', s, re.S)
        self.assertIsNotNone(panel)
        markup = panel.group(0)
        self.assertEqual(re.findall(r'<th class="p-2">([^<]+)</th>', markup), [
            "代碼／指標", "原始值", "觀測日", "狀態／口徑", "來源"
        ])
        self.assertIn('colspan="5"', markup)
        renderer = re.search(r'<script id="v703-render-raw-data">(.*?)</script>', s, re.S)
        self.assertIsNotNone(renderer)
        self.assertNotIn("r.method", renderer.group(1))
        self.assertIn("r.source", renderer.group(1))

    def test_html_document_and_unique_ids(self):
        s = self.source
        for tag in ("html", "body"):
            self.assertEqual(len(re.findall(r"<" + tag + r"\b", s, re.I)), 1)
            self.assertEqual(len(re.findall(r"</" + tag + r">", s, re.I)), 1)
        ids = re.findall(r'\bid="([^"]+)"', s)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()

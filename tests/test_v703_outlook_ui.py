# 最後修改日期：2026/11/17（台灣時間）｜檔案名稱：test_v703_outlook_ui.py｜CAP與四欄狀態的實際行為驗證
"""Regression tests for V70-3-27 macro-health UI preparation.

Run: python -m unittest tests/test_v703_outlook_ui.py -v
This checks source invariants, not browser behavior or deployed output.
"""
from pathlib import Path
import json
import re
import subprocess
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
        # Execute the approved cap calculation, including the CPI provisional
        # branch, rather than requiring the old one-line variable assignment.
        caps = re.search(r'const capMin\s*=.*?const mSafe_final\s*=.*?;', s, re.S)
        self.assertIsNotNone(caps)
        guards = re.findall(
            r'if\s*\((window\.v703CanPublishFormalAllocation\(\)\s*&&\s*Number\.isFinite\(mSafe_final\))\)', s)
        self.assertTrue(guards, 'Formal display must require both verification and a finite score')
        js = "const vm=require('node:vm'),assert=require('node:assert/strict');\n"
        js += 'const code=' + json.dumps(caps.group(0)) + ';\n'
        js += 'const guard=' + json.dumps(guards[0]) + ';\n'
        js += """
        for (const [raw,panic,crisis,recession,expected] of [
          [88,60,100,100,60],[88,100,55,100,55],
          [88,100,100,45,45],[30,60,55,45,30]]) {
          const input={mSafe_raw:raw,cap_panic:panic,cap_crisis:crisis,cap_recession:recession,provisional:false};
          const actual=vm.runInNewContext(code+';({computedFinal,mSafe_final})',input);
          assert.equal(actual.computedFinal,expected);assert.equal(actual.mSafe_final,expected);
          const provisional=vm.runInNewContext(code+';({computedFinal,mSafe_final})',{...input,provisional:true});
          assert.equal(provisional.computedFinal,expected);assert.ok(Number.isNaN(provisional.mSafe_final));
        }
        for (const [verified,score,expected] of [[true,55,true],[false,55,false],[true,NaN,false]]) {
          assert.equal(vm.runInNewContext(guard,{window:{v703CanPublishFormalAllocation:()=>verified},mSafe_final:score}),expected);
        }
        """
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("calcAlloc(", s)

    def test_raw_data_panel_keeps_explanation_visible_when_values_are_missing(self):
        s = self.source
        self.assertIn('id="v703-raw-data-placeholder"', s)
        self.assertIn("圖表與季度／月度口徑說明仍可查看", s)
        self.assertIn("缺值維持 MISSING／NA，不補值", s)
        self.assertIn("if(entries.length===0)", s)
        self.assertIn("body.replaceChildren()", s)

    def test_raw_data_table_hides_method_and_source_columns(self):
        s = self.source
        panel = re.search(r'<details id="v703-raw-data-panel".*?</details>', s, re.S)
        self.assertIsNotNone(panel)
        markup = panel.group(0)
        self.assertEqual(re.findall(r'<th class="border border-slate-700 p-2"(?: style="[^"]*")?>([^<]+)</th>', markup), [
            "指標（程式變數）", "數值", "日期", "狀態"
        ])
        self.assertIn('colspan="4"', markup)
        renderer = re.search(r'<script id="v703-render-raw-data">(.*?)</script>', s, re.S)
        self.assertIsNotNone(renderer)
        # Source/policy evidence may be used internally to determine status.
        # Verify the actual rendered four cells, not a function's parameter list
        # or a ban on the word "verification" in its implementation.
        js = "const vm=require('node:vm'),assert=require('node:assert/strict');\n"
        js += 'const renderer=' + json.dumps(renderer.group(1)) + ';\n'
        js += """
        const element=()=>({children:[],style:{},textContent:'',appendChild(e){this.children.push(e)},replaceChildren(){this.children=[]}});
        const body=element(),summary=element(),node=element(),stamp='2026-11-17T01:00:00Z';
        const evidence={source:'SOURCE_MUST_NOT_BE_A_CELL',method:'METHOD_MUST_NOT_BE_A_CELL',detail:'DETAIL_MUST_NOT_BE_A_CELL'};
        const row=(value,status)=>({...evidence,value,status,dataDate:'2026-11-16',unit:'%'});
        const feed={asOf:stamp,indicators:{m07:row(17.2,'OK'),m15:row(54.5,'STALE'),
          m19:row(null,'MISSING'),m06_rate:{...row(4.375,'OK'),policyIssues:['policy verification time']},
          m05:row(null,'OFFICIAL_UNAVAILABLE')}};
        node.textContent=JSON.stringify(feed);
        const window={};
        const ctx={window,Date,Number,JSON,Object,String,
          document:{getElementById:id=>({'v70-embedded-feed':node,'v703-raw-data-body':body,'v703-raw-data-status':summary}[id]),createElement:element},
          v703SnapshotCurrent:asOf=>asOf===stamp,v703PolicyIssues:r=>r.policyIssues||[],
          v703DateNowUTC:()=>new Date(stamp),v703ObservationStale:()=>false};
        vm.runInNewContext(renderer,ctx);
        assert.equal(body.children.length,5);
        for (const tr of body.children) {
          assert.equal(tr.children.length,4);
          for (const td of tr.children) assert.ok(!/SOURCE_MUST|METHOD_MUST|DETAIL_MUST|開啟來源|沿用人工查證/.test(td.textContent));
        }
        const status=id=>body.children.find(tr=>tr.children[0].textContent.startsWith(id+'｜')).children[3].textContent;
        assert.ok(status('m07').includes('目前：正常'));
        assert.ok(status('m15').includes('目前：過期'));
        assert.ok(status('m19').includes('目前：缺資料'));
        assert.ok(status('m06_rate').includes('目前：過期'));
        assert.ok(status('m05').includes('目前：官方資料不足'));
        assert.ok(summary.textContent.includes('上次建置：正常'));
        window.v703RenderRawData({...feed,asOf:'2020-01-01T00:00:00Z'});
        assert.ok(body.children.every(tr=>tr.children[3].textContent.includes('目前：過期（整批快照）')));
        assert.ok(summary.textContent.includes('禁止正式配置'));
        """
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_raw_data_table_shows_program_variable_names_with_full_grid(self):
        s = self.source
        self.assertTrue(s.startswith("<!DOCTYPE html>"))
        panel = re.search(r'<details id="v703-raw-data-panel".*?</details>', s, re.S)
        self.assertIsNotNone(panel)
        markup = panel.group(0)
        self.assertIn('border-collapse border border-slate-700', markup)
        self.assertGreaterEqual(markup.count('class="border border-slate-700 p-2"'), 4)
        self.assertGreaterEqual(markup.count('style="border:1px solid #475569"'), 5)
        renderer = re.search(r'<script id="v703-render-raw-data">(.*?)</script>', s, re.S)
        self.assertIsNotNone(renderer)
        self.assertIn("id+'｜'+(labels[id]||'其他指標')", renderer.group(1))
        self.assertIn("td.className='border border-slate-700 p-2'", renderer.group(1))
        self.assertIn("td.style.border='1px solid #475569'", renderer.group(1))

    def test_html_document_and_unique_ids(self):
        s = self.source
        for tag in ("html", "body"):
            self.assertEqual(len(re.findall(r"<" + tag + r"\b", s, re.I)), 1)
            self.assertEqual(len(re.findall(r"</" + tag + r">", s, re.I)), 1)
        ids = re.findall(r'\bid="([^"]+)"', s)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()

"""Real Chromium, offline HTML/PDF/reader and mock delivery acceptance.

Set W6_APPROVED_ARCHIVE to the exact approved ZIP. Missing assets skip these
browser tests explicitly; unit/contract tests do not need that private archive.
Set REPORT_HTML_EVIDENCE_DIR to retain synthetic artifacts and QA receipts.
"""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("report_browser_fixture", Path(__file__).parent / "fixtures/report_html/synthetic.py")
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)


class RenderedHTMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get("W6_APPROVED_ARCHIVE")
        if not archive:
            raise unittest.SkipTest("W6_APPROVED_ARCHIVE not supplied; real browser render not run")
        from playwright.sync_api import sync_playwright
        cls.tmp = TemporaryDirectory(prefix="synthetic-report-qa-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.folder = Path(cls.tmp.name)
        cls.current = F.current()
        cls.rendered = F.R.render_current_w6(cls.current, archive)
        partial = F.case(); partial["sections"] = {}; partial["target_context"] = None
        F.refresh(partial, scope="SOURCE_REVIEW", result=False, c7=False)
        cls.partial = F.R.render_current_w6(F.current(partial), archive)
        member=F.member_case()
        inputs=F.A.make_member_review_inputs(member["source"],member["request"],member["result"],
            source_id="SYNTHETIC_NATIVE_MEMBER_REPORT",rules_sha="e"*64)
        cls.member=F.R.render_current_w6(F.D.build_w6_current_data(member["source"],**inputs),archive)
        cls.long_current=F.current(F.long_reference_case())
        cls.long_rendered=F.R.render_current_w6(cls.long_current,archive)
        cls.db_current=F.current(F.db_review_case())
        cls.db_rendered=F.R.render_current_w6(cls.db_current,archive)
        for name, raw in cls.rendered["artifacts"].items():
            (cls.folder / name).write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(cls.rendered["artifacts"]["report.zip"])) as z:
            z.extractall(cls.folder / "unzipped")
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        cls.browser = cls.pw.chromium.launch(executable_path=shutil.which("chromium") or shutil.which("google-chrome"),
                                              headless=True, args=["--no-sandbox"])
        cls.addClassCleanup(cls.browser.close)
        cls.receipt = {"scope": "SYNTHETIC_REPORT_INCREMENT_ONLY_NOT_FINANCIAL_OR_CUSTOMER_E2E",
                       "approved_zip_sha256": sha256(Path(archive).read_bytes()).hexdigest(),
                       "client_id": cls.current["client_id"], "run_id": cls.current["run_id"],
                       "market_as_of": cls.current["market_as_of"], "page_count": cls.rendered["page_count"],
                       "chromium": cls.browser.version, "checks": {},
                       "direct_file_navigation": "NOT_VERIFIED: managed Chromium blocks file:// (ERR_BLOCKED_BY_ADMINISTRATOR); exact saved bytes loaded with set_content, no paginator injected"}
        cls.addClassCleanup(cls.save_evidence)

    @classmethod
    def save_evidence(cls):
        destination = os.environ.get("REPORT_HTML_EVIDENCE_DIR")
        if destination:
            target = Path(destination); target.mkdir(parents=True, exist_ok=True)
            for name, raw in cls.rendered["artifacts"].items(): (target / name).write_bytes(raw)
            (target / "current.synthetic.json").write_text(json.dumps(cls.current, ensure_ascii=False, indent=2), encoding="utf-8")
            (target / "render_qa.json").write_text(json.dumps(cls.receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            long_folder=target/'long_reference';long_folder.mkdir(exist_ok=True)
            for name,raw in cls.long_rendered['artifacts'].items():(long_folder/name).write_bytes(raw)
            (long_folder/'current.synthetic.json').write_text(json.dumps(cls.long_current,ensure_ascii=False,indent=2),encoding='utf-8')
            db_folder=target/'db_review';db_folder.mkdir(exist_ok=True)
            for name,raw in cls.db_rendered['artifacts'].items():(db_folder/name).write_bytes(raw)
            (db_folder/'current.synthetic.json').write_text(json.dumps(cls.db_current,ensure_ascii=False,indent=2),encoding='utf-8')

    def test_native_member_review_renders_unknown_nav_and_source_dated_holdings(self):
        page=self.context(java_script_enabled=False).new_page()
        page.set_content(self.member["artifacts"]["report.html"].decode())
        body=page.locator("body").inner_text()
        self.assertIn("UNKNOWN；尚未取得完整同輪市值",body)
        self.assertIn("來源查核時點（市值尚未核實）",body)
        self.assertIn("已記錄數量",body)
        self.assertIn("2026-10-29T20:00:00Z",body)
        self.assertIn("合成研究類別",body)
        self.assertEqual(page.locator("#toc a").count(),13)
        self.assertEqual(len(set(page.locator("[data-chapter]").evaluate_all(
            "nodes=>nodes.map(n=>n.dataset.chapter)"))),14)
        self.receipt["checks"]["partial_native_member_unknown_nav_and_original_facts"]="PASS_SYNTHETIC"

    def test_db_only_report_renders_new_current_without_claiming_native_financial_analysis(self):
        page=self.context(java_script_enabled=False).new_page()
        page.set_content(self.db_rendered['artifacts']['report.html'].decode())
        text=page.locator('body').inner_text()
        self.assertIn('已記錄數量',text)
        self.assertIn('來源查核時點（市值尚未核實）',text)
        self.assertIn('UNKNOWN；尚未取得完整同輪市值',text)
        self.assertNotIn('原逐檔分析狀態',text)
        self.assertEqual(page.locator('#toc a').count(),13)
        self.assertEqual(len(set(page.locator('[data-chapter]').evaluate_all('ns=>ns.map(n=>n.dataset.chapter)'))),14)
        lineage=json.loads(page.locator('#lineage').text_content())
        self.assertEqual(lineage['current_digest'],self.db_current['digest'])
        self.receipt['checks']['fresh_db_review_without_native_analysis']='PASS_SYNTHETIC'

    def context(self, **kwargs):
        context = self.browser.new_context(**kwargs)
        context.set_offline(True)
        self.addCleanup(context.close)
        return context

    def source_reference_geometry(self,page):
        return page.locator('.source-reference').evaluate_all("""nodes=>nodes.map(n=>{
          const card=n.closest('article'),p=n.closest('.page'),c=card.getBoundingClientRect();
          const b=p.getBoundingClientRect(),s=getComputedStyle(card),r=n.getBoundingClientRect();
          const range=document.createRange();range.selectNodeContents(n);
          const rect=x=>({left:x.left,top:x.top-b.top,right:x.right,bottom:x.bottom-b.top});
          return {text:n.textContent,page:[...document.querySelectorAll('.page')].indexOf(p),
            page_width:b.width,card_left:c.left+parseFloat(s.borderLeftWidth)+parseFloat(s.paddingLeft),
            card_right:c.right-parseFloat(s.borderRightWidth)-parseFloat(s.paddingRight),page_left:b.left,
            box:rect(r),lines:[...range.getClientRects()].map(rect),
            scroll_width:n.scrollWidth,client_width:n.clientWidth,font_size:getComputedStyle(n).fontSize};
        })""")

    def test_long_source_references_fit_cards_text_ranges_and_all_page_widths(self):
        page=self.context(java_script_enabled=False,viewport={'width':1135,'height':1600}).new_page()
        page.set_content(self.long_rendered['artifacts']['report.html'].decode())
        rows=self.source_reference_geometry(page)
        self.assertEqual(len(rows),12)  # Eight chapter sources and all four radar panels.
        for row in rows:
            self.assertEqual(row['font_size'],'18px')
            self.assertGreater(len(row['lines']),1)
            self.assertLessEqual(row['scroll_width'],row['client_width']+1)
            for r in [row['box'],*row['lines']]:
                self.assertGreaterEqual(r['left'],row['card_left']-1,row)
                self.assertLessEqual(r['right'],row['card_right']+1,row)
        widths=page.locator('.page,.content,article').evaluate_all(
            'ns=>ns.map(n=>({scroll:n.scrollWidth,client:n.clientWidth}))')
        self.assertTrue(all(r['scroll']<=r['client']+1 for r in widths),widths)
        for name,envelope in self.long_current['report_source_lineage']['sections'].items():
            texts=page.locator(f'[data-chapter="{next(k for k,v in F.R.CONTENTS.items() if v==name)}"] .source-reference').all_text_contents()
            matches=[text for text in texts if envelope['payload'][0]['source_reference'] in text]
            self.assertEqual(len(matches),1)
            text=matches[0]
            self.assertIn(envelope['as_of'],text)
            self.assertIn(envelope['scope'],text)
        self.receipt['checks']['long_reference_ranges_and_container_widths']='PASS_SYNTHETIC_12_SOURCE_CARDS'
        self.receipt['long_reference_geometry']=rows

    def test_long_source_pdf_boxes_and_all_static_pages_match_saved_pngs(self):
        import fitz
        from PIL import Image,ImageChops
        page=self.context(java_script_enabled=False,viewport={'width':1135,'height':1600},device_scale_factor=1).new_page()
        page.set_content(self.long_rendered['artifacts']['report.html'].decode());page.evaluate('document.fonts.ready')
        rows=self.source_reference_geometry(page)
        self.assertEqual(len(rows),12)
        pdf=fitz.open(stream=self.long_rendered['artifacts']['report.pdf'],filetype='pdf');self.addCleanup(pdf.close)
        self.assertEqual(len(pdf),self.long_rendered['page_count'])
        for row in rows:
            p=pdf[row['page']];scale=p.rect.width/row['page_width']
            left=(row['card_left']-row['page_left'])*scale
            right=(row['card_right']-row['page_left'])*scale
            top=row['box']['top']*scale;bottom=row['box']['bottom']*scale
            lines=[line for block in p.get_text('dict')['blocks'] if 'lines' in block for line in block['lines']
                   if top<=(line['bbox'][1]+line['bbox'][3])/2<=bottom
                   and left-1<=line['bbox'][0]<right]
            self.assertTrue(lines,row)
            for line in lines:
                x0,y0,x1,y1=line['bbox']
                self.assertGreaterEqual(x0,left-1,row)
                self.assertLessEqual(x1,right+1,row)
                self.assertGreaterEqual(x0,-1);self.assertLessEqual(x1,p.rect.width+1)
            text=''.join(span['text'] for line in lines for span in line['spans'])
            self.assertEqual(''.join(text.split()),''.join(row['text'].split()))
        qa=page.locator('.page').evaluate_all("""ns=>ns.map(p=>{const b=p.getBoundingClientRect();return {
          overflow:[...p.querySelectorAll('.part,article,.source-reference')].filter(n=>{const r=n.getBoundingClientRect();
          return r.left<b.left-1||r.right>b.right+1||r.bottom>b.bottom-70}).length};})""")
        self.assertTrue(all(r['overflow']==0 for r in qa),qa)
        with zipfile.ZipFile(io.BytesIO(self.long_rendered['artifacts']['report.zip'])) as z:
            for name in ('report.html','report.pdf','index.html'):
                self.assertEqual(z.read(name),self.long_rendered['artifacts'][name])
            for i in range(len(pdf)):
                actual=Image.open(io.BytesIO(page.locator('.page').nth(i).screenshot())).convert('RGB')
                expected=Image.open(io.BytesIO(z.read(f'pages/CR-IMG-{i+1:03d}.png'))).convert('RGB')
                self.assertIsNone(ImageChops.difference(actual,expected).getbbox(),f'long-reference physical page {i+1}')
        self.assertEqual(page.locator('#toc a').count(),13)
        self.receipt['checks']['long_reference_pdf_text_preserved_and_all_png_pages_equal']='PASS_SYNTHETIC'

    def test_saved_report_offline_without_javascript_has_all_body_pages_and_toc(self):
        page = self.context(java_script_enabled=False, viewport={"width": 1135, "height": 1600}).new_page()
        page.set_content((self.folder / "report.html").read_text(encoding="utf-8"))
        self.assertEqual(page.locator(".page").count(), self.rendered["page_count"])
        self.assertEqual(page.locator("#blocks").count(), 0)
        self.assertGreater(page.locator("main#pages .part").count(), 14)
        self.assertEqual(page.locator("#toc a").count(), 13)
        body = page.locator("body").inner_text()
        for name in F.A.SECTION_NAMES: self.assertIn("SYNTHETIC::" + name + "::完整內文。", body)
        self.assertEqual(body.count("資料日期：2026-10-01T00:00:00Z"), 8)
        self.assertIn(F.LABEL, body)
        self.assertNotIn("Joseph", body)
        lineage = json.loads(page.locator("#lineage").text_content())
        self.assertEqual(lineage["run_id"], self.current["run_id"])
        self.assertEqual(lineage["client_id"], self.current["client_id"])
        self.assertEqual(lineage["data_as_of"], self.current["market_as_of"])
        for anchor in page.locator("#toc a").all():
            self.assertEqual(page.locator(anchor.get_attribute("href")).count(), 1)
        self.receipt["checks"]["offline_static_body_14_chapters_13_toc_links"] = "PASS"

    def test_partial_source_review_renders_unknown_instead_of_empty_or_zero_chapters(self):
        page = self.context(java_script_enabled=False).new_page()
        page.set_content(self.partial["artifacts"]["report.html"].decode("utf-8"))
        chapters = page.locator("main .page").evaluate_all("xs => [...new Set(xs.map(x=>x.dataset.chapter))]")
        self.assertEqual(len(chapters), 14)
        self.assertIn("UNKNOWN；尚待核准目標來源", page.locator('[data-chapter="5"]').inner_text())
        self.assertIn("UNKNOWN；尚待正式目標及漂移來源", page.locator('[data-chapter="6"]').inner_text())
        self.assertIn("未提供正式雷達來源", page.locator('[data-chapter="9"]').inner_text())
        self.receipt["checks"]["partial_review_unknown_target_drift_radar_sections_14_chapters"] = "PASS"

    def test_pdf_page_count_identity_dates_target_and_drift_match_static_dom(self):
        import fitz
        pdf = fitz.open(stream=self.rendered["artifacts"]["report.pdf"], filetype="pdf")
        self.addCleanup(pdf.close)
        self.assertEqual(len(pdf), self.rendered["page_count"])
        text = "".join(page.get_text() for page in pdf)
        compact = "".join(text.split())
        for value in ("Arthur", self.current["run_id"], self.current["market_as_of"], "1,000.00", "300.00", "-100.00", "-200.00"):
            self.assertIn(value, compact)
        for name in F.A.SECTION_NAMES: self.assertIn("SYNTHETIC::" + name + "::", compact)
        self.assertIn("HOLD_PROTECTED", compact)
        self.assertTrue(all(abs(p.rect.width - 815.25) < 1 and abs(p.rect.height - 1152) < 1 for p in pdf))
        self.receipt["checks"]["pdf_identity_dates_values_and_page_count"] = "PASS"

    def test_each_static_page_pixels_match_zip_png_and_no_content_overflow(self):
        from PIL import Image, ImageChops
        page = self.context(java_script_enabled=False, viewport={"width": 1135, "height": 1600}, device_scale_factor=1).new_page()
        page.set_content((self.folder / "report.html").read_text(encoding="utf-8")); page.evaluate("document.fonts.ready")
        qa = page.evaluate("""() => [...document.querySelectorAll('.page')].map((p,i)=>{
          const b=p.getBoundingClientRect();
          const nodes=[...p.querySelectorAll('.part,td,th,.barrow,article,svg text')];
          return {physical_page:i+1,chapter:p.dataset.chapter||'cover',
            overflow:nodes.filter(n=>{const r=n.getBoundingClientRect();return r.right>b.right+1||r.left<b.left-1||r.bottom>b.bottom-70}).length,
            footer:p.querySelector('.num')?.textContent||null,
            background_inline:(getComputedStyle(p.querySelector('.mast,.hero')).backgroundImage.includes('data:image/jpeg'))};
        })""")
        self.assertTrue(all(x["overflow"] == 0 and x["background_inline"] for x in qa), qa)
        for i in range(self.rendered["page_count"]):
            actual = Image.open(io.BytesIO(page.locator(".page").nth(i).screenshot())).convert("RGB")
            expected = Image.open(self.folder / "unzipped/pages" / f"CR-IMG-{i+1:03d}.png").convert("RGB")
            self.assertIsNone(ImageChops.difference(actual, expected).getbbox(), f"physical page {i+1}")
            self.assertEqual(actual.size, (1087, 1536))
        self.receipt["checks"]["all_pages_static_zip_png_pixel_equal"] = "PASS"
        self.receipt["pages"] = qa

    def test_mobile_reader_standalone_fallback_toc_arrows_tap_and_multitouch(self):
        page = self.context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content((self.folder / "index.html").read_text(encoding="utf-8"))
        page.wait_for_function("baseImg.complete && baseImg.naturalWidth>0")
        self.assertTrue(page.locator("#baseImg").get_attribute("src").startswith("data:image/png;base64,"))
        self.assertEqual(page.evaluate("FILES.length"), self.rendered["page_count"])
        self.assertEqual(page.evaluate("BODY_TOTAL"), self.rendered["page_count"] - 1)
        page.locator("#next").click(); page.wait_for_function("!busy && current===1")
        self.assertEqual(page.locator(".toc-jump").count(), 13)
        link = page.locator(".toc-jump").last
        target = page.evaluate("FILES.indexOf(TOC_LINKS[TOC_LINKS.length-1].file)")
        link.click(); page.wait_for_function(f"!busy && current==={target}")
        self.assertIn("總經與機構研究", page.locator("#baseImg").get_attribute("alt"))
        page.locator("#baseImg").tap(position={"x": 180, "y": 220})
        self.assertEqual(page.evaluate("current"), target)
        page.evaluate("""() => {const s=document.getElementById('stage');
          const a=new Touch({identifier:1,target:s,clientX:120,clientY:120});
          const b=new Touch({identifier:2,target:s,clientX:220,clientY:220});
          s.dispatchEvent(new TouchEvent('touchstart',{touches:[a,b],bubbles:true}));
          s.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[a,b],bubbles:true}));} """)
        self.assertEqual(page.evaluate("current"), target)
        page.locator("#prev").click(); page.wait_for_function(f"!busy && current==={target-1}")
        self.assertEqual(errors, [])
        self.assertLessEqual(page.locator("#book").bounding_box()["width"], 390)
        self.receipt["checks"]["mobile_offline_data_uri_toc_arrows_tap_multitouch"] = "PASS"
        destination = os.environ.get("REPORT_HTML_EVIDENCE_DIR")
        if destination:
            Path(destination).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(destination) / "mobile.png"))

    def test_zip_same_folder_reader_pngs_pdf_and_full_html_are_identical(self):
        context = self.context(viewport={"width": 1280, "height": 900})
        def local_asset(route):
            relative = route.request.url.split("https://synthetic-report.invalid/", 1)[-1]
            path = self.folder / "unzipped" / relative
            if path.is_file():
                route.fulfill(path=path, content_type="image/png" if path.suffix==".png" else "text/html")
            else:
                route.abort()
        context.route("https://synthetic-report.invalid/**", local_asset)
        page = context.new_page()
        page.goto("https://synthetic-report.invalid/index.html")
        page.wait_for_function("baseImg.complete && baseImg.naturalWidth>0")
        self.assertTrue(page.locator("#baseImg").get_attribute("src").startswith("pages/"))
        self.assertEqual((self.folder / "unzipped/report.html").read_bytes(), self.rendered["artifacts"]["report.html"])
        self.assertEqual((self.folder / "unzipped/report.pdf").read_bytes(), self.rendered["artifacts"]["report.pdf"])
        self.receipt["checks"]["zip_same_folder_png_fallback_and_html_pdf_bytes"] = "PASS_LOCAL_ASSET_ROUTE_NO_NETWORK"

    def test_full_chain_to_staging_and_mock_receipts_readbacks(self):
        delivery = F.load("report_browser_delivery", "on_demand_report_delivery.py")
        adapter = F.load("report_browser_ondemand", "on_demand_w6.py")
        c = F.case()
        wrapped = adapter.OnDemandW6Renderer(lambda source, options: {"market": c["market"], "engine": c["engine"]},
            lambda current: self.rendered if current["digest"] == self.current["digest"] else None)
        output = wrapped(c["source"], {})
        stage = self.folder / "stage"; stage.mkdir()
        plan = delivery.prepare_report_delivery(output, account="AR", client_id=F.CLIENT,
            folder_id="SYNTHETIC_REPORT_FOLDER", output_dir=stage,
            created_at=datetime(2026, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(plan["status"], "STAGED_NOT_PERSISTED")
        receipts, remote = [], {}
        for i, row in enumerate(plan["uploads"]):
            file_id = "SYNTHETIC_MOCK_FILE_" + str(i)
            receipts.append({"success": True, "id": file_id, "name": row["name"], "parent_id": "SYNTHETIC_REPORT_FOLDER"})
            remote[file_id] = Path(row["path"]).read_bytes()
        manifest = delivery.prepare_verified_manifest(plan, receipts, remote)
        self.assertEqual(manifest["status"], "ARTIFACTS_REMOTE_VERIFIED__MANIFEST_PENDING")
        result = delivery.verify_published_manifest(manifest,
            {"success": True, "name": manifest["manifest_filename"], "id": "SYNTHETIC_MANIFEST",
             "parent_id": "SYNTHETIC_REPORT_FOLDER"}, manifest["manifest_bytes"])
        self.assertEqual(result["status"], "PERSISTED_REMOTE_VERIFIED")
        self.assertEqual(result["manifest_sha256"], sha256(manifest["manifest_bytes"]).hexdigest())
        self.receipt["checks"]["canonical_current_render_staging_mock_receipts_readbacks"] = "PASS_MOCK_ONLY_NO_DRIVE_WRITE"


if __name__ == "__main__": unittest.main()

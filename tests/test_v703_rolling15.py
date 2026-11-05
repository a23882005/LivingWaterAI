"""15 calendar-day history: audit selection, gaps, live gates, and mobile layout."""
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.v703_rolling_history import history_payload, embed_history, observation_summary, SCHEMA

HTML = ROOT / '系統工程/總經V70/V70-3-27.html'


class ArchiveTests(unittest.TestCase):
    def test_daily_selection_is_chronological_and_excludes_unqualified_rows(self):
        fields = ['observation_date', 'health_score', 'score_status', 'feed_asof_utc',
                  'run_timestamp_utc', 'daily_record_id', 'source_commit', 'v70_version', 'neutral_imputed_items']
        def row(date, hour, score, status='FORMAL_VALID'):
            return dict(zip(fields, [date, score, status, f'{date}T{hour}:00:00Z',
                                     f'{date}T{hour}:05:00Z', hour+str(score), 'abc', 'v1', '']))
        rows = [row('2026-11-04', '04', '60'), row('2026-11-04', '03', '50'),
                row('2026-11-05', '03', '99', 'DEMO'), row('2026-11-05', '04', 'nan'),
                row('2026-11-06', '03', '70'), row('2026-08-01', '03', '70'),
                row('2026-11-05', '05', '101'), row('2026-11-05', '06', '62')]
        # UTC 18:00 belongs to the next Taipei date; reject mislabeled dates.
        rows.append(row('2026-11-05', '18', '90'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'archive.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader(); writer.writerows(rows)
            before = path.read_bytes()
            payload = history_payload(path, dt.date(2026, 11, 5))
            self.assertEqual([(r['date'], r['score']) for r in payload['rows']],
                             [('2026-11-04', 60), ('2026-11-05', 62)])
            self.assertEqual(payload['archiveThrough'], '2026-11-05')
            self.assertEqual(path.read_bytes(), before)

    def test_empty_archive_and_safe_embedding(self):
        with tempfile.TemporaryDirectory() as temp:
            payload = history_payload(Path(temp)/'absent.csv')
            self.assertEqual(payload['rows'], [])
            markup = '<script id="v703-daily-history" type="application/json">{}</script>'
            payload['note'] = '</script><script>alert(1)</script>'
            encoded = embed_history(markup, payload)
            self.assertEqual(encoded.count('</script>'), 1)
            self.assertIn('\\u003c/script>', encoded)

    def test_builder_refreshes_archive_in_the_deploy_artifact(self):
        # Exercise the builder's actual embedding call with the current archive.
        from scripts import build_daily_v703_site as builder
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(builder, 'embed_history', wraps=embed_history) as embed:
                builder.build(ROOT/'data/18_macro_verification.json', ROOT/'data/8_macro_supplement_verified.json', HTML, temp)
            self.assertEqual(embed.call_count, 1)
            built = (Path(temp)/'index.html').read_text()
            payload = json.loads(re.search(r'<script id="v703-daily-history" type="application/json">(.*?)</script>', built, re.S)[1])
            self.assertEqual(payload, history_payload())
            qa = json.loads((Path(temp)/'QA.json').read_text())
            self.assertEqual(qa['rolling15'], observation_summary(payload))

    def test_action_summary_counts_missing_calendar_dates(self):
        payload = {'rows':[{'date':'2026-10-21'}, {'date':'2026-11-04'}, {'date':'2026-11-05'}],
                   'archiveThrough':'2026-11-05'}
        summary = observation_summary(payload, dt.date(2026, 11, 5))
        self.assertEqual(summary['windowStart'], '2026-10-22')
        self.assertEqual(summary['validArchivedDays'], 2)
        self.assertEqual(len(summary['missingDates']), 13)
        self.assertNotIn('2026-10-21', summary['missingDates'])


@unittest.skipIf(os.environ.get('V703_SKIP_BROWSER') == '1', 'Archive-only deploy checks; browser cases run in regression job')
class RollingBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.driver.stop()

    def open_panel(self, payload=None, now='2026-11-05T04:00:00Z', mobile=False):
        context = self.browser.new_context(viewport={'width':390 if mobile else 1200,'height':900}, timezone_id='Asia/Taipei')
        self.addCleanup(context.close)
        page = context.new_page()
        page.clock.install(time=dt.datetime.fromisoformat(now.replace('Z', '+00:00')))
        source = HTML.read_text()
        panel = source[source.index('<!-- 2026/11/05｜15日'):source.index('<section id="v703-family-profile"')]
        if payload is not None: panel = embed_history(panel, payload)
        page.set_content('<!DOCTYPE html><html><body>'+panel+'</body></html>')
        page.wait_for_function('window.v703Rolling15?.state')
        return page

    @staticmethod
    def payload(dates_scores):
        return {'schema':SCHEMA, 'archiveThrough':'2026-11-05', 'rows':[
            {'date':date,'score':score,'version':'v1','feedAsOf':date+'T03:00:00Z','kind':'archive'}
            for date, score in dates_scores]}

    def test_window_gaps_daily_deltas_and_threshold_boundaries(self):
        page = self.open_panel(self.payload([('2026-10-21',99),('2026-10-22',65),('2026-11-03',61),('2026-11-04',58),('2026-11-05',52)]))
        state = page.evaluate('window.v703Rolling15.state')
        self.assertEqual(len(state['rows']),15)
        self.assertEqual(state['rows'][0]['date'],'2026-10-22')
        self.assertEqual(state['available'],4)
        self.assertIsNone(state['rows'][12]['delta'])
        self.assertEqual(state['latest']['delta'],-6)
        self.assertEqual(state['declines'],2)
        self.assertEqual(state['net'],-13)
        self.assertEqual(page.locator('.r15-segment').count(),2)
        levels=page.evaluate('[0,1,1.01,3,3.01,5,5.01,-6,null].map(window.v703Rolling15.classify)')
        self.assertEqual(levels,['一般波動','一般波動','值得觀察','值得觀察','明顯變化，檢查原因','明顯變化，檢查原因','重大變化，優先調查','重大變化，優先調查','NA｜無相鄰日資料'])

    def test_live_only_accepts_current_verified_non_demo_score(self):
        page = self.open_panel(self.payload([('2026-11-04',58)]))
        page.evaluate("""() => {
          window.v703Latest={macroSafety:54,ruleVersion:'v1',dataValidation:{allMacroValuesPresent:true,allDatesAndSourcesValid:true}};
          window.v703SourceBatch={asOf:'2026-11-05T04:00:00Z'};
          window.v703FeedVerified=true;window.v703CanPublishFormalAllocation=()=>true;
          window.v703Rolling15.render();
        }""")
        self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.kind'),'current')
        self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.delta'),-4)
        for code in ['window.v703DemoMode=true',
                     'window.v703DemoMode=false;window.v703CanPublishFormalAllocation=()=>false',
                     "window.v703CanPublishFormalAllocation=()=>true;window.v703SourceBatch.asOf='2026-11-04T04:00:00Z'",
                     "window.v703SourceBatch.asOf='2026-11-05T04:00:00Z';window.v703Latest.syntheticInputs=true"]:
            page.evaluate(code+';window.v703Rolling15.render()')
            self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.date'),'2026-11-04')

    def test_midnight_rolls_by_taipei_date_without_reload(self):
        page = self.open_panel(self.payload([('2026-10-22',65),('2026-11-05',58)]),now='2026-11-05T15:59:30Z')
        page.clock.run_for(60000)
        state=page.evaluate('window.v703Rolling15.state')
        self.assertEqual(state['rows'][0]['date'],'2026-10-23')
        self.assertEqual(state['rows'][-1]['date'],'2026-11-06')
        self.assertEqual(state['available'],1)
        self.assertIn('今日尚無合格紀錄',page.locator('#r15-status').inner_text())

    def test_empty_and_version_changes_have_no_fabricated_trends(self):
        page=self.open_panel({'schema':SCHEMA,'rows':[]})
        self.assertEqual(page.locator('#r15-chart circle').count(),0)
        self.assertIn('尚無合格紀錄',page.locator('#r15-status').inner_text())
        data=self.payload([('2026-11-04',58),('2026-11-05',52)])
        data['rows'][-1]['version']='v2'
        page=self.open_panel(data)
        state=page.evaluate('window.v703Rolling15.state')
        self.assertIsNone(state['latest']['delta']); self.assertIsNone(state['net'])
        self.assertEqual(page.locator('.r15-segment').count(),0)

    def test_mobile_scroll_and_accessible_daily_details(self):
        page=self.open_panel(self.payload([('2026-11-04',58),('2026-11-05',62)]),mobile=True)
        self.assertEqual(page.locator('#r15-rows tr').count(),15)
        self.assertEqual(page.locator('#r15-reference-rows tr').count(),4)
        self.assertTrue(page.evaluate('document.querySelector("#r15-chart").parentElement.scrollWidth>document.querySelector("#r15-chart").parentElement.clientWidth'))
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
        self.assertEqual(page.locator('#r15-chart circle[aria-label]').count(),2)

    def test_full_dashboard_uses_original_verified_score(self):
        from v703_browser_fixture import feed, NOW
        data=feed()
        context=self.browser.new_context(timezone_id='Asia/Taipei')
        self.addCleanup(context.close)
        page=context.new_page();page.clock.install(time=NOW)
        markup=re.sub(r'(<script id="v70-embedded-feed" type="application/json">).*?(</script>)',lambda m:m[1]+json.dumps(data)+m[2],HTML.read_text(),count=1,flags=re.S)
        markup=embed_history(markup,{'schema':SCHEMA,'rows':[]})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url=='http://rolling.test/':r.fulfill(content_type='text/html',body=markup)
            elif r.request.url=='http://rolling.test/V70_macro_latest.json':r.fulfill(json=data)
            else:r.abort()
        page.route('**/*',route)
        page.goto('http://rolling.test/',wait_until='domcontentloaded')
        page.wait_for_function('window.v703Rolling15.state.latest?.kind==="current"')
        self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.score'),page.evaluate('window.v703Latest.macroSafety'))
        self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()

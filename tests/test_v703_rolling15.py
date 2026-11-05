"""NYSE sessions, holiday/time-zone mapping, continuous curves and live gates."""
import csv
import copy
import datetime as dt
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.v703_rolling_history import history_payload, embed_history, observation_summary, session_date, SCHEMA
HTML = ROOT / '系統工程/總經V70/V70-3-27.html'
NOW = dt.datetime.fromisoformat('2026-11-05T04:00:00+00:00')


def empty_payload(now=NOW):
    return copy.deepcopy(history_payload(ROOT/'tests/nonexistent-daily-archive.csv', now=now))


def fixture(dates_scores, now=NOW):
    payload = empty_payload(now)
    for date, score in dates_scores:
        feed = date+'T22:00:00Z'  # After the session's regular close, including DST.
        observed = dt.datetime.fromisoformat(feed.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()
        payload['rows'].append({'date':date,'snapshotDateTaipei':observed,'score':score,
                               'version':'v1','feedAsOf':feed,'kind':'archive'})
    payload['archiveThrough'] = max((r['date'] for r in payload['rows']), default=None)
    return payload


class ArchiveTests(unittest.TestCase):
    def test_selection_maps_latest_snapshot_to_completed_session_without_mutating_archive(self):
        fields = ['observation_date','health_score','score_status','feed_asof_utc','run_timestamp_utc',
                  'daily_record_id','source_commit','v70_version','neutral_imputed_items']
        def row(date, hour, score, status='FORMAL_VALID'):
            return dict(zip(fields,[date,score,status,f'{date}T{hour}:00:00Z',f'{date}T{hour}:05:00Z',date+hour+str(score),'abc','v1','']))
        rows=[row('2026-10-31','03','59'),row('2026-11-01','03','60'),row('2026-11-02','03','61'),
              row('2026-11-04','04','58'),row('2026-11-04','03','50'),row('2026-11-05','03','99','DEMO'),
              row('2026-11-05','04','nan'),row('2026-11-06','03','70'),row('2026-11-05','02','62')]
        # UTC18 belongs to the next Taipei date and must not inherit a wrong archive label.
        rows.append(row('2026-11-05','18','90'))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'archive.csv'
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            before=path.read_bytes();payload=history_payload(path,now=NOW)
            self.assertEqual([(r['date'],r['score']) for r in payload['rows']],
                             [('2026-10-30',61),('2026-11-03',58),('2026-11-04',62)])
            self.assertEqual(payload['rows'][0]['snapshotDateTaipei'],'2026-11-02')
            self.assertEqual(path.read_bytes(),before)

    def test_calendar_excludes_exchange_holidays_and_knows_early_close_and_dst(self):
        payload=empty_payload(dt.datetime.fromisoformat('2026-07-06T22:00:00+00:00'))
        dates={r['date'] for r in payload['calendar']['sessions']}
        for closed in ['2026-04-03','2026-06-19','2026-07-03','2026-11-26','2026-12-25']:
            self.assertNotIn(closed,dates)
        calendar=payload['calendar']
        self.assertEqual(session_date(calendar,dt.datetime.fromisoformat('2026-11-27T17:59:59+00:00')),'2026-11-25')
        self.assertEqual(session_date(calendar,dt.datetime.fromisoformat('2026-11-27T18:00:00+00:00')),'2026-11-27')
        closes={r['date']:r['closeUtc'] for r in calendar['sessions']}
        self.assertEqual(closes['2026-10-30'],'2026-10-30T20:00:00Z')
        self.assertEqual(closes['2026-11-02'],'2026-11-02T21:00:00Z')

    def test_empty_archive_and_safe_embedding(self):
        payload=empty_payload();self.assertEqual(payload['rows'],[])
        payload['note']='</script><script>alert(1)</script>'
        result=embed_history('<script id="v703-daily-history" type="application/json">{}</script>',payload)
        self.assertEqual(result.count('</script>'),1);self.assertIn('\\u003c/script>',result)

    def test_builder_refreshes_calendar_history_and_qa_together(self):
        from scripts import build_daily_v703_site as builder
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(builder,'embed_history',wraps=embed_history) as embed:
                builder.build(ROOT/'data/18_macro_verification.json',ROOT/'data/8_macro_supplement_verified.json',HTML,temp)
            self.assertEqual(embed.call_count,1)
            built=(Path(temp)/'index.html').read_text()
            payload=json.loads(re.search(r'<script id="v703-daily-history" type="application/json">(.*?)</script>',built,re.S)[1])
            self.assertEqual(payload,history_payload())
            self.assertEqual(json.loads((Path(temp)/'QA.json').read_text())['rolling15'],observation_summary(payload))

    def test_summary_counts_only_fifteen_completed_trading_sessions(self):
        payload=fixture([('2026-10-14',65),('2026-11-03',58),('2026-11-04',62)])
        summary=observation_summary(payload,now=NOW)
        self.assertEqual(summary['windowStart'],'2026-10-15')
        self.assertEqual(summary['windowEnd'],'2026-11-04')
        self.assertEqual(summary['tradingDays'],15)
        self.assertEqual(summary['validArchivedDays'],2)
        self.assertEqual(len(summary['missingDates']),13)
        self.assertNotIn('2026-11-01',summary['missingDates'])
        self.assertNotIn('2026-10-31',summary['sessionDates'])


@unittest.skipIf(os.environ.get('V703_SKIP_BROWSER')=='1','Archive-only deploy checks; Chromium cases run in regression job')
class RollingBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.driver=sync_playwright().start();cls.browser=cls.driver.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.driver.stop()

    def open_panel(self,payload=None,now=NOW,mobile=False):
        context=self.browser.new_context(viewport={'width':390 if mobile else 1200,'height':900},timezone_id='Asia/Taipei')
        self.addCleanup(context.close);page=context.new_page();page.clock.install(time=now)
        source=HTML.read_text();panel=source[source.index('<!-- 2026/11/05｜15日'):source.index('<section id="v703-family-profile"')]
        if payload is not None:panel=embed_history(panel,payload)
        page.set_content('<!DOCTYPE html><html><body>'+panel+'</body></html>')
        page.wait_for_function('window.v703Rolling15?.state');return page

    def test_window_filters_missing_points_but_curve_is_always_connected(self):
        page=self.open_panel(fixture([('2026-10-14',99),('2026-10-15',65),('2026-11-02',61),('2026-11-03',58),('2026-11-04',52)]))
        state=page.evaluate('window.v703Rolling15.state')
        self.assertEqual(len(state['rows']),15);self.assertEqual(state['available'],4)
        self.assertIsNone(state['points'][1]['delta']) # An actually missing open session is not a holiday.
        self.assertEqual(state['latest']['delta'],-6);self.assertEqual(state['declines'],2);self.assertEqual(state['net'],-13)
        self.assertEqual(page.locator('.r15-segment').count(),3)
        self.assertEqual(page.locator('#r15-chart circle').count(),4)
        self.assertEqual(page.locator('#r15-chart text').filter(has_text='NA').count(),0)
        self.assertEqual(page.locator('#r15-rows tr').count(),4)
        self.assertIn('開市但缺合格分數',page.locator('#r15-status').inner_text())
        levels=page.evaluate('[0,1,1.01,3,3.01,5,5.01,-6,null].map(window.v703Rolling15.classify)')
        self.assertEqual(levels,['一般波動','一般波動','值得觀察','值得觀察','明顯變化，檢查原因','明顯變化，檢查原因','重大變化，優先調查','重大變化，優先調查','NA｜缺前一交易日合格分數'])

    def test_friday_to_monday_is_one_trading_change_not_a_gap(self):
        page=self.open_panel(fixture([('2026-10-30',60),('2026-11-02',58),('2026-11-03',56)]))
        state=page.evaluate('window.v703Rolling15.state')
        self.assertEqual([r['date'] for r in state['points']],['2026-10-30','2026-11-02','2026-11-03'])
        self.assertEqual([r['delta'] for r in state['points']],[None,-2,-2])
        self.assertEqual(state['declines'],2);self.assertEqual(page.locator('.r15-segment').count(),2)
        self.assertNotIn('2026-11-01',page.locator('#r15-rows').inner_text())

    def test_good_friday_holiday_is_skipped_and_curve_stays_connected(self):
        now=dt.datetime.fromisoformat('2026-04-06T22:30:00+00:00')
        page=self.open_panel(fixture([('2026-04-02',60),('2026-04-06',58)],now),now=now)
        state=page.evaluate('window.v703Rolling15.state')
        self.assertNotIn('2026-04-03',[r['date'] for r in state['rows']])
        self.assertEqual(state['latest']['delta'],-2);self.assertEqual(page.locator('.r15-segment').count(),1)

    def test_live_gates_and_taipei_snapshot_to_us_session(self):
        page=self.open_panel(fixture([('2026-11-03',58)]))
        page.evaluate("""() => {
          window.v703Latest={macroSafety:54,ruleVersion:'v1',dataValidation:{allMacroValuesPresent:true,allDatesAndSourcesValid:true}};
          window.v703SourceBatch={asOf:'2026-11-05T04:00:00Z'};
          window.v703FeedVerified=true;window.v703CanPublishFormalAllocation=()=>true;window.v703Rolling15.render();
        }""")
        current=page.evaluate('window.v703Rolling15.state.latest')
        self.assertEqual(current['date'],'2026-11-04');self.assertEqual(current['snapshotDateTaipei'],'2026-11-05')
        self.assertEqual(current['delta'],-4)
        for code in ['window.v703DemoMode=true','window.v703DemoMode=false;window.v703CanPublishFormalAllocation=()=>false',
                     "window.v703CanPublishFormalAllocation=()=>true;window.v703SourceBatch.asOf='2026-11-04T04:00:00Z'",
                     "window.v703SourceBatch.asOf='2026-11-05T04:00:00Z';window.v703Latest.syntheticInputs=true"]:
            page.evaluate(code+';window.v703Rolling15.render()')
            self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.date'),'2026-11-03')

    def test_rolls_at_us_close_instead_of_taipei_midnight(self):
        payload=fixture([('2026-11-03',58),('2026-11-04',62)])
        for now,expected in [('2026-11-05T15:59:30+00:00','2026-11-04'),('2026-11-05T20:59:30+00:00','2026-11-05')]:
            with self.subTest(now=now):
                page=self.open_panel(payload,now=dt.datetime.fromisoformat(now));page.clock.run_for(60000)
                state=page.evaluate('window.v703Rolling15.state');self.assertEqual(state['windowEnd'],expected)
                self.assertEqual(page.locator('.r15-segment').count(),1)

    def test_version_change_does_not_break_curve_or_compute_cross_version_delta(self):
        payload=fixture([('2026-11-03',58),('2026-11-04',52)]);payload['rows'][-1]['version']='v2'
        page=self.open_panel(payload);state=page.evaluate('window.v703Rolling15.state')
        self.assertIsNone(state['latest']['delta']);self.assertIsNone(state['net'])
        self.assertEqual(page.locator('.r15-segment').count(),1)
        self.assertIn('跨版本連線僅供看圖',page.locator('#r15-status').inner_text())

    def test_empty_history_and_calendar_expiry_are_explicit(self):
        page=self.open_panel(empty_payload());self.assertEqual(page.locator('#r15-chart circle').count(),0)
        self.assertIn('尚無合格分數',page.locator('#r15-status').inner_text())
        payload=fixture([('2026-11-04',62)]);payload['calendar']['coverageEnd']='2026-10-01'
        page=self.open_panel(payload);self.assertIn('交易日曆已超過',page.locator('#r15-status').inner_text())

    def test_mobile_has_only_effective_rows_and_accessible_continuous_points(self):
        page=self.open_panel(fixture([('2026-11-03',58),('2026-11-04',62)]),mobile=True)
        self.assertEqual(page.locator('#r15-rows tr').count(),2);self.assertEqual(page.locator('#r15-reference-rows tr').count(),4)
        rounded=self.open_panel(fixture([('2026-11-04',62.745)]))
        self.assertIn('62.75',rounded.locator('#r15-stats').inner_text())
        self.assertTrue(page.evaluate('document.querySelector("#r15-chart").parentElement.scrollWidth<=document.querySelector("#r15-chart").parentElement.clientWidth'))
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
        page.locator('#r15-chart circle').last.focus();self.assertIn('台灣快照 2026-11-05',page.locator('#r15-point').inner_text())

    def test_fifteen_points_fit_phone_and_resize_without_scrolling(self):
        from scripts.v703_rolling_history import observation_summary
        days=observation_summary(empty_payload(),now=NOW)['sessionDates']
        page=self.open_panel(fixture([(day,50+i%5) for i,day in enumerate(days)]),mobile=True)
        self.assertEqual(page.locator('#r15-chart circle').count(),15)
        self.assertEqual(page.locator('#r15-chart path.r15-segment').count(),14)
        self.assertEqual(page.locator('#r15-chart .r15-date').count(),15)
        for width in [320,390,768]:
            page.set_viewport_size({'width':width,'height':900})
            page.wait_for_function('Math.abs(document.querySelector("#r15-chart").viewBox.baseVal.width-document.querySelector("#r15-chart").parentElement.clientWidth)<1')
            boxes=page.evaluate("""() => {const svg=document.querySelector('#r15-chart');return {svg:svg.getBoundingClientRect().toJSON(),dots:[...svg.querySelectorAll('circle')].map(e=>e.getBoundingClientRect().toJSON()),overflow:svg.parentElement.scrollWidth>svg.parentElement.clientWidth}}""")
            self.assertFalse(boxes['overflow'])
            for dot in boxes['dots']:
                self.assertGreaterEqual(dot['left'],boxes['svg']['left'])
                self.assertLessEqual(dot['right'],boxes['svg']['right'])
        page.locator('#r15-chart').click(position={'x':100,'y':50})
        self.assertIn('美股交易日',page.locator('#r15-point').inner_text())

    def test_smooth_curve_passes_through_points_and_stays_within_adjacent_values(self):
        page=self.open_panel(empty_payload())
        for values in [[50,55,53,62,62,58],[0,100,0,100],[30,30,30],[80,70,20,19]]:
            segments=page.evaluate('(values)=>window.v703Rolling15.smoothSegments(values.map((y,i)=>({x:i*20,y})))',values)
            self.assertEqual(len(segments),len(values)-1)
            for i,s in enumerate(segments):
                self.assertEqual(s['start']['y'],values[i]);self.assertEqual(s['end']['y'],values[i+1])
                for j in range(101):
                    t=j/100;value=(1-t)**3*s['start']['y']+3*(1-t)**2*t*s['c1']['y']+3*(1-t)*t*t*s['c2']['y']+t**3*s['end']['y']
                    self.assertGreaterEqual(value,min(values[i:i+2])-1e-8)
                    self.assertLessEqual(value,max(values[i:i+2])+1e-8)
                if i:
                    previous=segments[i-1]
                    left=(previous['end']['y']-previous['c2']['y'])/(previous['end']['x']-previous['c2']['x'])
                    right=(s['c1']['y']-s['start']['y'])/(s['c1']['x']-s['start']['x'])
                    self.assertAlmostEqual(left,right,places=10)

    def test_full_dashboard_keeps_original_verified_score(self):
        from v703_browser_fixture import feed,NOW as fixture_now
        data=feed();context=self.browser.new_context(timezone_id='Asia/Taipei');self.addCleanup(context.close)
        page=context.new_page();page.clock.install(time=fixture_now)
        markup=re.sub(r'(<script id="v70-embedded-feed" type="application/json">).*?(</script>)',lambda m:m[1]+json.dumps(data)+m[2],HTML.read_text(),count=1,flags=re.S)
        markup=embed_history(markup,empty_payload(fixture_now));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url=='http://rolling.test/':r.fulfill(content_type='text/html',body=markup)
            elif r.request.url=='http://rolling.test/V70_macro_latest.json':r.fulfill(json=data)
            else:r.abort()
        page.route('**/*',route);page.goto('http://rolling.test/',wait_until='domcontentloaded')
        page.wait_for_function('window.v703Rolling15.state.latest?.kind==="current"')
        self.assertEqual(page.evaluate('window.v703Rolling15.state.latest.score'),page.evaluate('window.v703Latest.macroSafety'))
        self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()

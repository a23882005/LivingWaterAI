"""Historical snapshot and fail-closed loader regression in the existing browser job."""
import copy
import datetime as dt
import json
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright
from v703_browser_fixture import HTML, NOW, feed

FIXTURES = Path(__file__).parent / 'fixtures'
STALE_NOW = dt.datetime.fromisoformat('2026-10-24T09:03:00+08:00')


class SnapshotBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def open_feed(self, data, now, embedded=None, offline=False):
        context = self.browser.new_context(locale='zh-TW', timezone_id='Asia/Taipei')
        self.addCleanup(context.close)
        page = context.new_page()
        page.clock.install(time=now)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        html = re.sub(r'(<script id="v70-embedded-feed" type="application/json">).*?(</script>)',
                      lambda m: m[1] + json.dumps(data if embedded is None else embedded) + m[2],
                      HTML.read_text(), count=1, flags=re.S)

        def route(r):
            if r.request.url == 'http://snapshot.test/':
                r.fulfill(content_type='text/html', body=html)
            elif r.request.url == 'http://snapshot.test/V70_macro_latest.json' and not offline:
                r.fulfill(json=data)
            else:
                r.abort()

        page.route('**/*', route)
        page.goto('http://snapshot.test/', wait_until='domcontentloaded')
        page.wait_for_function("!document.querySelector('#family-data-status').textContent.includes('正在讀取')")
        self.assertEqual(errors, [])
        return page

    def state(self, page):
        return page.evaluate("""() => ({
            formal:window.v703CanPublishFormalAllocation(),verified:window.v703FeedVerified,
            issues:window.v703DateIssues,raw:document.querySelector('#v703-raw-data-status').textContent,
            policy:window.v703VerifiedInputSnapshot?.m06_rate,
            pe:window.v703PEReferenceVerified,calendar:window.v703MonthlyReleaseCalendar,
            rows:[...document.querySelectorAll('#v703-raw-data-body tr')].map(x=>x.textContent)
        })""")

    def test_real_expired_snapshot_retains_evidence_online_and_standalone(self):
        data = json.loads((FIXTURES / 'v703_20261022_snapshot.json').read_text())
        self.assertEqual(data['asOf'], '2026-10-22T10:30:55.784753Z')
        for offline in (False, True):
            with self.subTest(offline=offline):
                page = self.open_feed(data, STALE_NOW, offline=offline)
                result = self.state(page)
                self.assertFalse(result['formal'])
                self.assertFalse(result['verified'])
                self.assertIn('歷史快照', result['raw'])
                self.assertIn('非獨立計分指標數', result['raw'])
                self.assertTrue(all('目前：過期（整批快照）' in row for row in result['rows']))
                self.assertTrue(any('整批快照過期' in issue for issue in result['issues']))
                self.assertTrue(all(result['pe'][key] for key in ('m03_qqq', 'm03_spy', 'm03_vt')))
                for key in ('m04', 'm05', 'm15', 'm18', 'm19', 'm20'):
                    self.assertIn(key, result['calendar'])
                    self.assertFalse(any(issue.startswith(key + ':') for issue in result['issues']), result['issues'])
                self.assertEqual(result['policy'], data['indicators']['m06_rate'])
                self.assertIn('m06_rate:policy verification time', result['issues'])
                self.assertFalse(any('target bounds' in issue or 'missing policy evidence' in issue for issue in result['issues']))

    def test_failed_sibling_keeps_its_own_evidence_instead_of_embedded(self):
        data = json.loads((FIXTURES / 'v703_20261022_snapshot.json').read_text())
        embedded = copy.deepcopy(data)
        embedded['indicators']['m06_rate'].pop('lowerBound')
        embedded['indicators']['m03_qqq'].pop('sourceEvidence')
        result = self.state(self.open_feed(data, STALE_NOW, embedded=embedded))
        self.assertEqual(result['policy'], data['indicators']['m06_rate'])
        self.assertTrue(result['pe']['m03_qqq'])

    def test_fresh_complete_and_invalid_evidence_dates_and_values(self):
        valid = feed()
        page = self.open_feed(valid, NOW)
        result = self.state(page)
        self.assertTrue(result['verified'])
        self.assertTrue(result['formal'], result['issues'])
        self.assertEqual(result['issues'], [])
        for key, value in [('in_m03_qqq', '99'), ('v703-date-m05', '2026-10-23')]:
            with self.subTest(manual=key):
                page = self.open_feed(valid, NOW)
                page.locator('#' + key).evaluate('(e,v)=>e.value=v', value)
                self.assertFalse(self.state(page)['formal'])
        for fault in ('pe_evidence', 'policy_evidence', 'policy_time', 'invalid_date', 'changed_value', 'expired_pe'):
            with self.subTest(fault=fault):
                data = copy.deepcopy(valid)
                rows = data['indicators']
                if fault == 'pe_evidence':
                    rows['m03_qqq'].pop('sourceEvidence')
                elif fault == 'policy_evidence':
                    rows['m06_rate'].pop('sourceEvidence')
                elif fault == 'policy_time':
                    rows['m06_rate']['lastVerifiedAt'] = '2026-10-20T00:00:00Z'
                elif fault == 'invalid_date':
                    rows['m05']['dataDate'] = '2026-02-30'
                elif fault == 'changed_value':
                    rows['m03_qqq']['value'] += 1
                else:
                    rows['m03_qqq']['lastVerifiedAt'] = '2026-10-01T00:00:00Z'
                result = self.state(self.open_feed(data, NOW))
                self.assertFalse(result['verified'])
                self.assertFalse(result['formal'])
                self.assertTrue(result['issues'])
                if fault == 'expired_pe':
                    self.assertIn('m03_qqq:ETF本益比核實時間過期（超過7天）', result['issues'])


class SahmUsageBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    open_feed = SnapshotBrowserTests.open_feed

    def test_fred_api_notice_and_both_terms_links_are_visible(self):
        page = self.open_feed(feed(), NOW)
        notice = page.locator('#v703-fred-api-notice')
        self.assertTrue(notice.is_visible())
        self.assertIn('not endorsed or certified by the Federal Reserve Bank of St. Louis.', notice.inner_text())
        self.assertIn('即表示同意受', notice.inner_text())
        self.assertEqual(set(notice.locator('a').evaluate_all('(xs)=>xs.map(x=>x.href)')), {
            'https://fred.stlouisfed.org/docs/api/terms_of_use.html',
            'https://fred.stlouisfed.org/legal/terms/',
        })

    def test_sahm_markdown_and_json_download_preserve_values_and_incomplete_reasons(self):
        data = feed()
        data['indicators']['m18'].update(value=0, unit='',
            method='Official FRED Sahm Rule Recession Indicator (real-time vintage), published series')
        page = self.open_feed(data, NOW)
        original = page.evaluate('JSON.parse(JSON.stringify(window.v703Latest))')
        incomplete = page.evaluate('window.getLivingWaterV70Output().incompleteReasons')
        with page.expect_download() as pending:
            page.evaluate('window.downloadLivingWaterV70Markdown()')
        markdown = Path(pending.value.path()).read_text()
        self.assertIn('| m18 | Sahm Rule | 0 | pp |', markdown)
        self.assertIn('Claudia Sahm', markdown)
        self.assertIn('SAHMREALTIME', markdown)
        self.assertIn('FRED', markdown)
        self.assertIn('百分點（pp）', markdown)
        self.assertEqual(page.evaluate('window.getLivingWaterV70Output().incompleteReasons'), incomplete)
        with page.expect_download() as pending:
            page.evaluate('window.v703Export()')
        exported = json.loads(Path(pending.value.path()).read_text())
        meta = exported.pop('sourceAttribution')['sahm']
        exported.pop('calculatedAt'); original.pop('calculatedAt')
        self.assertEqual(exported, original)
        self.assertEqual(meta['series'], 'SAHMREALTIME')
        self.assertEqual(meta['observationDate'], data['indicators']['m18']['dataDate'])
        self.assertEqual(meta['unit'], 'pp')
        self.assertNotIn('value', meta)
        self.assertNotIn('m18', exported)

    def test_fallback_and_missing_provenance_do_not_claim_published_realtime_series(self):
        page = self.open_feed(feed(), NOW)
        fallback = page.evaluate('''() => {
            window.v703FeedDocument.indicators.m18 = {
                method:'Sahm computed from 3-month unemployment average versus minimum over preceding 12 months',
                source:'https://api.bls.gov/publicAPI/v2/timeseries/data/'
            };
            return window.v703SahmUsageMetadata();
        }''')
        self.assertIsNone(fallback['series'])
        self.assertIsNone(fallback['observationDate'])
        self.assertEqual(fallback['retrievedVia'], 'See input source')
        self.assertNotIn('SAHMREALTIME', fallback['citationUrl'])
        missing = page.evaluate('''() => {
            delete window.v703FeedDocument.indicators.m18;
            return window.v703SahmUsageMetadata();
        }''')
        self.assertIsNone(missing['series'])
        self.assertIsNone(missing['observationDate'])
        self.assertIsNone(missing['lastVerifiedAt'])
        self.assertEqual(missing['sourceUrl'], '')
        self.assertNotIn('value', missing)


if __name__ == '__main__':
    unittest.main()

"""CPI-unavailable data publication must never restore a cached total."""
import shutil
import test_v703_snapshot_frontend as snapshot
import datetime as dt
import json
from pathlib import Path

NOW = dt.datetime(2026, 11, 11, 3, tzinfo=dt.timezone.utc)

def feed():
    return json.loads((Path(__file__).parent / "fixtures/v703_frontend_november_synthetic.json").read_text())
from playwright.sync_api import sync_playwright


def data_only():
    doc = feed()
    doc['verification'].update(ready=False, publicationReady=True,
                              requiredScoringIndicatorsValidated=21)
    doc['publication'] = dict(schema='V70.3/publication-state-v1', mode='DATA_ONLY', reason='CPI_YOY_BASE_PERIOD_MISSING', scoringAllowed=False, provisionalScoringAllowed=True,
                              calculationPolicy='CPI_EXCLUDED_WITHIN_GROUP_MEAN', excludedIndicators=['m05'])
    doc['indicators']['m05'].update(value=None, status='OFFICIAL_UNAVAILABLE',
                                    dataDate='2026-10-01', detail='官方資料不足：缺少去年同期基期')
    return doc


class DataOnlyBrowserTests(snapshot.SnapshotBrowserTests):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        cls.browser = cls.driver.chromium.launch(headless=True, executable_path=shutil.which('chromium'))

    def assert_data_only(self, page, loaded=True, provisional=None):
        if provisional is None:provisional=loaded
        result = page.evaluate("""() => ({loaded:window.v703DataLoaded,
          formal:window.v703CanPublishFormalAllocation(),latest:window.v703Latest,
          verified:window.v703FeedVerified,cpi:document.querySelector('#in_m05').value,
          risk:document.querySelector('#sc_m05').textContent,
          total:Number.isFinite(window.v703MacroSnapshot?.mSafe_final),
          provisional:window.v703ProvisionalSnapshot,
          scoreUI:document.querySelector('#macro-safety-val').textContent,
          status:document.querySelector('#family-data-status').textContent,
          result:document.querySelector('#v703-result').textContent,
          rows:document.querySelector('#v703-raw-data-body').textContent})""")
        self.assertEqual(result['loaded'], loaded, result)
        self.assertFalse(result['formal'])
        self.assertFalse(result['verified'])
        self.assertIsNone(result['latest'])
        self.assertEqual(result['cpi'], '')
        self.assertEqual(result['risk'], 'NA')
        self.assertFalse(result['total'])
        self.assertIn('官方資料不足', result['status'])
        self.assertIn('官方資料不足', result['rows'])
        self.assertNotIn('研究用安全分數', result['result'])
        if provisional:
            score=result['provisional']
            self.assertIsInstance(score['mSafe_final'], (int,float))
            self.assertGreater(score['mSafe_final'],0)
            self.assertEqual(score['excludedIndicators'],['m05'])
            self.assertEqual(score['effectiveWeights'],dict(m05=0,m13=12.6))
            self.assertEqual(score['denominator'],100)
            self.assertAlmostEqual(score['avgRiskBase'],sum(score['groupRisk'][g]*w for g,w in score['groupWeights'].items())/100)
            self.assertAlmostEqual(score['mSafe_final'],min((10-min(10,max(0,score['avgRiskBase']+score['accelAdd'])))*10,score['cap_panic'],score['cap_crisis'],score['cap_recession']))
            self.assertIn('暫行總分',result['result'])
            self.assertIn('6.3%→12.6%',result['result'])
            self.assertIn('暫行',result['scoreUI'])
        else:
            self.assertIsNone(result['provisional'])
            self.assertNotIn('暫行總分：',result['result'])

    def test_current_data_only_repeated_load_and_cache(self):
        doc = data_only()
        page = self.open_feed(doc, NOW, embedded=feed())
        self.assert_data_only(page)
        self.assertEqual(page.locator('#in_m07').input_value(), str(doc['indicators']['m07']['value']))
        page.evaluate("""() => {
          localStorage.setItem('v52_m05','2.9');
          document.querySelector('#in_m05').value='2.9';
          document.querySelector('#sc_m05').textContent='5.0';
          calcTotal();window.v703Recompute();
        }""")
        self.assert_data_only(page)
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page)
        page.reload(wait_until='domcontentloaded')
        page.wait_for_function("window.v703DataLoaded===true")
        self.assert_data_only(page)
        # Loss of the network after loading must not select a stale embedded complete feed.
        page.route('**/V70_macro_latest.json', lambda r: r.abort())
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page)

    def test_previously_valid_total_is_cleared(self):
        page = self.open_feed(feed(), NOW)
        self.assertTrue(page.evaluate('Number.isFinite(window.v703MacroSnapshot.mSafe_final)'))
        page.route('**/V70_macro_latest.json', lambda r: r.fulfill(json=data_only()))
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page)

    def test_other_gates_and_contract_stay_strict(self):
        for fault in ('pe', 'credit', 'count', 'permission', 'reason', 'schema', 'method', 'candidate_checks', 'cpi_date'):
            with self.subTest(fault=fault):
                doc=data_only()
                if fault=='pe':doc['indicators']['m03_qqq'].pop('sourceEvidence')
                elif fault=='credit':doc['indicators']['m02']['status']='MISSING'
                elif fault=='count':doc['verification']['requiredScoringIndicatorsValidated']=22
                elif fault=='permission':doc['publication']['scoringAllowed']=True
                elif fault=='reason':doc['publication']['reason']='UNKNOWN'
                elif fault=='schema':doc['publication']['schema']='UNKNOWN'
                elif fault=='method':doc['indicators']['m06_inf']['method']=''
                elif fault=='candidate_checks':doc['indicators']['m06_output_gap']['candidateChecks']=[]
                else:doc['indicators']['m05']['dataDate']='2026-02-30'
                self.assert_data_only(self.open_feed(doc, NOW, embedded=feed()), loaded=False)

    def test_data_only_receipt_never_claims_scoring_verification(self):
        doc = data_only()
        page = self.open_feed(doc, NOW)
        receipt = dict(status='LIVE_DATA_ONLY', asOf=doc['asOf'],
                       verifiedAtUtc=doc['asOf'], publication=doc['publication'])
        page.route('**/v703_deployment_receipt.json', lambda r: r.fulfill(json=receipt))
        page.evaluate('window.v703ReloadFeed()')
        page.wait_for_function("document.querySelector('#v703-update-banner').textContent.includes('線上資料更新驗收（非完整正式計分）')")
        self.assert_data_only(page)
        receipt['status'] = 'LIVE_VERIFIED'
        page.evaluate('window.v703ReloadFeed()')
        page.wait_for_function("document.querySelector('#v703-update-banner').textContent.includes('線上部署驗收紀錄待確認')")
        self.assertNotIn('線上部署驗收：', page.locator('#v703-update-banner').text_content())
        self.assert_data_only(page)

    def test_missing_provisional_contract_does_not_enable_calculation(self):
        for field,value in [('provisionalScoringAllowed',False),('calculationPolicy','OTHER'),('excludedIndicators',['m05','m13'])]:
            with self.subTest(field=field):
                doc=data_only();doc['publication'][field]=value
                self.assert_data_only(self.open_feed(doc,NOW),provisional=False)

    def test_manual_other_input_and_stale_snapshot_clear_provisional(self):
        page=self.open_feed(data_only(),NOW)
        self.assert_data_only(page)
        before=page.evaluate('window.v703ProvisionalSnapshot.mSafe_final')
        page.evaluate("document.querySelector('#in_m13').value='99';calcTotal();window.v703Recompute()")
        self.assert_data_only(page,provisional=False)
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page)
        self.assertEqual(page.evaluate('window.v703ProvisionalSnapshot.mSafe_final'),before)
        page.clock.set_fixed_time(NOW+dt.timedelta(hours=27))
        page.evaluate('calcTotal();window.v703Recompute()')
        self.assert_data_only(page,provisional=False)

    def test_score_control_poison_does_not_change_provisional(self):
        page=self.open_feed(data_only(),NOW)
        before=page.evaluate('window.v703ProvisionalSnapshot.mSafe_final')
        page.evaluate("document.querySelector('#sc_m13').textContent='0';calcTotal();window.v703Recompute()")
        self.assert_data_only(page)
        self.assertEqual(page.evaluate('window.v703ProvisionalSnapshot.mSafe_final'),before)

    def test_invalid_new_feed_cannot_keep_previous_provisional(self):
        page=self.open_feed(data_only(),NOW)
        self.assert_data_only(page)
        bad=data_only();bad['indicators']['m02']['status']='MISSING'
        page.route('**/V70_macro_latest.json',lambda r:r.fulfill(json=bad))
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page,loaded=False)

    def test_only_inflation_mean_changes_against_complete_model(self):
        page=self.open_feed(feed(),NOW)
        original=page.evaluate('window.v703MacroSnapshot')
        m13=page.evaluate("Number(document.querySelector('#sc_m13').textContent)")
        page.route('**/V70_macro_latest.json',lambda r:r.fulfill(json=data_only()))
        page.evaluate('window.v703ReloadFeed()')
        self.assert_data_only(page)
        current=page.evaluate('window.v703ProvisionalSnapshot')
        self.assertAlmostEqual(current['groupRisk']['inflation'],m13)
        self.assertAlmostEqual(current['avgRiskBase'],original['avgRiskBase']+.126*(m13-original['groupRisk']['inflation']))
        for group,value in original['groupRisk'].items():
            if group!='inflation':self.assertEqual(current['groupRisk'][group],value)
        for field in ['accelAdd','cap_panic','cap_crisis','cap_recession']:
            self.assertEqual(current[field],original[field])

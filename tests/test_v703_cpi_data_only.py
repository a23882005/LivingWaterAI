"""The approved CPI exception updates data, never substitutes a formal score."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, call, patch
import requests
from scripts import refresh_v703_predeploy as refresh
from scripts import v703_cpi_availability as cpi
from scripts import build_daily_v703_site as builder
from scripts.v703_cpi_availability import verify_official_gap, valid_official_gap
from scripts.validate_v703_publication import validate_publication_gate
from scripts.capture_v703_daily_snapshot import validate_feed, CaptureError

NOW=dt.datetime(2026,11,11,3,0,tzinfo=dt.timezone.utc)
CSV=b'observation_date,CPILFESL\n2025-10-01,\n2026-09-01,338.896\n2026-10-01,339.900\n'
BLS=b'''CONSUMER PRICE INDEX - OCTOBER 2026. November 10, 2026.
BLS did not collect survey data for October 2025 because of a lapse in appropriations.
BLS cannot publish 12-month percent changes for October 2026.
The Consumer Price Index news release for November 2026 is scheduled to be published on Thursday, December 10, 2026, at 8:30 a.m. (ET).'''


def evidence():
    return verify_official_gap(CSV,BLS,NOW)


def data_only():
    obj=json.loads((Path(__file__).parent/'fixtures/v703_frontend_november_synthetic.json').read_text())
    obj['asOf']=NOW.isoformat()
    obj['verification'].update(ready=False,publicationReady=True,valid=25,totalRequired=26,
        independentIndicators=25,transportIndicators=28,requiredScoringIndicators=22,
        requiredScoringIndicatorsValidated=21,missing=[],problems=['m05: status STALE'])
    obj['publication']={'schema':'V70.3/publication-state-v1','mode':'DATA_ONLY',
        'reason':'CPI_YOY_BASE_PERIOD_MISSING','scoringAllowed':False,
        'provisionalScoringAllowed':True,'calculationPolicy':'CPI_EXCLUDED_WITHIN_GROUP_MEAN',
        'excludedIndicators':['m05']}
    obj['indicators']['m05'].update(value=None,status='OFFICIAL_UNAVAILABLE',dataDate='2026-10-01',
        officialUnavailable=evidence())
    return obj


class OfficialCpiGapTests(unittest.TestCase):
    def test_official_gap_and_expiry(self):
        ev=evidence()
        self.assertTrue(valid_official_gap(ev,NOW))
        self.assertFalse(valid_official_gap(ev,NOW+dt.timedelta(hours=26)))
        self.assertFalse(valid_official_gap(ev,dt.datetime(2026,12,10,13,30,tzinfo=dt.timezone.utc)))

    def test_real_denominator_or_newer_month_removes_exception(self):
        self.assertIsNone(verify_official_gap(CSV.replace(b'2025-10-01,\n',b'2025-10-01,331\n'),BLS,NOW))
        self.assertIsNone(verify_official_gap(CSV+b'2026-11-01,340\n',BLS,NOW))

    def test_official_notice_and_source_identity_required(self):
        with self.assertRaises(ValueError):verify_official_gap(CSV,b'news summary only',NOW)
        with self.assertRaises(ValueError):verify_official_gap(CSV.replace(b'CPILFESL',b'CPIAUCSL'),BLS,NOW)
        for key,value in [('sourceUrl','https://example.com'),('baseIndex',331),
                          ('sourceSha256',''),('observationMonth','2026-11')]:
            ev=evidence();ev[key]=value
            with self.subTest(key=key):self.assertFalse(valid_official_gap(ev,NOW))

    def test_only_cpi_may_be_missing(self):
        config=set(builder.MACRO_CONFIG_IDS)-{'m05'}
        scoring=set(builder.SCORING_IDS)-{'m05'}
        self.assertTrue(builder._cpi_data_only_eligible([],config,scoring,['m05: status STALE'],evidence(),NOW))
        for bad in builder.MACRO_CONFIG_IDS:
            if bad=='m05':continue
            with self.subTest(bad=bad):
                self.assertFalse(builder._cpi_data_only_eligible([],config-{bad},scoring-{bad},['m05: status STALE',bad+': invalid'],evidence(),NOW))
        self.assertFalse(builder._cpi_data_only_eligible(['m03_spy'],config,scoring,['m05: status STALE'],evidence(),NOW))

    def test_data_only_can_publish_but_cannot_archive_score(self):
        obj=data_only()
        self.assertEqual(validate_publication_gate(obj,NOW),'DATA_ONLY')
        with self.assertRaises(CaptureError):validate_feed(obj)

    def test_complete_real_input_contract_restores_formal_mode(self):
        obj=data_only()
        obj['indicators']['m05'].update(value=2.5,status='OK',method='Synthetic complete YoY fixture')
        obj['indicators']['m05'].pop('officialUnavailable')
        obj['verification'].update(ready=True,valid=26,requiredScoringIndicatorsValidated=22,problems=[])
        obj['publication'].update(mode='FORMAL',reason=None,scoringAllowed=True)
        self.assertEqual(validate_publication_gate(obj,NOW),'FORMAL')
        self.assertEqual(len(validate_feed(obj)),28)

    def test_publication_rechecks_values_and_contract(self):
        cases=[]
        bad=data_only();bad['indicators']['m07']['status']='STALE';cases.append(bad)
        bad=data_only();bad['indicators']['m05']['value']=2.5;cases.append(bad)
        bad=data_only();bad['publication']['scoringAllowed']=True;cases.append(bad)
        bad=data_only();bad['publication']['provisionalScoringAllowed']=False;cases.append(bad)
        bad=data_only();bad['publication']['calculationPolicy']='UNKNOWN';cases.append(bad)
        bad=data_only();bad['publication']['excludedIndicators']=['m05','m13'];cases.append(bad)
        bad=data_only();bad['indicators']['m06_rate']['candidateChecks']=[];cases.append(bad)
        bad=data_only();bad['indicators']['m05']['officialUnavailable'].pop('sourceSha256');cases.append(bad)
        for index,bad in enumerate(cases):
            with self.subTest(index=index),self.assertRaises(ValueError):validate_publication_gate(bad,NOW)


def response(status=200, body=b'x' * 150):
    result = requests.Response()
    result.status_code = status
    result._content = body
    result.url = cpi.FRED_CPI
    return result


class CPIFetchRetriesTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.sleep = patch.object(refresh.time, 'sleep').start()
        self.addCleanup(patch.stopall)

    def test_same_official_urls_longer_read_timeout_and_fresh_body(self):
        for url in (cpi.FRED_CPI, cpi.BLS_CPI):
            self.session.reset_mock()
            raw = (url * 3).encode()
            self.session.get.return_value = response(body=raw)
            self.assertEqual(refresh.fetch_cpi_official_evidence(self.session, url), raw)
            self.session.get.assert_called_once_with(url, timeout=(10, 60), headers=refresh.CPI_OFFICIAL_HEADERS)
        self.sleep.assert_not_called()

    def test_retry_timeout_connection_429_and_server_errors(self):
        for failure in (requests.Timeout('timeout'), requests.ConnectionError('connection'),
                        response(429), response(500), response(502), response(503), response(504)):
            with self.subTest(failure=failure):
                self.session.reset_mock()
                self.sleep.reset_mock()
                self.session.get.side_effect = [failure, response()]
                self.assertEqual(refresh.fetch_cpi_official_evidence(self.session, cpi.FRED_CPI), b'x'*150)
                self.assertEqual(self.session.get.call_args_list, [call(cpi.FRED_CPI, timeout=(10, 60), headers=refresh.CPI_OFFICIAL_HEADERS)]*2)
                self.sleep.assert_called_once_with(1)

    def test_exhaustion_is_bounded_and_propagates_without_cache(self):
        for failure in (requests.ReadTimeout('still timed out'), response(503)):
            with self.subTest(failure=failure):
                self.session.reset_mock()
                self.sleep.reset_mock()
                self.session.get.side_effect = [failure] * 3
                with self.assertRaises(requests.RequestException):
                    refresh.fetch_cpi_official_evidence(self.session, cpi.FRED_CPI)
                self.assertEqual(self.session.get.call_count, 3)
                self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])

    def test_403_and_other_client_errors_propagate_immediately(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.session.reset_mock()
                self.session.get.side_effect = None
                self.session.get.return_value = response(status)
                with self.assertRaises(requests.HTTPError):
                    refresh.fetch_cpi_official_evidence(self.session, cpi.FRED_CPI)
                self.assertEqual(self.session.get.call_count, 1)
        self.sleep.assert_not_called()

    def test_short_data_and_certificate_errors_are_not_retried(self):
        for failure, error in ((response(body=b'short'), ValueError),
                               (requests.exceptions.SSLError('certificate'), requests.exceptions.SSLError)):
            with self.subTest(error=error):
                self.session.reset_mock()
                self.session.get.side_effect = [failure]
                with self.assertRaises(error):
                    refresh.fetch_cpi_official_evidence(self.session, cpi.FRED_CPI)
                self.assertEqual(self.session.get.call_count, 1)
        self.sleep.assert_not_called()

    def test_invalid_evidence_still_fails_existing_verifier_without_retry(self):
        self.session.get.return_value = response(body=b'wrong,columns\n' + b'bad,data\n'*20)
        raw = refresh.fetch_cpi_official_evidence(self.session, cpi.FRED_CPI)
        with self.assertRaisesRegex(ValueError, 'identity/date'):
            cpi.verify_official_gap(raw, b'invalid release', dt.datetime(2026,11,11,tzinfo=dt.timezone.utc))
        self.session.get.assert_called_once()
        self.sleep.assert_not_called()

    def test_non_cpi_fetch_retains_existing_policy(self):
        self.session.get.side_effect = requests.ReadTimeout('timeout')
        with self.assertRaises(requests.ReadTimeout):
            refresh.fetch(self.session, refresh.FED)
        self.session.get.assert_called_once_with(refresh.FED, timeout=(6,18))
        self.sleep.assert_not_called()



if __name__=='__main__':unittest.main()

# 最後修改日期：2026/11/17（台灣時間）｜檔案名稱：test_v703_monthly_release.py｜版本：官方日曆續接、歷史反例與來源原件校驗
"""V70-3-27 official monthly release-calendar gate acceptance tests (2026-10-18)."""
import datetime as dt
import copy
import base64
import gzip
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from scripts import refresh_v703_predeploy as refresh

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v703_daily_builder", ROOT / "scripts/build_daily_v703_site.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
SNAPSHOT = ROOT / "tests/fixtures/v703_20261022_snapshot.json"
MONTHLY_SIX = ("m04", "m05", "m15", "m18", "m19", "m20")


class OfficialMonthlyReleaseTests(unittest.TestCase):
    def test_missing_cpi_base_is_diagnosed_without_accepting_stale_value(self):
        from copy import deepcopy
        item = {"label": "Core CPI YoY", "status": "STALE", "value": 2.565841,
                "observation_date": "2026-09-01", "source_url": "https://fred.stlouisfed.org/series/CPILFESL",
                "method": "historical cache", "retrieval_error": "All FRED sources failed",
                "source_attempts": {"CPILFESL": [
                    {"result": "FAILED", "error": "FRED_CSV: ValueError: Insufficient CPILFESL history; missing 2025-10"}]}}
        before = deepcopy(item)
        diagnostics = builder._scoring_source_diagnostics({"m05": item}, set(builder.SCORING_IDS)-{"m05"})
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["code"], "CPI_YOY_BASE_PERIOD_MISSING")
        self.assertEqual(diagnostics[0]["missingBasePeriods"], ["2025-10"])
        self.assertEqual(item, before)
        now = dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc)
        self.assertIn("m05: status STALE", builder._validate("m05", item, now.date(), {}, now))

    def test_diagnostics_do_not_reuse_old_errors_for_valid_cpi_or_infer_outage(self):
        valid = {"m05": {"status": "OK", "error": "Insufficient CPILFESL history; missing 2025-10"}}
        self.assertEqual(builder._scoring_source_diagnostics(valid, set(builder.SCORING_IDS)), [])
        invalid = {"m05": {"status": "STALE", "error": "HTTP request timed out"}}
        result = builder._scoring_source_diagnostics(invalid, set(builder.SCORING_IDS)-{"m05"})
        self.assertEqual(result[0]["code"], "SCORING_INPUT_INVALID")
        self.assertNotIn("missingBasePeriods", result[0])

    def setUp(self):
        # The existing archived fixture contains September observations and the
        # corresponding official release calendar. Never read mutable production
        # inputs in this historical boundary test: October jobs are correctly fresh.
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.observed = {
            key: dict(snapshot["indicators"][key],
                      observation_date=snapshot["indicators"][key]["dataDate"],
                      source_url=snapshot["indicators"][key]["source"])
            for key in MONTHLY_SIX
        }
        self.now = dt.datetime(2026, 10, 18, 8, 15, tzinfo=dt.timezone.utc)
        self.today = self.now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        self.calendar_data = snapshot["monthlyReleaseCalendar"]
        self.calendar_data["checked_at_utc"] = "2026-10-18T08:00:00Z"
        self.fixture_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture_directory.cleanup)
        fixture_path = pathlib.Path(self.fixture_directory.name) / "calendar.json"
        fixture_path.write_text(json.dumps(self.calendar_data), encoding="utf-8")
        self.calendar = builder._official_release_calendar(fixture_path, self.today)

    def test_frozen_six_observations_and_calendar_are_september(self):
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                self.assertEqual(self.observed[key]["observation_date"], "2026-09-01")
                self.assertEqual(self.observed[key]["status"], "OK")
                self.assertEqual(self.calendar[key]["observation_month"], "2026-09")

    def test_new_october_observation_passes_at_september_expiry(self):
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                release = dt.datetime.fromisoformat(
                    self.calendar[key]["next_release_at_utc"].replace("Z", "+00:00"))
                current = dict(self.observed[key], observation_date="2026-10-01")
                self.assertEqual(builder._validate(
                    key, current, release.date(), self.calendar, release), [])

    def test_official_latest_september_observations_pass_after_day_46(self):
        self.assertEqual(set(self.calendar), set(MONTHLY_SIX))
        for key in MONTHLY_SIX:
            with self.subTest(key=key):
                self.assertEqual((self.today-dt.date(2026,9,1)).days, 47)
                self.assertEqual(builder._validate(key, self.observed[key],
                                                   self.today, self.calendar, self.now), [])

    def test_after_next_report_release_same_previous_month_must_fail(self):
        for key in MONTHLY_SIX:
            release = dt.datetime.fromisoformat(self.calendar[key]["next_release_at_utc"].replace("Z","+00:00"))
            with self.subTest(key=key):
                # One second before real release the existing latest report is still good.
                before = release-dt.timedelta(seconds=1)
                self.assertFalse(builder._validate(key, self.observed[key],
                                 before.date(), self.calendar, before))
                # At release timestamp a stale dataset must block deployment.
                errors = builder._validate(key, self.observed[key],
                                           release.date(), self.calendar, release)
                self.assertTrue(any("monthly data stale" in x for x in errors), errors)

    def test_66_day_latest_month_is_valid_until_official_november_release(self):
        # 2026/11/06: September is 66 calendar days old, but the official
        # October CPI and jobs reports have not yet been released at this time.
        # This regression guards the real 18/22 -> 22/22 V70 incident.
        now = dt.datetime(2026, 11, 6, 4, 0, tzinfo=dt.timezone.utc)
        day = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
        self.assertEqual((day - dt.date(2026, 9, 1)).days, 66)
        for key in ("m05", "m18", "m19", "m20"):
            with self.subTest(key=key):
                item = dict(self.observed[key], status="OK", observation_date="2026-09-01")
                self.assertEqual(builder._validate(key, item, day, self.calendar, now), [])

    def test_unverified_month_and_no_calendar_fail_closed(self):
        data = dict(self.observed["m04"], observation_date="2026-08-01")
        self.assertTrue(builder._validate("m04", data, self.today, self.calendar, self.now))
        self.assertTrue(builder._validate("m04", self.observed["m04"], self.today, {}, self.now))

    def test_calendar_rejects_untrusted_source_and_future_verification(self):
        data=json.loads(json.dumps(self.calendar_data))
        data["items"]["m04"]["calendar_source_url"]="https://phishing.invalid/ism"
        with tempfile.TemporaryDirectory() as directory:
            p=pathlib.Path(directory)/"calendar.json"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"untrusted"):
                builder._official_release_calendar(p,self.today)
            data["items"]["m04"]["calendar_source_url"]="https://www.ismworld.org/calendar"
            data["checked_at_utc"]="2027-01-01T00:00:00Z"
            p.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"verification date"):
                builder._official_release_calendar(p,self.today)


class CurrentMonthlyCalendarRefreshTests(unittest.TestCase):
    """Replay actual publisher/BLS/FRED originals plus marked failure mutations."""
    def setUp(self):
        fixture = json.loads((ROOT/'tests/fixtures/v703_calendar_sources_20261117.json').read_text())
        self.now = dt.datetime.fromisoformat(fixture['clock_utc'])
        self.sources = copy.deepcopy(fixture['sources'])
        for row in self.sources.values():
            archive=(ROOT/row['archive_path']).read_bytes()
            self.assertEqual(hashlib.sha256(archive).hexdigest(),row['archive_sha256'])
            if row.get('archive_kind') == 'EXTRACTED_CALENDAR_FACTS_JSON':
                # Clearly synthetic prose built from actual archived date facts;
                # this is not represented as the original publisher response.
                facts=json.loads(archive)
                pub=refresh._utc_time(facts['publication_at_utc']).astimezone(refresh.ZoneInfo('America/New_York'))
                nxt=refresh._utc_time(facts['next_release_at_utc']).astimezone(refresh.ZoneInfo('America/New_York'))
                period=dt.datetime.strptime(facts['observation_month'],'%Y-%m')
                next_period=dt.datetime.strptime(refresh._next_month(facts['observation_month']),'%Y-%m')
                row['raw']=(period.strftime('%B %Y')+' ISM Services PMI Report '
                    +'News provided by Institute for Supply Management '+pub.strftime('%b %d, %Y, %H:%M ET')
                    +' The next ISM Services PMI Report featuring '+next_period.strftime('%B %Y')
                    +' data will be released at '+nxt.strftime('%I:%M ').lstrip('0')+'a.m. ET on '
                    +nxt.strftime('%A, %B %d, %Y')+'. SOURCE Institute for Supply Management').encode()
                row['fixture_kind']='RECONSTRUCTED_BOUNDARY_TEST_NOT_ORIGINAL_HTTP'
                row['response_sha256']=hashlib.sha256(row['raw']).hexdigest();row['response_bytes']=len(row['raw'])
            else:
                row['raw'] = gzip.decompress(archive)
        self.calendar = json.loads(SNAPSHOT.read_text())['monthlyReleaseCalendar']
        self.calendar['checked_at_utc'] = '2026-10-18T08:00:00Z'
        self.core = {'items':{k:{'observation_date':'2026-10-01','value':0} for k in refresh.CALENDAR_TARGETS}}

    def apply(self, sources=None, now=None, core=None):
        return refresh.apply_monthly_calendar_updates(self.calendar,core or self.core,
                                                      self.sources if sources is None else sources,now or self.now)

    def mutate_body(self, name, change):
        row=self.sources[name];row['raw']=change(row['raw'])
        row['response_sha256']=hashlib.sha256(row['raw']).hexdigest();row['response_bytes']=len(row['raw'])

    def receipts_before(self, now):
        # Controlled verification-clock mutation for historical boundary cases.
        for row in self.sources.values():row['fetched_at_utc']=(now-dt.timedelta(seconds=1)).isoformat()

    def test_actual_four_sources_and_original_values_preserved(self):
        cal,core=copy.deepcopy(self.calendar),copy.deepcopy(self.core)
        new,result=self.apply()
        self.assertTrue(all(r['status']=='VERIFIED' for r in result.values()),result)
        self.assertEqual(new['items']['m15']['publication_date'],'2026-11-04')
        self.assertEqual(new['items']['m15']['next_release_at_utc'],'2026-12-03T15:00:00Z')
        for key in ('m18','m19','m20'):
            self.assertEqual(new['items'][key]['publication_date'],'2026-11-06')
            self.assertEqual(new['items'][key]['next_release_at_utc'],'2026-12-04T13:30:00Z')
        self.assertEqual(self.calendar,cal);self.assertEqual(self.core,core)
        for key in ('m04','m05'):self.assertEqual(new['items'][key],cal['items'][key])

    def test_actual_ISM_distribution_and_Sahm_cutoff_are_disclosed(self):
        new,_=self.apply()
        ism=new['items']['m15'];sahm=new['items']['m18']
        self.assertEqual(ism['calendar_source_url'],refresh.ISM_CAL)
        self.assertEqual(ism['source_evidence'][0]['url'],refresh.ISM_SERVICES_RELEASES['2026-10'])
        self.assertEqual(ism['release_time_basis'],'ISM_PUBLISHER_DISTRIBUTED_RELEASE')
        self.assertFalse(sahm['fred_posting_time_claimed'])
        self.assertIn('CONSERVATIVE_UPSTREAM_BLS_CUTOFF',sahm['release_time_basis'])

    def test_services_before_and_at_next_release(self):
        release=dt.datetime(2026,12,3,15,tzinfo=dt.timezone.utc)
        before,result=self.apply(now=release-dt.timedelta(seconds=1))
        self.assertEqual(result['m15']['status'],'VERIFIED')
        after,result=self.apply(now=release)
        self.assertEqual(result['m15']['status'],'RETAINED_UNVERIFIED')
        self.assertEqual(after['items']['m15'],self.calendar['items']['m15'])
        self.assertTrue(all(result[k]['status']=='VERIFIED' for k in ('m18','m19','m20')))
        old={'status':'OK','value':54.5,'observation_date':'2026-10-01','source_url':refresh.ISM_CAL,
             'method':'ISM Services PMI published reference month'}
        self.assertEqual(builder._validate('m15',old,release.date(),before['items'],release-dt.timedelta(seconds=1)),[])
        self.assertTrue(builder._validate('m15',old,release.date(),before['items'],release))

    def test_employment_before_and_at_next_release(self):
        release=dt.datetime(2026,12,4,13,30,tzinfo=dt.timezone.utc)
        _,before=self.apply(now=release-dt.timedelta(seconds=1))
        after,result=self.apply(now=release)
        for key in ('m18','m19','m20'):
            self.assertEqual(before[key]['status'],'VERIFIED')
            self.assertEqual(result[key]['status'],'RETAINED_UNVERIFIED')
            self.assertEqual(after['items'][key],self.calendar['items'][key])

    def test_not_yet_published_observation_does_not_certify(self):
        now=dt.datetime(2026,11,6,13,29,59,tzinfo=dt.timezone.utc);self.receipts_before(now)
        new,result=self.apply(now=now)
        self.assertEqual(result['m15']['status'],'VERIFIED')
        for key in ('m18','m19','m20'):
            self.assertEqual(result[key]['status'],'RETAINED_UNVERIFIED')
            self.assertEqual(new['items'][key],self.calendar['items'][key])

    def test_missing_services_evidence_continues_other_three(self):
        del self.sources['ism'];new,result=self.apply()
        self.assertEqual(new['items']['m15'],self.calendar['items']['m15'])
        self.assertEqual(result['m15']['status'],'RETAINED_UNVERIFIED')
        self.assertTrue(all(result[k]['status']=='VERIFIED' for k in ('m18','m19','m20')))

    def test_missing_BLS_evidence_continues_services(self):
        del self.sources['bls'];new,result=self.apply()
        self.assertEqual(result['m15']['status'],'VERIFIED')
        for key in ('m18','m19','m20'):self.assertEqual(new['items'][key],self.calendar['items'][key])

    def test_fred_wrong_release_identity_does_not_block_U3_or_NFP(self):
        self.mutate_body('fred',lambda b:b.replace(b'rid=456',b'rid=999'))
        new,result=self.apply()
        self.assertEqual(new['items']['m18'],self.calendar['items']['m18'])
        self.assertEqual(result['m19']['status'],'VERIFIED');self.assertEqual(result['m20']['status'],'VERIFIED')

    def test_unverified_reference_month_does_not_extend(self):
        self.core['items']['m19']['observation_date']='2026-08-01'
        new,result=self.apply()
        self.assertEqual(new['items']['m19'],self.calendar['items']['m19'])
        self.assertEqual(result['m18']['status'],'VERIFIED');self.assertEqual(result['m20']['status'],'VERIFIED')

    def test_future_verification_time_even_on_same_day_is_rejected(self):
        for row in self.sources.values():row['fetched_at_utc']=(self.now+dt.timedelta(minutes=1)).isoformat()
        new,result=self.apply()
        self.assertTrue(all(r['status']=='RETAINED_UNVERIFIED' for r in result.values()))
        self.assertEqual(new['items'],self.calendar['items'])

    def test_corrupted_original_hash_is_rejected(self):
        self.sources['ism']['raw']+=b' changed'
        new,result=self.apply()
        self.assertEqual(new['items']['m15'],self.calendar['items']['m15'])
        self.assertIn('hash/size',result['m15']['error'])

    def test_login_redirect_is_not_calendar_verification(self):
        self.sources['ism']['final_url']='https://ecommerce.ismworld.org/SSO/Login.aspx'
        new,result=self.apply()
        self.assertEqual(new['items']['m15'],self.calendar['items']['m15'])
        self.assertIn('redirect',result['m15']['error'])

    def test_official_timezone_evidence_is_required(self):
        self.mutate_body('bls_timezone',lambda b:b.replace(b'All times on calendar are Eastern Time',b'unspecified timezone'))
        new,result=self.apply()
        self.assertEqual(result['m15']['status'],'VERIFIED')
        for key in ('m18','m19','m20'):self.assertEqual(new['items'][key],self.calendar['items'][key])

    def test_actual_BLS_schedule_uses_DST_instead_of_fixed_UTC_offset(self):
        rows=refresh.parse_employment_schedule(self.sources['bls']['raw'])
        self.assertEqual(rows['2027-04'].isoformat(),'2027-05-07T12:30:00+00:00')
        self.assertEqual(rows['2027-02'].isoformat(),'2027-03-05T13:30:00+00:00')

    def test_wrong_ISM_reference_month_is_rejected(self):
        self.mutate_body('ism',lambda b:b.replace(b'October 2026',b'September 2026'))
        new,result=self.apply()
        self.assertEqual(new['items']['m15'],self.calendar['items']['m15'])
        self.assertEqual(result['m19']['status'],'VERIFIED')

    def test_original_refresh_entry_fetches_and_archives_each_source_once(self):
        responses={row['url']:row['raw'] for row in self.sources.values()};calls=[]
        class Session:
            def get(self,url,**kwargs):
                calls.append(url)
                return SimpleNamespace(content=responses[url],url=url,status_code=200,raise_for_status=lambda:None)
        now=self.now
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return now.astimezone(tz) if tz else now.replace(tzinfo=None)
        clock=SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')});clock.datetime=Fixed
        with tempfile.TemporaryDirectory() as folder,patch.object(refresh,'ROOT',pathlib.Path(folder)),patch.object(refresh,'dt',clock):
            new=refresh.refresh_monthly_release_calendars(Session(),self.core,self.calendar)
            self.assertTrue(all(r['status']=='VERIFIED' for r in new['target_refresh_results'].values()))
            self.assertEqual(len(calls),len(set(calls)));self.assertEqual(len(calls),4)
            self.assertEqual(len(new['source_archives']),4)
            for key in refresh.CALENDAR_TARGETS:
                for ev in new['items'][key]['source_evidence']:
                    archive=(pathlib.Path(folder)/ev['archive_path']).read_bytes()
                    self.assertEqual(hashlib.sha256(archive).hexdigest(),ev['archive_sha256'])
                    packet=new['source_archives'][ev['archive_sha256']]
                    self.assertEqual(base64.b64decode(packet['base64'],validate=True),archive)
                    self.assertEqual(packet['bytes'],len(archive))
                    if ev['archive_kind']=='EXTRACTED_CALENDAR_FACTS_JSON':
                        self.assertEqual(json.loads(archive)['original_response_sha256'],ev['response_sha256'])
                    else:
                        self.assertEqual(hashlib.sha256(gzip.decompress(archive)).hexdigest(),ev['response_sha256'])
            first={ev['archive_path']:(pathlib.Path(folder)/ev['archive_path']).read_bytes()
                   for row in new['items'].values() for ev in row.get('source_evidence',[])}
            old_ism=new['items']['m15']['source_evidence'][0]['archive_path']
            now+=dt.timedelta(seconds=1)
            again=refresh.refresh_monthly_release_calendars(Session(),self.core,new)
            self.assertNotEqual(again['items']['m15']['source_evidence'][0]['archive_path'],old_ism)
            for path,body in first.items():
                self.assertEqual((pathlib.Path(folder)/path).read_bytes(),body,
                                 'A later refresh must preserve frozen originals')

    def test_incomplete_ISM_calendar_response_still_refreshes_other_three(self):
        incomplete=(b'Release Dates for the ISM Manufacturing and Services '
            b'Services 10:00 a.m. (EST) <table><tr><td>November 2026</td>'
            b'<td>2</td><td>4</td></tr></table>')
        responses={row['url']:row['raw'] for row in self.sources.values()}
        responses[refresh.ISM_CAL]=incomplete
        class Session:
            def get(self,url,**kwargs):
                return SimpleNamespace(content=responses[url],url=url,status_code=200,raise_for_status=lambda:None)
        now=self.now
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return now.astimezone(tz) if tz else now.replace(tzinfo=None)
        clock=SimpleNamespace(**{n:getattr(dt,n) for n in dir(dt) if not n.startswith('__')});clock.datetime=Fixed
        with tempfile.TemporaryDirectory() as folder,patch.object(refresh,'ROOT',pathlib.Path(folder)),patch.object(refresh,'dt',clock),patch.object(refresh,'ISM_SERVICES_RELEASES',{}):
            new=refresh.refresh_monthly_release_calendars(Session(),self.core,self.calendar)
        self.assertEqual(new['items']['m15'],self.calendar['items']['m15'])
        self.assertEqual(new['target_refresh_results']['m15']['status'],'RETAINED_UNVERIFIED')
        for key in ('m18','m19','m20'):
            self.assertEqual(new['target_refresh_results'][key]['status'],'VERIFIED')


class SahmUnitMetadataTests(unittest.TestCase):
    def test_sahm_empty_unit_preserves_zero_missing_values_and_provenance(self):
        for value in (0.0, None):
            for unit in ('', None):
                with self.subTest(value=value, unit=unit):
                    row = {'value': value, 'unit': unit, 'observation_date': '2026-10-01',
                           'source_url': 'https://fred.stlouisfed.org/series/SAHMREALTIME',
                           'method': 'published series', 'status': 'OK',
                           'last_verified_at': '2026-11-06T15:47:00Z'}
                    original = copy.deepcopy(row)
                    actual = builder._normalize(row, 'm18')
                    self.assertEqual(actual['unit'], 'pp')
                    self.assertEqual(actual['value'], value)
                    self.assertEqual(actual['dataDate'], row['observation_date'])
                    self.assertEqual(actual['source'], row['source_url'])
                    self.assertEqual(actual['lastVerifiedAt'], row['last_verified_at'])
                    self.assertEqual(row, original)

    def test_explicit_sahm_unit_and_other_indicators_are_not_rewritten(self):
        row = {'value': 0, 'unit': 'Percentage Points'}
        self.assertEqual(builder._normalize(row, 'm18')['unit'], 'Percentage Points')
        for key in ('m19', 'm05', None):
            self.assertEqual(builder._normalize({'value': 0, 'unit': ''}, key)['unit'], '')


if __name__ == "__main__":
    unittest.main()

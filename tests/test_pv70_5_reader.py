import copy
import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
ROOT = WORKSPACE if (WORKSPACE/'frozen').is_dir() else Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT/'frozen' if (ROOT/'frozen').is_dir() else ROOT
SCRIPT = ROOT/'staging/scripts/pv70_5_reader.py' if (ROOT/'staging/scripts/pv70_5_reader.py').is_file() else ROOT/'scripts/pv70_5_reader.py'
spec = importlib.util.spec_from_file_location('pv70_reader', SCRIPT)
reader = importlib.util.module_from_spec(spec); spec.loader.exec_module(reader)
COMMIT = '1' * 40
TIME = '2026-10-20T15:00:00+08:00'

class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)/'repo'; self.repo.mkdir()
        for path in reader.SCHEMAS:
            d = json.loads((SOURCE_ROOT/path).read_bytes())
            self.write(path, d)
        self.write('data/v703_official_monthly_release_calendar.json', {'schema':'V70.3/monthly-official-release-calendar-v1', 'fixture_type':'SYNTHETIC_TEST_ONLY'})
        self.write('data/macro_safety_daily.csv', 'daily_record_id,observation_date,score_status,health_score,source_commit\nTEST_DAILY,2026-10-19,FORMAL_VALID,50,'+COMMIT+'\n')
        for region,symbol,currency,exchange in [('global','TEST_US','USD','TEST_XNAS'),('taiwan','TEST_TW','TWD','TEST_XTAI')]:
            self.write(f'data/market_history/{region}/{symbol}.csv', 'Date,Close,Adj Close\n2026-10-16,11,10\n2026-10-19,12.34,10.5\n')
            self.write(f'data/market_history/{region}/manifest.json', {'region':region,'generated_utc':'2026-10-20T01:00:00Z','data_source':'SYNTHETIC_TEST_ONLY', 'items':{symbol:{'status':'OK','rows':2,'latest_observation':'2026-10-19','currency':currency,'exchange':exchange,'instrument_id':symbol+'_ID'}}})
        self.sync_formal(); self.lock = self.make_lock()

    def write(self,path,data):
        p=self.repo/path; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False)+'\n' if not isinstance(data,str) else data)

    def mutate_json(self,path,fn,*,sync=True):
        d=json.loads((self.repo/path).read_bytes());fn(d);self.write(path,d)
        if sync:self.sync_formal()
        self.lock=self.make_lock()

    def sync_formal(self):
        p=self.repo/reader.CANONICAL;d=json.loads(p.read_bytes())
        for k,path in [('macro18','data/18_macro_verification.json'),('macro8','data/8_macro_supplement_verified.json'),('wallstreet5','data/wallstreet5_forecasts.json'),('officialReleaseCalendar','data/v703_official_monthly_release_calendar.json')]:
            d['sourceSnapshot'][k]=reader.git_blob_sha1((self.repo/path).read_bytes())
        self.write(reader.CANONICAL,d)

    def make_lock(self):
        return {'schema':'LivingWaterAI/p70-5-source-lock-v1','fixture_type':'SYNTHETIC_TEST_ONLY','source_commit':COMMIT,'files':{p.relative_to(self.repo).as_posix():{'source_commit':COMMIT,'size':p.stat().st_size,'sha256':reader.content_sha256(p.read_bytes()),'git_blob_sha1':reader.git_blob_sha1(p.read_bytes())} for p in self.repo.rglob('*') if p.is_file()}}

    def run_reader(self,commit=COMMIT):
        return reader.read_sources(self.repo,commit,self.lock,TIME)

    def assert_issue(self,code):
        r=self.run_reader();self.assertEqual(r['value_state'],'BLOCKED');self.assertTrue(any(x.startswith(code) for x in r['issue_codes']),r['issue_codes'])

    def test_p01_valid_18_8_five_quotes_values_and_raw_formal(self):
        r=self.run_reader();self.assertEqual(r['value_state'],'OK');self.assertEqual(r['issue_codes'],[])
        self.assertEqual(len(r['macro18']['items'])-1,18);self.assertEqual(len(r['macro8']['items']),8)
        self.assertEqual(len(r['wallstreet5']),5);self.assertEqual(len(r['quotes']),2)
        self.assertEqual(r['quotes'][0]['value'],12.34);self.assertEqual(r['quotes'][0]['adjusted_value'],10.5)
        self.assertEqual(r['quotes'][0]['source_csv_line'],3)
        self.assertEqual(r['formal_feed'],json.loads((self.repo/reader.CANONICAL).read_bytes()))

    def test_p01_replay_is_identical_zero_network_and_no_input_writes(self):
        before=self.make_lock();calls=[]
        def denied(*a,**kw):calls.append(a);raise AssertionError('network attempted')
        with patch.object(socket,'socket',denied),patch.object(socket,'create_connection',denied):
            a=self.run_reader();b=self.run_reader()
        self.assertEqual(a,b);self.assertEqual(calls,[]);self.assertEqual(before,self.make_lock())

    def test_n01_missing_source_and_tampered_source(self):
        p=self.repo/'data/18_macro_verification.json';b=p.read_bytes();p.unlink();self.assert_issue('SOURCE_MISSING')
        p.write_bytes(b+b' ');self.assert_issue('SOURCE_HASH_OR_SIZE_MISMATCH')

    def test_n01_bad_json_and_duplicate_json_keys(self):
        for text in ['{bad','{"schema":"x","schema":"y"}', '{"value":NaN}']:
            with self.subTest(text=text):
                self.write('data/18_macro_verification.json',text);self.lock=self.make_lock();self.assert_issue('JSON_INVALID')

    def test_n01_wrong_canonical_schema_never_uses_legacy(self):
        self.mutate_json(reader.CANONICAL,lambda d:d.update(schema='V70.3/macro-feed-v1'),sync=False)
        self.write('V70_macro_latest.json',{'schema':'V70.3/family-macro-feed-v3','asOf':'2099-01-01'})
        self.lock=self.make_lock();self.assert_issue('SCHEMA_MISMATCH')

    def test_n01_status_stale_missing_and_formal_not_ready(self):
        for state in ['STALE','MISSING','UNKNOWN']:
            with self.subTest(state=state):
                self.mutate_json('data/18_macro_verification.json',lambda d:d['items']['m07'].update(status=state))
                self.assert_issue('MACRO_STATUS_NOT_USABLE')
        self.mutate_json(reader.CANONICAL,lambda d:d['verification'].update(ready=False),sync=False)
        self.assert_issue('CANONICAL_FEED_NOT_READY')

    def test_n01_mixed_commit_and_lock_commit(self):
        self.assertEqual(self.run_reader('2'*40)['issue_codes'],['SOURCE_COMMIT_MISMATCH'])
        self.lock['files']['data/18_macro_verification.json']['source_commit']='2'*40
        self.assert_issue('SOURCE_FILE_COMMIT_MISMATCH')

    def test_n01_manifest_count_date_and_bad_csv(self):
        self.mutate_json('data/market_history/global/manifest.json',lambda d:d['items']['TEST_US'].update(rows=99))
        self.assert_issue('MANIFEST_CSV_MISMATCH')
        self.write('data/market_history/global/TEST_US.csv','Date,Adj Close\n2026-10-19,99\n');self.lock=self.make_lock()
        self.assert_issue('CSV_INVALID')

    def test_b01_adj_close_cannot_replace_raw_close(self):
        for close in ['', 'NaN','inf','0','-1']:
            with self.subTest(close=close):
                self.write('data/market_history/global/TEST_US.csv',f'Date,Close,Adj Close\n2026-10-19,{close},99\n');self.lock=self.make_lock()
                r=self.run_reader();self.assertEqual(r['value_state'],'BLOCKED');q=next(q for q in r['quotes'] if q['symbol']=='TEST_US');self.assertIsNone(q['value']);self.assertIn('NO_VALID_ORIGINAL_CLOSE',q['issue_codes'])

    def test_b01_later_invalid_row_is_not_silently_fresh(self):
        self.write('data/market_history/global/TEST_US.csv','Date,Close,Adj Close\n2026-10-16,11,10\n2026-10-19,,99\n');self.lock=self.make_lock()
        r=self.run_reader();q=r['quotes'][0];self.assertEqual(q['observation_date'],'2026-10-16');self.assertEqual(q['value'],11);self.assertIn('MANIFEST_CSV_COUNT_OR_DATE_MISMATCH',q['issue_codes']);self.assertEqual(r['value_state'],'BLOCKED')

    def test_b01_missing_identity_stays_unknown_and_dates_need_policy(self):
        self.mutate_json('data/market_history/global/manifest.json',lambda d:d['items']['TEST_US'].pop('currency'))
        r=self.run_reader();q=r['quotes'][0];self.assertIsNone(q['currency']);self.assertEqual(q['value_state'],'UNKNOWN');self.assertEqual(q['date_validity_state'],'NOT_EVALUATED_REQUIRES_REQUEST_POLICY')
        self.assertTrue(all(x['value_state'] != 'KNOWN' for x in r['quotes']))

    def test_n01_path_traversal_and_source_output_guard(self):
        x=reader.SourceReader(self.repo,COMMIT,self.lock);self.assertIsNone(x.raw('../outside.json'));self.assertTrue(x.issues[0].startswith('SOURCE_PATH_OUTSIDE_REPO'))
        lock=Path(self.temp.name)/'lock.json';lock.write_text(json.dumps(self.lock))
        before=self.make_lock();p=subprocess.run([sys.executable,str(SCRIPT),'--repo',str(self.repo),'--commit',COMMIT,'--source-lock',str(lock),'--out',str(self.repo/'data')],capture_output=True)
        self.assertEqual(p.returncode,2);self.assertEqual(before,self.make_lock())

if __name__=='__main__':unittest.main(verbosity=2)

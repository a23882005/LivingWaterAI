"""Current source intake and actual original V70 JS, without family data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_current_sources_module',HERE/'on_demand_current_sources.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
CLIENT='fam_'+'a'*32


class CurrentSourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'member.db'
        with sqlite3.connect(self.db) as c:
            c.executescript('''
            CREATE TABLE family_member_identity(client_id TEXT);
            CREATE TABLE portfolio_snapshot_run(client_id TEXT,run_id TEXT,run_state TEXT,
                source_kind TEXT,as_of_utc TEXT,version_no INTEGER,data_state TEXT);
            CREATE TABLE portfolio_snapshot_item(client_id TEXT,run_id TEXT,item_no INTEGER,
                domain_code TEXT,entity_key TEXT,field_key TEXT,value_state TEXT,value_text TEXT,
                source_reference TEXT);
            CREATE TABLE cash_balance_snapshot(cash_snapshot_id TEXT,client_id TEXT,account_key TEXT,
                currency_code TEXT,as_of_utc TEXT,version INTEGER,amount INTEGER,data_state TEXT,
                source_reference TEXT);
            CREATE VIEW cash_available_view AS SELECT cash_snapshot_id,client_id,account_key,
                currency_code,as_of_utc,version,
                CASE WHEN data_state='VERIFIED' THEN amount END AS available_minor,
                CASE WHEN data_state='VERIFIED' THEN 'VERIFIED' ELSE 'NEEDS_REVIEW' END AS available_state
                FROM cash_balance_snapshot;
            CREATE VIEW funding_planning_view AS SELECT client_id FROM cash_balance_snapshot WHERE 0;
            ''')
            c.execute('INSERT INTO family_member_identity VALUES(?)',(CLIENT,))
            c.execute('INSERT INTO portfolio_snapshot_run VALUES(?,?,?,?,?,?,?)',
                (CLIENT,'SOURCE-1','SEALED','OWNER_VERIFIED','2026-10-25T00:00:00Z',1,'PARTIAL'))
            for n,key,value in [(1,'stock_weight','0.8'),(2,'bond_weight','0.2')]:
                c.execute('INSERT INTO portfolio_snapshot_item VALUES(?,?,?,?,?,?,?,?,?)',
                    (CLIENT,'SOURCE-1',n,'PROFILE','LONG_TERM',key,'KNOWN',value,'test-owner-confirmation'))
            c.execute('INSERT INTO cash_balance_snapshot VALUES(?,?,?,?,?,?,?,?,?)',
                ('CASH-1',CLIENT,'A','TWD','2026-10-25T00:00:00Z',1,5000000,'NEEDS_REVIEW','test-cash'))
        self.tables={'portfolio_instrument':[{'instrument_key':'VT','ticker':'VT'}],
                     'final_target_version':[{'target_key':'LONG_TERM','version_no':1,
                        'lifecycle_state':'CONFIRMED','completeness_state':'COMPLETE'}],
                     'final_target_allocation':[{'target_key':'LONG_TERM','version_no':1,
                        'instrument_key':'VT','allocation_state':'ACCEPTED','weight_units':1000000}]}

    def snapshot(self):
        return {'schema_version':'Family.W5.W1Snapshot.v1','client_id':CLIENT,
                'data_provenance':'SOURCE_BACKED','tables':self.tables,
                'payload_digest':M._module('official_holdings_source')._digest(self.tables),
                'source_sha256':hashlib.sha256(self.db.read_bytes()).hexdigest()}

    def intake(self,**kwargs):
        # The DB tests isolate source logic; the separate class below runs JS itself.
        with patch.object(M,'run_original_v70',return_value={'status':'V70_DATA_READY'}) as runner:
            result=M.build_current_sources(self.snapshot(),self.db,repo_root=M.REPO,
                evaluation_at='2026-10-27T00:00:00Z',**kwargs)
        return result,runner

    def test_confirmed_base_and_unknown_cash_preserved(self):
        before=self.db.read_bytes();out,runner=self.intake()
        self.assertEqual((out['strategic']['stock_percent'],out['strategic']['bond_percent']),(80,20))
        self.assertEqual(out['funding_latest'][0]['available_state'],'NEEDS_REVIEW')
        self.assertIsNone(out['funding_latest'][0]['available_minor'])
        self.assertIsNone(out['monetary_tactical_amounts'])
        self.assertEqual(out['confirmed_target_details'][0]['target_key'],'LONG_TERM')
        self.assertIn('verified_settled_available_funding',out['missing'])
        self.assertEqual(self.db.read_bytes(),before);runner.assert_called_once()

    def test_verified_cash_is_not_invented_whole_portfolio_nav(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cash_balance_snapshot SET data_state='VERIFIED'")
        out,_=self.intake()
        self.assertEqual(out['funding_latest'][0]['available_minor'],5000000)
        self.assertNotIn('verified_settled_available_funding',out['missing'])
        self.assertIsNone(out['monetary_tactical_amounts'])

    def test_latest_unknown_cash_never_reuses_old_verified_balance(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE cash_balance_snapshot SET data_state='VERIFIED'")
            c.execute("INSERT INTO cash_balance_snapshot VALUES('CASH-2',?,'A','TWD',"
                      "'2026-10-26T00:00:00Z',1,100,'NEEDS_REVIEW','new')",(CLIENT,))
        out,_=self.intake()
        self.assertEqual(len(out['funding_latest']),1)
        self.assertIsNone(out['funding_latest'][0]['available_minor'])

    def test_other_client_and_changed_database_rejected(self):
        for key,value in [('client_id','fam_'+'b'*32),('source_sha256','0'*64)]:
            s=self.snapshot();s[key]=value
            with self.subTest(key=key),self.assertRaises(PermissionError):M.build_current_sources(s,self.db)

    def test_missing_strategic_base_has_no_default_60_40(self):
        with sqlite3.connect(self.db) as c:c.execute('DELETE FROM portfolio_snapshot_item')
        out,runner=self.intake();self.assertIsNone(out['strategic']);self.assertIsNone(out['v70'])
        runner.assert_not_called()

    def test_future_owner_facts_rejected(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE portfolio_snapshot_run SET as_of_utc='2030-01-01T00:00:00Z'")
        with self.assertRaisesRegex(ValueError,'FUTURE_FACTS'):self.intake()


class OriginalV70RuntimeTest(unittest.TestCase):
    def setUp(self):
        feed=json.loads((M.REPO/'系統工程/總經V70/V70_macro_latest.json').read_text())
        stamps=[feed['asOf']]
        for row in feed['indicators'].values():
            for k in ('lastVerifiedAt','last_verified_at'):
                if row.get(k):stamps.append(row[k])
        self.when=(max(datetime.fromisoformat(s.replace('Z','+00:00')) for s in stamps)
                   +timedelta(hours=1)).isoformat()

    def test_original_feed_and_scoring_execute_without_network(self):
        out=M.run_original_v70(M.REPO,{'stock_percent':80,'bond_percent':20},evaluation_at=self.when)
        self.assertEqual(out['status'],'V70_DATA_READY')
        self.assertFalse(out['gates']['demo']);self.assertTrue(out['gates']['feed_verified'])
        self.assertAlmostEqual(sum(out['tactical_percentages'].values()),100)
        self.assertEqual(out['macro_snapshot']['allocation']['S0'],80)
        self.assertEqual(out['original_latest']['status'],'AUTO_ALLOCATION_CANDIDATE_PENDING_BACKTEST')
        self.assertIsNone(out['monetary_amounts'])
        self.assertTrue(all(x in ['/V70_macro_latest.json','/v703_deployment_receipt.json'] for x in out['local_reads']))
        self.assertEqual(out['trade_authorization'],'NONE')

    def test_original_loader_rejects_unready_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'系統工程/總經V70';folder.mkdir(parents=True)
            for name in ['V70-3-27.html','V70_macro_latest.json']:
                shutil.copyfile(M.REPO/'系統工程/總經V70'/name,folder/name)
            p=folder/'V70_macro_latest.json';feed=json.loads(p.read_text());feed['verification']['ready']=False
            p.write_text(json.dumps(feed))
            out=M.run_original_v70(root,{'stock_percent':80,'bond_percent':20},evaluation_at=self.when)
            self.assertEqual(out['status'],'V70_DATA_UNAVAILABLE')
            self.assertIsNone(out['tactical_percentages'])


if __name__=='__main__':unittest.main()

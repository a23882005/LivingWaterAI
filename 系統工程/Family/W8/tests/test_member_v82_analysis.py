"""Synthetic all-account/target-only coverage and original-native replay.

These fixtures are isolated engineering evidence, never household portfolios.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import sys

HERE = Path(__file__).resolve().parents[1]; ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5')]
from family_input import digest
from member_v82_analysis import target_source, universe, MemberV82SourceProducer
from member_market_source import read_market
from on_demand_analysis import OnDemandAnalysisProvider
from approved_v04_technical import load_profile
from native_asset_source import FORMAL_CLASSES


class MemberV82Tests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name); self.client = 'fam_'+'a'*32
        self.at = '2026-10-29T23:00:00Z'
        clock = patch('member_v82_analysis.datetime', wraps=datetime)
        fixed = clock.start(); self.addCleanup(clock.stop)
        fixed.now.return_value = datetime.fromisoformat(self.at.replace('Z', '+00:00'))
        def instrument(key, ticker, kind):
            return {'client_id':self.client, 'instrument_key':key, 'ticker':ticker,
                    'instrument_type':kind, 'identity_state':'KNOWN', 'quote_currency':'USD'}
        instruments = [instrument('CORE','VT','ETF'), instrument('BOND','SGOV','ETF'),
                       instrument('CASH',None,'CASH'), instrument('HELD','QQQ','ETF')]
        version = {'client_id':self.client,'target_key':'SYNTHETIC_LONG_TERM','version_no':1,
            'lifecycle_state':'CONFIRMED','completeness_state':'COMPLETE','confirmed_by':'SYNTHETIC_OWNER',
            'confirmation_source_ref':'SYNTHETIC_APPROVAL','confirmed_at_utc':'2026-10-01T00:00:00Z',
            'created_at_utc':'2026-10-01T00:00:00Z'}
        allocations = [{'client_id':self.client,'target_key':version['target_key'],'version_no':1,
            'instrument_key':key,'weight_units':weight,'allocation_state':'ACCEPTED',
            'allocation_source_ref':'SYNTHETIC_APPROVAL','created_at_utc':'2026-10-01T00:00:00Z'}
            for key, weight in [('CORE',600000),('BOND',200000),('CASH',200000)]]
        positions = [{'client_id':self.client,'account_key':'SYNTHETIC_US','instrument_key':'HELD',
            'quantity_decimal':qty,'as_of_utc':day} for qty, day in
            [('1','2026-10-01T00:00:00Z'),('2','2026-10-20T00:00:00Z')]]
        self.snapshot = {'schema_version':'Family.W5.W1Snapshot.v1','client_id':self.client,
            'source_sha256':'a'*64,'data_provenance':'SOURCE_BACKED',
            'tables':{'portfolio_instrument':instruments,'portfolio_position':positions,
                'final_target_version':[version],'final_target_allocation':allocations}}
        self.seal()
        rule = self.folder/'SYNTHETIC_RULE_SOURCE.md'
        rule.write_text('\n'.join(FORMAL_CLASSES)+'\n# 第四十九章｜VT／VWRA型\n# 第四十六章｜QQQ型\n')
        self.config = {'repo_root':str(ROOT),'client_id':self.client,'source_db_sha256':'a'*64,
            'classification_source':{'local_path':str(rule),'sha256':sha256(rule.read_bytes()).hexdigest(),
                                     'source_reference':'SYNTHETIC_RULE_SOURCE'},'market_sources':{}}

    def seal(self):
        self.snapshot['payload_digest'] = digest(self.snapshot['tables'])

    def coverage(self):
        target = target_source(self.snapshot, self.config, self.at)
        return universe(self.snapshot, target, self.at, ROOT)

    def market(self, symbol='VT', *, incomplete=False, invalid=False):
        days=[]; d=datetime(2025,10,1,tzinfo=timezone.utc)
        while len(days)<260:
            if d.weekday()<5:days.append(d)
            d+=timedelta(days=1)
        quote={k:[] for k in ('open','high','low','close','volume')}
        sessions=[]
        for i, d in enumerate(days):
            c=100+i/10+(i%7)/100
            for k,v in [('open',c),('high',c+1),('low',c-1),('close',c+.1),('volume',1000+i)]:quote[k].append(v)
            sessions.append({'session_id':d.date().isoformat(),
                'open_at':d.replace(hour=13).isoformat(),'close_at':d.replace(hour=20).isoformat()})
        if incomplete:sessions[-1]['close_at']='2026-10-30T20:00:00Z'
        if invalid:quote['high'][-2]=quote['low'][-2]-1
        calendar=self.folder/(symbol+'_SYNTHETIC_CALENDAR.json')
        calendar.write_text(json.dumps({'exchange':'SYNTHETIC_EXCHANGE','timezone':'UTC',
            'provider':'SYNTHETIC_CALENDAR','version':'SYNTHETIC_1',
            'coverage_cutoff':'2026-11-01T23:00:00Z','sessions':sessions}))
        raw={'chart':{'error':None,'result':[{'meta':{'symbol':symbol,'currency':'USD',
            'exchangeTimezoneName':'UTC','exchangeName':'SYNTHETIC','instrumentType':'ETF'},
            'timestamp':[int(d.replace(hour=13).timestamp()) for d in days],
            'indicators':{'quote':[quote]}}]}}
        path=self.folder/(symbol+'_SYNTHETIC_MARKET.json');path.write_text(json.dumps(raw))
        return {'provider':'YAHOO_CHART','symbol':symbol,'provider_symbol':symbol,'currency':'USD',
            'timezone':'UTC','provider_exchange':'SYNTHETIC','exchange':'SYNTHETIC_EXCHANGE',
            'source_reference':'https://synthetic.invalid/observations','retrieved_at':self.at,
            'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
            'calendar_source':{'local_path':str(calendar),'sha256':sha256(calendar.read_bytes()).hexdigest()}}

    def test_latest_account_position_is_selected_not_added_to_history(self):
        coverage=self.coverage();rows={r['symbol']:r for r in coverage['assets']}
        self.assertEqual(coverage['expected_count'],2)
        self.assertEqual(rows['QQQ']['holdings'][0]['quantity'],'2')
        self.assertEqual(len(rows['QQQ']['holdings']),1)
        self.assertEqual(rows['VT']['coverage_basis'],'TARGET_ONLY')
        self.assertEqual(rows['VT']['holdings'],[])

    def test_preclose_acquisition_replayed_after_close_reports_stale_expected_session(self):
        descriptor=self.market('VT')
        calendar=json.loads(Path(descriptor['calendar_source']['local_path']).read_text())
        last=calendar['sessions'][-1]
        close=datetime.fromisoformat(last['close_at'])
        descriptor['retrieved_at']=(close-timedelta(minutes=1)).isoformat()
        value=read_market(descriptor,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
            profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
        self.assertNotEqual(value['observed_date'],last['session_id'])
        self.assertEqual(value['latest_expected_completed_session'],last['session_id'])
        self.assertIn(last['session_id'],{r['date'] for r in value['history_quality']['excluded_uncompleted_rows']})

    def test_delayed_provider_quote_is_not_promoted_to_final_close_after_exchange_close(self):
        descriptor=self.market('VT')
        calendar=json.loads(Path(descriptor['calendar_source']['local_path']).read_text())
        last=calendar['sessions'][-1];close=datetime.fromisoformat(last['close_at'])
        descriptor['retrieved_at']=(close+timedelta(minutes=5)).isoformat()
        path=Path(descriptor['local_path']);raw=json.loads(path.read_text())
        raw['chart']['result'][0]['meta']['regularMarketTime']=int((close-timedelta(minutes=15)).timestamp())
        path.write_text(json.dumps(raw));descriptor['sha256']=sha256(path.read_bytes()).hexdigest()
        value=read_market(descriptor,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
            profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
        self.assertNotEqual(value['observed_date'],last['session_id'])
        self.assertEqual(value['latest_expected_completed_session'],last['session_id'])
        excluded={r['date']:r['reason'] for r in value['history_quality']['excluded_uncompleted_rows']}
        self.assertEqual(excluded[last['session_id']],'PROVIDER_LATEST_BAR_FINAL_CLOSE_NOT_CONFIRMED')

    def test_cash_remains_in_weight_denominator_and_bond_is_separate(self):
        coverage=self.coverage()
        self.assertEqual(coverage['approval_weight_denominator'],'1')
        excluded={r['symbol']:r for r in coverage['excluded']}
        self.assertEqual(excluded[None]['route'],'CASH')
        self.assertEqual(excluded['SGOV']['route'],'V75_SEPARATE')
        self.assertEqual(excluded['SGOV']['targets'][0]['weight']['value'],'0.2')

    def test_second_account_is_preserved_without_cross_account_addition(self):
        position=deepcopy(self.snapshot['tables']['portfolio_position'][-1])
        position.update(account_key='SYNTHETIC_SECOND_ACCOUNT',quantity_decimal='3')
        self.snapshot['tables']['portfolio_position'].append(position);self.seal()
        held=next(r for r in self.coverage()['assets'] if r['symbol']=='QQQ')
        self.assertEqual(len(held['holdings']),2)
        self.assertEqual({r['quantity'] for r in held['holdings']},{'2','3'})

    def test_unconfirmed_latest_approval_does_not_fall_back(self):
        v=deepcopy(self.snapshot['tables']['final_target_version'][0])
        v.update(version_no=2,lifecycle_state='DRAFT')
        self.snapshot['tables']['final_target_version'].append(v);self.seal()
        with self.assertRaisesRegex(ValueError,'NOT_CURRENT_COMPLETE_CONFIRMED'):self.coverage()

    def test_duplicate_latest_position_is_rejected(self):
        row=deepcopy(self.snapshot['tables']['portfolio_position'][-1]);row['quantity_decimal']='99'
        self.snapshot['tables']['portfolio_position'].append(row);self.seal()
        with self.assertRaisesRegex(ValueError,'LATEST_POSITION_AMBIGUOUS'):self.coverage()

    def test_incomplete_weight_total_cannot_be_normalized(self):
        self.snapshot['tables']['final_target_allocation'][0]['weight_units']=500000;self.seal()
        with self.assertRaisesRegex(ValueError,'ALLOCATION_INVALID'):self.coverage()

    def test_no_money_base_still_reads_real_weights_without_inventing_amount(self):
        target=target_source(self.snapshot,self.config,self.at)
        self.assertEqual(target['weight_denominator'],'1')
        self.assertTrue(all(r['target_amount']['value_state']=='UNKNOWN'
                            for r in target['payload']['draft']['target_lines']))

    def test_native_menu_provider_runs_target_only_without_funding_or_cash_overlay(self):
        self.config['market_sources']={s:self.market(s) for s in ('VT','QQQ')}
        producer=MemberV82SourceProducer(**self.config)
        provider=OnDemandAnalysisProvider(producer,repo_root=ROOT)
        with patch('family_boundary.prepare_input',side_effect=AssertionError('Financial adapter called')):
            request,runner=provider(self.snapshot,{'question':'SYNTHETIC_MEMBER_REPLAY'})
            result=runner.analyze(request)
        self.assertEqual(result['summary']['expected'],2)
        self.assertEqual(result['summary']['native_components_computed'],2)
        self.assertFalse(result['cash_overlay_applied']);self.assertIsNone(result['canonical_result'])
        vt=next(r for r in result['positions'] if r['symbol']=='VT')
        self.assertIsNone(vt['holding']['quantity']);self.assertIsNone(vt['proposed_amount'])
        self.assertEqual(vt['holding']['quantity_state'],'UNKNOWN')
        self.assertIn('confirmed_position_quantity',vt['formal_conclusion']['deployment_gap']['missing_fields'])
        self.assertEqual(vt['formal_conclusion']['approved_v10_analysis']['qP']['status'],'UNKNOWN')
        self.assertIn('V82.evaluate_core_rule_state',vt['call_trace'])
        self.assertIn('V82.CMR7.complete_right_entry',vt['call_trace'])
        self.assertIsNotNone(vt['market']['numeric']['ma20'])
        self.assertEqual(vt['trade_action'],'NO_TRADE')
        technical=vt['market']['approved_technical']
        eps=next(r for r in technical['signals']['up_confirm'] if r['name']=='eps_guidance_not_worse')
        self.assertEqual(eps['truth'],'NOT_APPLICABLE')
        self.assertEqual(technical['trend_timing_inputs']['previous_technical']['up_confirm'][-1],'FALSE')
        qqq=next(r for r in result['positions'] if r['symbol']=='QQQ')
        self.assertEqual(qqq['core_observation']['actual_inputs']['valuation_waterfall'],
                         ['FORWARD_PE','EV_EBITDA','EV_SALES','FCF_YIELD'])
        runner.report['positions'][0]['holding']['quantity']='999999'
        with self.assertRaisesRegex(PermissionError,'NATIVE_SOURCE_REPLAY_MISMATCH'):
            runner.analyze(request)

    def test_foreign_client_config_is_rejected(self):
        self.config['client_id']='fam_'+'b'*32
        with self.assertRaisesRegex(PermissionError,'SNAPSHOT_OR_OWNER_MISMATCH'):
            MemberV82SourceProducer(**self.config)(self.snapshot,{'question':'SYNTHETIC'})

    def test_foreign_client_row_cannot_hide_under_a_matching_snapshot_digest(self):
        self.snapshot['tables']['portfolio_position'][0]['client_id']='fam_'+'b'*32;self.seal()
        with self.assertRaisesRegex(PermissionError,'FOREIGN_CLIENT_ROW'):
            MemberV82SourceProducer(**self.config)(self.snapshot,{'question':'SYNTHETIC'})

    def test_provider_symbol_conflict_cannot_borrow_other_asset(self):
        source=self.market();source['provider_symbol']='WRONG'
        with self.assertRaisesRegex(PermissionError,'PROVIDER_IDENTITY_CONFLICT'):
            read_market(source,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
                profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)

    def test_uncompleted_bar_is_excluded_at_original_acquisition(self):
        source=self.market(incomplete=True)
        result=read_market(source,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
            profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
        self.assertEqual(result['rows'],259)
        self.assertEqual(len(result['history_quality']['excluded_uncompleted_rows']),1)

    def test_invalid_bar_is_preserved_and_not_bridged_over(self):
        source=self.market(invalid=True)
        result=read_market(source,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
            profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
        self.assertEqual(result['rows'],1)
        self.assertEqual(len(result['history_quality']['invalid_source_rows']),1)
        self.assertEqual(result['history_quality']['discarded_before_last_gap'],258)
        self.assertEqual(result['source_sha256'],source['sha256'])
        independent=result['independent_close_observation']
        self.assertEqual(independent['rows'],260)
        self.assertIsNotNone(independent['numeric']['ma200'])
        self.assertIsNone(independent['numeric']['atr14'])
        self.assertFalse(independent['formal_deployment_eligible'])

    def test_bad_one_asset_calendar_does_not_erase_other_native_results(self):
        source=self.market();path=Path(source['calendar_source']['local_path'])
        data=json.loads(path.read_text());data['coverage_cutoff']='2020-01-01T00:00:00Z'
        path.write_text(json.dumps(data));source['calendar_source']['sha256']=sha256(path.read_bytes()).hexdigest()
        self.config['market_sources']={'VT':source,'QQQ':self.market('QQQ')}
        pack=MemberV82SourceProducer(**self.config)(self.snapshot,{'question':'SYNTHETIC_PARTIAL'})
        rows={r['symbol']:r for r in pack['member_v82_report']['positions']}
        self.assertEqual(rows['VT']['execution_status'],'SOURCE_BLOCKED')
        self.assertEqual(rows['QQQ']['execution_status'],'NATIVE_COMPONENTS_COMPUTED')
        self.assertEqual(rows['VT']['missing_inputs'][0]['reason'],'MEMBER_MARKET_CALENDAR_COVERAGE')

    def test_same_ticker_different_registered_listings_require_disambiguation(self):
        row=deepcopy(self.snapshot['tables']['portfolio_instrument'][0]);row['instrument_key']='SECOND_LISTING'
        self.snapshot['tables']['portfolio_instrument'].append(row);self.seal()
        with self.assertRaisesRegex(ValueError,'LISTING_AMBIGUOUS'):self.coverage()

    def test_changed_raw_bytes_fail_before_native_calculation(self):
        source=self.market();Path(source['local_path']).write_text('{}')
        with self.assertRaisesRegex(PermissionError,'HASH_MISMATCH'):
            read_market(source,symbol='VT',evaluation_at=self.at,repo_root=ROOT,
                profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)

    def test_equity_macro_independence_does_not_create_a_bond_macro_default(self):
        source=self.market('SGOV')
        with self.assertRaisesRegex(ValueError,'BOND_MACRO_SOURCE_REQUIRED'):
            read_market(source,symbol='SGOV',evaluation_at=self.at,repo_root=ROOT,
                profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)

"""Analysis A preserves real native facts without entering deployment B."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import holdings_analysis as H
import native_asset_source as M
from family_input import digest
from loop2_cash_scenario import build_cash_overlay


class HoldingAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)/'synthetic-project.md'
        p.write_text('- VT：Vanguard 7/31 P/E20.8x、P/B3.3x\n')
        rule=Path(self.tmp.name)/'synthetic-rules.md'
        rule.write_text('\n'.join(M.FORMAL_CLASSES)+'\n# 第四十九章｜VT／VWRA型\n')
        self.client='fam_'+'a'*32;self.owner={'client_id':self.client,'funding_domain':'US_BROKER',
            'broker':'SYNTHETIC_IB','account':'SYNTHETIC_IB_ACCOUNT','currency':'USD'}
        instrument={'instrument_key':'SYNTHETIC_VT','ticker':'VT','identity_state':'KNOWN','instrument_type':'ETF'}
        self.snapshot={'schema_version':'Family.W5.W1Snapshot.v1','client_id':self.client,
            'source_sha256':'a'*64,'payload_digest':'synthetic',
            'tables':{'portfolio_position':[{'instrument_key':instrument['instrument_key']}],
                'portfolio_instrument':[instrument]}}
        self.position={'instrument_key':instrument['instrument_key'],'quantity':'1.2500','quantity_state':'KNOWN',
            'source_instrument':instrument,'source_position':{'as_of_utc':None,
                'received_at_utc':'2026-10-20T00:00:00Z','source_kind':'SYNTHETIC','source_row':{}}}
        self.prepared=SimpleNamespace(payload={'positions':[self.position]})
        self.request={'client_id':self.client,'owner':self.owner,'run_id':'SYNTHETIC_RUN',
            'evaluation_at':'2026-10-27T12:00:00Z','client_snapshot':{'payload':self.snapshot},
            'expected_versions':{},'trade_authorization':'NONE'}
        self.context={'client_id':self.client,'expected_versions':{},'approved_document_target_source':{
            'local_source_path':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_PROJECT_SOURCE'}}
        raw_macro={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-01T00:00:00Z',
            'verification':{'ready':False}}
        self.macro={'payload':raw_macro,'digest':digest(raw_macro)}
        self.holdings={'client_id':self.client,'source_db_sha256':'a'*64,
            'snapshot_digest':'synthetic','analysis_security_positions':[],'ledger_only_positions':[]}
        self.producer=M.AssetSourceProducer(repo_root=ROOT,request_seed=self.request,context_seed=self.context,
            cash_policy={},classification_source={'local_path':str(rule),
                'sha256':hashlib.sha256(rule.read_bytes()).hexdigest(),'source_reference':'SYNTHETIC_RULE_CATALOG'},
            source_commit='SYNTHETIC_COMMIT')
        self.policy={'schema_version':'Family.W8.CashTrialPolicy.v1','missing_cash_value':'0','source_reference':'SYNTHETIC_AUTH'}
        scenario=build_cash_overlay({k:None for k in ('total','available','unsettled','reserved')},
            snapshot=self.snapshot,owner=self.owner,authorization=self.policy,run_id='SYNTHETIC_RUN')
        self.trial={'issues':[],'scenario':scenario,'decimal_values':scenario['effective_cash'],
            'owner':self.owner,'assumptions':scenario['assumptions']}

    def observations(self):
        import on_demand_market_observations as market
        return market.build_member_market_observations(self.snapshot,[],self.macro,repo_root=ROOT,
            evaluation_at=self.request['evaluation_at'])

    def report(self,observations=None):
        return H.build_analysis_report(self.producer,self.request,self.context,self.prepared,
            self.holdings,observations if observations is not None else self.observations(),self.trial)

    def test_analysis_source_branches_before_work3_work4_with_no_funding_fields(self):
        macro=self.macro
        frozen=deepcopy(self.snapshot)
        with patch.object(M,'prepare_input',return_value=self.prepared),\
             patch.object(M,'project_official_holdings',return_value=self.holdings),\
             patch.object(M,'cash_trial',return_value=self.trial),\
             patch('market_bridge.read_macro_snapshot',return_value=macro),\
             patch.object(M,'load_c_module',side_effect=AssertionError('Deployment adapter called')):
            pack=self.producer(self.snapshot,{'question':'SYNTHETIC_QUESTION'})
        self.assertEqual(pack['analysis_report']['status'],'ANALYSIS_PARTIAL')
        self.assertEqual(pack['analysis_report']['deployment_status']['status'],'NOT_RUN')
        self.assertNotIn('native_bundle',pack['request']);self.assertEqual(self.snapshot,frozen)

    def test_real_original_algorithms_and_raw_facts_remain_visible(self):
        row=self.report()['analysis_result']['positions'][0]
        self.assertIsNotNone(row['market']['numeric']['ma20'])
        self.assertIsNotNone(row['market']['numeric']['atr14'])
        self.assertIn('reclaim_ma20',row['market']['base_facts'])
        signals=[x for a in row['market']['observed_named_signals'].values() for x in a]
        self.assertTrue(any(x['truth']!='UNKNOWN' for x in signals))
        self.assertEqual(next(x for x in signals if x['name']=='atr_expanding_fast')['truth'],'UNKNOWN')
        self.assertIn('ORIGINAL.analytics.technical',row['call_trace'])

    def test_dated_valuation_source_values_are_mapped_without_forward_pe_invention(self):
        facts=H.vt_valuation_observations(self.context)
        self.assertEqual({v['metric_name']:v['current'] for v in facts},{'TRAILING_PE':'20.8','PB':'3.3'})
        self.assertTrue(all(v['freshness']=='UNKNOWN' and v['historical_median'] is None for v in facts))
        self.assertFalse(any(v['metric_name']=='FORWARD_PE' for v in facts))

    def test_missing_history_retains_position_and_precise_blocker(self):
        report=self.report({'assets':[],'missing':[{'symbol':'VT','code':'EXACT_SYMBOL_CACHE_UNAVAILABLE'}]})
        self.assertEqual(report['analysis_result']['coverage']['returned'],1)
        row=report['analysis_result']['positions'][0]
        self.assertEqual(row['status'],'ANALYSIS_BLOCKED')
        self.assertTrue(any(p['field_path']=='market.history' for p in row['issues']))
        self.assertEqual(report['deployment_status']['status'],'NOT_RUN')

    def test_cash_conflict_is_visible_but_does_not_remove_independent_analysis(self):
        self.trial['issues']=[{'code':'CASH_ASSUMPTION_CONFLICT','field_path':'cash_state.available'}]
        report=self.report();self.assertEqual(report['status'],'ANALYSIS_PARTIAL')
        self.assertTrue(report['analysis_result']['positions'][0]['market']['numeric'])
        self.assertTrue(any(p['code']=='CASH_ASSUMPTION_CONFLICT' for p in report['issues']))

    def test_analysis_never_publishes_deployment_canonical_or_mentor(self):
        report=self.report()
        self.assertIsNone(report['mentor']);self.assertIsNone(report['canonical_result'])
        self.assertEqual(report['trade_action'],'NO_TRADE')
        self.assertNotIn('Work4',str(report['call_trace']))

    def test_runner_rejects_cross_owner_position_and_changed_quantity(self):
        for key,value in [('owner',{**self.owner,'account':'OTHER'}),
                          ('holding',{'quantity':'9','observed_at':None})]:
            report=self.report();report['analysis_result']['positions'][0][key]=value
            report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
            with patch.object(H,'prepare_input',return_value=self.prepared),self.assertRaises(PermissionError):
                H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)

    def test_runner_rejects_future_market_even_if_report_redigested(self):
        report=self.report();report['analysis_result']['positions'][0]['market']['provider_verified_at']='2099-01-01T00:00:00Z'
        report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
        with patch.object(H,'prepare_input',return_value=self.prepared),self.assertRaises(PermissionError):
            H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)

    def test_runner_calls_original_boundary_and_rejects_fake_mentor(self):
        report=self.report();report['mentor']={'fake':'text'}
        report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
        with patch.object(H,'prepare_input',return_value=self.prepared) as guard,self.assertRaises(PermissionError):
            H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)
        guard.assert_called_once()

    def test_official_menu_keeps_partial_analysis_status_instead_of_completed(self):
        sys.path.insert(0,str(HERE.parent/'W7'))
        from family_menu import FamilyMenu
        menu=FamilyMenu(SimpleNamespace(require_login=lambda:'SYNTHETIC_LOGIN'),
            project_name='SYNTHETIC',login_account='SYNTHETIC_LOGIN',
            handlers={'deployment_pace':lambda payload:{'status':'ANALYSIS_PARTIAL',
                'deployment_status':{'status':'NOT_RUN'}}})
        output=menu.select('04')
        self.assertEqual(output['status'],'ANALYSIS_PARTIAL')
        self.assertEqual(output['result']['deployment_status']['status'],'NOT_RUN')


if __name__=='__main__':unittest.main()

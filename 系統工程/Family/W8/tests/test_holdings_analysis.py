"""Analysis A preserves real native facts without entering deployment B."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
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
        runtime=ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'
        sys.path.insert(0,str(runtime))
        from livingwater_v82_runtime.canonical_output import CANONICAL_FIELD_NAMES
        rule.write_text('\n'.join(M.FORMAL_CLASSES)+'\n# 第四十九章｜VT／VWRA型\n'+
            'MA_RECLAIM_N HISTOGRAM_CONTRACTING RSI<30 20日收盤新高\n'+
            '\n'.join(f'|{n}|{field}|Synthetic|Synthetic|Synthetic|'+
                ('Optional' if n in (5,22,23) else 'Required')+'|Yes|Synthetic policy|'
                for n,field in enumerate(CANONICAL_FIELD_NAMES,1)))
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
        manifest=json.loads((ROOT/'data/market_history/global/manifest.json').read_text())
        latest=max(datetime.fromisoformat(r['last_verified_utc'].replace('Z','+00:00')) for r in manifest['items'].values() if r.get('status')=='OK')
        self.request['evaluation_at']=max(datetime.fromisoformat(self.request['evaluation_at'].replace('Z','+00:00')),latest+timedelta(seconds=1)).isoformat()
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

    def enable_product(self,symbol):
        rule=Path(self.producer.class_source['local_path'])
        rule.write_text(rule.read_text()+'\n廣泛分散核心市場結構 → `A`\n')
        self.producer.class_source['sha256']=hashlib.sha256(rule.read_bytes()).hexdigest()
        url=('https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf'
            if symbol=='VT' else 'https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating')
        facts=(['FTSE Global All Cap Index','Passively managed','developed and emerging',
            'large-, mid-, and small-capitalization'] if symbol=='VT' else
            ['FTSE All-World Index','passive management','physical acquisition','large and mid-sized','developed and emerging'])
        path=Path(self.tmp.name)/(symbol+'.json')
        path.write_text(json.dumps({'symbol':symbol,'source_url':url,'excerpts':facts,
            'isin':'IE00BK5BQT80','listing':{'exchange':'XLON','currency':'USD','reuters':'VWRA.L'}}))
        self.producer.product_sources[symbol]={'local_path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_verified_product_routes_to_core_and_ma20_comparison_is_not_gate(self):
        self.enable_product('VT')
        obs=self.observations();obs['assets'][0]['base_facts']['above_ma20']=True
        row=self.report(obs)['analysis_result']['positions'][0]
        core=row['core_observation']
        self.assertEqual(row['native_product_identity']['engine_route'],'V82_GLOBAL_ETF_CORE')
        self.assertEqual(core['actual_inputs']['ma20_ok'],'UNKNOWN')
        self.assertIn('safety.material_events',[g['field_path'] for g in core['input_gaps']])
        self.assertFalse(core['result']['permission']['new_buy_order_permission'])
        self.assertEqual(row['requirements']['optional_unavailable'],['secondary_framework'])

    def test_vwra_routes_only_with_its_independent_product_evidence(self):
        self.enable_product('VWRA')
        self.position['source_instrument']['ticker']='VWRA'
        self.position['source_instrument']['quote_currency']='USD'
        row=self.report()['analysis_result']['positions'][0]
        self.assertIsNotNone(row['core_observation'])
        self.assertEqual(row['valuation_observations'],[])
        self.producer.product_sources['VWRA']=self.producer.product_sources.pop('VWRA')
        self.producer.product_sources['VT']=self.producer.product_sources.pop('VWRA')
        row=self.report()['analysis_result']['positions'][0]
        self.assertIsNone(row['core_observation'])

    def test_issuer_values_remove_only_their_actual_value_gaps_not_direction(self):
        from core_analysis_inputs import issuer_inputs,valuation_path_audit
        facts={'source_url':'SYNTHETIC_ISSUER','source_sha256':'f'*64,'as_of':'2026-09-30',
            'metrics':{'TRAILING_PE':{'value':'20','unit':'multiple'},
                'PB':{'value':'3','unit':'multiple'},'ROE':{'value':'15','unit':'percent'},
                'EARNINGS_GROWTH':{'value':'10','unit':'percent'}}}
        metrics,fields=issuer_inputs(facts)
        self.assertTrue(all(f['field_value_state']=='KNOWN' for f in fields))
        self.assertTrue(all(f['direction']=='UNKNOWN' for f in fields))
        paths=valuation_path_audit(metrics)
        self.assertNotIn('current',paths[1]['missing_fields'])
        self.assertIn('own_historical_reference_or_authorized_range',paths[1]['missing_fields'])
        self.assertEqual(paths[0]['metric'],'FORWARD_PE')
        self.assertIn('current',paths[0]['missing_fields'])

    def test_original_core_executes_legal_fallback_without_all_metrics(self):
        self.enable_product('VT')
        obs=self.observations()['assets'][0]
        result=self.producer.core_observation(obs,valuation_metrics=[{
            'metric_name':'PB','current':'3','historical_median':'3','data_quality':'OK',
            'freshness':'FRESH','pit_status':'VERIFIED','unit':'multiple',
            'source_reference':'SYNTHETIC_LEGAL_PB_SCALE','as_of':'2026-10-26'}])
        self.assertEqual(result['result']['valuation']['primary_metric'],'PB')
        self.assertEqual(result['result']['valuation']['level'],'NORMAL')
        self.assertTrue(result['result']['valuation']['fallback_used'])
        self.assertEqual(result['actual_inputs']['ma20_ok'],'UNKNOWN')

    def test_formal_signal_mapping_preserves_false_and_unknown_independently(self):
        from formal_analysis_signals import map_formal_observations
        from technical_source_bridge import NAMES
        vectors={k:[{'name':n,'truth':'UNKNOWN'} for n in names] for k,names in NAMES.items()}
        rows=[{'Close':float(n)} for n in range(1,22)]
        formal=map_formal_observations(rows,{'macd_histogram':-2,'rsi14':40},
            {'macd_histogram':-1,'rsi14':45},{'reclaim_ma20':False},{},vectors,self.producer.class_source)
        known={r['name']:r['truth'] for g in vectors.values() for r in g}
        self.assertEqual(known['macd_bear_hist_shrinking_or_positive'],'FALSE')
        self.assertEqual(known['above_ma20'],'FALSE')
        self.assertEqual(known['new_20d_close_high'],'TRUE')
        self.assertEqual(known['break_confirmed_swing_high'],'UNKNOWN')
        self.assertEqual(known['kd_golden_cross'],'UNKNOWN')
        self.assertFalse(formal['reduction_candidates_used'])

    def test_report_delivery_is_independent_of_missing_orders_and_target(self):
        self.enable_product('VT');report=self.report();row=report['analysis_result']['positions'][0]
        delivery=row['current_analysis']
        self.assertTrue(delivery['analysis_report_delivered'])
        self.assertEqual(report['analysis_delivery']['reports_delivered'],1)
        self.assertFalse(delivery['acceptance']['full_04_passed'])
        self.assertIsNone(delivery['execution_amount']['amount'])
        self.assertIsNotNone(delivery['technical']['numeric']['ma20'])
        self.assertIsNone(report['canonical_result']);self.assertIsNone(report['mentor'])
    def test_published_v70_forward_reaches_core_and_left_price_without_publication_metadata(self):
        self.enable_product('VT')
        raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-01T00:00:00Z',
            'verification':{'ready':True},'indicators':{'m03_vt':{'value':'15.9','unit':'倍 Forward',
                'status':'OK','dataDate':'2026-09-30','source':'SYNTHETIC_PROVIDER',
                'sourceEvidence':{'label':'Forward PE','value':'15.9','source_url':'SYNTHETIC_PROVIDER'}}}}
        self.request['macro_snapshot']={'payload':raw,'digest':digest(raw),'source_sha256':'a'*64}
        row=self.report()['analysis_result']['positions'][0]
        self.assertEqual(row['core_observation']['result']['valuation']['level'],'NORMAL')
        self.assertEqual(row['formal_conclusion']['left_inputs']['price_condition_at_least_one'],'TRUE')
        self.assertEqual(row['current_analysis']['valuation']['native_result']['level'],'NORMAL')
        self.assertIsNone(row['valuation_observations'][0]['available_at'])
        self.assertEqual(row['formal_conclusion']['formal_stage'],'UNKNOWN')
        self.assertTrue(row['current_analysis']['analysis_report_delivered'])
        self.assertFalse(row['current_analysis']['current_judgment']['execution_authorized'])
    def test_owner_scoped_judgment_reuses_original_selector_without_execution_permission(self):
        self.enable_product('VT');row=self.report()['analysis_result']['positions'][0]
        row['core_observation']['result']['valuation']['formal_output_eligible']=True
        row['core_observation']['result']['technical']={'right_confirmation':'TRUE','runaway_up':'FALSE','runaway_down':'FALSE'}
        row['market']['approved_technical']={'off_low':'TRUE'}
        from current_analysis_delivery import current_judgment
        out=current_judgment(row,ROOT)
        self.assertEqual(out['mode'],'Right Confirmation');self.assertEqual(out['stage_reference'],'STAGE_8')
        self.assertFalse(out['execution_authorized']);self.assertFalse(out['formal_deployment_decision'])
        self.assertFalse(row['core_observation']['result']['permission']['new_buy_order_permission'])
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

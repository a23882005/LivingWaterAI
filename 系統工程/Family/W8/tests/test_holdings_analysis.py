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
    def test_price_currency_requires_same_holding_and_explicit_per_share_unit(self):
        position={'source_instrument':{'ticker':'SYNTHETIC'},'source_position':{'source_row':{'id':'own'}}}
        fact={'value_state':'KNOWN','currency_code':'USD','unit':'USD_PER_SHARE'}
        holding={'symbol':'SYNTHETIC','source_row':{'id':'own'},
            'source_fields':{'last_price_displayed':[fact]}}
        holdings={'analysis_security_positions':[holding]}
        self.assertEqual(H.holding_price_currency(position,holdings)['quote_currency'],'USD')
        holding['source_row']={'id':'other'}
        self.assertIsNone(H.holding_price_currency(position,holdings))
        holding['source_row']={'id':'own'};fact['unit']='USD'
        self.assertIsNone(H.holding_price_currency(position,holdings))

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

    def test_industry_etfs_use_independent_issuer_identity_and_keep_their_own_route(self):
        source=self.producer.class_source;p=Path(source['local_path'])
        p.write_text(p.read_text()+'\n`SECTOR_ETF / INDUSTRY_ETF / THEME_ETF` → `C`\n'+
            'SOXX（iShares Semiconductor ETF）專屬半導體框架\n第四十七章｜PPH型\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        for symbol in ('SOXX','SMH','PPH'):
            identity=M.classification(symbol,source)
            self.assertEqual(identity['asset_type'],'INDUSTRY_ETF')
            self.assertEqual(identity['asset_grade'],'C')
            self.assertNotIn('V82_GLOBAL_ETF_CORE',identity['analysis_capabilities'])
        p.write_text(p.read_text()+'\n## 32.8 Semiconductor｜半導體\nForward P/E → EV/EBITDA → EV/Sales → P/S → FCF Yield\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        self.position['source_instrument']['ticker']='SOXX'
        row=self.report()['analysis_result']['positions'][0]
        self.assertEqual(row['native_product_identity']['engine_route'],'V82_SEMICONDUCTOR_CORE')
        self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'],
            ['FORWARD_PE','EV_EBITDA','EV_SALES','PS','FCF_YIELD'])
        self.assertEqual(row['core_observation']['result']['valuation']['level'],'UNKNOWN')
        self.assertTrue(row['core_observation']['actual_inputs']['right_signals'])
        from core_analysis_inputs import issuer_inputs
        facts={'metrics':{'EV_EBITDA':{'value':'12','unit':'multiple'}},'source_url':'SYNTHETIC',
            'source_sha256':'a'*64,'as_of':'2026-10-27'}
        metrics,_=issuer_inputs(facts,allowed_metrics=['EV_EBITDA'])
        self.assertEqual(metrics[0]['current'],'12')
        self.assertEqual(metrics[0]['metric_name'],'EV_EBITDA')

        p.write_text(p.read_text()+'\n製藥／醫療ETF：Forward P/E → EV/EBITDA → FCF Yield\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        self.position['source_instrument']['ticker']='PPH'
        healthcare=self.report()['analysis_result']['positions'][0]
        self.assertEqual(healthcare['native_product_identity']['engine_route'],'V82_HEALTHCARE_CORE')
        self.assertEqual(healthcare['core_observation']['actual_inputs']['valuation_waterfall'],
            ['FORWARD_PE','EV_EBITDA','FCF_YIELD'])
        wrong=HERE/'PPH_product_identity.json'
        with self.assertRaisesRegex(ValueError,'INDEPENDENT_INDUSTRY_ETF_STRUCTURE_EVIDENCE_REQUIRED'):
            M.classification('SOXX',source,{'local_path':str(wrong),
                'sha256':hashlib.sha256(wrong.read_bytes()).hexdigest()})

    def test_london_global_etf_uses_own_identity_and_forward_value(self):
        source=self.producer.class_source;p=Path(source['local_path'])
        p.write_text(p.read_text()+'\n廣泛分散核心市場結構 → `A`\n'+
            '| VT／VWRA型 | `<14` | `>=14 且 <18` | `>=18 且 <20` | `>=20 且 <23` | `>=23` |\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        identity=M.classification('VALU',source)
        self.assertEqual(identity['asset_type'],'BROAD_ETF');self.assertEqual(identity['asset_grade'],'A')
        self.assertIn('/E161/',identity['grade_evidence']['source_url'])
        from v10_source_observations import current_forward_observations
        facts={'symbol':'VALU','source_url':'SYNTHETIC_PROVIDER','source_sha256':'a'*64,'as_of':'2026-10-28',
            'source_original_data_date':None,'as_of_basis':'CURRENT_PROVIDER_OBSERVATION__NOT_ORIGINAL_FINANCIAL_DATE',
            'metrics':{'FORWARD_PE':{'value':'16','unit':'multiple'}},
            'current_forward_observation':{'label':'Forward PE','metric_name':'FORWARD_PE',
                'purpose':'OWNER_AUTHORIZED_RECENT_CURRENT_ANALYSIS_ONLY'}}
        observed=current_forward_observations(facts,identity,source)
        self.assertEqual(observed[0]['valuation_level'],'NORMAL')
        self.assertIsNone(observed[0]['source_original_data_date'])
        self.assertFalse(observed[0]['historical_publication_time_verified'])
        facts['current_forward_observation']['label']='Trailing PE'
        self.assertEqual(current_forward_observations(facts,identity,source),[])
        facts['current_forward_observation']['label']='Forward PE';facts['symbol']='VT'
        self.assertEqual(current_forward_observations(facts,identity,source),[])
        wrong=HERE/'QQQ_product_identity.json'
        with self.assertRaisesRegex(ValueError,'STRUCTURE_EVIDENCE_REQUIRED'):
            M.classification('VALU',source,{'local_path':str(wrong),
                'sha256':hashlib.sha256(wrong.read_bytes()).hexdigest()})

    def test_defence_theme_identity_has_its_own_formal_waterfall(self):
        source=self.producer.class_source;p=Path(source['local_path'])
        p.write_text(p.read_text()+'\n`SECTOR_ETF / INDUSTRY_ETF / THEME_ETF` → `C`\n'+
            '第五十二章｜國防／航太／軍工型\n## 32.9 Defense｜國防軍工\n'+
            'Forward P/E → EV/EBITDA → FCF Yield → EV/Sales\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        identity=M.classification('NATO',source)
        self.assertEqual(identity['asset_type'],'THEME_ETF');self.assertEqual(identity['asset_grade'],'C')
        self.assertIn('V82_DEFENCE_CORE',identity['analysis_capabilities'])
        self.assertEqual(identity['valuation_waterfall'],['FORWARD_PE','EV_EBITDA','FCF_YIELD','EV_SALES'])

    def test_company_core_runs_without_inventing_grade_thesis_or_etf_waterfall(self):
        source=self.producer.class_source;p=Path(source['local_path'])
        p.write_text(p.read_text()+'\n單一上市公司之普通股／股票權益\n'+
            '## 32.8 Semiconductor｜半導體\nForward P/E → EV/EBITDA → EV/Sales → P/S → FCF Yield\n')
        source['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        for symbol in ('NVDA','IBKR'):
            self.position['source_instrument']['ticker']=symbol
            row=self.report()['analysis_result']['positions'][0]
            self.assertEqual(row['native_product_identity']['asset_type'],'INDIVIDUAL_STOCK')
            self.assertEqual(row['native_product_identity']['asset_grade'],'UNKNOWN')
            self.assertEqual(row['core_observation']['function'],'V82.evaluate_core_rule_state')
            self.assertEqual(row['core_observation']['structural_confirmation_applicability'],'REQUIRED')
            self.assertEqual(row['core_observation']['result']['structural_risk']['state'],'UNKNOWN')
            self.assertIsNone(row['formal_conclusion']['etf_viability_audit'])
            self.assertEqual(row['formal_conclusion']['individual_thesis_audit']['scope'],'INDIVIDUAL_STOCK__NOT_ETF_VIABILITY')
            self.assertIsNone(row['formal_conclusion']['canonical_target_rate'])
            self.assertEqual(row['native_product_identity']['company_listing_source']['symbol'],symbol)
            if symbol=='IBKR':
                self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'],[])
            else:self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'][1],'EV_EBITDA')

    def test_owner_no_orders_propagates_to_report_and_mentor_without_guessing_judgment(self):
        self.producer.order_confirmation={'schema_version':'Family.W8.OwnerNoOpenOrders.v1',
            'client_id':self.client,'owner':deepcopy(self.owner),'no_open_orders':True,
            'source_reference':'SYNTHETIC_OWNER_NO_ORDERS'}
        report=self.report();row=report['analysis_result']['positions'][0]
        self.assertEqual(report['order_source']['active_orders'],[])
        self.assertEqual(row['current_analysis']['long_term_allocation_target']['status'],'LOOP2_TARGET_PRODUCER_PENDING')
        self.assertFalse(row['current_analysis']['long_term_allocation_target']['owner_input_required'])
        self.assertTrue(row['current_analysis']['current_round_deployment_target']['not_portfolio_allocation_weight'])
        self.assertNotIn('active_orders_and_fill_reconciliation',row['current_analysis']['recommendation']['missing_fields'])
        self.assertEqual(report['recommendation_report']['net_after_orders_status'],'OWNER_CONFIRMED_NO_OPEN_ORDERS')
        self.assertNotIn('掛單扣除後淨額待確認',report['recommendation_report']['markdown'])
        self.assertIsNone(report['canonical_result'])
        # A verified empty order source is not a mode/target/funding assertion.
        self.assertIsNone(row['current_analysis']['recommendation']['buy_gap_amount'])
        self.producer.order_confirmation['client_id']='OTHER_MEMBER'
        with self.assertRaisesRegex(PermissionError,'SCOPE_MISMATCH'):self.report()

    def test_report_delivery_is_independent_of_missing_orders_and_target(self):
        self.enable_product('VT');report=self.report();row=report['analysis_result']['positions'][0]
        delivery=row['current_analysis']
        self.assertTrue(delivery['analysis_report_delivered'])
        self.assertEqual(report['analysis_delivery']['reports_delivered'],1)
        self.assertFalse(delivery['acceptance']['full_04_passed'])
        self.assertIsNone(delivery['execution_amount']['amount'])
        self.assertIsNotNone(delivery['technical']['numeric']['ma20'])
        self.assertIsNone(report['canonical_result']);self.assertFalse(report['mentor']['full_native_deployment_mentor'])
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
    def test_technical_r_alone_does_not_replace_same_run_full_entry_and_stage(self):
        self.enable_product('VT');row=self.report()['analysis_result']['positions'][0]
        row['core_observation']['result']['valuation']['formal_output_eligible']=True
        row['core_observation']['result']['technical']={'right_confirmation':'TRUE','runaway_up':'FALSE','runaway_down':'FALSE'}
        row['market']['approved_technical']={'off_low':'TRUE'}
        from current_analysis_delivery import current_judgment
        out=current_judgment(row,ROOT)
        self.assertEqual(out['mode'],'UNKNOWN');self.assertEqual(out['stage_reference'],'UNKNOWN')
        self.assertFalse(out['execution_authorized']);self.assertFalse(out['formal_deployment_decision'])
        self.request['confirmed_target']={'payload':{'draft':{'target_lines':[{'ticker':'VT',
            'weight':{'value_state':'KNOWN','value':'0.2'},
            'target_amount':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}]}}}
        row['formal_conclusion']['approved_project_target']={'value_state':'KNOWN','amount':'1000','currency':'USD'}
        before=deepcopy(self.request)
        from current_analysis_delivery import deliver
        view=deliver(row,self.request,repo_root=ROOT)
        self.assertEqual(view['long_term_allocation_target']['weight']['value'],'0.2')
        self.assertIsNone(view['current_round_deployment_target']['cumulative_rate'])
        self.assertIsNone(view['current_round_deployment_target']['amount'])
        self.assertEqual(self.request,before)

        self.assertFalse(row['core_observation']['result']['permission']['new_buy_order_permission'])
    def test_readable_report_cannot_diverge_from_native_results_after_redigest(self):
        for field in ('rows','html'):
            report=self.report();view=report['recommendation_report']
            if field=='rows':view['rows'][0]['holding_gap_amount']='999999'
            else:view['html']='<p>BUY 999999</p>'
            view['digest']=digest({k:v for k,v in view.items() if k!='digest'})
            report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
            with patch.object(H,'prepare_input',return_value=self.prepared),self.assertRaisesRegex(PermissionError,'READABLE_REPORT_SOURCE_RESULT_MISMATCH'):
                H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)

    def test_approved_decision_replays_supplementary_bytes_and_native_analysis(self):
        self.enable_product('VT')
        from v82_approved_context import validate
        path=Path(self.tmp.name)/'SYNTHETIC_APPROVED_SOURCE.json'
        path.write_text(json.dumps({'schema_version':'Family.W8.V82ApprovedSource.v1',
            'client_id':self.client,'owner':self.owner,'asset_id':'VT',
            'source_db_sha256':self.snapshot['source_sha256'],
            'source_reference':'SYNTHETIC_PIT_SOURCE','available_at':self.request['evaluation_at']}))
        self.context['v82_approved_sources']={'VT':{'local_path':str(path),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
        report=self.report();row=report['analysis_result']['positions'][0]
        validate(ROOT,row,self.request,self.context,target_projection=report['loop2_target_projection'])
        row['formal_conclusion']['approved_v10_analysis']['formal_stage']='STAGE_9'
        with self.assertRaisesRegex(PermissionError,'NATIVE_REPLAY_MISMATCH'):
            validate(ROOT,row,self.request,self.context,target_projection=report['loop2_target_projection'])
        path.write_text('{}')
        with self.assertRaisesRegex(PermissionError,'SOURCE_HASH_MISMATCH'):
            validate(ROOT,row,self.request,self.context,target_projection=report['loop2_target_projection'])

    def test_readable_report_is_complete_independently_of_pending_order_net(self):
        r=self.report();view=r['recommendation_report']
        self.assertEqual(view['report_delivery_status'],'COMPLETE')
        self.assertEqual(view['positions_returned'],1)
        self.assertEqual(view['net_after_orders_status'],'PENDING_OWNER_ORDER_CONFIRMATION')
        self.assertIsNone(view['rows'][0]['holding_gap_amount'])
        self.assertIsNone(view['rows'][0]['proposed_existing_asset_redeployment_amount'])
        self.assertIn('持股缺口不等於本次立即應買金額',view['markdown'])
        self.assertIn('<table>',view['html']);self.assertFalse(view['full_native_deployment_complete'])

    def test_scoped_mentor_preserves_unknown_buy_amount_and_zero_external_contribution(self):
        from new_investment_scenario import build_plan
        policy={'schema_version':'Family.W8.NewInvestmentTrialPolicy.v1','client_id':self.client,
            'new_external_money':'0','source_reference':'SYNTHETIC_OWNER_ZERO_EXTERNAL'}
        plan=build_plan(self.snapshot,self.owner,policy)
        report=H.build_analysis_report(self.producer,self.request,self.context,self.prepared,
            self.holdings,self.observations(),self.trial,investment=plan)
        item=report['mentor']['items'][0]
        self.assertEqual(item['recommendation']['new_external_funding_buy_amount'],'0')
        self.assertIsNone(item['recommendation']['recommended_buy_amount']['amount'])
        self.assertEqual(item['recommendation']['recommended_buy_amount']['status'],'UNKNOWN')
        self.assertIn('既有現金及資產調整另計',item['explanation'])
        self.assertFalse(report['mentor']['broker_execution_allowed'])
        from mentor_scope import validate_advice_scope
        scope=validate_advice_scope(report['mentor'])
        self.assertIs(scope['execution_advice_allowed'],True)
        self.assertIs(scope['financial_mutation_allowed'],False)
        with patch.object(H,'prepare_input',return_value=self.prepared):
            self.assertEqual(H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)['mentor'],report['mentor'])

    def test_scoped_mentor_cannot_change_amount_or_other_owner_after_redigest(self):
        for field,value in [('new_external_funding_buy_amount','999'),('asset_id','OTHER_ASSET')]:
            report=self.report();report['mentor']['items'][0]['recommendation'][field]=value
            report['report_digest']=digest({k:v for k,v in report.items() if k!='report_digest'})
            with patch.object(H,'prepare_input',return_value=self.prepared),self.assertRaises(PermissionError):
                H.HoldingsAnalysisRunner(context=self.context,report=report).analyze(self.request)

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

    def test_analysis_publishes_scoped_work9_mentor_without_full_deployment_canonical(self):
        report=self.report()
        self.assertFalse(report['mentor']['full_native_deployment_mentor']);self.assertIsNone(report['canonical_result'])
        self.assertTrue(any('Work9.build_holdings_recommendation_return' in str(c) for c in report['call_trace']))
        self.assertEqual(len(report['mentor']['items']),1)
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


import native_funding_advice as F


class NativeFundingAdviceTest(unittest.TestCase):
    def case(self):
        stock=json.loads((HERE.parent/'W5/tests/fixtures/work4_adapter_request.json').read_text())
        w=stock['work3_handoff'];client=w['client_state_context']['payload']['client_id']
        owner={**w['owner'],'client_id':client,'currency':w['currency']}
        contexts=deepcopy(stock['c7_funding_context']['contexts'])
        for c in contexts:
            c['bucket_new_investment_amount']=0
            c['brokerage_cash_state']={k:0 for k in ('total','available','unsettled','reserved')}
            for leg in c['executable_budget'].values():leg['amount']=0
        selected=next(c for c in contexts if c['domain']==owner['funding_domain'])
        selected['brokerage_cash_state']['total']=500
        snapshot={'client_id':client,'source_sha256':'a'*64,'tables':{}}
        at='2026-10-27T23:59:00+00:00'
        request={'run_id':w['run_id'],'client_id':client,'owner':owner,'evaluation_at':at,
            'client_snapshot':{'payload':snapshot,'as_of':at},'expected_versions':{'target':'SYNTHETIC'},
            'macro_snapshot':{'digest':'b'*64,'asOf':at,'payload':{'scope':'SYNTHETIC'}},
            'confirmed_target':{'payload':{'confirmation_evidence':deepcopy(w['final_target']['confirmation_proof']),
                'draft':{'allocation_id':w['final_target']['allocation_id'],
                    'target_lines':[{'instrument_id':'QQQ','ticker':'QQQ',
                        'target_amount':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}]}}}}
        row={'instrument_id':'SYNTHETIC_QQQ','symbol':'QQQ','holding':{'quantity':'5'},
            'market':{'observed_close':'100'},'native_product_identity':{'asset_type':'BROAD_ETF','asset_grade':'B'},
            'core_observation':{'result':{'permission':{'hard_gate':'NOT_TRIGGERED','new_buy_order_permission':True,'reason_codes':[]}}},
            'current_analysis':{'current_judgment':{'target_rate_reference':'0.95'},
                'recommendation':{'confirmed_holdings_component':{'positive_gap_amount':'450'}}}}
        producer=SimpleNamespace(root=ROOT,fx_observation=None,funding_contexts=lambda *args:(deepcopy(contexts),{}))
        trial={'decimal_values':{'available':'0'},'cash_state':deepcopy(selected['brokerage_cash_state'])}
        investment={'total_new_investment_amount':'0','account_contributions':{}}
        tactical={'native_currency_amounts':{'stock':'1000','bond':'0','dry_powder':'0'}}
        return producer,request,{'analysis_result':{'positions':[row]}},trial,investment,tactical

    def test_bond_component_route_never_enters_stock_funding_adapter(self):
        p,r,report,trial,investment,tactical=self.case()
        row=report['analysis_result']['positions'][0]
        row['symbol']='SGOV';row['core_observation']=None
        row['native_product_identity']={'engine_route':'V75_PREDICATES','asset_type':None,'asset_grade':'UNKNOWN'}
        out=F.build(p,r,report,trial=trial,investment=investment,tactical=tactical)
        item=out['items'][row['instrument_id']]
        self.assertEqual(item['status'],'BOND_DELEGATED_TO_V75')
        self.assertEqual(item['issues'],[])
        self.assertEqual(item['call_trace'],[])
        self.assertNotIn('stock_request',item);self.assertNotIn('native_plan',item)

    def test_original_work4_and_native_zero_budget_plan_keep_positive_gap(self):
        p,r,report,trial,investment,tactical=self.case()
        before=deepcopy((r,report,trial))
        out=F.build(p,r,report,trial=trial,investment=investment,tactical=tactical)
        item=out['items']['SYNTHETIC_QQQ']
        self.assertEqual(item['status'],'CASH_TRIAL_ADVICE_COMPUTED',item['issues'])
        self.assertEqual(item['native_plan']['execution_amount'],'0')
        self.assertEqual(item['native_plan']['residual_gap_amount'],'450.00')
        self.assertIn('MAXIMUM_ALLOWED_BUY_AMOUNT_ZERO',item['native_plan']['reason_codes'])
        self.assertFalse(item['active_orders_assumed_empty'])
        self.assertEqual((r,report,trial),before)
        report['native_funding_advice']=out
        report['analysis_result']['positions'][0]['current_analysis']['native_funding_advice']=F.delivery(item)
        F.validate(ROOT,report,r)
        item['native_plan']['execution_amount']='900'
        report['analysis_result']['positions'][0]['current_analysis']['native_funding_advice']=F.delivery(item)
        with self.assertRaisesRegex(PermissionError,'PLAN_MISMATCH'):F.validate(ROOT,report,r)

    def test_positive_cash_without_budget_assignment_is_not_zeroed(self):
        p,r,report,trial,investment,tactical=self.case();trial['decimal_values']['available']='50'
        out=F.build(p,r,report,trial=trial,investment=investment,tactical=tactical)
        item=out['items']['SYNTHETIC_QQQ']
        self.assertEqual(item['status'],'INPUT_UNAVAILABLE')
        self.assertIn('funding.equity_executable_budget_assignment',[x['field_path'] for x in item['issues']])
        self.assertNotIn('native_plan',item)

    def test_official_opaque_instrument_key_maps_to_unique_native_ticker(self):
        p,r,report,trial,investment,tactical=self.case()
        r['confirmed_target']['payload']['draft']['target_lines'][0]['instrument_id']='OPAQUE_W1_KEY'
        out=F.build(p,r,report,trial=trial,investment=investment,tactical=tactical)
        item=out['items']['SYNTHETIC_QQQ']
        self.assertEqual(item['status'],'CASH_TRIAL_ADVICE_COMPUTED',item['issues'])
        targets=item['stock_request']['work3_handoff']['final_target']['payload']['instrument_targets']
        self.assertEqual(targets['QQQ']['project_target_position'],'1000')
        self.assertEqual(targets['OPAQUE_W1_KEY'],targets['QQQ'])

    def test_two_roles_for_one_ticker_are_not_merged_into_native_target(self):
        p,r,report,trial,investment,tactical=self.case()
        lines=r['confirmed_target']['payload']['draft']['target_lines']
        duplicate=deepcopy(lines[0]);duplicate['instrument_id']='SECOND_ROLE'
        lines.append(duplicate)
        out=F.build(p,r,report,trial=trial,investment=investment,tactical=tactical)
        item=out['items']['SYNTHETIC_QQQ']
        self.assertEqual(item['status'],'INPUT_UNAVAILABLE')
        self.assertTrue(any(i['field_path']=='approved_project_target_amount' for i in item['issues']))
        self.assertNotIn('native_plan',item)


class ApprovedZeroTargetMappingTest(unittest.TestCase):
    def pack(self,paragraph):
        from approved_target_input import build_approved_target_view
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        path=Path(tmp.name)/'synthetic-approved.md';line='| VT | 100% | NT$1,000 | core |'
        path.write_text('| 標的 | 目標比例 | 目標台幣 | 角色 |\n|---|---|---|---|\n'+line+'\n'+paragraph)
        return build_approved_target_view(client_id='fam_'+'a'*32,source_path=path,
            source_reference='SYNTHETIC_APPROVED',source_available_at='2026-10-01T00:00:00Z',
            target_version=1,allocation_version='SYNTHETIC',rows=[{'source_line':line,'weight':'1'}],
            mappings=[{'instrument_id':'VT','ticker':'VT','asset_type':'ETF'}])

    def test_explicit_zero_percent_is_mapped_without_absence_or_sell_inference(self):
        from approved_target_input import enrich_document_target_view
        pack=self.pack('- ALPHA／BETA／GAMMA／DELTA目前仍屬既有小部位，長期目標0%；0%不等於立刻賣。\n')
        before=deepcopy(pack);view,proof=enrich_document_target_view(pack['target'],pack['trusted_approved_target_source'])
        rows=view['payload']['draft']['target_lines'];self.assertEqual(len(rows),5)
        self.assertEqual({r['ticker'] for r in rows[1:]},{'ALPHA','BETA','GAMMA','DELTA'})
        self.assertTrue(all(r['weight']['value']==0 and r['target_amount']['amount']=='0' for r in rows[1:]))
        self.assertTrue(all(r['policy']=='NO_NEW_BUY__NOT_AN_AUTOMATIC_SELL_INSTRUCTION' for r in rows[1:]))
        self.assertEqual(pack,before)
        self.assertEqual(enrich_document_target_view(view,proof),(view,proof))

    def test_other_section_zero_statement_does_not_change_active_allocation(self):
        from approved_target_input import enrich_document_target_view
        pack=self.pack('\n## Historical\n- ALPHA／BETA目前既有部位，長期目標0%。\n')
        view,_=enrich_document_target_view(pack['target'],pack['trusted_approved_target_source'])
        self.assertEqual([r['ticker'] for r in view['payload']['draft']['target_lines']],['VT'])


class AcceptedHoldingQuantityTimeTest(unittest.TestCase):
    def case(self):
        req={'client_id':'SYNTHETIC','owner':{'account':'SYNTHETIC_IB'},
            'evaluation_at':'2026-10-28T01:00:00Z',
            'client_snapshot':{'payload':{'source_sha256':'a'*64,'payload_digest':'b'*64}}}
        position={'source_kind':'OWNER_SCREENSHOT_SOURCE','as_of_utc':None}
        proof={'schema_version':'Family.W8.OfficialHoldingsAcceptance.v1','state':'COMPLETE',
            'client_id':'SYNTHETIC','account_key':'SYNTHETIC_IB','source_db_sha256':'a'*64,
            'snapshot_digest':'b'*64,'as_of':'2026-10-26T01:00:00Z',
            'owner_decision':{'action':'ACCEPT_EXISTING_OFFICIAL_HOLDINGS'}}
        return req,position,{'holdings_completeness':proof}

    def test_owner_boundary_does_not_invent_observation_date(self):
        from position_source_bridge import quantity_time
        req,position,ctx=self.case();before=deepcopy(position)
        at,basis=quantity_time(req,position,ctx)
        self.assertEqual(at,ctx['holdings_completeness']['as_of'])
        self.assertIn('NOT_ORIGINAL_OBSERVATION',basis);self.assertEqual(position,before)

    def test_other_account_or_snapshot_acceptance_cannot_date_a_position(self):
        from position_source_bridge import quantity_time
        from family_boundary import BoundaryError
        for field in ('account_key','source_db_sha256'):
            req,position,ctx=self.case();ctx['holdings_completeness'][field]='OTHER'
            with self.assertRaisesRegex(BoundaryError,'POSITION_OBSERVATION_TIME_REQUIRED'):
                quantity_time(req,position,ctx)


class AbsentAccountDownstreamTest(unittest.TestCase):
    def absent(self,source):
        out=deepcopy(source);out['contract_version']='C-W7-FUND-v1.1.0-ABSENT'
        row=next(c for c in out['contexts'] if c['domain']=='TW_SUB_BROKERAGE')
        removed=row['bucket_new_investment_amount'];out['total_new_investment_amount']-=removed
        row.update(broker=None,account=None,bucket_new_investment_amount=0,
            account_presence='OWNER_CONFIRMED_ABSENT',account_presence_source='SYNTHETIC_OWNER_ABSENCE',
            source_reference_ids=['SYNTHETIC_OWNER_ABSENCE'])
        row['brokerage_cash_state']={k:0 for k in ('total','available','unsettled','reserved')}
        for leg in row['executable_budget'].values():leg.update(amount=0,source_broker=None,source_account=None)
        return out

    def test_original_work5_work6_accept_same_versioned_absent_domain(self):
        from runtime_loader import load_c_module
        req=json.loads((HERE.parent/'W5/tests/fixtures/work5_adapter_request.json').read_text())
        c7=self.absent(req['c7_funding_context']);w3=req['work3_handoff']
        owner=tuple(w3['owner'][k] for k in ('funding_domain','broker','account'))
        w5=load_c_module(ROOT,5);w6=load_c_module(ROOT,6)
        selected=w5._validate_c7_against_work3(c7,w3,owner,req['run_id'])
        result=w6._c7_validate(c7,req['run_id'],owner,w3['currency'])
        self.assertEqual(selected['account'],owner[2]);self.assertEqual(result[0],selected)
        bad=deepcopy(c7);next(c for c in bad['contexts'] if c['domain']=='TW_SUB_BROKERAGE')['broker']='FAKE'
        with self.assertRaises(ValueError):w5._validate_c7_against_work3(bad,w3,owner,req['run_id'])
        with self.assertRaises(ValueError):w6._c7_validate(bad,req['run_id'],owner,w3['currency'])

    def test_actual_c7_engine_preserves_absent_domain_and_present_account_budget(self):
        from c7_engine import run_c7_engine
        b=HERE.parent/'W5/tests/fixtures/c7';read=lambda n:json.loads((b/n).read_text())
        funding=self.absent(read('W13_LOOP2_C7_FUNDING_CONTEXT_US_HAPPY.json'))
        source={'canonical_input':read('W13_C_WORK7_CANONICAL_INPUT_QA_RUN3.json'),
            'work6_result':read('W13_C_WORK6_SOURCE_QA_RUN3.json'),
            'funding_context':funding,'evaluated_at':read('W13_C_WORK7_ASSET_FRAMEWORK_RESULT_QA_RUN3.json')['created_at']}
        before=deepcopy(source);result=run_c7_engine(ROOT,source)['result']
        self.assertEqual(result['status'],'READY_FOR_PM_GATE',result.get('issues'))
        contexts=result['funding_context_snapshot']['contexts']
        absent=next(c for c in contexts if c['domain']=='TW_SUB_BROKERAGE')
        self.assertIsNone(absent['broker']);self.assertIsNone(absent['account'])
        self.assertEqual(next(c for c in contexts if c['domain']=='US_BROKER'),
            next(c for c in funding['contexts'] if c['domain']=='US_BROKER'))
        self.assertEqual(source,before)

    def test_original_full_pipeline_and_mentor_accept_absent_unused_account(self):
        import importlib.util
        if importlib.util.find_spec('pytest') is None:
            self.skipTest('Full native fixture helpers require pinned pytest; this check runs in CI')
        sys.path.insert(0,str(HERE.parent/'W5/tests'))
        from test_target_units import bound_case
        from c7_engine import run_c7_engine
        from native_pipeline import run_native_pipeline
        from mentor_bridge import explain_native
        bundle,source=bound_case();source['funding_context']=self.absent(source['funding_context'])
        bundle['asset_framework']=run_c7_engine(ROOT,source)['result']
        for branch in ('stock_request','bond_request'):
            bundle[branch]['c7_funding_context']=deepcopy(source['funding_context'])
        before=deepcopy((bundle,source))
        result=run_native_pipeline(ROOT,bundle,c7_source=source)
        self.assertEqual(result['status'],'NATIVE_PIPELINE_COMPLETE')
        unified=result['unified_result']
        mentor=explain_native(ROOT,result['work9_request'],unified,trusted_context={
            'client_id':result['client_id'],'run_id':result['run_id'],'owner':unified['owner'],
            'currency':unified['currency'],'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE',
            'runtime_mode':'REAL_DETERMINISTIC','data_provenance':'SYNTHETIC','expected_result_digest':digest(unified)})
        self.assertTrue(mentor['recommendations_allowed']);self.assertFalse(mentor['broker_execution_allowed'])
        self.assertEqual((bundle,source),before)


if __name__=='__main__':unittest.main()


from loop2_target_projection import produce as project_loop2_targets,validate as validate_loop2_projection
from approved_target_input import build_approved_target_view,enrich_document_target_view

class CompleteTargetProjectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'approved.md'
        path.write_text('| 標的 | 目標比例 | 目標金額（US$） |\n|---|---|---|\n| AAA | 60% | 600 |\n| BBB | 40% | 400 |\n')
        client='fam_'+'a'*32
        pack=build_approved_target_view(client_id=client,source_path=path,
            source_reference='SYNTHETIC_APPROVED_FULL_ALLOCATION',source_available_at='2026-10-27T00:00:00Z',
            target_version=1,allocation_version='SYNTHETIC',rows=[{'source_line':'| AAA | 60% | 600 |','weight':'0.6'},
                {'source_line':'| BBB | 40% | 400 |','weight':'0.4'}],
            mappings=[{'instrument_id':'AAA_ROLE','ticker':'AAA','asset_type':'股票ETF'},
                {'instrument_id':'BBB_ROLE','ticker':'BBB','asset_type':'股票ETF'}])
        target,proof=enrich_document_target_view(pack['target'],pack['trusted_approved_target_source'])
        self.request={'client_id':client,'run_id':'SYNTHETIC_RUN','owner':{'client_id':client,'account':'SYNTHETIC'},
            'client_snapshot':{'payload':{'source_sha256':'a'*64}},'confirmed_target':target}
        self.context={'approved_document_target_source':proof}
        self.policy={'schema_version':'Family.W8.CompleteTargetProjectionPolicy.v1','client_id':client,
            'scope':'EXISTING_CONFIRMED_FULL_ALLOCATION_ONLY','source_reference':'SYNTHETIC_OWNER_EXISTING_TARGETS'}
    def project(self):return project_loop2_targets(ROOT,self.request,self.context,self.policy,['AAA','NEW'])
    def test_native_complete_target_lookup_preserves_approval_and_derives_only_missing_zero(self):
        before=deepcopy((self.request,self.context));out=self.project()
        self.assertEqual(out['status'],'SOURCE_BASELINE_PROJECTED')
        self.assertNotIn('AAA',out['targets']);self.assertEqual(out['targets']['NEW']['weight']['value'],'0.0')
        self.assertEqual(out['targets']['NEW']['target_amount']['amount'],'0.0')
        self.assertEqual((self.request,self.context),before)
        validate_loop2_projection(ROOT,self.request,self.context,{'loop2_target_projection':out})
        out['targets']['NEW']['target_amount']['amount']='500';out['output_digest']=digest(out['targets'])
        with self.assertRaisesRegex(PermissionError,'REPLAY_MISMATCH'):
            validate_loop2_projection(ROOT,self.request,self.context,{'loop2_target_projection':out})
    def test_incomplete_unknown_or_other_client_is_not_a_zero_target(self):
        self.request['confirmed_target']['payload']['draft']['target_lines'].pop()
        self.context['approved_document_target_source']['target_view_digest']=digest(self.request['confirmed_target'])
        out=self.project();self.assertEqual(out['status'],'INCOMPLETE_SOURCE');self.assertEqual(out['targets'],{})
        self.policy['client_id']='OTHER'
        with self.assertRaisesRegex(PermissionError,'POLICY_SCOPE_MISMATCH'):self.project()
    def test_grouped_symbol_is_not_closed_world_absence(self):
        self.request['confirmed_target']['payload']['draft']['target_lines'][0]['original_document_row']='| AAA + NEW | 60% | 600 |'
        self.context['approved_document_target_source']['target_view_digest']=digest(self.request['confirmed_target'])
        out=self.project();self.assertNotIn('NEW',out['targets'])
        self.assertEqual(out['issues'][0]['code'],'GROUPED_TARGET_MAPPING_REQUIRED')
    def test_unknown_budget_currency_remains_unknown_money(self):
        self.request['confirmed_target']['payload']['draft']['denominator']={'value_state':'UNKNOWN','amount':None,'currency':None}
        self.context['approved_document_target_source']['target_view_digest']=digest(self.request['confirmed_target'])
        out=self.project();money=out['targets']['NEW']['target_amount']
        self.assertEqual(out['targets']['NEW']['weight']['value'],'0.0')
        self.assertEqual(money['value_state'],'UNKNOWN');self.assertIsNone(money['amount']);self.assertIsNone(money['currency'])
    def add_grouping(self,heading):
        from hashlib import sha256
        proof=self.context['approved_document_target_source'];path=Path(proof['local_source_path'])
        path.write_text(path.read_text()+'\n## '+heading+'\n- 全球核心桶可由AAA＋NEW共同解讀。\n')
        proof['source_sha256']=sha256(path.read_bytes()).hexdigest()
    def test_drift_display_grouping_does_not_duplicate_or_split_approved_target(self):
        self.add_grouping('客戶專屬漂移圖規則')
        before=deepcopy(self.request['confirmed_target']);out=self.project()
        self.assertEqual(out['targets']['NEW']['target_amount']['amount'],'0.0')
        group=out['targets']['NEW']['current_exposure_display_groups'][0]
        self.assertEqual(group['scope'],'GROUPED_CURRENT_EXPOSURE_DISPLAY')
        self.assertFalse(out['targets']['NEW']['new_strategic_allocation_created'])
        self.assertEqual(before,self.request['confirmed_target'])
        self.assertNotIn('AAA',out['targets'])
    def test_grouped_target_instruction_outside_drift_display_remains_unresolved(self):
        self.add_grouping('正式配置目標規則')
        out=self.project();self.assertNotIn('NEW',out['targets'])
        self.assertEqual(out['issues'][0]['code'],'GROUPED_TARGET_MAPPING_REQUIRED')
    def test_drift_source_bytes_are_rechecked_before_zero_lookup(self):
        proof=self.context['approved_document_target_source'];path=Path(proof['local_source_path'])
        path.write_text(path.read_text()+'changed')
        with self.assertRaisesRegex(PermissionError,'DOCUMENT_CHANGED'):self.project()

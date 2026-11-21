"""FAMILY-PM-ROUTING-20261117-01: approved routing, synthetic numbers.

Official product identity records are real captured source evidence. All
portfolio, price, valuation and core proof values here are synthetic fixtures;
private real-input before/after evidence is delivered separately to the PM.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json,sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
import native_asset_source as N
from equity_product_identity import classify
from core_analysis_inputs import issuer_inputs
from v82_core_source import read
import test_v82_core_source as core_fixture
import test_member_v82_analysis as member_fixture

RULE=(HERE/'tests/fixtures/routing_2454_vdc_approved_v1.22.2.txt').read_text()
RULES='\n'.join(N.FORMAL_CLASSES)+'\n'+RULE
AT='2026-11-17T08:00:00Z'
ORDERS={'VDC':['FORWARD_PE','EV_EBITDA','FCF_YIELD','EV_SALES'],
        '2454':['FORWARD_PE','EV_EBITDA','EV_SALES','PS','FCF_YIELD']}


class Routing2454VDCTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        p=self.folder/'rule.md';p.write_text(RULES)
        self.source={'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),
            'source_reference':'APPROVED_RULE_EXCERPTS__SYNTHETIC_TEST_RECEIPT'}
        self.fixture=core_fixture.CoreSourceTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def product(self,symbol):return json.loads((HERE/(symbol+'_product_identity.json')).read_text())

    def identity(self,symbol):return N.classification(symbol,self.source,evaluation_at=AT)

    def evaluate(self,symbol,metrics=()):
        f=self.fixture;f.data['asset_id']=symbol
        f.leaf('valuation_metrics',list(metrics))
        p=self.folder/'core.json';p.write_text(json.dumps(f.data))
        qualified=read({'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()},f.request,symbol)
        return N.native_core_observation(ROOT,f.observed,broad_etf=symbol=='VDC',
            valuation_waterfall=self.identity(symbol)['valuation_waterfall'],qualified_core_source=qualified)

    def metric(self,name='FORWARD_PE',*,median='20'):
        proof=self.fixture.proof
        return {'metric_name':name,'current':'15','historical_median':median,'unit':'multiple',
            'source_reference':proof['source_reference'],'source_sha256':proof['sha256'],
            'as_of':proof['as_of'],'freshness':'FRESH','pit_status':'VERIFIED','data_quality':'OK'}

    def test_01_vdc_official_sector_identity_and_approved_dispatch(self):
        out=self.identity('VDC')
        self.assertEqual((out['asset_type'],out['asset_grade'],out['primary_class']),
            ('SECTOR_ETF','C','產業／主題ETF'))
        self.assertEqual(out['sector'],'Consumer Staples')
        self.assertEqual(out['valuation_route'],'PROFITABLE_NONFINANCIAL_GENERIC')
        self.assertEqual(out['valuation_waterfall'],ORDERS['VDC'])
        self.assertIn('PROVIDER_CLASSIFICATION_SNAPSHOT',out['taxonomy_version_scope'])
        self.assertFalse(out['grade_evidence']['current_safety_or_valuation_inferred'])
        context=out['grade_evidence']['facts']['supplementary_observations']
        self.assertEqual(context['fund']['unlabelled_price_earnings'],'24.6')
        self.assertEqual(context['benchmark']['unlabelled_price_earnings'],'24.5')
        core=self.evaluate('VDC')
        self.assertEqual(core['actual_inputs']['valuation_metrics'],[])
        self.assertFalse(core['result']['permission']['new_buy_order_permission'])

    def test_02_changed_symbol_url_or_original_hash_rejected(self):
        for symbol in ORDERS:
            for field,value in [('symbol','OTHER'),('source_url','https://synthetic.invalid')]:
                p=self.product(symbol);p[field]=value
                with self.subTest(symbol=symbol,field=field),self.assertRaises(ValueError):
                    classify(symbol,p,RULES,evaluation_at=AT)
            p=self.product(symbol);p['sources'][0]['source_sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'IDENTITY_OR_HASH'):
                classify(symbol,p,RULES,evaluation_at=AT)

    def test_02_changed_product_artifact_rejected_at_original_entry(self):
        p=self.folder/'product.json';p.write_text(json.dumps(self.product('VDC')))
        source={'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
        p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'PRODUCT_STRUCTURE_SOURCE_CHANGED'):
            N.classification('VDC',self.source,source,evaluation_at=AT)

    def test_02_missing_taxonomy_version_provider_or_classification_time_rejected(self):
        for field in ('taxonomy_version','taxonomy_provider','taxonomy_version_scope',
                      'classification_as_of','classification_available_at'):
            p=self.product('VDC');p.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):
                classify('VDC',p,RULES,evaluation_at=AT)

    def test_02_future_missing_naive_or_backdated_source_availability_rejected(self):
        for symbol in ORDERS:
            p=self.product(symbol)
            with self.subTest(symbol=symbol),self.assertRaisesRegex(ValueError,'NOT_AVAILABLE'):
                classify(symbol,p,RULES,evaluation_at='2026-09-30T23:59:59Z')
            for stamp in (None,'2026-11-17T07:46:27','2020-01-01T00:00:00Z','2027-01-01T00:00:00Z'):
                p=self.product(symbol);p['sources'][0].update(available_at=stamp,retrieved_at=stamp)
                with self.subTest(symbol=symbol,stamp=stamp),self.assertRaises(ValueError):
                    classify(symbol,p,RULES,evaluation_at=AT)

    def test_02_unapproved_rule_or_wrong_sector_not_routed(self):
        p=self.product('VDC');p['sector']='Financials'
        with self.assertRaises(ValueError):classify('VDC',p,RULES,evaluation_at=AT)
        with self.assertRaisesRegex(ValueError,'FORMAL_VDC'):
            classify('VDC',self.product('VDC'),'',evaluation_at=AT)

    def test_03_mediatek_common_stock_five_methods_no_grade_inference(self):
        out=self.identity('2454')
        self.assertEqual(out['asset_type'],'INDIVIDUAL_STOCK')
        self.assertEqual(out['valuation_waterfall'],ORDERS['2454'])
        self.assertEqual(out['company_identity']['listing']['ticker'],'2454')
        self.assertIn('INDUSTRY_ROUTE_ONLY',out['framework_scope'])
        self.assertNotIn('SEC_10K',json.dumps(out))
        self.assertNotIn('NVDA',json.dumps(out))
        core=self.evaluate('2454')
        self.assertEqual(core['structural_confirmation_applicability'],'REQUIRED')
        self.assertFalse(core['result']['permission']['new_buy_order_permission'])

    def test_04_company_grade_unknown_does_not_erase_approved_industry_route(self):
        out=self.identity('2454')
        self.assertEqual((out['asset_grade'],out['primary_class']),('UNKNOWN','UNKNOWN'))
        self.assertEqual(out['primary_framework'],'V82.md §32.8 Semiconductor')
        self.assertEqual(out['grade_evidence']['assessment_kind'],'IDENTITY_ONLY__GRADE_UNKNOWN')
        self.assertNotIn('valuation.product_specific_waterfall',
            {g['field_path'] for g in self.evaluate('2454')['input_gaps']})

    def test_05_missing_qualified_primary_and_fallback_stays_insufficient(self):
        for symbol in ORDERS:
            out=self.evaluate(symbol)
            self.assertIsNone(out['result']['valuation']['primary_metric'])
            self.assertIn('VALUATION_DATA_INSUFFICIENT',out['result']['valuation']['reason_codes'])

    def test_05_unlabelled_pe_is_never_forward_pe(self):
        for symbol in ORDERS:
            facts={'source_url':'SYNTHETIC','source_sha256':'a'*64,'as_of':'2026-10-30',
                'metrics':{'PE':{'value':'24.6','unit':'multiple'},'PB':{'value':'4.2'}}}
            metrics,_=issuer_inputs(facts,allowed_metrics=ORDERS[symbol])
            self.assertEqual(metrics,[])
            out=self.evaluate(symbol,metrics)
            self.assertIsNone(out['result']['valuation']['primary_metric'])

    def test_05_qualified_fallback_follows_each_assets_own_order(self):
        for symbol in ORDERS:
            out=self.evaluate(symbol,[self.metric('EV_EBITDA')])
            self.assertEqual(out['result']['valuation']['primary_metric'],'EV_EBITDA')
            self.assertTrue(out['result']['valuation']['fallback_used'])

    def test_06_missing_history_keeps_valid_primary_without_cherry_picking(self):
        for symbol in ORDERS:
            metrics=[self.metric(median=None),self.metric('EV_EBITDA')]
            before=deepcopy(metrics);out=self.evaluate(symbol,metrics)
            self.assertEqual(out['result']['valuation']['primary_metric'],'FORWARD_PE')
            self.assertEqual(out['result']['valuation']['level'],'UNKNOWN')
            self.assertFalse(out['result']['valuation']['fallback_used'])
            self.assertEqual(metrics,before)

    def test_07_08_original_menu_entry_routes_two_assets_and_preserves_sources(self):
        f=member_fixture.MemberV82Tests();f.setUp();self.addCleanup(f.doCleanups)
        f.at=AT
        member_fixture.MemberV82SourceProducer.__call__.__globals__['datetime'].now.return_value=datetime.fromisoformat(AT.replace('Z','+00:00'))
        tables=f.snapshot['tables']
        tables['portfolio_instrument'][0]['ticker']='VDC'
        tables['portfolio_instrument'][3].update(ticker='2454',instrument_type='STOCK')
        f.seal();before=deepcopy(f.snapshot)
        rule=Path(f.config['classification_source']['local_path']);rule.write_text(RULES)
        f.config['classification_source']['sha256']=sha256(rule.read_bytes()).hexdigest()
        for symbol in ORDERS:
            descriptor=f.market(symbol)
            path=Path(descriptor['calendar_source']['local_path'])
            cal=json.loads(path.read_text());cal['coverage_cutoff']=AT
            path.write_text(json.dumps(cal));descriptor['calendar_source']['sha256']=sha256(path.read_bytes()).hexdigest()
            if symbol=='2454':
                path=Path(descriptor['local_path']);raw=json.loads(path.read_text())
                raw['chart']['result'][0]['meta']['instrumentType']='EQUITY'
                path.write_text(json.dumps(raw));descriptor['sha256']=sha256(path.read_bytes()).hexdigest()
            f.config['market_sources'][symbol]=descriptor
        provider=member_fixture.OnDemandAnalysisProvider(
            member_fixture.MemberV82SourceProducer(**f.config),repo_root=ROOT)
        request,runner=provider(f.snapshot,{'question':'SYNTHETIC_ROUTING_TWO_ASSETS'})
        target=deepcopy(request['confirmed_target']);result=runner.analyze(request)
        self.assertEqual(set(r['symbol'] for r in result['positions']),set(ORDERS))
        for row in result['positions']:
            self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'],ORDERS[row['symbol']])
            self.assertIn('V82.evaluate_core_rule_state',row['call_trace'])
            self.assertNotIn('valuation.product_specific_waterfall',
                {g['field'] for g in row['missing_inputs']})
        self.assertEqual(f.snapshot,before);self.assertEqual(request['confirmed_target'],target)
        self.assertEqual(sum(e['route']=='CASH' for e in result['universe']['excluded']),1)
        self.assertEqual(next(r for r in result['positions'] if r['symbol']=='2454')['holding']['quantity'],'2')
        self.assertFalse(result['database_written']);self.assertEqual(result['trade_authorization'],'NONE')

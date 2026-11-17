"""Approved 00956 mapping through the original source reader and native Core.

All numerical values and history attestations below are synthetic fixtures.
The rule text fixture is the actual approved product-specific clause.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
import broad_product_identity as B
import native_asset_source as N
from v82_core_source import read
import test_v82_core_source as core_fixture
import test_member_v82_analysis as member_fixture
import test_holdings_analysis as holdings_fixture

RULE=(HERE/'tests/fixtures/00956_approved_rule_v1.22.2.txt').read_text()
GRADE='中度集中／成長或大型權值集中，但仍屬Broad核心曝險 → `B`'
RULES='\n'.join(N.FORMAL_CLASSES)+'\n廣泛分散核心市場結構 → `A`\n'+GRADE+'\n'+RULE


class NikkeiValuationTests(TestCase):
    def setUp(self):
        self.fixture=core_fixture.CoreSourceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.rules=self.path/'rules.md';self.rules.write_text(RULES)
        self.source={'local_path':str(self.rules),'sha256':sha256(self.rules.read_bytes()).hexdigest(),
                     'source_reference':'SYNTHETIC_RULE_RECEIPT'}
        self.identity=N.classification('00956',self.source)
        self.fixture.data['asset_id']='00956'
        self.profile=self.identity['valuation_profile']

    def metric(self,name='FORWARD_PE',current='15',median='20'):
        f=self.fixture
        method=('NIKKEI_INDEX_WEIGHTED_FISCAL_YEAR_ESTIMATE' if name=='FORWARD_PE'
                else 'NIKKEI_INDEX_WEIGHTED_LATEST_QUARTER_BOOK')
        history={'index_name':'Nikkei 225 High Dividend Yield Stock 50 Index',
            'scope':'INDEX_PROXY','method':method,'pit_status':'VERIFIED',
            'constituent_basis':'AS_KNOWN_AT_EACH_OBSERVATION',
            'historical_median':median,'qualification':'VERIFIED_UNDER_EXISTING_V82_HISTORY_RULES',
            'source_reference':'SYNTHETIC_QUALIFIED_HISTORY',
            'historical_publication_receipt_reference':'SYNTHETIC_PIT_HISTORY',
            'available_at':'2026-10-29T00:00:00Z'}
        if name=='FORWARD_PE':history['forecast_horizon']='PROVIDER_FISCAL_YEAR_ROLL'
        p=self.path/(name+'.history.json');p.write_text(json.dumps(history))
        basis={**history,'proof':{'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}}
        return {'metric_name':name,'current':current,'historical_median':median,'unit':'multiple',
            'source_reference':f.proof['source_reference'],'source_sha256':f.proof['sha256'],
            'as_of':f.proof['as_of'],'freshness':'FRESH','pit_status':'VERIFIED','data_quality':'OK',
            'scope':'INDEX_PROXY','index_name':history['index_name'],'method':method,
            'methodology_reference':'https://indexes.nikkei.co.jp/nkave/archives/file/users_guide_en.pdf',
            'product_evidence_sha256':self.profile['product_evidence']['source_artifact_sha256'],
            'forecast_horizon':'PROVIDER_FISCAL_YEAR_ROLL','applicable_fiscal_year':'FY_SYNTHETIC',
            'fiscal_year_roll_rule':'NEXT_BUSINESS_DAY_AFTER_ANNUAL_RESULTS',
            'book_value_period':'SYNTHETIC_LATEST_QUARTER','historical_basis':basis}

    def evaluate(self,metrics):
        f=self.fixture
        f.leaf('valuation_metrics',metrics)
        p=self.path/'core.json';p.write_text(json.dumps(f.data))
        qualified=read({'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()},f.request,'00956')
        return N.native_core_observation(ROOT,f.observed,valuation_waterfall=['FORWARD_PE','PB'],
            valuation_profile=self.profile,qualified_core_source=qualified)

    def test_01_approved_mapping_and_product_proof(self):
        self.assertEqual(self.identity['primary_class'],'日本高股息股票ETF')
        self.assertEqual(self.identity['primary_framework'],'FAMILY-00956-VALUATION-20261117')
        self.assertEqual(self.identity['asset_grade'],'B')
        self.assertEqual(self.identity['asset_type'],'BROAD_ETF')
        self.assertEqual(self.identity['valuation_waterfall'],['FORWARD_PE','PB'])
        self.assertFalse(self.profile['absolute_range_applicability'])
        product=deepcopy(self.profile['product_evidence']);product['benchmark']='Nikkei 225'
        with self.assertRaises(ValueError):B.classify('00956',product,RULES)

    def test_02_old_or_changed_approval_does_not_enable_mapping(self):
        for text in (GRADE,RULES.replace('RULE_APPROVED_FOR_IMPLEMENTATION','PROPOSAL_PENDING'),
                     RULES.replace('[FORWARD_PE, PB]','[PB, FORWARD_PE]'),RULES+'\n'+RULE):
            with self.subTest(text=text[:30]):
                result=B.classify('00956',self.profile['product_evidence'],text)
                self.assertEqual(result['primary_class'],'UNKNOWN')
                self.assertEqual(result['valuation_waterfall'],[])

    def test_03_fy_method_retained_through_original_reader_and_core(self):
        out=self.evaluate([self.metric()])
        row=out['actual_inputs']['valuation_metrics'][0]
        self.assertEqual(row['method'],'NIKKEI_INDEX_WEIGHTED_FISCAL_YEAR_ESTIMATE')
        self.assertEqual(row['forecast_horizon'],'PROVIDER_FISCAL_YEAR_ROLL')
        self.assertEqual(row['scope'],'INDEX_PROXY')
        self.assertEqual(out['result']['valuation']['level'],'CHEAP')
        self.assertFalse(out['result']['permission']['new_buy_order_permission'])
        for bad in ('NTM','TRAILING_PE'):
            metric=self.metric();metric['forecast_horizon']=bad
            self.assertEqual(self.evaluate([metric])['result']['valuation']['level'],'UNKNOWN')

    def test_04_missing_primary_uses_qualified_pb(self):
        out=self.evaluate([self.metric('PB','1.2','2')])
        self.assertEqual(out['result']['valuation']['primary_metric'],'PB')
        self.assertTrue(out['result']['valuation']['fallback_used'])
        self.assertEqual(out['result']['valuation']['level'],'CHEAP')
        audit=out['valuation_path_audit']
        self.assertEqual(audit[0]['status'],'UNAVAILABLE')

    def test_05_missing_both_stays_insufficient(self):
        out=self.evaluate([])
        self.assertIn('VALUATION_DATA_INSUFFICIENT',out['result']['valuation']['reason_codes'])
        self.assertIsNone(out['result']['valuation']['primary_metric'])

    def test_06_wrong_index_method_or_history_cannot_classify(self):
        for field,value in [('index_name','Nikkei 225'),('method','NTM'),
                            ('constituent_basis','TODAY_COMPONENTS_BACKFILLED')]:
            metric=self.metric();metric['historical_basis'][field]=value
            out=self.evaluate([metric,self.metric('PB')])
            self.assertEqual(out['result']['valuation']['primary_metric'],'FORWARD_PE')
            self.assertEqual(out['result']['valuation']['level'],'UNKNOWN')
            self.assertIsNone(out['actual_inputs']['valuation_metrics'][0]['historical_median'])
        metric=self.metric();metric['index_name']='S&P 500'
        self.assertIsNone(self.evaluate([metric])['result']['valuation']['primary_metric'])

    def test_07_yield_or_roe_cannot_create_cheap_or_buy(self):
        for name in ('FORECAST_DIVIDEND_YIELD','FUND_DISTRIBUTION_YIELD','ROE'):
            # Supplementary observations never enter the two-method resolver.
            metrics,audit=B.japan_valuation_inputs([{'metric_name':name,'current':'99'}],self.profile)
            self.assertEqual(metrics,[])
            self.assertIn('SUPPLEMENTARY_NOT_PRIMARY',audit[0]['issues'])
        self.assertFalse(self.evaluate([])['result']['permission']['new_buy_order_permission'])

    def test_08_other_products_keep_their_existing_routes(self):
        full=RULES+'\n廣泛分散核心市場結構 → `A`\n# 第五十章｜0050型\n# 第四十八章｜S&P 500／VOO型'
        for symbol in ('0050','VOO','VEA'):
            product=json.loads((HERE/(symbol+'_product_identity.json')).read_text())
            before=B.classify(symbol,product,full.replace(RULE,''))
            self.assertEqual(B.classify(symbol,product,full),before)

    def test_09_expensive_primary_does_not_cherry_pick_pb(self):
        out=self.evaluate([self.metric(current='28',median='20'),self.metric('PB','1','2')])
        self.assertEqual(out['result']['valuation']['primary_metric'],'FORWARD_PE')
        self.assertEqual(out['result']['valuation']['level'],'EXPENSIVE')
        self.assertFalse(out['result']['valuation']['fallback_used'])

    def test_10_nonpositive_earnings_quality_remains_visible_with_pb(self):
        metric=self.metric(current='-1');metric['earnings_quality_issue']='SYNTHETIC_NONPOSITIVE_EARNINGS'
        out=self.evaluate([metric,self.metric('PB','1','2')])
        self.assertEqual(out['result']['valuation']['primary_metric'],'PB')
        audit=out['product_valuation_audit']['metrics'][0]
        self.assertIn('NONPOSITIVE_OR_UNAVAILABLE_DENOMINATOR_METRIC',audit['issues'])
        self.assertEqual(audit['earnings_quality_issue'],'SYNTHETIC_NONPOSITIVE_EARNINGS')
        self.assertFalse(out['result']['permission']['new_buy_order_permission'])

    def test_11_missing_year_or_historical_publication_not_invented(self):
        metric=self.metric();metric['applicable_fiscal_year']=None
        out=self.evaluate([metric]);row=out['actual_inputs']['valuation_metrics'][0]
        self.assertIsNone(row['applicable_fiscal_year'])
        self.assertIsNone(out['result']['valuation']['primary_metric'])
        metric=self.metric();p=Path(metric['historical_basis']['proof']['local_path'])
        history=json.loads(p.read_text());history['historical_publication_receipt_reference']=None
        p.write_text(json.dumps(history));metric['historical_basis']['proof']['sha256']=sha256(p.read_bytes()).hexdigest()
        out=self.evaluate([metric])
        self.assertEqual(out['result']['valuation']['level'],'UNKNOWN')
        self.assertIsNone(out['actual_inputs']['valuation_metrics'][0]['historical_median'])

    def test_12_inputs_immutable_and_unqualified_raw_scale_not_used(self):
        metric=self.metric();metric['valuation_level']='CHEAP'
        metric.pop('historical_basis')
        before=deepcopy(metric);out=self.evaluate([metric])
        self.assertEqual(metric,before)
        self.assertEqual(out['result']['valuation']['level'],'UNKNOWN')
        self.assertEqual(out['product_valuation_audit']['fund_context_status'],'NOT_PROVIDED')

    def test_future_or_changed_history_cannot_qualify(self):
        metric=self.metric();p=Path(metric['historical_basis']['proof']['local_path'])
        history=json.loads(p.read_text());history['available_at']='2027-01-01T00:00:00Z'
        p.write_text(json.dumps(history));metric['historical_basis']['proof']['sha256']=sha256(p.read_bytes()).hexdigest()
        self.assertEqual(self.evaluate([metric])['result']['valuation']['level'],'UNKNOWN')
        p.write_text('{}')
        with self.assertRaisesRegex(PermissionError,'HISTORY_BYTES_CHANGED'):self.evaluate([metric])

    def test_verified_extreme_confirmation_uses_unchanged_native_rule(self):
        metric=self.metric(current='30',median='20')
        p=Path(metric['historical_basis']['proof']['local_path'])
        history=json.loads(p.read_text());history['expensiveness_percentile']='96'
        p.write_text(json.dumps(history));metric['historical_basis']['proof']['sha256']=sha256(p.read_bytes()).hexdigest()
        metric['expensiveness_percentile']='96'
        out=self.evaluate([metric])
        self.assertEqual(out['result']['valuation']['level'],'EXTREME_CANDIDATE')
        self.assertEqual(out['result']['valuation']['extreme_flag'],'ON')

    def test_member_menu_passes_approved_profile_to_original_core(self):
        f=member_fixture.MemberV82Tests();f.setUp();self.addCleanup(f.doCleanups)
        instrument=f.snapshot['tables']['portfolio_instrument'][0];instrument['ticker']='00956'
        f.seal()
        rules=Path(f.config['classification_source']['local_path'])
        rules.write_text('# 第四十六章｜QQQ型\n'+RULES)
        f.config['classification_source']['sha256']=sha256(rules.read_bytes()).hexdigest()
        f.config['market_sources']={s:f.market(s) for s in ('00956','QQQ')}
        provider=member_fixture.OnDemandAnalysisProvider(
            member_fixture.MemberV82SourceProducer(**f.config),repo_root=ROOT)
        request,runner=provider(f.snapshot,{'question':'SYNTHETIC_00956_METHOD_MAPPING'})
        before=deepcopy(request['confirmed_target'])
        result=runner.analyze(request)
        row=next(r for r in result['positions'] if r['symbol']=='00956')
        self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'],['FORWARD_PE','PB'])
        self.assertEqual(row['native_product_identity']['primary_class'],'日本高股息股票ETF')
        self.assertIn('VALUATION_DATA_INSUFFICIENT',row['core_observation']['result']['valuation']['reason_codes'])
        self.assertFalse(result['database_written'])
        self.assertEqual(request['confirmed_target'],before)

    def test_original_holdings_analysis_also_passes_profile(self):
        f=holdings_fixture.HoldingAnalysisTest();f.setUp();self.addCleanup(f.doCleanups)
        market_fixture=member_fixture.MemberV82Tests()
        market_fixture.setUp();self.addCleanup(market_fixture.doCleanups)
        descriptor=market_fixture.market('00956')
        from member_market_source import read_market
        from approved_v04_technical import load_profile
        observed=read_market(descriptor,symbol='00956',evaluation_at=market_fixture.at,
            repo_root=ROOT,profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
        observed['source_gaps']=['SYNTHETIC_HOLDINGS_SOURCE_CONTRACT_NOT_ATTESTED']
        observed.update(provider='SYNTHETIC',provider_verified_at=market_fixture.at,
            cache_validation='SYNTHETIC_ONLY',formal_identity_verified=False)
        observations=f.observations()
        observations['assets']=[observed]
        observations['missing']=[]
        f.request['evaluation_at']=market_fixture.at
        f.position['source_instrument']['ticker']='00956'
        rules=Path(f.producer.class_source['local_path'])
        rules.write_text(rules.read_text()+'\n廣泛分散核心市場結構 → `A`\n'+GRADE+'\n'+RULE)
        f.producer.class_source['sha256']=sha256(rules.read_bytes()).hexdigest()
        report=f.report(observations)
        row=report['analysis_result']['positions'][0]
        self.assertEqual(row['native_product_identity']['primary_class'],'日本高股息股票ETF')
        self.assertEqual(row['core_observation']['actual_inputs']['valuation_waterfall'],['FORWARD_PE','PB'])
        self.assertEqual(row['core_observation']['product_valuation_audit']['profile']['scope'],'INDEX_PROXY')

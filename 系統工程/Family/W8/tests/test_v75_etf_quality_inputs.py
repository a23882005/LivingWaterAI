"""Frozen quality boundaries, source ambiguity and same-account zero budgets."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from html import escape
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,sys
import pytest
import exchange_calendars as xc

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import formal_v75_parameters as P
import v75_etf_quality_inputs as Q
import v75_issuer_facts as I
import v75_macro_inputs as M
from test_v75_market_contract import fixture,save_manifest,macro


def good(market='US'):
    return {'authorized_universe':True,'liquidation_or_termination_announced':False,
        'unapproved_material_methodology_change':False,'abs_latest_premium_discount_pct':'1',
        'median_20d_abs_premium_discount_pct':'.5','median_20d_bid_ask_spread_pct':'.30' if market=='US' else '.50',
        'order_to_median_dollar_volume_pct':'10','aum':'100000000' if market=='US' else '1000000000',
        'trailing_12m_roc_pct':'10'}


@pytest.mark.parametrize('market',['US','TW'])
def test_exact_ok_boundaries_and_unknown_are_not_normal_or_automatic_review(market):
    facts=good(market);states,missing=Q.components(facts,market)
    assert not missing and states=={'structure_state':'STRUCTURE_OK','liquidity_state_etf':'LIQUIDITY_OK',
        'distribution_quality_state':'DISTRIBUTION_OK'}
    facts['liquidation_or_termination_announced']=None
    assert Q.components(facts,market)[0]['structure_state']=='UNKNOWN'
    facts=good(market);facts['median_20d_bid_ask_spread_pct']=None
    assert Q.components(facts,market)[0]['liquidity_state_etf']=='UNKNOWN'
    facts['order_to_median_dollar_volume_pct']='25.0001'
    assert Q.components(facts,market)[0]['liquidity_state_etf']=='LIQUIDITY_ABNORMAL'


@pytest.mark.parametrize('key,value,component,expected',[
    ('abs_latest_premium_discount_pct','2','structure_state','REVIEW_REQUIRED'),
    ('abs_latest_premium_discount_pct','2.0001','structure_state','STRUCTURE_ABNORMAL'),
    ('median_20d_abs_premium_discount_pct','.5001','structure_state','REVIEW_REQUIRED'),
    ('median_20d_bid_ask_spread_pct','1','liquidity_state_etf','REVIEW_REQUIRED'),
    ('median_20d_bid_ask_spread_pct','1.0001','liquidity_state_etf','LIQUIDITY_ABNORMAL'),
    ('order_to_median_dollar_volume_pct','25','liquidity_state_etf','REVIEW_REQUIRED'),
    ('trailing_12m_roc_pct','25','distribution_quality_state','REVIEW_REQUIRED'),
    ('trailing_12m_roc_pct','25.0001','distribution_quality_state','DISTRIBUTION_ABNORMAL')])
def test_formal_threshold_boundaries(key,value,component,expected):
    facts=good();facts[key]=value;assert Q.components(facts,'US')[0][component]==expected


def test_low_aum_needs_explicit_exemption_evidence_and_never_invents_one():
    facts=good();facts['aum']='49999999'
    assert Q.components(facts,'US')[0]['liquidity_state_etf']=='UNKNOWN'
    facts['formal_market_maker_liquidity_exemption']=False
    assert Q.components(facts,'US')[0]['liquidity_state_etf']=='LIQUIDITY_ABNORMAL'
    facts['formal_market_maker_liquidity_exemption']=True
    assert Q.components(facts,'US')[0]['liquidity_state_etf']=='REVIEW_REQUIRED'
    facts=good();facts['trailing_12m_roc_pct']=None
    assert Q.components(facts,'US')[0]['distribution_quality_state']=='UNKNOWN'
    facts['product_explicitly_non_distributing']=True
    assert Q.components(facts,'US')[0]['distribution_quality_state']=='NOT_APPLICABLE'


def issuer_html():
    def point(value,day='Oct 28, 2026',label=None):return {'formattedValue':value,'formattedAsOfDate':day,'label':label or 'SYNTHETIC'}
    cal=xc.get_calendar('XNYS',start='2026-09-01',end='2026-11-01')
    days=[d.strftime('%Y%m%d') for d in cal.sessions_in_range('2026-09-15','2026-10-28')]
    chart={'asOfDate':days,'value':['-0.4','0.2']*(len(days)//2)+(['0.2'] if len(days)%2 else [])}
    columns=[{'name':name,'formattedValue':value} for name,value in (
        ('exDate',['Oct 01, 2026']),('totalDistribution',['.3']),('incomeAmount',['.3']),
        ('shortTermCapitalGain',['0']),('longTermCapitalGain',['0']),('returnOnCapital',['0']))]
    columns[1]['infoBubble']='Current year distributions are not classified until calendar year-end.'
    components=[{'componentId':'keyFundFacts','dataPoints':{
        'cusip':point('46436E718'),'totalNetAssetsFundLevel':point('100,000,000'),
        'thirtyDayMedianBidAskSpread':point('0.01%')}},
        {'componentId':'fundamentalsAndRisk','dataPoints':{
            'modelOad':point('.11 yrs'),'fxHedgedYield':point('4.03%'),
            'thirtyDaySecYield':point('3.78%')},'rocPct12Month':{'value':'-','asOfDate':'-'}},
        {'componentId':'performance','containersByNameMap':{'premium-discount-chart':{
            'dataPointsByNameMap':{'premiumDiscountChartData':chart}}}},
        {'componentId':'performance','distributionTableData':columns}]
    return ('<walrus-context value="'+escape(json.dumps({'productId':314116}),quote=True)+'"></walrus-context>'+
        ''.join('<walrus-render-on-client componentprops="'+escape(json.dumps(c),quote=True)+'"></walrus-render-on-client>' for c in components))


def test_issuer_zero_columns_are_not_complete_roc_and_twenty_day_median_uses_abs_first():
    parser=I.IssuerHTML();parser.feed(issuer_html());facts=I.ishares(parser)
    assert facts['distribution_characterization']['current_year_classification']=='NOT_CLASSIFIED_UNTIL_YEAR_END'
    assert not facts['distribution_characterization']['complete_trailing_12m_breakdown_attested']
    metrics,basis=Q.pd_window(facts['premium_discount_history'],'2026-10-29T02:00:00Z')
    assert basis['missing_sessions']==[] and Decimal(metrics['median_20d_abs_premium_discount_pct'])==Decimal('.3')
    facts['premium_discount_history'].pop(-5)
    metrics,basis=Q.pd_window(facts['premium_discount_history'],'2026-10-29T02:00:00Z')
    assert metrics['median_20d_abs_premium_discount_pct'] is None and len(basis['missing_sessions'])==1


def test_ssga_fund_fields_do_not_select_index_yields_and_graph_bps_are_converted():
    def section(title,rows):
        return '<section><h3>'+title+'</h3><p>as of Oct 27 2026</p><table>'+''.join(
            '<tr><th>'+key+'</th><td>'+value+'</td></tr>' for key,value in rows)+'</table></section>'
    html='<p>SPSB USD 78464A474 US78464A4748</p><p>Assets Under Management</p><p>$100.00 M</p><p>as of Oct 27 2026</p>'
    html+=section('Fund Characteristics',[('Yield to Maturity','5.32%'),('Option Adjusted Duration','1.84 years')])
    html+=section('Index Characteristics',[('Yield to Maturity','99%'),('Option Adjusted Duration','99 years')])
    html+=section('Yields',[('30 Day SEC Yield','5.28%'),('30 Day SEC Yield (Unsubsidized)','5.25%')])
    html+=section('Fund Market Price',[('30-Day Median Bid/Ask Spread','.03%')])
    chart={'attrs':[{'period_date':'27-Oct-2026','value':'2.8191'}]}
    html+='<input id="premium-history-chart" value="'+escape(json.dumps(chart),quote=True)+'">'
    parser=I.IssuerHTML();parser.feed(html);facts=I.ssga(parser)
    assert facts['portfolio_ytm']['value']=='5.32' and facts['effective_duration']['value']=='1.84'
    assert facts['sec_yield_30d']['value']=='5.28'
    assert facts['premium_discount_history']==[{'date':'2026-10-27','value_pct':'0.028191'}]
    assert facts['bid_ask_spread_30_calendar_days']['value']=='0.03'


def formal_manifest(tmp_path):
    source,manifest=fixture(tmp_path);path=tmp_path/'synthetic-formal-params.md'
    path.write_bytes(b'SYNTHETIC CONTRACT: accepted only with explicit test hash patch')
    expected=sha256(path.read_bytes()).hexdigest()
    manifest['formal_parameter_source']={'schema_version':'Family.W8.FormalV75ParameterSource.v1',
        'parameter_version':P.VERSION,'local_path':str(path),'sha256':expected,
        'source_available_at':'2026-10-29T01:30:00Z','outer_sha256':P.WORK6_SHA256,
        'inner_sha256':P.WORK1_SHA256,'outer_crc_passed':True,'inner_crc_passed':True}
    raw=tmp_path/'sgov-issuer.html';raw.write_text(issuer_html());receipt=tmp_path/'sgov-issuer.receipt.json'
    h=sha256(raw.read_bytes()).hexdigest();receipt.write_text(json.dumps({'url':I.URLS['SGOV'],
        'http_status':200,'sha256':h,'requested_at':'2026-10-29T01:35:00Z','available_at':'2026-10-29T01:36:00Z'}))
    manifest['etf_issuer_sources']={'SGOV':{'local_path':str(raw),'sha256':h,
        'receipt_path':str(receipt),'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}}
    save_manifest(source,manifest);return source,manifest,expected


def test_bound_formal_source_replays_original_quality_and_preserves_yield_income_separation(tmp_path):
    source,manifest,expected=formal_manifest(tmp_path);at='2026-10-29T02:00:00Z'
    with patch.object(P,'PARAMETER_SHA256',expected):
        pool=M.read(source,at);out=M.apply({'assets':[{'symbol':'SGOV','call_trace':[]}]},pool,
            evaluation_at=at,repo_root=ROOT,macro=macro());row=out['assets'][0]
        assert pool['canonical_yield_observations']['SGOV']['current']['value']=='4.03'
        assert pool['income_observations']['SGOV']['calculation']['latest_ttm_cash_per_share']
        assert row['v75_original_predicates']['PRED-008']['original_result']['assessment_status']=='INSUFFICIENT_DATA'
        assert row['v75_original_predicates']['PRED-003']['input_freshness_verified']
        assert row['v75_original_predicates']['PRED-004']['input_freshness_verified']
        assert row['v75_original_predicates']['PRED-010']['original_result']['aggregate_state']=='ETF_QUALITY_UNKNOWN'
        assessment=pool['etf_quality_assessments']['SGOV']
        assert 'median_20d_bid_ask_spread_pct' not in assessment['normalized_facts']
        assert assessment['known_auxiliary_observations']['bid_ask_spread_30_calendar_days']['value']=='0.01'
        assert not assessment['raw_evidence_complete']
        report={'v75_macro_inputs':pool,'analysis_result':{'positions':[{'market':row}]}}
        M.validate({'evaluation_at':at},{'v75_macro_source_manifest':source},report,ROOT)
        row['v75_original_predicates']['PRED-010']['metrics']['structure_state']='STRUCTURE_OK'
        with pytest.raises(PermissionError,match='PREDICATE_REPLAY'):
            M.validate({'evaluation_at':at},{'v75_macro_source_manifest':source},report,ROOT)
        Path(manifest['etf_issuer_sources']['SGOV']['local_path']).write_text('changed')
        with pytest.raises(PermissionError,match='ISSUER_SOURCE_BYTES_CHANGED'):M.read(source,at)


def test_order_amount_uses_same_account_zero_bond_budget_not_physical_sgov(tmp_path):
    source,_,expected=formal_manifest(tmp_path);at='2026-10-29T02:00:00Z'
    with patch.object(P,'PARAMETER_SHA256',expected):pool=M.read(source,at)
    request={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN','evaluation_at':at,
        'owner':{'account':'SYNTHETIC_ACCOUNT','currency':'USD'}}
    entry={'adapter_request':{'SYNTHETIC_ONLY':True},'predicate_observations':{'SGOV':{}},
        'physical_holdings':{'SGOV':{'valuation':{'amount':'100000','currency':'USD'}}}}
    run=SimpleNamespace(broker_account_id='SYNTHETIC_ACCOUNT',currency='USD',bond_executable_budget=SimpleNamespace(amount=Decimal('0')))
    Q.bind_native(request,entry,pool,run);assessment=entry['etf_quality_assessments']['SGOV']
    assert assessment['intended_order_amount']=='0'
    assert Decimal(assessment['normalized_facts']['order_to_median_dollar_volume_pct'])==0
    assert assessment['order_source']['owner']==request['owner']
    assert not assessment['order_source']['sgov_physical_or_approved_target_used_as_cash']
    run.bond_executable_budget.amount=Decimal('100')
    Q.bind_native(request,entry,pool,run)
    assert entry['etf_quality_assessments']['SGOV']['intended_order_amount'] is None
    run.broker_account_id='ANOTHER_SYNTHETIC_ACCOUNT'
    with pytest.raises(PermissionError,match='ACCOUNT_BINDING'):Q.bind_native(request,entry,pool,run)

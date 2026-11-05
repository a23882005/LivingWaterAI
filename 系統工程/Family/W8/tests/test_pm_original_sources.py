"""Synthetic PM exports; none of these fixtures are real account evidence."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import pytest
from test_massive_daily_source import fixture as massive_fixture
from test_member_financial_facts import case as money_case,save
from member_market_source import read_market
from ibkr_daily_source import audit,PRICE_BASIS
from historical_source_qualification import bind
from member_financial_facts import broker_observations
from pm_source_document import read,history

HERE=Path(__file__).resolve().parents[1]

def write_document(path,data,heading='# SYNTHETIC PM ORIGINAL\n'):
    path.write_text(heading+json.dumps(data));return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())


def fixture(tmp_path):
    base=massive_fixture(tmp_path);at=base['retrieved_at']
    days=['2026-10-28','2026-10-29','2026-10-30','2026-11-02']
    data=dict(chart_step=86400,chart_start=days[0]+'T00:00:00Z',chart_end='2026-11-03T00:00:00Z',
        expires='2026-11-03T01:00:00Z',source='Last',time=[d+'T13:30:00Z' for d in days],
        open=[100]*4,high=[101]*4,low=[99]*4,close=[100]*4,volume=[1000]*4,
        corp_actions=[dict(type='Splits',date='20261103',announce_date='20261001',value='3.0')])
    document=dict(schema='Family.PM.IBKR.PublicHistoricalBatch.v1',client_scope='SYNTHETIC PUBLIC PRICES ONLY',
        source_tool='IB.get_price_history',batch=1,query=dict(period='FIVE_YEARS',step='ONE_DAY',outside_rth=False,include_corporate_actions=True),
        observations=[dict(ticker='TEST',contract_id=123,exchange='NYSE',started_at=at,retrieved_at=at,source=data)])
    source=dict(**write_document(tmp_path/'original.txt',document),provider='IBKR_LAST_DAILY_OBSERVATION',
        symbol='TEST',provider_symbol='TEST',contract_id=123,provider_exchange='NYSE',exchange='XNYS',currency='USD',
        timezone='America/New_York',source_reference='SYNTHETIC_PM_PUBLIC_ORIGINAL',retrieved_at=at,
        identity_source={**base['identity_source'],'format':'MASSIVE_REFERENCE_CSV'},calendar_source=base['calendar_source'])
    return source,document


def update(source,document):source.update(write_document(Path(source['local_path']),document))


def market(source,at='2026-11-03T00:00:00Z',is_etf=True):
    return read_market(source,symbol='TEST',evaluation_at=at,repo_root=HERE.parents[2],profile=None,
        is_etf=is_etf,observation_route='V75')


def test_original_daily_spelling_action_and_split_basis_reach_existing_intake(tmp_path):
    s,d=fixture(tmp_path);d['observations'][0]['source']['close'][0]=100.12345678901234;update(s,d)
    out=market(s);q=out['history_quality'];p=out['provider_completion_evidence']
    assert len(out['completed_rows'])==4 and out['completed_rows'][0]['Close']=='100.12345678901234'
    assert q['price_basis']==PRICE_BASIS and not q['formal_deployment_eligible']
    assert p['corporate_action_observations'][0]['value']=='3.0'
    assert not p['raw_unadjusted_request_verified'] and not p['price_adjustment_reversed'] and not p['split_quantity_reapplied']
    assert not p['historical_PIT_attested'] and not p['corporate_action_coverage_attested']


def test_original_bad_ohlc_is_a_gap_and_not_repaired_from_close_or_other_provider(tmp_path):
    s,d=fixture(tmp_path);d['observations'][0]['source']['high'][1]=90;update(s,d)
    out=market(s);assert len(out['completed_rows'])==2
    assert out['history_quality']['invalid_source_rows'][0]['date']=='2026-10-29'
    a=audit(s,'2026-11-03T00:00:00Z');assert a['invalid_OHLC_sessions']==['2026-10-29']
    assert len(a['raw_observed_bars'])==4 and a['raw_observed_bars'][1]['original_values']['high']=='90'


@pytest.mark.parametrize('change',[
    lambda s,d:s.update(contract_id=999),lambda s,d:s.update(provider_symbol='OTHER'),
    lambda s,d:s.update(provider_exchange='NASDAQ'),lambda s,d:s.update(exchange='XNAS'),
    lambda s,d:s.update(currency='TWD'),lambda s,d:s.update(timezone='UTC'),
    lambda s,d:s.update(retrieved_at='2099-01-01T00:00:00Z'),
    lambda s,d:d.update(source_tool='OTHER'),lambda s,d:d.update(schema='Family.PM.IBKR.ReadOnlyObservation.v1'),
    lambda s,d:d['query'].update(outside_rth=0),lambda s,d:d['query'].update(outside_rth=True),
    lambda s,d:d['query'].update(include_corporate_actions=False),lambda s,d:d['query'].update(period='ONE_YEAR'),
    lambda s,d:d['query'].update(step='ONE_WEEK'),lambda s,d:d['observations'][0].update(ticker='OTHER'),
    lambda s,d:d['observations'][0].update(started_at='2099-01-01T00:00:00Z'),
    lambda s,d:d['observations'].append(deepcopy(d['observations'][0]))])
def test_wrong_contract_query_provider_time_and_account_document_are_rejected(tmp_path,change):
    s,d=fixture(tmp_path);change(s,d);update(s,d)
    with pytest.raises((PermissionError,ValueError)):market(s)


@pytest.mark.parametrize('change',[
    lambda d:d.update(source='Midpoint'),lambda d:d.update(chart_step=3600),
    lambda d:d['close'].pop(),lambda d:d['time'].reverse(),
    lambda d:d['time'].__setitem__(1,d['time'][0]),lambda d:d['close'].__setitem__(0,True),
    lambda d:d['close'].__setitem__(0,None),lambda d:d.update(chart_end='2026-10-28T00:00:00Z'),
    lambda d:d['corp_actions'][0].update(value='0'),lambda d:d['corp_actions'][0].update(type='OTHER'),
    lambda d:d['corp_actions'].append(deepcopy(d['corp_actions'][0]))])
def test_incomplete_or_conflicting_original_arrays_and_actions_are_not_usable(tmp_path,change):
    s,d=fixture(tmp_path);change(d['observations'][0]['source']);update(s,d)
    with pytest.raises((PermissionError,ValueError)):market(s)


def test_original_text_and_independent_product_identity_are_pinned(tmp_path):
    s,d=fixture(tmp_path)
    with pytest.raises(PermissionError,match='PRODUCT_TYPE_CONFLICT'):market(s,is_etf=False)
    Path(s['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='ORIGINAL_BYTES_CHANGED'):market(s)


def test_future_acquisition_is_not_available_to_a_past_decision(tmp_path):
    s,_=fixture(tmp_path)
    with pytest.raises(PermissionError):market(s,at='2026-11-01T00:00:00Z')


def test_reference_can_be_verified_after_capture_but_never_after_decision(tmp_path):
    s,_=fixture(tmp_path);s['identity_source']['retrieved_at']='2026-11-02T23:59:00Z'
    out=market(s)
    assert out['provider_completion_evidence']['independent_identity_retrieved_at']=='2026-11-02T23:59:00Z'
    s['identity_source']['retrieved_at']='2026-11-03T00:00:01Z'
    with pytest.raises(PermissionError,match='REFERENCE_TIME'):market(s)


def test_vt_named_document_section_preserves_missing_query_start_time(tmp_path):
    s,d=fixture(tmp_path);item=d['observations'][0]
    meta=dict(schema='Family.PM.PublicVT5Y_IndependentSources.v1',captured_at_utc=s['retrieved_at'],
        original_requested_sources=[dict(tool='IB.get_price_history',args={**d['query'],'contract_id':123,'security_type':'STK'})])
    text='# SYNTHETIC\n'+json.dumps(meta)+'\n## IB Connector original parsed response (exact JSON serialization from tools)\n'+json.dumps(item['source'])+'\n## Massive daily original returned CSV\nSYNTHETIC'
    p=Path(s['local_path']);p.write_text(text);s.update(sha256=sha256(p.read_bytes()).hexdigest(),symbol='VT',provider_symbol='VT',provider_exchange='NYSE ARCA')
    data,receipt=history(s)
    assert data['time']==item['source']['time'] and receipt['started_at'] is None
    assert not receipt['historical_publication_times_attested']
    s['symbol']='TEST'
    with pytest.raises(PermissionError,match='EXACT_ASSET'):history(s)


def test_new_observations_reach_original_v82_without_raw_or_financial_qualification(tmp_path):
    from approved_v04_technical import load_profile
    s,_=fixture(tmp_path)
    out=read_market(s,symbol='TEST',evaluation_at='2026-11-03T00:00:00Z',repo_root=HERE.parents[2],
        profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
    assert out['rows']==4 and out['history_quality']['price_basis']==PRICE_BASIS
    assert not out['history_quality']['formal_deployment_eligible']


def test_history_binding_reports_actions_and_calendar_without_manufacturing_native_inputs(tmp_path):
    s,_=fixture(tmp_path);req,_,_=money_case();req['evaluation_at']='2026-11-03T00:00:00Z'
    out=bind({'ibkr_history':s},req,'TEST');a=out['sources']['ibkr_history']
    assert a['returned_bar_count']==4 and a['actions_observed_count']==1 and a['calendar_date_coverage_observed']
    assert out['qualified_qP_history'] is None and out['qualified_qV_history'] is None
    assert not out['financial_qualification_released'] and not a['qP_history_qualified'] and not a['qV_history_qualified']
    with pytest.raises(PermissionError):bind({'ibkr_history':s},req,'OTHER')


def test_calendar_gap_or_uncompleted_bar_does_not_attest_complete_history(tmp_path):
    s,d=fixture(tmp_path);chart=d['observations'][0]['source']
    for k in ('time','open','high','low','close','volume'):chart[k].pop(1)
    update(s,d);a=audit(s,'2026-11-03T00:00:00Z')
    assert a['missing_calendar_sessions']==['2026-10-29'] and not a['calendar_date_coverage_observed']


def test_text_duplicate_json_keys_cannot_choose_one_of_two_original_values(tmp_path):
    p=tmp_path/'duplicate.txt';p.write_text('# SYNTHETIC\n{"schema":"first","schema":"second"}')
    with pytest.raises(ValueError,match='DUPLICATE'):read(dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest()))


def account_case(tmp_path):
    req,_,_=money_case();at='2026-11-04T01:00:00Z'
    original=dict(schema='Family.PM.IBKR.ReadOnlyObservation.v1',client_scope='Joseph ONLY; SYNTHETIC',
        retrieved_at_utc=at,finance_eligibility='OBSERVED_NOT_CONFIRMED_FULL_FINANCE',trading='NONE',
        source_tool_names=['get_account_balances','get_account_positions','get_account_summary',
            'get_account_orders(show_completed=true)','get_account_trades(DAYS_30)'],
        balances={'balances':[{'currency':c,'cash_balance':-5.5,'settled_cash':-5.5} for c in ('BASE','USD')]},
        positions={'positions':[dict(contract_id=123,contract_description='SGOV',position=14,market_price=100,
            market_value=1400,currency='USD',asset_class='STK')]},
        summary=dict(gross_position_value=1410,net_liquidation=1405,buying_power=10000,available_funds=5000),
        orders=dict(orders=[dict(order_id=1,order_status='REPLACED')]),recent_trades=dict(trades=[dict(symbol='VALL')]))
    doc=write_document(tmp_path/'account.txt',original)
    manifest=dict(schema_version='Family.W8.MemberBrokerObservations.v1',
        **{k:req[k] for k in ('client_id','run_id','evaluation_at')},
        source_db_sha256=req['client_snapshot']['payload']['source_sha256'],
        snapshot_digest=req['client_snapshot']['payload']['payload_digest'],target_version=1,
        source_reference='SYNTHETIC_PM_ACCOUNT_ONLY',available_at=at,member_scope='Joseph',pm_document_source=doc)
    return req,original,manifest


def test_pm_negative_cash_nav_mismatch_and_unresolved_orders_remain_non_executable(tmp_path):
    req,original,m=account_case(tmp_path);before=deepcopy(req)
    out=broker_observations(req,save(tmp_path/'manifest.json',m));q=out['PM_document_reconciliation_quality']
    assert len(out['cash_observations'])==1 and out['cash_observations'][0]['broker_settled_observation']=='-5.5'
    assert q['negative_settled_cash'] and q['position_sum_minus_broker_gross']=='-10'
    assert q['position_sum_plus_cash_minus_NAV']=='-10.5' and q['trade_symbols_without_exact_position_symbol']==['VALL']
    assert out['summary_observations']['buying_power']==10000 and out['summary_observations']['available_funds']==5000
    assert len(out['replaced_orders_requiring_successor_or_release'])==1 and out['trade_query']=={'period':'DAYS_30'}
    assert out['complete_NAV'] is None and out['qualified_available_cash'] is None and out['pending_exposure'] is None
    assert not out['margin_funds_used_as_cash'] and not out['replacement_release_inferred'] and not out['orders_complete']
    assert not q['quantities_adjusted_again'] and not q['SGOV_role_confirmation_created'] and req==before


@pytest.mark.parametrize('change',[
    lambda r,o,m:r.update(client_id='OTHER'),lambda r,o,m:m.update(member_scope='MOU'),
    lambda r,o,m:m.update(calls={'positions':{}}),lambda r,o,m:o.update(client_scope='MOU ONLY; SYNTHETIC'),
    lambda r,o,m:o.update(finance_eligibility='FULL_FINANCE'),lambda r,o,m:o.update(trading='BUY'),
    lambda r,o,m:o.update(retrieved_at_utc='2099-01-01T00:00:00Z'),
    lambda r,o,m:o['positions']['positions'][0].update(currency='TWD'),
    lambda r,o,m:o['positions']['positions'].append(deepcopy(o['positions']['positions'][0])),
    lambda r,o,m:o['source_tool_names'].pop(),lambda r,o,m:o['balances']['balances'].append(deepcopy(o['balances']['balances'][-1]))])
def test_private_account_receipts_cannot_cross_member_scope_or_become_confirmations(tmp_path,change):
    req,o,m=account_case(tmp_path);change(req,o,m);m['pm_document_source']=write_document(Path(m['pm_document_source']['local_path']),o)
    with pytest.raises((PermissionError,ValueError)):broker_observations(req,save(tmp_path/'manifest.json',m))

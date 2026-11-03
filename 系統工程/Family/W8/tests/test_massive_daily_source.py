"""Synthetic raw-query receipts; historical PIT is never inferred."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pytest
from test_nasdaq_daily_source import source_case,change,HERE
from member_market_source import read_market


def save(path,data):
    path.write_text(json.dumps(data));return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())


def fixture(tmp_path):
    original=source_case(tmp_path);at=original['retrieved_at']
    path=tmp_path/'raw.csv';rows=['o,h,l,c,v,t']
    for day in ['2026-10-28','2026-10-29','2026-10-30','2026-11-02']:
        stamp=int(datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('America/New_York')).timestamp()*1000)
        rows.append('100,101,99,100,1000,'+str(stamp))
    text='\n'.join(rows)+'\n';path.write_text(text)
    raw=dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())
    endpoint='/v2/aggs/ticker/TEST/range/1/day/2026-10-28/2026-11-02'
    acquisition=save(tmp_path/'acquisition.json',dict(schema_version='Family.W8.MassiveDailyAcquisition.v1',
        tool='Massive.call_api',symbol='TEST',path=endpoint,params=dict(adjusted=False,sort='asc',limit=50000),
        started_at=at,retrieved_at=at,response_is_error=False,response_csv=text,response_sha256=raw['sha256']))
    identity=tmp_path/'identity.csv';identity.write_text('ticker,market,locale,type,active,currency_name,primary_exchange,share_class_figi\nTEST,stocks,us,ETF,true,usd,XNYS,BBG001S5N8V8\n')
    return dict(**raw,provider='MASSIVE_RAW_DAILY',symbol='TEST',provider_symbol='TEST',currency='USD',
        timezone='America/New_York',provider_exchange='XNYS',exchange='XNYS',retrieved_at=at,
        requested_start='2026-10-28',requested_end='2026-11-02',
        source_reference='https://api.massive.com'+endpoint+'?adjusted=false&sort=asc&limit=50000',
        acquisition_source=acquisition,identity_source=dict(local_path=str(identity),sha256=sha256(identity.read_bytes()).hexdigest(),
            retrieved_at=at,source_reference='https://api.massive.com/v3/reference/tickers/TEST?date=2026-11-02'),
        calendar_source=original['calendar_source'])


def read(source,at='2026-11-03T00:00:00Z',is_etf=True):
    return read_market(source,symbol='TEST',evaluation_at=at,repo_root=HERE.parents[2],profile=None,
        is_etf=is_etf,observation_route='V75')


def body(source,text,*,rebind=True):
    path=Path(source['local_path']);path.write_text(text);source['sha256']=sha256(path.read_bytes()).hexdigest()
    if rebind:change(source['acquisition_source'],lambda d:d.update(response_csv=text,response_sha256=source['sha256']))


def test_raw_ohlcv_and_decimal_spellings_reach_original_completed_session_intake(tmp_path):
    source=fixture(tmp_path);out=read(source)
    assert out['observed_date']=='2026-11-02' and len(out['completed_rows'])==4
    assert out['completed_rows'][-1]==dict(Date='2026-11-02',Open='100',High='101',Low='99',Close='100',Volume='1000')
    assert out['history_quality']['price_basis']=='RAW_UNADJUSTED_PROVIDER_OHLC__NOT_PIT_WEALTH'
    proof=out['provider_completion_evidence']
    assert proof['raw_unadjusted_request_verified'] and proof['ohlcv_from_single_original_response']
    assert not proof['historical_PIT_attested'] and not proof['corporate_action_coverage_attested']
    assert not proof['requested_range_complete_attested'] and not out['history_quality']['formal_deployment_eligible']


@pytest.mark.parametrize('change_query',[
    lambda d:d['params'].update(adjusted=True),lambda d:d['params'].update(adjusted=0),
    lambda d:d['params'].update(adjusted='false'),lambda d:d['params'].update(sort='desc'),
    lambda d:d.update(symbol='OTHER'),lambda d:d.update(path=d['path'].replace('TEST','OTHER')),
    lambda d:d.update(response_is_error=True),lambda d:d.update(schema_version='OTHER'),
    lambda d:d.update(tool='OTHER'),lambda d:d.update(retrieved_at='2026-11-04T00:00:00Z'),
    lambda d:d.update(started_at='2026-11-04T00:00:00Z')])
def test_raw_route_requires_original_exact_query_and_available_receipt(tmp_path,change_query):
    source=fixture(tmp_path);change(source['acquisition_source'],change_query)
    with pytest.raises((PermissionError,ValueError)):read(source)


@pytest.mark.parametrize('original,replacement',[
    ('TEST,stocks','OTHER,stocks'),(',us,',',gb,'),(',true,',',false,'),(',usd,',',twd,'),
    (',XNYS,',',XNAS,'),(',BBG001S5N8V8',',MISSING'),(',ETF,',',OPT,')])
def test_independent_reference_must_match_exact_us_listing_and_type(tmp_path,original,replacement):
    source=fixture(tmp_path);identity=source['identity_source'];path=Path(identity['local_path'])
    path.write_text(path.read_text().replace(original,replacement));identity['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError):read(source)


def test_no_cross_product_or_provider_substitution(tmp_path):
    source=fixture(tmp_path)
    with pytest.raises(PermissionError,match='PRODUCT_TYPE_CONFLICT'):read(source,is_etf=False)
    source['provider']='IBKR'
    with pytest.raises(PermissionError,match='IDENTITY_OR_TIME'):read(source)


def test_project_asset_cannot_be_replaced_by_an_unverified_provider_alias(tmp_path):
    source=fixture(tmp_path);source['symbol']='OTHER'
    with pytest.raises(PermissionError,match='ASSET_ALIAS_NOT_VERIFIED'):
        read_market(source,symbol='OTHER',evaluation_at='2026-11-03T00:00:00Z',
            repo_root=HERE.parents[2],profile=None,is_etf=True,observation_route='V75')


def test_raw_bytes_and_the_original_response_must_both_replay(tmp_path):
    source=fixture(tmp_path);path=Path(source['local_path'])
    path.write_text(path.read_text().replace('100,101','100,102'))
    with pytest.raises(PermissionError,match='ORIGINAL_BYTES_CHANGED'):read(source)
    source['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError,match='RESPONSE_BYTES_MISMATCH'):read(source)


@pytest.mark.parametrize('issue',['warning','duplicate_header','duplicate_date','out_of_range','not_numeric','nonfinite','missing_column','extra_column_value','unsorted'])
def test_provider_warning_or_ambiguous_raw_table_is_not_history(tmp_path,issue):
    source=fixture(tmp_path);text=Path(source['local_path']).read_text();lines=text.splitlines()
    if issue=='warning':text='Warning [NOT_ENTITLED]: unavailable\n'
    elif issue=='duplicate_header':text=text.replace('o,h,l,c,v,t','o,h,l,c,o,t')
    elif issue=='duplicate_date':text+='\n'.join([lines[-1]])+'\n'
    elif issue=='out_of_range':text=text.replace(lines[1].split(',')[-1],'1')
    elif issue=='not_numeric':text=text.replace('100,101','unknown,101')
    elif issue=='nonfinite':text=text.replace('100,101','NaN,101')
    elif issue=='missing_column':text=text.replace('o,h,l,c,v,t','o,h,l,c,v,not_timestamp')
    elif issue=='extra_column_value':text=text.replace(lines[1],lines[1]+',unexpected')
    else:text='\n'.join([lines[0],*reversed(lines[1:])])+'\n'
    body(source,text)
    with pytest.raises(ValueError):read(source)


def test_incoherent_ohlc_remains_an_original_gap_and_no_price_is_repaired(tmp_path):
    source=fixture(tmp_path);path=Path(source['local_path']);lines=path.read_text().splitlines()
    lines[-2]=lines[-2].replace('100,101,99','100,101,102');body(source,'\n'.join(lines)+'\n')
    out=read(source)
    assert len(out['completed_rows'])==1 and len(out['history_quality']['invalid_source_rows'])==1


def test_preclose_capture_is_not_promoted_when_replayed_after_market_close(tmp_path):
    source=fixture(tmp_path);source['retrieved_at']='2026-11-02T20:00:00Z'
    source['identity_source']['retrieved_at']=source['retrieved_at']
    change(source['acquisition_source'],lambda d:d.update(started_at=source['retrieved_at'],retrieved_at=source['retrieved_at']))
    out=read(source)
    assert out['observed_date']=='2026-10-30' and out['latest_expected_completed_session']=='2026-11-02'
    assert out['history_quality']['excluded_uncompleted_rows'][0]['date']=='2026-11-02'


def test_reference_from_other_day_or_after_acquisition_is_rejected(tmp_path):
    source=fixture(tmp_path);source['identity_source']['retrieved_at']='2026-11-04T00:00:00Z'
    with pytest.raises(PermissionError,match='REFERENCE_SCOPE_OR_TIME'):read(source)
    source=fixture(tmp_path);source['identity_source']['source_reference']=source['identity_source']['source_reference'].replace('2026-11-02','2026-11-01')
    with pytest.raises(PermissionError,match='REFERENCE_SCOPE_OR_TIME'):read(source)


def test_raw_source_reaches_original_native_v82_observations(tmp_path):
    from approved_v04_technical import load_profile
    source=fixture(tmp_path)
    out=read_market(source,symbol='TEST',evaluation_at='2026-11-03T00:00:00Z',
        repo_root=HERE.parents[2],profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
    assert out['observed_close']==100 and out['rows']==4
    assert out['history_quality']['price_basis']=='RAW_UNADJUSTED_PROVIDER_OHLC__NOT_PIT_WEALTH'
    assert out['call_trace'] and out['history_quality']['formal_deployment_eligible'] is False


def test_original_quantity_times_raw_close_does_not_create_nav_or_deployable_cash(tmp_path):
    from test_member_position_valuation import case
    from member_position_valuation import produce
    request,coverage,rows,inputs=case(tmp_path)
    market=read(fixture(tmp_path),at=request['evaluation_at']);rows[0]['market']=market
    result=produce(request,coverage,rows,inputs)
    assert result['positions'][0]['amount']=='300'
    assert result['positions'][0]['price_basis']=='RAW_UNADJUSTED_PROVIDER_OHLC__NOT_PIT_WEALTH'
    assert result['qualified_portfolio_NAV'] is None and result['deployable_cash'] is None
    assert result['new_buy_amount'] is None and result['trade_action']=='NO_TRADE'
    assert result['latest_owner_cash_reports'][0]['amount']=='100000'

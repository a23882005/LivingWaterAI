"""Synthetic original-reference fixtures; no real financial qualification claim."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import csv, io, json
import pytest
from test_v82_approved_context import case, ROOT
from test_v10_own_history import valuation_case, complete_price
from family_input import digest
from v82_approved_context import build, read_source
from livingwater_v82_runtime.approved_decision import evaluate


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}


def fixture(tmp_path, *, all_accounts=True, price=False):
    request,row,descriptor,*_=case(tmp_path)
    history=complete_price() if price else valuation_case()
    request['evaluation_at']=history['decision_at']
    if all_accounts:
        request['owner']={'client_id':request['client_id'],'scope':'ALL_MEMBER_ACCOUNTS',
            'account':None,'broker':None,'currency':None,'funding_domain':None}
    market={'listing':'XNAS','share_class':'BBG001S5N8V8','currency':'USD'}
    security={'asset_id':'QQQ',**market}
    history['identity'].update(security)
    if price:
        history['actions'].update(security)
        for bar in history['bars']:bar.update(security)
        history['comparable_from']='2012-01-01T00:00:00Z'
    else:
        history['current'].update(security,value='10')
        for sample in history['history']:sample.update(security)
    original={'ticker':'QQQ','market':'stocks','locale':'us','primary_exchange':'XNAS',
        'type':'ETF','active':'true','currency_name':'usd','share_class_figi':market['share_class']}
    raw=tmp_path/'SYNTHETIC_reference.csv'
    def write_original(record):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(record))
        writer.writeheader();writer.writerow(record);raw.write_text(stream.getvalue())
    write_original(original)
    at=datetime.fromisoformat(request['evaluation_at'].replace('Z','+00:00'))
    from zoneinfo import ZoneInfo
    day=at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    bound={k:request[k] for k in ('client_id','run_id','evaluation_at')}
    bound.update(asset_id='QQQ',source_db_sha256=request['client_snapshot']['payload']['source_sha256'])
    reference='https://api.massive.com/v3/reference/tickers/QQQ?date='+day
    evidence={'schema_version':'Family.W8.PV2MarketIdentitySource.v1',**bound,
        'provider':'MASSIVE','endpoint':'/v3/reference/tickers/QQQ','query':{'date':day},
        'source_reference':reference,'started_at':(at-timedelta(minutes=3)).isoformat(),
        'retrieved_at':(at-timedelta(minutes=2)).isoformat(),
        'source':{'local_path':str(raw),'sha256':sha256(raw.read_bytes()).hexdigest()}}
    data=json.loads(Path(descriptor['local_path']).read_text())
    data.update(**bound,owner=deepcopy(request['owner']),market_identity=market,
        available_at=(at-timedelta(minutes=1)).isoformat(),source_reference=reference,
        market_identity_source=evidence)
    data['price_history' if price else 'valuation_history']=history
    descriptor=save(Path(descriptor['local_path']),data)
    return request,row,descriptor,data,original,write_original


def produce(request,row,descriptor):
    return build(ROOT,row,request,fundamental=True,price_conditions={'value':True},
        left_safety=True,source_descriptor=descriptor)


@pytest.mark.parametrize('price',[False,True])
def test_all_accounts_uses_original_market_currency_with_same_real_producer_as_single_account(tmp_path,price):
    request,row,descriptor,data,*_=fixture(tmp_path,price=price)
    before=deepcopy(request)
    context,result=produce(request,row,descriptor)
    key='qP' if price else 'qV'
    assert result[key]['status']=='COMPLETE' and result[key]['value'] is not None
    assert request==before and context['identity']['owner']['currency'] is None
    assert context['market_identity']['currency']=='USD'
    assert context['market_identity']['currency_source']['historical_financial_PIT_attested'] is False
    single=deepcopy(context);single['identity']['owner'].update(scope='SINGLE_ACCOUNT',
        account='SYNTHETIC',broker='SYNTHETIC',currency='USD',funding_domain='US_DIRECT')
    assert evaluate(single,row['core_observation']['result'])[key]==result[key]
    assert result['trade_action']=='NO_TRADE'


def test_single_account_original_currency_guard_cannot_be_overridden(tmp_path):
    request,row,descriptor,*_=fixture(tmp_path,all_accounts=False)
    context,result=produce(request,row,descriptor)
    assert result['qV']['status']=='COMPLETE'
    context['identity']['owner']['currency']='TWD'
    assert evaluate(context,row['core_observation']['result'])['qV']['reason_codes']==['PV2_SOURCE_INSTRUMENT_IDENTITY_CONFLICT']


@pytest.mark.parametrize('field,value',[
    ('client_id','OTHER'),('run_id','OTHER'),('evaluation_at','2025-01-18T00:00:00Z'),
    ('source_db_sha256','OTHER'),('asset_id','OTHER'),('provider','OTHER'),
    ('endpoint','/v3/reference/tickers/OTHER'),('query',{'date':'2000-01-01'}),
    ('started_at','2025-01-18T00:00:00Z'),('retrieved_at','2025-01-18T00:00:00Z')])
def test_family_rejects_cross_identity_or_time_reference(tmp_path,field,value):
    request,row,descriptor,data,*_=fixture(tmp_path)
    data['market_identity_source'][field]=value
    descriptor=save(Path(descriptor['local_path']),data)
    with pytest.raises((PermissionError,ValueError)):produce(request,row,descriptor)


@pytest.mark.parametrize('field,value',[
    ('ticker','OTHER'),('primary_exchange',''),('share_class_figi',''),('currency_name',''),
    ('market','fx'),('locale','gb'),('active','false'),('type','')])
def test_reference_original_must_identify_one_active_us_listing(tmp_path,field,value):
    request,row,descriptor,data,original,write=fixture(tmp_path)
    original[field]=value;write(original)
    raw=data['market_identity_source']['source']
    raw['sha256']=sha256(Path(raw['local_path']).read_bytes()).hexdigest()
    descriptor=save(Path(descriptor['local_path']),data)
    with pytest.raises(PermissionError,match='ORIGINAL_SECURITY'):produce(request,row,descriptor)


@pytest.mark.parametrize('field,value',[
    ('listing','XNYS'),('share_class','BBG000B9XRY4'),('currency','TWD')])
def test_projection_and_history_cannot_cross_listing_class_or_currency(tmp_path,field,value):
    request,row,descriptor,data,*_=fixture(tmp_path)
    data['market_identity'][field]=value
    with pytest.raises(PermissionError,match='PROJECTION_MISMATCH'):
        produce(request,row,save(Path(descriptor['local_path']),data))
    data['market_identity'][field]={'listing':'XNAS','share_class':'BBG001S5N8V8','currency':'USD'}[field]
    data['valuation_history']['identity'][field]=value
    _,result=produce(request,row,save(Path(descriptor['local_path']),data))
    assert result['qV']['reason_codes']==['PV2_SOURCE_INSTRUMENT_IDENTITY_CONFLICT']


@pytest.mark.parametrize('field,value',[
    ('client_id','OTHER'),('run_id','OTHER'),('evaluation_at','2025-01-18T00:00:00Z'),
    ('source_db_sha256','OTHER'),('asset_id','OTHER'),('retrieved_at','2025-01-18T00:00:00Z')])
def test_native_rechecks_bound_provenance_even_with_recomputed_fingerprint(tmp_path,field,value):
    request,row,descriptor,*_=fixture(tmp_path)
    context,_=produce(request,row,descriptor)
    proof=context['market_identity']['currency_source'];proof[field]=value
    proof.pop('digest');proof['digest']=digest(proof)
    result=evaluate(context,row['core_observation']['result'])
    assert result['qV']['value'] is None
    assert result['qV']['reason_codes']==['PV2_MARKET_IDENTITY_SOURCE_UNVERIFIED']


def test_original_rechecked_at_both_boundaries_and_plain_currency_is_insufficient(tmp_path):
    request,row,descriptor,data,*_=fixture(tmp_path)
    context,_=produce(request,row,descriptor)
    plain=deepcopy(context);plain['market_identity'].pop('currency_source')
    assert evaluate(plain,row['core_observation']['result'])['qV']['reason_codes']==['PV2_MARKET_IDENTITY_SOURCE_UNVERIFIED']
    raw=Path(data['market_identity_source']['source']['local_path']);raw.write_text(raw.read_text().replace('usd','twd'))
    with pytest.raises(PermissionError,match='ORIGINAL_BYTES_CHANGED'):produce(request,row,descriptor)
    assert evaluate(context,row['core_observation']['result'])['qV']['reason_codes']==['PV2_MARKET_IDENTITY_SOURCE_UNVERIFIED']


def test_reference_does_not_supply_missing_financial_histories_or_change_funding(tmp_path):
    request,row,descriptor,data,*_=fixture(tmp_path)
    data.pop('valuation_history')
    context,result=produce(request,row,save(Path(descriptor['local_path']),data))
    assert result['qP']['value'] is None and result['qV']['value'] is None
    assert context['funding_layers'] is None and context['cycle_snapshot'] is None
    assert context['planning_ledger_source'] is None and context['execution_costs'] is None
    assert context['identity']['owner']==request['owner']


@pytest.mark.parametrize('change',['empty','multiple','duplicate_header','naive_time','derived_input'])
def test_ambiguous_expired_or_derived_source_is_rejected(tmp_path,change):
    request,row,descriptor,data,*_=fixture(tmp_path)
    raw=Path(data['market_identity_source']['source']['local_path'])
    if change=='empty':raw.write_text(raw.read_text().splitlines()[0]+'\n')
    elif change=='multiple':raw.write_text(raw.read_text()+raw.read_text().splitlines()[1]+'\n')
    elif change=='duplicate_header':raw.write_text(raw.read_text().replace('ticker,market','ticker,ticker'))
    elif change=='naive_time':data['market_identity_source']['retrieved_at']='2025-01-16T23:58:00'
    else:data['verified_market_identity']={'currency':'USD'}
    data['market_identity_source']['source']['sha256']=sha256(raw.read_bytes()).hexdigest()
    with pytest.raises((PermissionError,ValueError)):
        produce(request,row,save(Path(descriptor['local_path']),data))

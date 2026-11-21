"""Source receipts, action basis and existing same-run chain; synthetic fixtures."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from massive_action_source import read,compare_ibkr
from datetime import date
from historical_source_qualification import bind


def case(tmp_path,at='2026-11-05T19:45:00Z'):
    def save(name,value):
        p=tmp_path/name;p.write_text(value if isinstance(value,str) else json.dumps(value))
        return {'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
    text={
        'dividends':'id,ticker,ex_dividend_date,declaration_date,cash_amount,currency,split_adjusted_cash_amount\nD1,SYN,2021-11-03,2021-10-20,1.00,USD,0.25\n',
        'splits':'id,ticker,execution_date,split_from,split_to,adjustment_type,historical_adjustment_factor\nS1,SYN,2021-11-02,1,4,forward_split,0.125\n'}
    m=dict(schema_version='Family.W8.MassiveActionSources.v1',provider='MASSIVE',symbol='SYN',currency='USD',
        requested_start='2021-11-01',requested_end='2021-11-03',known_by=at,
        source_reference='SYNTHETIC_PUBLIC_ACTION_ORIGINALS',sources={})
    captures={};originals={}
    for kind,column in [('dividends','ex_dividend_date'),('splits','execution_date')]:
        source=save(kind+'.csv',text[kind]);originals[kind]={'isError':False,'structuredContent':{'result':text[kind]}}
        original=save(kind+'.tool.json',originals[kind])
        captures[kind]=dict(schema_version='Family.W8.MassiveActionAcquisition.v1',tool='Massive.call_api',
            path='/stocks/v1/'+kind,params=dict(ticker='SYN',**{column+'.gte':m['requested_start'],
            column+'.lte':m['requested_end'],'sort':column+'.asc','limit':5000}),
            started_at=at,retrieved_at=at,response_is_error=False,response_sha256=source['sha256'],tool_response_source=original)
        m['sources'][kind]={'source':source,'acquisition_source':save(kind+'.capture.json',captures[kind])}
    def descriptor():
        for kind in captures:
            m['sources'][kind]['source']=save(kind+'.csv',text[kind])
            captures[kind]['response_sha256']=m['sources'][kind]['source']['sha256']
            captures[kind]['tool_response_source']=save(kind+'.tool.json',originals[kind])
            m['sources'][kind]['acquisition_source']=save(kind+'.capture.json',captures[kind])
        return save('manifest.json',m)
    def replace(kind,value):
        text[kind]=value;originals[kind]['structuredContent']['result']=value
    return m,captures,originals,text,descriptor,replace


def test_exact_original_cash_ratio_and_dates_remain_observations(tmp_path):
    m,_,_,_,desc,_=case(tmp_path);before=deepcopy(m)
    d=desc();result=read(d,'SYN',m['known_by']);actions=result['corporate_action_observations']
    cash=actions['dividends']['records'][0];split=actions['splits']['records'][0]
    assert cash['original_cash_amount']=='1.00' and cash['split_adjusted_cash_amount_not_used']=='0.25'
    assert split['new_per_old']=='4' and split['historical_adjustment_factor_not_used']=='0.125'
    assert cash['available_at'] is None and not cash['historical_PIT_verified']
    assert not cash['cash_per_old_share_basis_verified'] and not split['pure_split_semantics_verified']
    assert not result['complete_corporate_action_coverage_verified'] and result['qualified_native_actions'] is None
    assert not result['qP_history_qualified'] and not result['qV_history_qualified']
    assert not any(a['native_wealth_event_applied'] for v in actions.values() for a in v['records'])
    assert result==read(d,'SYN',m['known_by'])


@pytest.mark.parametrize('kind',['dividends','splits'])
def test_empty_provider_warning_never_proves_zero_events(tmp_path,kind):
    m,_,_,_,desc,replace=case(tmp_path)
    replace(kind,'Warning [EMPTY]: ticker may be invalid, delisted, or have no records.')
    action=read(desc(),'SYN',m['known_by'])['corporate_action_observations'][kind]
    assert action['records']==[] and action['warning']
    assert not action['complete_event_coverage_verified'] and not action['pagination_completeness_attested']


@pytest.mark.parametrize('field',['symbol','provider','currency','known_by','schema_version'])
def test_foreign_asset_provider_currency_schema_and_future_manifest_rejected(tmp_path,field):
    m,_,_,_,desc,_=case(tmp_path);m[field]='2026-11-06T00:00:00Z' if field=='known_by' else 'OTHER'
    with pytest.raises(PermissionError):read(desc(),'SYN','2026-11-05T19:45:00Z')


@pytest.mark.parametrize('change',['ticker','scope','endpoint','sort','limit','future','time_order','error'])
def test_actual_query_and_capture_are_bound(tmp_path,change):
    m,c,_,_,desc,_=case(tmp_path);r=c['splits']
    if change=='ticker':r['params']['ticker']='OTHER'
    elif change=='scope':r['params']['execution_date.gte']='2021-11-02'
    elif change=='endpoint':r['path']='/stocks/v1/dividends'
    elif change=='sort':r['params']['sort']='execution_date.desc'
    elif change=='limit':r['params']['limit']=True
    elif change=='future':r['retrieved_at']='2026-11-06T00:00:00Z'
    elif change=='time_order':r['started_at']='2026-11-06T00:00:00Z'
    else:r['response_is_error']=True
    with pytest.raises(PermissionError):read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('which',['manifest','csv','receipt','tool'])
def test_every_source_byte_is_rechecked(tmp_path,which):
    m,c,_,_,desc,_=case(tmp_path);d=desc();source={'manifest':d,'csv':m['sources']['splits']['source'],
        'receipt':m['sources']['splits']['acquisition_source'],'tool':c['splits']['tool_response_source']}[which]
    Path(source['local_path']).write_text('CHANGED')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read(d,'SYN',m['known_by'])


@pytest.mark.parametrize('change',['response','error'])
def test_coherent_csv_hash_cannot_override_captured_connector_result(tmp_path,change):
    m,_,o,_,desc,_=case(tmp_path)
    if change=='response':o['splits']['structuredContent']['result']='OTHER'
    else:o['splits']['isError']=True
    with pytest.raises(PermissionError,match='CONNECTOR_RESPONSE'):read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('change',['duplicate','other_ticker','outside','duplicate_header','truncated','nan','zero_ratio','type','currency','declaration'])
def test_action_identity_numbers_dates_and_original_structure_not_repaired(tmp_path,change):
    m,_,_,text,desc,replace=case(tmp_path);kind='splits';s=text[kind]
    if change=='duplicate':s+=s.splitlines()[1]+'\n'
    elif change=='other_ticker':s=s.replace(',SYN,',',OTHER,')
    elif change=='outside':s=s.replace('2021-11-02','2021-11-05')
    elif change=='duplicate_header':s=s.replace('split_from','split_to')
    elif change=='truncated':s=s.rsplit(',',1)[0]+'\n'
    elif change=='nan':s=s.replace(',1,4,',',NaN,4,')
    elif change=='zero_ratio':s=s.replace(',1,4,',',0,4,')
    elif change=='type':s=s.replace('forward_split','unknown')
    else:
        kind='dividends';s=text[kind]
        s=s.replace(',USD,',',TWD,') if change=='currency' else s.replace('2021-10-20','2021-11-04')
    replace(kind,s)
    with pytest.raises((ValueError,PermissionError)):read(desc(),'SYN',m['known_by'])


def test_stock_dividend_observation_does_not_become_pure_split(tmp_path):
    m,_,_,text,desc,replace=case(tmp_path);replace('splits',text['splits'].replace('forward_split','stock_dividend'))
    event=read(desc(),'SYN',m['known_by'])['corporate_action_observations']['splits']['records'][0]
    assert event['adjustment_type']=='stock_dividend' and not event['pure_split_semantics_verified']


def test_small_original_dividend_difference_is_preserved_without_epsilon(tmp_path):
    m,_,_,text,desc,replace=case(tmp_path)
    replace('dividends',text['dividends'].replace('1.00','0.2724'))
    observations=read(desc(),'SYN',m['known_by'])['corporate_action_observations']
    events=[dict(type='CashDividends',date='20211103',value='0.27239',currency='USD'),
        dict(type='Splits',date='20211102',value='4.0')]
    before=deepcopy((observations,events))
    compared=compare_ibkr(observations,events,date(2021,11,1),date(2021,11,3))
    assert len(compared['matching_numeric_observations'])==1
    assert compared['differing_original_values']==[dict(kind='dividends',session_id='2021-11-03',
        IB_original_value='0.27239',Massive_original_value='0.2724')]
    assert not compared['original_values_repaired'] and not compared['cash_or_split_basis_reconciled']
    assert (observations,events)==before


def test_two_real_distributions_on_same_date_are_not_silently_collapsed_or_summed(tmp_path):
    m,_,_,text,desc,replace=case(tmp_path)
    replace('dividends',text['dividends']+text['dividends'].splitlines()[1].replace('D1,','D2,')+'\n')
    observations=read(desc(),'SYN',m['known_by'])['corporate_action_observations']
    compared=compare_ibkr(observations,[dict(type='CashDividends',date='20211103',value='1.00',currency='USD')],
        date(2021,11,1),date(2021,11,3))
    assert not compared['matching_numeric_observations'] and not compared['differing_original_values']
    assert len(compared['ambiguous_same_date_events'][0]['Massive_original_rows'])==2


@pytest.mark.parametrize('change',['duplicate','currency','type','date','value'])
def test_comparison_cannot_hide_invalid_or_ambiguous_original_events(tmp_path,change):
    m,_,_,_,desc,_=case(tmp_path);observations=read(desc(),'SYN',m['known_by'])['corporate_action_observations']
    events=[dict(type='CashDividends',date='20211103',value='1.00',currency='USD')]
    if change=='duplicate':events.append(deepcopy(events[0]))
    else:events[0][change]={'currency':'TWD','type':'OTHER','date':'BAD','value':'NaN'}[change]
    with pytest.raises((ValueError,PermissionError)):compare_ibkr(observations,events,date(2021,11,1),date(2021,11,3))


def test_receipt_bound_public_ibkr_original_is_compared_through_real_document_reader(tmp_path):
    m,_,_,_,desc,_=case(tmp_path)
    original=dict(schema='Family.PM.IBKR.PublicHistoricalBatch.v1',source_tool='IB.get_price_history',
        query=dict(period='FIVE_YEARS',step='ONE_DAY',outside_rth=False,include_corporate_actions=True),
        observations=[dict(ticker='SYN',contract_id=123,exchange='NYSE ARCA',started_at=m['known_by'],
            retrieved_at=m['known_by'],source={'corp_actions':[dict(type='CashDividends',date='20211103',value='0.999',currency='USD')]})])
    p=tmp_path/'PUBLIC_IB.json';p.write_text(json.dumps(original))
    m['ibkr_comparison_source']=dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest(),
        symbol='SYN',contract_id=123,provider_exchange='NYSE ARCA',retrieved_at=m['known_by'])
    result=read(desc(),'SYN',m['known_by']);comparison=result['cross_provider_comparison']
    assert len(comparison['differing_original_values'])==1 and not result['qP_history_qualified']
    m['ibkr_comparison_source']['symbol']='OTHER'
    with pytest.raises(PermissionError,match='COMPARISON_ASSET_OR_TIME'):read(desc(),'SYN',m['known_by'])


def test_new_public_route_reaches_original_same_run_c7_observations_without_releasing_scope(tmp_path):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import assemble
    _,_,request,context,tactical,identities,_,_=original_case(tmp_path)
    m,_,_,_,desc,_=case(tmp_path,request['evaluation_at']);sources={'corporate_actions':desc()}
    observed=bind(sources,request,'SYN')
    context['public_history_source_binding']={**{k:request[k] for k in ('client_id','run_id')},
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],'asset_id':'SYN',
        'source_descriptors':sources,'digest':observed['digest']}
    result=assemble(ROOT,request,context,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities)
    assert result['original_observations']['public_history_source_qualification']==observed
    assert not observed['financial_qualification_released'] and observed['qualified_qP_history'] is None
    assert result.get('source_descriptor') is None

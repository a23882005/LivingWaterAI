"""Source shortfalls do not become full history, zero events or native qP."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from historical_source_qualification import read_market,bind


def case(tmp_path):
    def file(name,text):
        p=tmp_path/name;p.write_text(text)
        return {'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
    stamps=[int(datetime(2021,11,d,tzinfo=ZoneInfo('America/New_York')).timestamp()*1000) for d in (1,2,3)]
    prices='v,o,c,h,l,t\n'+''.join(f'100,10,11,12,9,{t}\n' for t in stamps)
    div='id,ticker,ex_dividend_date,declaration_date,cash_amount,currency,split_adjusted_cash_amount\nD1,SYN,2021-11-03,2021-11-01,1.00,USD,0.25\n'
    split='id,ticker,execution_date,split_from,split_to,adjustment_type,historical_adjustment_factor\nS1,SYN,2021-11-02,1,4,forward_split,0.25\n'
    m={'schema_version':'Family.W8.HistoricalMarketIntake.v1','provider':'MASSIVE','symbol':'SYN',
        'exchange_timezone':'America/New_York','quote_currency':'USD','requested_start':'2021-11-01',
        'requested_end':'2021-11-03','known_by':'2026-11-03T15:00:00Z',
        'prices':{'source':file('prices.csv',prices),'query':{'path':'/v2/aggs/ticker/SYN/range/1/day/2021-11-01/2021-11-03',
            'params':{'adjusted':False,'sort':'asc','limit':50000}}}}
    for key,path,column,text in [('dividends','/stocks/v1/dividends','ex_dividend_date',div),('splits','/stocks/v1/splits','execution_date',split)]:
        m[key]={'source':file(key+'.csv',text),'query':{'path':path,'params':{'ticker':'SYN',column+'.gte':'2021-11-01',column+'.lte':'2021-11-03'}}}
    def descriptor():
        for key in ('prices','dividends','splits'):
            source=m[key]['source'];source['sha256']=sha256(Path(source['local_path']).read_bytes()).hexdigest()
        return file('manifest.json',json.dumps(m))
    return m,descriptor


def test_raw_prices_and_original_cash_are_observations_without_historical_pit(tmp_path):
    _,desc=case(tmp_path);out=read_market(desc(),'SYN','2026-11-03T16:00:00Z')
    assert out['returned_bar_count']==3 and out['query_requested_unadjusted']
    assert out['corporate_action_observations']['dividends']['records'][0]['original_cash_amount']=='1.00'
    assert out['corporate_action_observations']['splits']['records'][0]['new_per_old']=='4'
    assert all(r['available_at'] is None for r in out['raw_observed_bars'])
    assert not out['qP_history_qualified'] and not out['qV_history_qualified']
    assert out['qualified_native_price_history'] is None and not out['adjusted_close_or_split_adjusted_dividend_used']


def test_entitlement_or_listing_gaps_are_named_and_never_filled(tmp_path):
    m,desc=case(tmp_path);p=Path(m['prices']['source']['local_path']);lines=p.read_text().splitlines()
    p.write_text('\n'.join([lines[0],*lines[2:]])+'\n');out=read_market(desc(),'SYN','2026-11-03T16:00:00Z')
    assert out['returned_bar_count']==2
    assert any(x['code'].startswith('REQUESTED_START_NOT_RETURNED') for x in out['issues'])


@pytest.mark.parametrize('kind',['dividends','splits'])
def test_empty_warning_does_not_prove_zero_events_or_ticker_validity(tmp_path,kind):
    m,desc=case(tmp_path);Path(m[kind]['source']['local_path']).write_text('Warning [EMPTY]: may be invalid, delisted, or have no data')
    out=read_market(desc(),'SYN','2026-11-03T16:00:00Z')
    assert out['corporate_action_observations'][kind]['records']==[]
    assert not out['corporate_action_observations'][kind]['complete_event_coverage_verified']
    assert any(x['code']=='EMPTY_OR_OTHER_WARNING_IS_NOT_COMPLETE_ZERO_EVENTS' for x in out['issues'])


@pytest.mark.parametrize('change',['adjusted','symbol','future','duplicate','ohlc','currency','action_scope'])
def test_adjusted_price_foreign_sources_and_incoherent_original_rows_rejected(tmp_path,change):
    m,desc=case(tmp_path)
    if change=='adjusted':m['prices']['query']['params']['adjusted']=True
    elif change=='symbol':m['symbol']='OTHER'
    elif change=='future':m['known_by']='2026-11-04T16:00:00Z'
    elif change=='action_scope':m['splits']['query']['params']['ticker']='OTHER'
    else:
        key='dividends' if change=='currency' else 'prices';p=Path(m[key]['source']['local_path']);s=p.read_text()
        if change=='currency':s=s.replace(',USD,',',GBP,')
        elif change=='duplicate':s+=s.splitlines()[1]+'\n'
        else:s=s.replace('100,10,11,12,9,','100,10,99,12,9,',1)
        p.write_text(s)
    with pytest.raises((ValueError,PermissionError)):read_market(desc(),'SYN','2026-11-03T16:00:00Z')


def test_original_source_hash_cannot_be_replaced_by_saved_projection(tmp_path):
    m,desc=case(tmp_path);d=desc();Path(m['prices']['source']['local_path']).write_text('REPLACED')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read_market(d,'SYN','2026-11-03T16:00:00Z')


def test_public_history_projection_carries_actual_member_run_without_qualifying_finance(tmp_path):
    _,desc=case(tmp_path);request={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN',
        'evaluation_at':'2026-11-03T16:00:00Z','client_snapshot':{'payload':{'source_sha256':'a'*64}}}
    out=bind({'market_acquisition':desc()},request,'SYN')
    assert out['client_id']==request['client_id'] and out['run_id']==request['run_id']
    assert out['source_db_sha256']=='a'*64 and out['asset_id']=='SYN'
    assert out['qualified_qP_history'] is out['qualified_qV_history'] is None
    assert not out['financial_qualification_released']


def test_member_financial_consumer_rejects_different_history_between_analysis_and_producer(tmp_path,monkeypatch):
    from member_financial_chain import complete_report
    import member_financial_producer
    report={'positions':[{'symbol':'SYN','history_source_qualification':{'digest':'a'*64}}],'report_digest':'b'*64}
    monkeypatch.setattr(member_financial_producer,'produce',lambda *args,**kwargs:({'public_history_source_binding':{'digest':'c'*64}},None))
    with pytest.raises(PermissionError,match='PUBLIC_HISTORY_SOURCE_REPLAY_MISMATCH'):
        complete_report(report,{'client_id':'SYNTHETIC_CLIENT'},
            {'financial_producer_sources':{'SYN':{}},'public_history_sources':{'SYN':{}}},ROOT)


@pytest.mark.parametrize('field',['client_id','run_id','source_db_sha256','digest'])
def test_original_c7_consumer_rejects_other_member_run_db_or_pasted_history_digest(tmp_path,monkeypatch,field):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import assemble
    import historical_source_qualification
    _,_,request,context,tactical,identities,_,_=original_case(tmp_path)
    binding={'client_id':request['client_id'],'run_id':request['run_id'],
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'asset_id':'SYN','source_descriptors':{'market_acquisition':{}},'digest':'b'*64}
    binding[field]='OTHER';context['public_history_source_binding']=binding
    monkeypatch.setattr(historical_source_qualification,'bind',lambda *args:{'digest':'b'*64})
    with pytest.raises(PermissionError):assemble(ROOT,request,context,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities)


def current_case(tmp_path):
    manifest, _ = case(tmp_path)
    captured = '2021-11-03T20:30:00Z'
    manifest.update(capture_format='MASSIVE_PROVIDER_RESPONSE_V1',exchange='XNAS',known_by=captured,
        first_covered_session='2021-11-01')

    def pin(name, value):
        path = tmp_path/name
        path.write_text(json.dumps(value))
        return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}

    manifest['calendar_check'] = pin('calendar.json',
        {'XNAS':{'sessions':3,'missing':[],'extra':[],'calendar_version':'4.13.2'}})
    for name in ('prices','dividends','splits'):
        item = manifest[name]
        receipt = {**item.pop('query'),'started_at':'2021-11-03T20:25:00Z','retrieved_at':captured,
            'provider_response':Path(item['source']['local_path']).read_text()}
        if name == 'prices':
            receipt['params']['adjusted'] = 'false'
            manifest['adjusted_prices'] = pin('adjusted.json',
                {**receipt,'params':{**receipt['params'],'adjusted':'true'},
                 'provider_response':receipt['provider_response'].replace('100,10,11,12,9,','400,2.5,2.75,3,2.25,',1)})
        elif name == 'splits':
            receipt['params']['execution_date.gte'] = '2021-11-02'
        item['source'] = pin(name+'.json',receipt)
    return pin('current.json',manifest)


def test_current_archive_segments_on_split_without_adjusted_or_partial_periods(tmp_path,monkeypatch):
    import on_demand_market_observations
    from historical_source_qualification import technical_market

    at = '2021-11-03T20:31:00Z'
    desc = current_case(tmp_path)
    history = read_market(desc,'SYN',at)
    assert history['current_history']['continuous_completed_session_count'] == 3
    assert history['current_history']['adjusted_price_evidence']['returned_bar_count'] == 3
    assert history['corporate_action_observations']['splits']['requested_start'] == '2021-11-02'
    assert history['corporate_action_observations']['dividends']['records'][0]['original_cash_amount'] == '1.00'

    def evaluate(rows, **options):
        assert [row['Date'] for row in rows] == ['2021-11-02','2021-11-03']
        assert [row['_source_decimal']['Volume'] for row in rows] == ['100','100']
        return {'approved_technical':{'timeframes':{}},'call_trace':[]}

    monkeypatch.setattr(on_demand_market_observations,'evaluate_observed_history',evaluate)
    obs = technical_market(history,evaluation_at=at,repo_root=ROOT,profile={},is_etf=True)
    assert obs['rows'] == 2 and obs['observed_close'] == 11
    assert obs['approved_technical']['timeframes']['weekly']['completed_period_count'] == 0
    assert obs['history_quality']['discarded_before_latest_observed_split'] == 1
    assert not obs['history_quality']['adjusted_prices_used']
    assert not history['qP_history_qualified']


def test_current_archive_rejects_future_capture_and_stale_completed_session(tmp_path):
    desc = current_case(tmp_path)
    with pytest.raises(PermissionError,match='TIME_MISMATCH'):
        read_market(desc,'SYN','2021-11-03T20:29:59Z')
    with pytest.raises(ValueError,match='CURRENT_CLOSE_STALE'):
        read_market(desc,'SYN','2021-11-04T20:31:00Z')

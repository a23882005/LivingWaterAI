"""Synthetic market receipts exercise replay, identity and no-promotion guards."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv,json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import qualified_equity_inputs as M
from family_input import digest
from technical_source_bridge import VERSION


def save(path,value):
    path.write_text(json.dumps(value));return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}


def fixture(folder,symbol='VT',post_close=False):
    import exchange_calendars as xc
    cal=xc.get_calendar('XNYS',start='2026-10-01',end='2026-11-05')
    sessions=cal.sessions_in_range('2026-10-01','2026-10-29' if post_close else '2026-10-28');days=[str(s.date()) for s in sessions]
    quote={k:[] for k in ('open','high','low','close','volume')};rows=[];receipts=[]
    available='2026-10-29T03:00:00Z';written='2026-10-29T03:00:01Z'
    if post_close:available='2026-10-29T21:00:00Z';written='2026-10-29T21:00:01Z'
    for i,session in enumerate(sessions):
        values={'open':100+i,'high':102+i,'low':99+i,'close':101+i,'volume':1000+i}
        for k,v in values.items():quote[k].append(v)
        rows.append({'Date':days[i],**{k:str(values[key]) for k,key in
            [('Open','open'),('High','high'),('Low','low'),('Close','close'),('Volume','volume')]}})
        receipts.append({'session':days[i],'close_at':cal.session_close(session).to_pydatetime().isoformat(),
            'available_at':available,'completed':True,'formal_close_available':True})
    exchange='ARCA' if symbol=='VT' else 'NASDAQ'
    chart={'chart':{'error':None,'result':[{'meta':{'symbol':symbol,'currency':'USD','exchangeName':'PCX' if symbol=='VT' else 'NGM',
        'instrumentType':'ETF','dataGranularity':'1d'},'timestamp':[int(cal.session_open(s).timestamp()) for s in sessions],
        'events':{'dividends':{'SYNTHETIC':{'amount':1}}},'indicators':{'quote':[quote]}}]}}
    yahoo=save(folder/'synthetic-yahoo.json',chart)
    receipt={'url':'https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?range=5y&interval=1d&events=div%2Csplits',
        'http_status':200,'sha256':yahoo['sha256'],'requested_at':'2026-10-29T02:59:00Z',
        'available_at':available,'artifact_written_at':written}
    receipt_source=save(folder/'synthetic-receipt.json',receipt)
    yahoo.update(receipt_path=receipt_source['local_path'],receipt_sha256=receipt_source['sha256'])
    contract={'symbol':symbol,'country_code':'US','exchange':exchange,'underlying_contract_id':123,
        'description':'SYNTHETIC_NOT_MARKET_EVIDENCE','sections':[{'security_type':'STK'}]}
    identity=save(folder/'synthetic-contract.json',{'structuredContent':{'results':[contract]}})
    ibkr=save(folder/'synthetic-ibkr.json',{'requested_at':'2026-10-29T02:50:00Z','available_at':'2026-10-29T02:51:00Z',
        'args':{'contract_id':123,'exchange':exchange,'security_type':'STK',
        'outside_rth':False,'period':'FIVE_YEARS','step':'ONE_DAY','include_corporate_actions':True},
        'contract':contract,'response':{'structuredContent':{'corp_actions':[{'type':'CashDividends','currency':'USD'}]}}})
    csv_path=folder/'synthetic-VT.csv'
    with csv_path.open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['Date','Open','High','Low','Close','Volume']);writer.writeheader();writer.writerows(rows)
    metadata={'asset_id':symbol,'symbol':symbol,'exchange':exchange,'currency':'USD','instrument_reference':'IBKR:123',
        'source_reference':receipt['url'],'receipt_reference':'SHA256:'+receipt_source['sha256'],
        'calendar_reference':'exchange_calendars@'+xc.__version__+':XNYS','session_timezone':'America/New_York',
        'provider_price_basis':'RAW_QUOTE_CLOSE_NOT_ADJ_CLOSE__NO_SPLIT_EVENTS_IN_WINDOW',
        'source_run':'READONLY_CAPTURE:'+yahoo['sha256'],'producer_version':VERSION,'timeframe':'DAILY',
        'price_field':'Close','auto_adjust':False,'split_basis_verified':True,
        'calendar_sessions':days,'bar_receipts':receipts,'history_digest':digest(rows),
        'evaluation_mode':'SNAPSHOT_AFTER_ACQUISITION','artifact_written_at':written,
        'fetch_completed_at':available,'data_provenance':'SOURCE_BACKED'}
    qualified={'schema_version':'Family.W8.EquitySourceQualification.v1','symbol':symbol,
        'source_evaluation_at':'2026-10-29T21:01:00Z' if post_close else '2026-10-29T03:01:00Z','contract':contract,'rows':len(rows),'excluded_bars':[],
        'source_artifacts':{'yahoo':yahoo,'ibkr_identity':identity,'ibkr_history':ibkr},
        'technical_source_template':{'csv_path':str(csv_path),'sha256':sha256(csv_path.read_bytes()).hexdigest(),
            'metadata':metadata}}
    return qualified,publish(folder,qualified)


def postclose_market(folder):
    _,descriptor=fixture(folder,post_close=True)
    pool=M.read(descriptor,'2026-10-29T21:02:00Z',ROOT);source=pool['items']['VT']
    return pool,{'symbol':'VT','observed_date':source['observed_date'],
        'provider_verified_at':source['source_available_at'],'formal_identity_verified':True,
        'qualified_equity_market_digest':source['digest'],
        'source_sha256':source['technical_source_template']['sha256']}


def test_holdings_accept_same_utc_day_only_after_qualified_equity_close_and_capture(tmp_path):
    from holdings_analysis import validate_market_time
    pool,market=postclose_market(tmp_path)
    assert pool['items']['VT']['status']=='FRESH' and market['observed_date']=='2026-10-29'
    validate_market_time(market,'VT','2026-10-29T21:02:00Z',pool)
    with pytest.raises(PermissionError,match='MARKET_BINDING_OR_TIME'):
        validate_market_time(market,'VT','2026-10-29T19:59:00Z',pool)


@pytest.mark.parametrize('changed',['digest','source_hash','identity','stale','preclose_capture','future_observed'])
def test_holdings_same_day_equity_proof_cannot_be_inferred_or_relabelled(tmp_path,changed):
    from holdings_analysis import validate_market_time
    pool,market=postclose_market(tmp_path);source=pool['items']['VT']
    if changed=='digest':market['qualified_equity_market_digest']='0'*64
    elif changed=='source_hash':market['source_sha256']='0'*64
    elif changed=='identity':market['formal_identity_verified']=False
    elif changed=='stale':source['status']='STALE'
    elif changed=='preclose_capture':source['raw_history_available_at']='2026-10-29T19:59:59Z'
    else:market['observed_date']='2026-10-30'
    with pytest.raises(PermissionError,match='MARKET_BINDING_OR_TIME'):
        validate_market_time(market,'VT','2026-10-29T21:02:00Z',pool)


def test_holdings_unqualified_same_day_market_remains_rejected(tmp_path):
    from holdings_analysis import validate_market_time
    _,market=postclose_market(tmp_path)
    with pytest.raises(PermissionError,match='MARKET_BINDING_OR_TIME'):
        validate_market_time(market,'VT','2026-10-29T21:02:00Z')


def publish(folder,qualified):
    source=save(folder/'synthetic-qualification.json',qualified)
    manifest=save(folder/'synthetic-manifest.json',{'schema_version':'Family.W8.EquitySourceQualificationManifest.v1',
        'items':{qualified['symbol']:source}})
    return {'schema_version':'Family.W8.QualifiedEquityManifestSource.v1',**manifest}


def test_raw_samples_are_complete_without_promoting_deployment_or_historical_pit(tmp_path):
    qualified,descriptor=fixture(tmp_path);pool=M.read(descriptor,'2026-10-29T04:00:00Z',ROOT)
    source=pool['items']['VT'];assert source['status']=='FRESH'
    assert source['technical_sample_state']=='COMPLETE'
    assert source['source_available_at']==qualified['source_evaluation_at']
    assert source['session_close_at']=='2026-10-28T20:00:00+00:00'
    assert source['formal_technical_producer_complete'] is False
    assert source['historical_publication_times_asserted'] is False
    assert source['full_equity_deployment_attestation'] is False
    assert M.read(None,'2026-10-29T04:00:00Z',ROOT) is None


@pytest.mark.parametrize('field',['auto_adjust','split_basis_verified','bar_receipts'])
def test_rehashed_metadata_cannot_relabel_price_basis_or_session_receipts(tmp_path,field):
    q,_=fixture(tmp_path);q['technical_source_template']['metadata'][field]=[] if field=='bar_receipts' else field=='auto_adjust'
    with pytest.raises(PermissionError,match='EQUITY_TECHNICAL_METADATA_MISMATCH'):
        M.read(publish(tmp_path,q),'2026-10-29T04:00:00Z',ROOT)


@pytest.mark.parametrize('kind',['country','security_type','duplicate'])
def test_primary_security_identity_is_not_inferred_from_a_symbol_only(tmp_path,kind):
    q,_=fixture(tmp_path);source=q['source_artifacts']['ibkr_identity'];data=json.loads(Path(source['local_path']).read_text())
    row=data['structuredContent']['results'][0]
    if kind=='country':row['country_code']='OTHER'
    elif kind=='security_type':row['sections']=[{'security_type':'IND'}]
    else:data['structuredContent']['results'].append(deepcopy(row))
    q['source_artifacts']['ibkr_identity']=save(Path(source['local_path']),data)
    with pytest.raises(PermissionError,match='EQUITY_CONTRACT_AMBIGUOUS_OR_CHANGED'):
        M.read(publish(tmp_path,q),'2026-10-29T04:00:00Z',ROOT)


def test_changed_source_bytes_and_future_qualification_are_rejected(tmp_path):
    q,descriptor=fixture(tmp_path)
    with pytest.raises(PermissionError,match='EQUITY_QUALIFICATION_IDENTITY_OR_TIME'):
        M.read(descriptor,'2026-10-29T03:00:00Z',ROOT)
    Path(q['source_artifacts']['yahoo']['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='EQUITY_SOURCE_BYTES_CHANGED'):
        M.read(descriptor,'2026-10-29T04:00:00Z',ROOT)


@pytest.mark.parametrize('kind',['qualification_before_capture','ibkr_after_qualification'])
def test_qualification_clock_cannot_backdate_either_provider_capture(tmp_path,kind):
    q,_=fixture(tmp_path)
    if kind=='qualification_before_capture':q['source_evaluation_at']='2026-10-29T02:00:00Z'
    else:
        source=q['source_artifacts']['ibkr_history'];body=json.loads(Path(source['local_path']).read_text())
        body['available_at']='2026-10-29T04:30:00Z'
        q['source_artifacts']['ibkr_history']=save(Path(source['local_path']),body)
    with pytest.raises(PermissionError,match='EQUITY_.*TIME'):
        M.read(publish(tmp_path,q),'2026-10-29T04:00:00Z',ROOT)


def test_csv_values_cannot_override_the_hash_bound_raw_quotes(tmp_path):
    q,_=fixture(tmp_path);template=q['technical_source_template'];path=Path(template['csv_path'])
    path.write_text(path.read_text().replace(',101,',',100.5,'))
    template['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError,match='EQUITY_HISTORY_RAW_OR_CALENDAR_MISMATCH'):
        M.read(publish(tmp_path,q),'2026-10-29T04:00:00Z',ROOT)


def test_analysis_updates_keep_approved_rules_and_replay_the_same_snapshot(tmp_path):
    _,descriptor=fixture(tmp_path);at='2026-10-29T04:00:00Z';pool=M.read(descriptor,at,ROOT)
    raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-29T02:00:00Z','verification':{'ready':False}}
    req={'evaluation_at':at,'qualified_equity_source_digest':digest(descriptor),
        'macro_snapshot':{'payload':raw,'digest':digest(raw)},'client_snapshot':{'payload':{
            'source_sha256':'a'*64,'tables':{'portfolio_instrument':[{'instrument_key':'SYNTHETIC_VT','ticker':'VT',
                'quote_currency':'USD','exchange_code':None}]}}}}
    ctx={'qualified_equity_source_manifest':descriptor,'sgov_role_classification_source':None}
    from approved_v04_technical import load_profile
    profile=load_profile(HERE/'owner_approved_v10.json')
    old={'assets':[{'symbol':'VT','instrument_key':'SYNTHETIC_VT','observed_date':'2026-10-27'}]}
    before=deepcopy((old,req,pool))
    result=M.apply(old,pool,req,ROOT,None,profile);market=result['assets'][0]
    assert market['observed_date']=='2026-10-28' and market['observed_close']==120
    assert market['approved_technical']['spec_version']=='1.0'
    assert market['formal_deployment_eligible'] is False
    assert market['analysis_identity_mapping']['held_exchange_inferred'] is False
    assert (old,req,pool)==before
    report={'qualified_equity_inputs':pool,'analysis_result':{'positions':[{'market':market}]}}
    M.validate(req,ctx,report,ROOT)
    market['observed_close']=999
    with pytest.raises(PermissionError,match='EQUITY_MARKET_REPLAY_MISMATCH'):M.validate(req,ctx,report,ROOT)


def test_qualified_market_contract_reaches_the_original_holdings_report_and_mentor(tmp_path):
    from test_holdings_analysis import HoldingAnalysisTest
    from approved_v04_technical import load_profile
    case=HoldingAnalysisTest();case.setUp()
    try:
        _,descriptor=fixture(tmp_path);at='2026-10-29T04:00:00Z';pool=M.read(descriptor,at,ROOT)
        case.request.update(evaluation_at=at,qualified_equity_source_digest=digest(descriptor))
        raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-29T02:00:00Z','verification':{'ready':False}}
        case.request['macro_snapshot']={'payload':raw,'digest':digest(raw)}
        case.snapshot['tables']['portfolio_instrument'][0]['quote_currency']='USD'
        old={'assets':[{'symbol':'VT','instrument_key':'SYNTHETIC_VT','observed_date':'2026-10-27'}],'missing':[]}
        observations=M.apply(old,pool,case.request,ROOT,case.producer.class_source,load_profile(HERE/'owner_approved_v10.json'))
        report=case.report(observations)
        row=report['analysis_result']['positions'][0]
        assert row['market']['observed_date']=='2026-10-28'
        ref=next(r for r in row['source_refs'] if r.get('source_kind')=='ISSUER_LISTING_ANALYSIS_REFERENCE')
        assert ref['sha256']==pool['manifest_sha256'] and ref['url']==pool['items']['VT']['source_reference']
        assert report['mentor'] is not None and report['canonical_result'] is None
        assert report['deployment_status']['status']=='NOT_RUN'
    finally:case.doCleanups()


def technical_binding_case(folder):
    _,descriptor=fixture(folder);at='2026-10-29T04:00:00Z';pool=M.read(descriptor,at,ROOT)
    owner={'client_id':'SYNTHETIC_CLIENT','account':'SYNTHETIC_ACCOUNT','broker':'SYNTHETIC_BROKER','currency':'USD'}
    source=deepcopy(pool['items']['VT']['technical_source_template'])
    approval=HERE/'owner_approved_v10.json'
    source.update(client_id=owner['client_id'],family_owner=owner,verified_asset_type='BROAD_ETF',
        owner_approved_rule_source={'local_path':str(approval),'sha256':sha256(approval.read_bytes()).hexdigest()})
    request={'client_id':owner['client_id'],'owner':owner,'evaluation_at':at,'technical_source_digest':digest(source),
        'native_bundle':{'stock_request':{'asset_context':{'asset':{'asset_id':'VT','asset_type':'BROAD_ETF'}}},
            'stock_evidence':{'exchange':'ARCA','currency':'USD'}}}
    context={'technical_source':source,'native_binding':{'data_provenance':'SOURCE_BACKED'}}
    return request,context,pool


def test_original_family_technical_bridge_retains_all_approved_v1_signals_and_nonvoting_eps(tmp_path):
    from family_technical_bridge import bind_technical_source,apply_technical_source
    from approved_v04_technical import load_profile,produce
    from technical_source_bridge import predicate_votes
    request,context,pool=technical_binding_case(tmp_path)
    result=bind_technical_source(ROOT,request,context)
    approved=produce(pool['items']['VT']['rows'],profile=load_profile(HERE/'owner_approved_v10.json'),is_etf=True)
    assert result['signals']==approved['signals'] and result['ma20_ok']==approved['ma20_ok']
    assert result['owner_approved_technical']['spec_version']=='1.0'
    bundle={'stock_evidence':{'core':{},'source_reference':'SYNTHETIC_NO_FINANCIAL_DECISIONS',
        'asset_id':'VT','currency':'USD','available_at':request['evaluation_at']},
        'stock_source_fields':{},'producer_contract':{}}
    effective=apply_technical_source(bundle,result)
    assert effective['stock_evidence']['core']['up_confirm']==predicate_votes(approved['signals']['up_confirm'])
    assert 'NOT_APPLICABLE' not in effective['stock_evidence']['core']['up_confirm']
    assert effective['producer_contract']['parameters']['owner_approved_spec_sha256']==approved['spec_sha256']


@pytest.mark.parametrize('kind',['approval_hash','approval_path','product_type'])
def test_rehashed_technical_source_cannot_replace_the_approved_rules_or_product_route(tmp_path,kind):
    from family_technical_bridge import bind_technical_source
    from family_boundary import BoundaryError
    request,context,_=technical_binding_case(tmp_path);source=context['technical_source']
    if kind=='approval_hash':source['owner_approved_rule_source']['sha256']='0'*64
    elif kind=='approval_path':source['owner_approved_rule_source']['local_path']=str(tmp_path/'other-approval.json')
    else:source['verified_asset_type']='INDIVIDUAL_STOCK'
    request['technical_source_digest']=digest(source)
    with pytest.raises(BoundaryError,match='TECHNICAL_APPROV'):
        bind_technical_source(ROOT,request,context)

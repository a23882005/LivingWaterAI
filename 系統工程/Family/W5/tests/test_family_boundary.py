from copy import deepcopy
from pathlib import Path
import json
import pytest
from family_input import TABLES,digest
from family_boundary import prepare_input,BoundaryError


def fixture(client='SYNTHETIC_A',empty=False):
    at='2026-10-20T12:00:00Z';past='2026-10-01T00:00:00Z'
    owner={'client_id':client,'funding_domain':'INVESTMENT_1','broker':'BROKER_1','account':'ACCOUNT_1','currency':'USD'}
    tables={t:[] for t in TABLES}
    def row(**kw):return {'client_id':client,'created_at_utc':past,**kw}
    tables['portfolio_account']=[row(account_key='ACCOUNT_1',account_state='KNOWN',account_currency='USD',as_of_utc=past)]
    tables['account_ownership']=[row(account_key='ACCOUNT_1',owner_client_id=client,ownership_state='VERIFIED')]
    tables['account_broker_link']=[row(account_key='ACCOUNT_1',broker_key='BROKER_1',link_state='ACTIVE')]
    tables['funding_account_domain_link']=[row(account_key='ACCOUNT_1',currency_code='USD',funding_domain_key='INVESTMENT_1',link_state='VERIFIED')]
    tables['funding_domain']=[row(funding_domain_key='INVESTMENT_1',domain_state='ACTIVE',purpose_code='INVESTMENT_CANDIDATE')]
    tables['portfolio_instrument']=[row(instrument_key='VT_KEY',ticker='VT',exchange_code='ARCA',quote_currency='USD')]
    if not empty:tables['portfolio_position']=[row(account_key='ACCOUNT_1',instrument_key='VT_KEY',as_of_utc=past,quantity_decimal='2.125')]
    payload={'client_id':client,'tables':tables,'payload_digest':digest(tables)}
    # W2-18 shape; explicitly synthetic confirmed record with historical run.
    draft={'identity':{'client_id':client,'run_id':'OLD_CONFIRMATION_RUN'},'allocation_id':'ALLOC-SYNTHETIC-1','status':'DRAFT','confirmation_status':'PENDING','is_trade_authorized':False,'target_lines':[]}
    draft['draft_hash']=digest(draft)
    evidence={'action':'CONFIRM','client_explicit_decision':'TRUE','confirmed_at':past,'confirmed_by':client,'source_reference_ids':['SYNTHETIC_CONFIRMATION']}
    record={'version':1,'target_id':'FT-SYNTHETIC-1','target_hash':draft['draft_hash'],'status':'CONFIRMED','draft':draft,
        'proposed_at':past,'expires_at':'2026-10-02T00:00:00Z','confirmation_evidence':evidence,'confirmation_evidence_hash':digest(evidence),'source_reference_ids':['SYNTHETIC_CONFIRMATION']}
    target={'payload':record,'target_hash':record['target_hash'],'target_version':1,'confirmation_run_id':'OLD_CONFIRMATION_RUN'}
    macro={'payload':{'asOf':past,'quality':'SYNTHETIC'},'asOf':past,'source_path':'SYNTHETIC','source_commit':'SYNTHETIC','source_sha256':'SYNTHETIC','reader_sha256':'SYNTHETIC'};macro['digest']=digest(macro['payload'])
    versions={'target':'1','funding':'SYNTHETIC_F1','market':macro['digest'],'policy':'SYNTHETIC_P1'}
    req={'schema_version':'Family.W5.request.v1','client_id':client,'request_id':'REQ1','run_id':'NEW_ANALYSIS_RUN','evaluation_at':at,
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','owner':owner,'expected_versions':versions,
        'client_snapshot':{'payload':payload,'digest':digest(payload),'snapshot_version':'S1','as_of':past},'confirmed_target':target,'macro_snapshot':macro}
    ctx={'client_id':client,'analysis_permission':'ANALYZE_ONLY','expected_versions':deepcopy(versions),'snapshot_version':'S1','snapshot_digest':digest(payload),'target_hash':target['target_hash'],
        'holdings_completeness':{'state':'COMPLETE','account_key':'ACCOUNT_1','as_of':past,'source_reference':'SYNTHETIC_FULL_ACCOUNT_SNAPSHOT','snapshot_digest':payload['payload_digest']}}
    return req,ctx


def refresh_snapshot(req,ctx):
    p=req['client_snapshot']['payload'];p['payload_digest']=digest(p['tables']);req['client_snapshot']['digest']=digest(p);ctx['snapshot_digest']=digest(p);ctx['holdings_completeness']['snapshot_digest']=p['payload_digest']


def test_selected_macro_source_requires_its_independent_context_binding():
    req,ctx=fixture()
    selected={'schema_version':'Family.W5.VerifiedMacroFeedSource.v1',
        'local_path':'SYNTHETIC_SOURCE_NOT_READ_BY_THIS_CAPTURE_BOUNDARY','sha256':'a'*64}
    ctx['verified_macro_feed_source']=selected
    req['macro_snapshot']['source_sha256']=selected['sha256']
    req['macro_snapshot']['capture_receipt']={'source_selection_digest':digest(selected)}
    ctx['macro_capture_digest']=digest(req['macro_snapshot']['capture_receipt'])
    assert prepare_input(req,trusted_context=ctx).payload['engine_calls']==0
    ctx['verified_macro_feed_source']={**selected,'sha256':'b'*64}
    with pytest.raises(BoundaryError,match='MACRO_SOURCE_SELECTION_MISMATCH'):
        prepare_input(req,trusted_context=ctx)


@pytest.mark.parametrize('client',['SYNTHETIC_A','SYNTHETIC_B','SYNTHETIC_C','SYNTHETIC_D'])
def test_client_and_historical_target_binding(client):
    req,ctx=fixture(client);before=deepcopy(req)
    out=prepare_input(req,trusted_context=ctx)
    assert out.payload['target_binding']['confirmation_run_id']=='OLD_CONFIRMATION_RUN'
    assert out.payload['target_binding']['analysis_run_id']=='NEW_ANALYSIS_RUN'
    assert out.payload['positions'][0]['quantity']=='2.125'
    assert req==before and out.payload['engine_calls']==0


@pytest.mark.parametrize('case,code',[
    ('client','CLIENT_MISMATCH'),('owner','SOURCE_ROW_MISSING'),('version','VERSIONS_REQUIRED'),
    ('target_hash','TARGET_HASH'),('snapshot','SNAPSHOT_DIGEST'),('permission','ANALYSIS_PERMISSION'),
    ('target_client','TARGET_CLIENT'),('funding','VERSION_CONFLICT'),('macro','MACRO_DIGEST'),
    ('unknown_holdings','HOLDINGS_COMPLETENESS'),('pending_target','TARGET_NOT_CONFIRMED')])
def test_invalid_input_stops_before_engines(case,code):
    req,ctx=fixture();calls=[]
    if case=='client':req['client_id']='OTHER'
    elif case=='owner':req['owner']['account']='OTHER'
    elif case=='version':req['expected_versions'].pop('policy')
    elif case=='target_hash':req['confirmed_target']['target_hash']='0'*64
    elif case=='snapshot':req['client_snapshot']['payload']['tables']['portfolio_position'][0]['quantity_decimal']='3'
    elif case=='permission':ctx['analysis_permission']='NONE'
    elif case=='target_client':req['confirmed_target']['payload']['draft']['identity']['client_id']='OTHER'
    elif case=='funding':ctx['expected_versions']['funding']='F2'
    elif case=='macro':req['macro_snapshot']['payload']['quality']='CHANGED'
    elif case=='unknown_holdings':ctx['holdings_completeness']['state']='UNKNOWN'
    elif case=='pending_target':req['confirmed_target']['payload']['status']='PENDING'
    with pytest.raises(BoundaryError,match=code):
        prepare_input(req,trusted_context=ctx)
        calls.append('ENGINE')
    assert calls==[]


def test_empty_and_unknown_quantity_are_distinct():
    req,ctx=fixture(empty=True)
    assert prepare_input(req,trusted_context=ctx).payload['positions']==[]
    req,ctx=fixture();req['client_snapshot']['payload']['tables']['portfolio_position'][0]['quantity_decimal']=None;refresh_snapshot(req,ctx)
    assert prepare_input(req,trusted_context=ctx).payload['positions'][0]['quantity_state']=='UNKNOWN'


def test_foreign_row_even_with_recomputed_digest_rejected():
    req,ctx=fixture();req['client_snapshot']['payload']['tables']['portfolio_position'][0]['client_id']='OTHER';refresh_snapshot(req,ctx)
    with pytest.raises(BoundaryError,match='CROSS_CLIENT_ROW'):prepare_input(req,trusted_context=ctx)


def test_actual_w2_confirmation_record_reused_unchanged():
    target=json.loads((Path(__file__).parent/'fixtures/w2_confirmed_target.json').read_text())
    client=target['payload']['draft']['identity']['client_id'];req,ctx=fixture(client)
    before=deepcopy(target);req['confirmed_target']=target;ctx['target_hash']=target['target_hash']
    out=prepare_input(req,trusted_context=ctx)
    assert target==before
    assert out.payload['target_binding']['original_payload_digest']==digest(target['payload'])
    assert out.payload['target_binding']['allocation_id']==target['payload']['draft']['allocation_id']
    assert out.payload['target_binding']['target_record_id']==target['payload']['target_id']


def test_account_identity_and_currency_isolation():
    for field,value in [('broker','OTHER'),('currency','TWD'),('funding_domain','OTHER')]:
        req,ctx=fixture();req['owner'][field]=value
        with pytest.raises(BoundaryError):prepare_input(req,trusted_context=ctx)

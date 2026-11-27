"""Synthetic dispatcher contracts; no household data or simulated live result."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from member_financial_producer import produce
from family_input import digest


def test_accepted_owner_cash_removes_only_the_resolved_part_of_legacy_compound_gap():
    from member_financial_producer import remaining_root_gaps
    gaps=[{'code':'SAME_CUTOFF_SETTLEMENT_RESERVES_ORDERS_AND_FUNDING_DOMAIN_REQUIRED','field_path':'account_funding'},
        {'code':'UNRELATED_ORIGINAL_SOURCE_REQUIRED','field_path':'other'}]
    accepted={'financial_facts':{'accepted_owner_financial_facts':{'digest':'a'*64}}}
    out=remaining_root_gaps(gaps,accepted)
    assert out[0]['owner_cash_and_settlement_accepted'] and out[0]['current_buy_absence_accepted']
    assert out[0]['original_source_issue']==gaps[0] and out[1]==gaps[1]
    assert remaining_root_gaps(gaps,None)==gaps


def case(tmp_path):
    owner={'client_id':'SYNTHETIC_CLIENT','broker':'SYNTHETIC_BROKER','account':'SYNTHETIC_ACCOUNT','currency':'USD','funding_domain':'SYNTHETIC_DOMAIN'}
    req={'client_id':owner['client_id'],'run_id':'SYNTHETIC_RUN','evaluation_at':'2026-10-30T00:00:00Z','question':'SYNTHETIC_TEST',
        'client_snapshot':{'payload':{'source_sha256':'a'*64,'client_id':owner['client_id'],'tables':{}}},
        'confirmed_target':{'target_version':2,'payload':{'draft':{'target_lines':[{'ticker':'SYNTHETIC_ASSET',
            'target_amount':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}]}}},
        'macro_snapshot':{'synthetic':'prequalified macro; factory stub only'}}
    seed={**deepcopy(req),'owner':owner,'trade_authorization':'NONE'}
    data={'schema_version':'Family.W8.MemberFinancialProducer.v1','client_id':owner['client_id'],'asset_id':'SYNTHETIC_ASSET',
        'source_db_sha256':'a'*64,'target_version':2,'source_reference':'SYNTHETIC_SOURCE',
        'configuration':{'request_seed':seed,'context_seed':{'client_id':owner['client_id'],
            'family_c7_profile':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'}},'artifact_directory':str(tmp_path/'private_artifacts')}
    def desc():
        file=tmp_path/'SYNTHETIC_RAW_PRODUCER_SETTINGS.json';file.write_text(json.dumps(data))
        return {'local_path':str(file),'sha256':sha256(file.read_bytes()).hexdigest()}
    return req,data,desc


def test_exact_missing_roots_do_not_become_a_financial_pack(tmp_path):
    r,d,desc=case(tmp_path);d['configuration']=None
    d['missing_source_facts']=[{'code':'OWNER_ACCOUNT_MAPPING_UNAVAILABLE','field_path':'owner.account',
        'kind':'EXTERNAL_ROOT_FACT_REQUIRED'}]
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc())
    assert pack is None and not out['qualified_financial_pack']
    assert out['issues']==d['missing_source_facts']


def test_same_run_macro_and_raw_settings_are_passed_to_original_producer(tmp_path):
    r,d,desc=case(tmp_path);seen=[]
    def factory(**cfg):
        seen.append(cfg)
        def run(snapshot,payload):
            assert snapshot==r['client_snapshot']['payload']
            child=deepcopy(cfg['request_seed']);child.update(run_id=r['run_id'],evaluation_at=r['evaluation_at'])
            return {'request':child,'source_production':{'status':'SOURCE_STAGE_INCOMPLETE',
                'source_validation_issues':[{'code':'ORIGINAL_ORDER_BOOK_REQUIRED','field_path':'active_orders'}]}}
        return run
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory)
    assert pack is None and out['issues'][0]['code']=='ORIGINAL_ORDER_BOOK_REQUIRED'
    assert seen[0]['run_binding']['macro_snapshot']==r['macro_snapshot']
    assert seen[0]['flow']=='DEPLOYMENT' and seen[0]['focus_symbol']=='SYNTHETIC_ASSET'


def test_member_issuer_sources_reach_original_financial_producer_without_mutating_seed(tmp_path):
    r,d,desc=case(tmp_path);before=deepcopy(d);seen=[]
    sources={'SYNTHETIC_ASSET':{'local_path':str(tmp_path/'SYNTHETIC_ISSUER.json'),'sha256':'f'*64}}
    def factory(**cfg):
        seen.append(cfg)
        def run(*args):
            return {'request':deepcopy(cfg['request_seed']),'source_production':{
                'status':'SOURCE_STAGE_INCOMPLETE','source_validation_issues':[{'code':'SYNTHETIC_OTHER_SOURCE_REQUIRED'}]}}
        return run
    produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory,issuer_facts_sources=sources)
    assert seen[0]['issuer_facts_sources']==sources and d==before


@pytest.mark.parametrize('field',['member','db','version','asset','pasted','bootstrap','profile'])
def test_cross_member_changed_approval_and_pasted_outputs_are_rejected(tmp_path,field):
    r,d,desc=case(tmp_path)
    if field=='member':d['client_id']='OTHER'
    elif field=='db':d['source_db_sha256']='b'*64
    elif field=='version':d['target_version']=3
    elif field=='asset':d['asset_id']='OTHER'
    elif field=='pasted':d['native_bundle']={}
    elif field=='bootstrap':d['configuration']['request_seed']['owner']['account']=None
    else:d['configuration']['context_seed'].pop('family_c7_profile')
    with pytest.raises(PermissionError):produce(ROOT,r,'SYNTHETIC_ASSET',desc())


def test_original_error_code_and_field_are_retained(tmp_path):
    r,d,desc=case(tmp_path)
    def factory(**cfg):
        def run(*args):raise ValueError('SOURCE_APPROVED_TARGET_BASE_REQUIRED')
        return run
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory)
    assert pack is None and out['issues'][0]['code']=='SOURCE_APPROVED_TARGET_BASE_REQUIRED'


def test_qualified_nav_inventory_survives_an_unrelated_native_history_rejection(tmp_path,monkeypatch):
    import member_reconciliation_source,family_c7_source_assembly
    r,_,desc=case(tmp_path);before=deepcopy(r)
    normalized={'digest':'b'*64,'current_portfolio_reference':{'formal_NAV_source_qualified':True},
        'client_id':r['client_id'],'run_id':r['run_id'],'source_db_sha256':'a'*64,'target_version':2}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
    inventory={'status':'SYN_QUALIFIED_NAV_ORIGINAL_INVENTORY','scope_candidate':{'current_nav':'SYN_KNOWN_NAV'}}
    monkeypatch.setattr(family_c7_source_assembly,'assemble',lambda *a,**k:deepcopy(inventory))
    def factory(**cfg):
        def run(*args):raise ValueError('SYN_HISTORY_RELEASE_HORIZON_REQUIRED')
        return run
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory,
        reconciliation_source={'local_path':'SYNTHETIC','sha256':'a'*64})
    assert pack is None and not out['qualified_financial_pack'] and r==before
    assert out['status']=='ORIGINAL_SOURCE_PRODUCER_REJECTED'
    assert out['issues'][0]['code']=='SYN_HISTORY_RELEASE_HORIZON_REQUIRED'
    assert out['family_scope_assembly']==inventory


def test_old_bootstrap_money_cannot_replace_unresolved_current_approval(tmp_path):
    r,d,desc=case(tmp_path)
    r['confirmed_target']['payload']['draft']['target_lines'][0]['target_amount'].update(value_state='UNKNOWN',amount=None)
    def forbidden(**cfg):pytest.fail('Withdrawn historical money must not enter the native financial producer')
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=forbidden)
    assert pack is None and out['issues'][0]['code']=='CURRENT_APPROVED_INVESTMENT_POOL_MONEY_BASE_REQUIRED'
    assert out['issues'][0]['historical_bootstrap_money_substituted'] is False


def test_complete_original_inputs_are_saved_for_the_existing_native_assembler(tmp_path):
    r,d,desc=case(tmp_path)
    def factory(**cfg):
        def run(*args):return {'request':deepcopy(cfg['request_seed']),'trusted_context':{},
            'native_sources':{'synthetic':'original source inputs; not a native result'},'source_metadata':{}}
        return run
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory)
    saved=json.loads(Path(pack['local_path']).read_text())
    assert saved['pack']['native_sources'] and not out['qualified_financial_pack']
    assert saved['pack'].get('native_result') is None


def test_same_run_uses_current_pinned_original_base_instead_of_stale_bootstrap_copy(tmp_path,monkeypatch):
    import member_reconciliation_source
    r,d,desc=case(tmp_path)
    old={'local_path':'SYNTHETIC_OLD_ORIGINAL','sha256':'b'*64}
    current={'local_path':'SYNTHETIC_CURRENT_ORIGINAL','sha256':'c'*64}
    d['configuration']['official_target_base_source']=old
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *args:{
        'digest':'d'*64,'client_id':r['client_id'],'run_id':r['run_id'],'source_db_sha256':'a'*64,
        'target_version':2,'original_target_sources':{'official_target_base_source':current}})
    def factory(**cfg):
        assert cfg['official_target_base_source']==current
        assert cfg['family_c7_assembly_inputs']['member_reconciliation_source']['sha256']=='e'*64
        def run(*args):
            child=deepcopy(cfg['request_seed'])
            return {'request':child,'source_production':{'status':'SOURCE_STAGE_INCOMPLETE',
                'source_validation_issues':[{'code':'ORIGINAL_COMPLETE_FACTS_STILL_REQUIRED'}]}}
        return run
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory,
        reconciliation_source={'local_path':'SYNTHETIC_REPLAYED_SOURCE','sha256':'e'*64})
    assert pack is None and not out['qualified_financial_pack']
    assert out['same_run_source_binding']['source_digest']=='d'*64


def test_public_history_source_reaches_original_c7_options_without_becoming_a_financial_pack(tmp_path,monkeypatch):
    import historical_source_qualification
    r,d,desc=case(tmp_path);sources={'sec_filings':{'local_path':'SYNTHETIC_ORIGINAL','sha256':'b'*64}}
    monkeypatch.setattr(historical_source_qualification,'bind',lambda *args:{'digest':'c'*64})
    def factory(**cfg):
        b=cfg['family_c7_assembly_inputs']['public_history_source_binding']
        assert b['client_id']==r['client_id'] and b['run_id']==r['run_id'] and b['asset_id']=='SYNTHETIC_ASSET'
        assert b['source_descriptors']==sources and b['digest']=='c'*64
        return lambda *args:{'request':deepcopy(cfg['request_seed']),'source_production':{
            'status':'SOURCE_STAGE_INCOMPLETE','source_validation_issues':[{'code':'ORIGINAL_FINANCIAL_FACTS_STILL_REQUIRED'}]}}
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=factory,public_history_sources=sources)
    assert out['public_history_source_binding']['digest']=='c'*64 and pack is None and not out['qualified_financial_pack']


def document_case(tmp_path):
    from approved_target_input import build_approved_target_view
    r,d,desc=case(tmp_path);client='fam_'+'a'*32;r['client_id']=d['client_id']=client
    line='| SYNTHETIC_ASSET | 100% | NT$1,000 |'
    document=tmp_path/'SYNTHETIC_APPROVED.md'
    document.write_text('# SYNTHETIC_BROKER\n| 標的 | 權重 | 目標金額NT$ |\n'+line+'\n')
    args={'client_id':client,'source_path':str(document),'source_reference':'SYNTHETIC_APPROVED_SOURCE',
        'source_available_at':'2026-10-01T00:00:00Z','target_version':2,'allocation_version':'SYNTHETIC_V2',
        'rows':[{'source_line':line,'weight':'1'}],
        'mappings':[{'instrument_id':'SYNTHETIC_ASSET','ticker':'SYNTHETIC_ASSET','asset_type':'股票ETF'}]}
    r['confirmed_target']=build_approved_target_view(**args)['target'];r['macro_snapshot']=None
    r['trade_authorization']='NONE'
    tables={'portfolio_account':[{'client_id':client,'account_key':'SYNTHETIC_ACCOUNT'}],
        'account_ownership':[{'account_key':'SYNTHETIC_ACCOUNT','owner_client_id':client,
            'ownership_state':'VERIFIED','created_at_utc':'2026-10-01T00:00:00Z'}],
        'account_broker_link':[{'account_key':'SYNTHETIC_ACCOUNT','broker_key':'SYNTHETIC_BROKER',
            'link_state':'ACTIVE','created_at_utc':'2026-10-01T00:00:00Z'}],
        'funding_domain':[],'funding_account_domain_link':[]}
    snapshot=r['client_snapshot']['payload'];snapshot.update(client_id=client,tables=tables,payload_digest=digest(tables))
    source={'schema_version':'Family.W8.MemberDocumentAccountAnalysis.v1','client_id':client,
        'asset_id':'SYNTHETIC_ASSET','source_db_sha256':'a'*64,'target_version':2,
        'source_reference':'SYNTHETIC_RAW_ANALYSIS_INPUT','available_at':'2026-10-01T00:00:00Z',
        'document_target':{**args,'sha256':sha256(document.read_bytes()).hexdigest()},
        'account_category':{'account_key':'SYNTHETIC_ACCOUNT','broker':'SYNTHETIC_BROKER',
            'broker_source_label':'SYNTHETIC_BROKER','currency':'TWD','funding_domain':'ANALYSIS_CATEGORY'},
        'classification_source':{'source_reference':'SYNTHETIC_CLASSIFICATION_NOT_CONSUMED_WITHOUT_MACRO'}}
    d['configuration']=None
    def sources():
        p=tmp_path/'SYNTHETIC_ANALYSIS_SOURCE.json';p.write_text(json.dumps(source))
        d['document_account_analysis_source']={'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
        return desc()
    return r,d,source,sources


def test_document_account_route_reaches_real_w5_before_missing_macro_without_funding(tmp_path):
    r,d,s,sources=document_case(tmp_path);before=deepcopy(r)
    def forbidden(**cfg):pytest.fail('Missing macro must not enter native financial production')
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',sources(),producer_factory=forbidden)
    bound=out['account_analysis_binding']
    assert bound['cash_verified'] is False and bound['holdings_completeness_verified'] is False
    assert bound['owner']['broker']=='SYNTHETIC_BROKER'
    assert out['issues'][0]['code']=='MEMBER_PRODUCER_PRECAPTURED_MACRO_REQUIRED'
    assert 'W5.family_boundary.bind_owner:document_analysis_category' in out['call_trace']
    assert pack is None and out['qualified_financial_pack'] is False and r==before


@pytest.mark.parametrize('change,code',[
    ('member','SCOPE_MISMATCH'),('db','SCOPE_MISMATCH'),('asset','SCOPE_MISMATCH'),
    ('version','SCOPE_MISMATCH'),('future','AFTER_CUTOFF'),
    ('account','ACCOUNT_CATEGORY_MISSING_OR_AMBIGUOUS'),
    ('ownership','ORIGINAL_ACCOUNT_CLASSIFICATION_REQUIRED'),('target','TARGET_REPLAY_MISMATCH')])
def test_document_analysis_source_cannot_change_owner_db_asset_approval_or_time(tmp_path,change,code):
    r,d,s,sources=document_case(tmp_path)
    if change=='member':s['client_id']='fam_'+'b'*32
    elif change=='db':s['source_db_sha256']='b'*64
    elif change=='asset':s['asset_id']='OTHER'
    elif change=='version':s['target_version']=3
    elif change=='future':s['available_at']='2099-01-01T00:00:00Z'
    elif change=='account':s['account_category']['account_key']='OTHER'
    elif change=='ownership':
        snap=r['client_snapshot']['payload'];snap['tables']['account_ownership'][0]['ownership_state']='UNKNOWN'
        snap['payload_digest']=digest(snap['tables'])
    else:r['confirmed_target']['target_hash']='changed'
    with pytest.raises((ValueError,PermissionError),match=code):
        produce(ROOT,r,'SYNTHETIC_ASSET',sources())


def test_document_analysis_source_and_document_bytes_are_pinned(tmp_path):
    r,d,s,sources=document_case(tmp_path);desc=sources()
    p=Path(d['document_account_analysis_source']['local_path']);p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(PermissionError,match='SOURCE_BYTES_CHANGED'):
        produce(ROOT,r,'SYNTHETIC_ASSET',desc)
    desc=sources();Path(s['document_target']['source_path']).write_text('changed')
    with pytest.raises(PermissionError,match='DOCUMENT_BYTES_CHANGED'):
        produce(ROOT,r,'SYNTHETIC_ASSET',desc)


def test_document_analysis_seed_reaches_original_dispatch_with_analysis_scope_only(tmp_path):
    r,d,s,sources=document_case(tmp_path);r['macro_snapshot']={'synthetic':'factory-only input'}
    seen=[]
    def factory(**cfg):
        seen.append(cfg)
        assert cfg['request_seed']['owner']['account']=='SYNTHETIC_ACCOUNT'
        assert cfg['context_seed']['approved_document_account_scope']['cash_verified'] is False
        assert cfg['cash_policy']=={}  # No hypothetical zero-cash authorization.
        return lambda *args:{'request':deepcopy(cfg['request_seed']),'source_production':{
            'status':'SOURCE_STAGE_INCOMPLETE','source_validation_issues':[{'code':'SYNTHETIC_REAL_FUNDING_STILL_REQUIRED'}]}}
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',sources(),producer_factory=factory)
    assert len(seen)==1 and pack is None and not out['qualified_financial_pack']
    assert out['issues'][0]['code']=='SYNTHETIC_REAL_FUNDING_STILL_REQUIRED'


@pytest.mark.parametrize('change',['trade','snapshot_digest'])
def test_document_analysis_cannot_relabel_trade_or_snapshot_integrity(tmp_path,change):
    r,d,s,sources=document_case(tmp_path)
    if change=='trade':r['trade_authorization']='OTHER'
    else:r['client_snapshot']['payload']['payload_digest']='changed'
    with pytest.raises(PermissionError,match='SCOPE_MISMATCH'):
        produce(ROOT,r,'SYNTHETIC_ASSET',sources())


def test_missing_macro_preserves_independent_source_work_without_deployment(tmp_path,monkeypatch):
    import family_c7_source_assembly
    r,d,desc=case(tmp_path);r.pop('macro_snapshot')
    d['configuration']['context_seed']['source_only_marker']='SYNTHETIC_SOURCE_CONTEXT'
    expected={'status':'PARTIAL_ORIGINAL_SOURCES','issues':[{'code':'SYNTHETIC_FUNDING_FACT_REQUIRED'}],
              'unknown_values_defaulted_to_zero':False}
    seen=[]
    def assemble(root,request,context,*,artifact_directory):
        assert root==ROOT and request==r
        assert context['source_only_marker']=='SYNTHETIC_SOURCE_CONTEXT'
        seen.append(str(artifact_directory));return deepcopy(expected)
    monkeypatch.setattr(family_c7_source_assembly,'assemble',assemble)
    def forbidden(**kwargs):pytest.fail('Macro-dependent deployment must remain unavailable')
    out,pack=produce(ROOT,r,'SYNTHETIC_ASSET',desc(),producer_factory=forbidden)
    assert len(seen)==1 and out['family_scope_assembly']==expected
    assert pack is None and out['qualified_financial_pack'] is False
    assert out['issues'][0]['code']=='MEMBER_PRODUCER_PRECAPTURED_MACRO_REQUIRED'
    assert out['call_trace'][-1]=='W8.family_c7_source_assembly:macro_independent'
    assert 'macro_snapshot' not in r


def test_missing_macro_still_rejects_invalid_independent_sources(tmp_path,monkeypatch):
    import family_c7_source_assembly
    r,d,desc=case(tmp_path);r.pop('macro_snapshot')
    def reject(*args,**kwargs):raise PermissionError('SYNTHETIC_SOURCE_BYTES_CHANGED')
    monkeypatch.setattr(family_c7_source_assembly,'assemble',reject)
    with pytest.raises(PermissionError,match='SYNTHETIC_SOURCE_BYTES_CHANGED'):
        produce(ROOT,r,'SYNTHETIC_ASSET',desc())

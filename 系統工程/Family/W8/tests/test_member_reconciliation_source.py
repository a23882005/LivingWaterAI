"""One member/run source envelope must replay originals before C7 consumes it."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import member_reconciliation_source as source
from family_input import digest


def case(tmp_path,monkeypatch):
    req={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN','evaluation_at':'2026-11-03T04:00:00Z',
        'owner':{'client_id':'SYNTHETIC_CLIENT','account':None},'trade_authorization':'NONE',
        'client_snapshot':{'payload':{'client_id':'SYNTHETIC_CLIENT','source_sha256':'a'*64,
            'payload_digest':digest({}),'tables':{}}},
        'confirmed_target':{'target_version':3,'payload':{'draft':{'target_lines':[
            {'instrument_id':'SYNTHETIC_ASSET','ticker':'TEST','weight':{'value_state':'KNOWN','value':'1'}}],
            'denominator':{'value_state':'UNKNOWN','amount':None,'currency':'USD'}}}}}
    raw=tmp_path/'original.json';raw.write_text('{"cash":"100"}')
    cfg={'client_id':req['client_id'],'source_db_sha256':'a'*64,'market_sources':{
        'TEST':{'local_path':str(raw),'sha256':sha256(raw.read_bytes()).hexdigest(),
            'retrieved_at':'2026-11-03T03:59:00Z'}}}
    def original(root,request,config):
        return dict(schema_version=source.SCHEMA,**source.binding(request),
            source_files=source.source_files(config,request['evaluation_at']),
            observations=json.loads(raw.read_bytes()),qualified_available_cash=None,
            reconciliation_attested=False,financial_cycle_initialized=False,trade_action='NO_TRADE')
    monkeypatch.setattr(source,'normalize',original)
    return req,cfg,raw


def test_immutable_source_envelope_replays_originals_without_qualifying_cash(tmp_path,monkeypatch):
    req,cfg,raw=case(tmp_path,monkeypatch)
    result,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private')
    assert source.read(ROOT,descriptor,req)==result
    assert source.persist(ROOT,req,cfg,tmp_path/'private')==(result,descriptor)
    assert result['observations']['cash']=='100' and result['qualified_available_cash'] is None
    assert result['reconciliation_attested'] is False and result['financial_cycle_initialized'] is False


@pytest.mark.parametrize('changed',['client','run','cutoff','db','snapshot','target_version','weight','money_base','macro'])
def test_changed_member_run_sources_or_approval_cannot_reuse_an_envelope(tmp_path,monkeypatch,changed):
    req,cfg,_=case(tmp_path,monkeypatch);_,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private')
    if changed=='client':req['client_id']='OTHER'
    elif changed=='run':req['run_id']='NEXT_RUN'
    elif changed=='cutoff':req['evaluation_at']='2026-11-04T04:00:00Z'
    elif changed=='db':req['client_snapshot']['payload']['source_sha256']='b'*64
    elif changed=='snapshot':req['client_snapshot']['payload']['tables']['injected']=[]
    elif changed=='target_version':req['confirmed_target']['target_version']=4
    elif changed=='weight':req['confirmed_target']['payload']['draft']['target_lines'][0]['weight']['value']='0.5'
    elif changed=='money_base':req['confirmed_target']['payload']['draft']['denominator']['amount']='100'
    else:req['macro_snapshot']={'different':'original feed'}
    with pytest.raises(PermissionError):source.read(ROOT,descriptor,req)


def test_native_target_enrichment_and_selected_account_do_not_change_original_allocation(tmp_path,monkeypatch):
    req,cfg,_=case(tmp_path,monkeypatch);_,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private')
    req['owner']['account']='SELECTED_ACCOUNT';req['confirmed_target']['extra_native_label']='ENRICHED'
    assert source.read(ROOT,descriptor,req)['run_id']==req['run_id']


@pytest.mark.parametrize('changed',['envelope','normalized','source_bytes','source_time'])
def test_hash_changes_or_pasted_normalized_results_cannot_replace_original_replay(tmp_path,monkeypatch,changed):
    req,cfg,raw=case(tmp_path,monkeypatch);_,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private')
    file=Path(descriptor['local_path']);data=json.loads(file.read_bytes())
    if changed=='source_bytes':raw.write_text('{"cash":"200"}')
    elif changed=='source_time':data['configuration']['market_sources']['TEST']['retrieved_at']='2026-11-04T00:00:00Z'
    else:data['normalized']['qualified_available_cash']='100'
    if changed!='source_bytes':
        file.write_text(json.dumps(data))
        if changed!='envelope':descriptor['sha256']=sha256(file.read_bytes()).hexdigest()
    with pytest.raises(PermissionError):source.read(ROOT,descriptor,req)


def test_nested_original_manifests_are_pinned_and_changed_sources_do_not_overwrite_saved_runs(tmp_path,monkeypatch):
    req,cfg,raw=case(tmp_path,monkeypatch)
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(cfg['market_sources']))
    outer={'market_sources':{'manifest':{'local_path':str(manifest),'sha256':sha256(manifest.read_bytes()).hexdigest()}}}
    assert len(source.source_files(outer,req['evaluation_at']))==2
    _,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private');before=Path(descriptor['local_path']).read_bytes()
    raw.write_text('{"cash":"200"}');cfg['market_sources']['TEST']['sha256']=sha256(raw.read_bytes()).hexdigest()
    with pytest.raises(PermissionError,match='SAVED_RUN_CHANGED'):source.persist(ROOT,req,cfg,tmp_path/'private')
    assert Path(descriptor['local_path']).read_bytes()==before


def test_same_run_cannot_be_rebound_to_a_changed_approved_target(tmp_path,monkeypatch):
    req,cfg,_=case(tmp_path,monkeypatch);_,descriptor=source.persist(ROOT,req,cfg,tmp_path/'private')
    before=Path(descriptor['local_path']).read_bytes()
    req['confirmed_target']['target_version']=4
    with pytest.raises(PermissionError,match='SAVED_RUN_CHANGED'):source.persist(ROOT,req,cfg,tmp_path/'private')
    assert Path(descriptor['local_path']).read_bytes()==before


@pytest.mark.parametrize('changed',['position_values','securities','coverage_digest'])
def test_financial_consumer_rejects_an_alternative_value_or_asset_coverage_projection(tmp_path,monkeypatch,changed):
    from member_financial_chain import complete_report
    req,_,_=case(tmp_path,monkeypatch)
    report={'positions':[{'symbol':'TEST'}],'report_digest':'a'*64,
        'source_position_valuations':{'original':'value'},
        'all_asset_coverage':{'expected':['TEST'],'coverage_digest':'b'*64}}
    normalized={'position_values':deepcopy(report['source_position_valuations']),
        'securities':['TEST'],'coverage_digest':'b'*64}
    normalized[changed]=None
    monkeypatch.setattr(source,'persist',lambda *args:(normalized,{}))
    with pytest.raises(PermissionError,match='ANALYSIS_SOURCE_VALUES_OR_COVERAGE_MISMATCH'):
        complete_report(report,req,{'financial_sources':{'TEST':{}},
            'financial_reconciliation_artifact_directory':str(tmp_path/'private')},ROOT)


def test_c7_root_inventory_consumes_known_original_quantity_without_inventing_nav_or_funding(tmp_path,monkeypatch):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import assemble
    _,_,req,ctx,tactical,identities,_,_=original_case(tmp_path)
    normalized={'digest':'b'*64,'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
        'position_values':{'positions':[{'symbol':'QQQ','account_key':'ORIGINAL_ACCOUNT','quantity':'60',
            'quantity_source':{'instrument_key':'ORIGINAL_KEY','observed_at':'2026-09-20T00:00:00Z',
                'received_at':'2026-09-21T00:00:00Z'}}]}}
    monkeypatch.setattr(source,'read',lambda *args:deepcopy(normalized))
    ctx['member_reconciliation_source']={'local_path':str(tmp_path/'source.json'),'sha256':'c'*64}
    result=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities)
    assert result['scope_candidate']['current_nav'] is None and result['scope_candidate']['funding_buckets'] is None
    assert result.get('source_descriptor') is None
    assert not result['original_observations']['same_run_financial_sources']['used_as_complete_reconciliation_facts']
    quantity=next(r for r in result['field_inventory'] if r['field_path'].endswith('ORIGINAL_ACCOUNT.ORIGINAL_KEY.quantity'))
    assert quantity['classification']=='EXISTING_BOUND_SOURCE' and quantity['source_locators'][0]['as_of']=='2026-09-20T00:00:00Z'


@pytest.mark.parametrize('qualified_originals',[False,True])
def test_reported_money_and_unbound_broker_observations_preserve_original_c7_contract(tmp_path,monkeypatch,qualified_originals):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import assemble
    _,_,req,ctx,tactical,identities,facts,desc=original_case(tmp_path)
    normalized={'digest':'b'*64,'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
        'position_values':{'positions':[]},'financial_facts':{'digest':'c'*64,'reported_money':{'facts':[
            {'fact_kind':'OWNER_INVESTMENT_INTENT','fact_digest':'d'*64,'amount':'50',
             'as_of':req['evaluation_at'],'available_at':req['evaluation_at'],'settlement_qualified':False}]},
            'broker_observations':{'source_descriptor':{'local_path':str(tmp_path/'candidate.json'),'sha256':'e'*64},
                'orders':[{'order_status':'REPLACED'}]}}}
    monkeypatch.setattr(source,'read',lambda *args:deepcopy(normalized))
    ctx['member_reconciliation_source']={'local_path':str(tmp_path/'same_run.json'),'sha256':'f'*64}
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities,
        portfolio_facts_source=desc() if qualified_originals else None)
    money=next(r for r in out['field_inventory'] if 'financial_observations.OWNER_INVESTMENT_INTENT' in r['field_path'])
    assert money['source_locators'][0]['original_money_fact']['amount']=='50'
    pending=next(r for r in out['field_inventory'] if r['field_path'].endswith('original_order_snapshot'))
    assert pending['value_state']=='UNKNOWN'
    assert ('source_descriptor' in out)==qualified_originals
    if not qualified_originals:
        assert out['scope_candidate']['current_nav'] is None and out['scope_candidate']['funding_buckets'] is None

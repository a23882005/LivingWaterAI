"""Pinned transport of synthetic source-owner inputs to unchanged PV2 rules."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from test_v10_own_history import valuation_case,complete_price
from native_history_source import read
from test_v82_approved_context import case as approved_case
from v82_approved_context import read_source,build
from livingwater_v82_runtime.own_history import valuation_percentile,price_percentile


def case(tmp_path,kind='valuation_history'):
    def save(name,data):
        path=tmp_path/name;path.write_text(json.dumps(data))
        return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())
    args=valuation_case() if kind=='valuation_history' else complete_price(1700)
    if kind=='price_history':args['comparable_from']='2012-01-01T00:00:00Z'
    # A synthetic original is a provenance fixture, never real price/PIT evidence.
    original=save('SYNTHETIC_ORIGINAL.json',{'purpose':'SYNTHETIC_SOURCE_OWNER_PROVENANCE_FIXTURE'})
    original.update(source_reference='SYNTHETIC_ORIGINAL',retrieved_at=args['decision_at'])
    def pin(value):
        if isinstance(value,dict):
            if 'source_hash' in value:value['source_hash']=original['sha256']
            for child in value.values():pin(child)
        elif isinstance(value,list):
            for child in value:pin(child)
    pin(args)
    request=dict(client_id='SYNTHETIC_CLIENT',run_id='SYNTHETIC_RUN',evaluation_at=args['decision_at'],
        owner={'client_id':'SYNTHETIC_CLIENT','account':'SYNTHETIC_ACCOUNT','currency':'USD'},
        client_snapshot={'payload':{'source_sha256':'a'*64}})
    manifest=dict(schema_version='Family.W8.NativeHistorySource.v1',
        **{k:request[k] for k in ('client_id','run_id','evaluation_at','owner')},
        source_db_sha256='a'*64,asset_id='SYNTHETIC',available_at=args['decision_at'],
        source_reference='SYNTHETIC_SOURCE_OWNER_APPROVED_INPUTS',original_sources=[original],
        histories={kind:save('SYNTHETIC_ARGUMENTS.json',args)})
    return manifest,request,args,lambda:save('SYNTHETIC_MANIFEST.json',manifest)


def change(source,fn):
    path=Path(source['local_path']);data=json.loads(path.read_text());fn(data)
    path.write_text(json.dumps(data));source['sha256']=sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('kind',['price_history','valuation_history'])
def test_exact_native_arguments_replay_same_formal_values_without_mutation(tmp_path,kind):
    m,request,args,desc=case(tmp_path,kind);before=deepcopy(args)
    actual,receipt=read(desc(),request,'SYNTHETIC')
    fn=price_percentile if kind=='price_history' else valuation_percentile
    expected=fn(**args);replayed=fn(**actual[kind])
    assert replayed==expected and expected['status']=='COMPLETE'
    assert args==before and actual[kind]==args
    assert not receipt['financial_gate_released']
    assert receipt['native_qualification_replay_required']
    assert not receipt['original_publication_semantics_independently_verified']
    assert read(desc(),request,'SYNTHETIC')==(actual,receipt)


@pytest.mark.parametrize('field',['client_id','run_id','evaluation_at','owner','asset_id','source_db_sha256','schema_version'])
def test_other_member_run_account_db_asset_or_schema_rejected(tmp_path,field):
    m,request,_,desc=case(tmp_path);m[field]='OTHER'
    with pytest.raises(PermissionError,match='MEMBER_RUN_DB_OWNER'):read(desc(),request,'SYNTHETIC')


@pytest.mark.parametrize('which',['manifest','arguments','original'])
def test_original_and_argument_bytes_are_rechecked_every_read(tmp_path,which):
    m,request,_,desc=case(tmp_path);source=desc()
    target=(source if which=='manifest' else m['histories']['valuation_history'] if which=='arguments' else m['original_sources'][0])
    Path(target['local_path']).write_text('CHANGED')
    with pytest.raises(PermissionError):read(source,request,'SYNTHETIC')


@pytest.mark.parametrize('change_args',[
    lambda a:a['history'][0].update(source_hash='UNPINNED'),
    lambda a:a['identity'].update(asset_id='OTHER'),
    lambda a:a.update(decision_at='2025-01-18T00:00:00Z'),
    lambda a:a['history'][0].update(retrieved_at='2025-01-18T00:00:00Z')])
def test_hash_reference_asset_cutoff_and_actual_acquisition_are_bound(tmp_path,change_args):
    m,request,_,desc=case(tmp_path);change(m['histories']['valuation_history'],change_args)
    with pytest.raises(PermissionError):read(desc(),request,'SYNTHETIC')


@pytest.mark.parametrize('change_manifest',[
    lambda m:m.update(original_sources=[]),lambda m:m.update(histories={}),
    lambda m:m['histories'].update(qP={'value':'100'}),
    lambda m:m.update(available_at='2025-01-18T00:00:00Z'),
    lambda m:m['original_sources'][0].update(retrieved_at='2025-01-18T00:00:00Z')])
def test_missing_originals_direct_percentile_and_future_sources_rejected(tmp_path,change_manifest):
    m,request,_,desc=case(tmp_path);change_manifest(m)
    with pytest.raises(PermissionError):read(desc(),request,'SYNTHETIC')


def test_matching_original_hashes_do_not_repair_unqualified_native_pit(tmp_path):
    m,request,_,desc=case(tmp_path)
    def invalidate(args):
        for row in args['history']:row['pit_status']='UNVERIFIABLE'
    change(m['histories']['valuation_history'],invalidate)
    actual,_=read(desc(),request,'SYNTHETIC')
    out=valuation_percentile(**actual['valuation_history'])
    assert out['status']=='UNKNOWN' and out['value'] is None
    assert all(r['pit_status']=='UNVERIFIABLE' for r in actual['valuation_history']['history'])


@pytest.mark.parametrize('field',['calendar','events'])
def test_pinned_price_transport_preserves_native_calendar_and_action_rejections(tmp_path,field):
    m,request,_,desc=case(tmp_path,'price_history')
    def invalidate(args):
        if field=='calendar':args['calendar']['approved']=False
        else:args['actions']['coverage_verified']=False
    change(m['histories']['price_history'],invalidate)
    arguments,_=read(desc(),request,'SYNTHETIC')
    result=price_percentile(**arguments['price_history'])
    assert result['status']=='UNKNOWN' and result['value'] is None
    assert result['reason_codes']==['CALENDAR_UNRESOLVED' if field=='calendar' else 'EVENT_COVERAGE_UNKNOWN']


def test_source_bundle_is_optional_existing_inline_route_remains_unchanged(tmp_path):
    request,_,source,*_=approved_case(tmp_path)
    original=read_source(source,request,'QQQ')
    assert 'native_history_source_readback' not in original


def test_pinned_route_cannot_override_inline_history_or_paste_derived_receipt(tmp_path):
    request,_,source,*_=approved_case(tmp_path,price_history={'SYNTHETIC':'INLINE'},native_history_source={})
    with pytest.raises(PermissionError,match='ROUTES_CONFLICT'):read_source(source,request,'QQQ')
    request,_,source,*_=approved_case(tmp_path,native_history_source_readback={'digest':'PASTED'})
    with pytest.raises(PermissionError,match='NOT_AN_INPUT'):read_source(source,request,'QQQ')


def test_approved_reader_loads_exact_pinned_arguments_without_approving_source_semantics(tmp_path):
    m,request,args,desc=case(tmp_path)
    data=dict(schema_version='Family.W8.V82ApprovedSource.v1',client_id=request['client_id'],
        owner=request['owner'],asset_id='SYNTHETIC',source_db_sha256='a'*64,
        source_reference='SYNTHETIC',available_at=request['evaluation_at'],native_history_source=desc())
    path=tmp_path/'APPROVED.json';path.write_text(json.dumps(data));source={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    actual=read_source(source,request,'SYNTHETIC')
    assert actual['valuation_history']==args
    assert actual['native_history_source_readback']['native_qualification_replay_required']
    assert 'price_history' not in actual


def test_pinned_history_reaches_existing_pv2_without_changing_primary_or_other_decisions(tmp_path):
    request,row,source,*_=approved_case(tmp_path)
    m,_,args,_=case(tmp_path)
    for record in [args['identity'],args['current'],*args['history']]:
        record.update(asset_id='QQQ',share_class='SYNTHETIC')
    args['decision_at']=request['evaluation_at'];args['current']['value']='10'
    change(m['histories']['valuation_history'],lambda data:(data.clear(),data.update(args)))
    m.update(**{k:request[k] for k in ('client_id','run_id','evaluation_at','owner')},asset_id='QQQ',
        source_db_sha256=request['client_snapshot']['payload']['source_sha256'],available_at=request['evaluation_at'])
    path=tmp_path/'SYNTHETIC_BOUND_MANIFEST.json';path.write_text(json.dumps(m))
    bundle={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    change(source,lambda d:d.update(valuation_history=args))
    _,inline=build(ROOT,row,request,fundamental=True,price_conditions={'value':True},left_safety=True,source_descriptor=source)
    change(source,lambda d:(d.pop('valuation_history'),d.update(native_history_source=bundle)))
    context,pinned=build(ROOT,row,request,fundamental=True,price_conditions={'value':True},left_safety=True,source_descriptor=source)
    assert pinned==inline and pinned['qV']['status']=='COMPLETE'
    assert pinned['qV']['metric_name']=='FORWARD_PE' and pinned['qP']['status']=='UNKNOWN'
    assert context['source_binding']['native_history_source_readback']['financial_gate_released'] is False
    change(m['histories']['valuation_history'],lambda a:a['identity'].update(metric_name='EV_SALES'))
    path.write_text(json.dumps(m));bundle['sha256']=sha256(path.read_bytes()).hexdigest()
    change(source,lambda d:d.update(native_history_source=bundle))
    _,conflict=build(ROOT,row,request,fundamental=True,price_conditions={'value':True},left_safety=True,source_descriptor=source)
    assert conflict['qV']['reason_codes']==['PV2_CURRENT_PRIMARY_SOURCE_CONFLICT']

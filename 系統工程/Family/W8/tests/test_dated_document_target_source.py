"""Dated target-source contracts using synthetic identities and asset values."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import sys

import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import TABLES,read_snapshot,digest
from family_boundary import validate_target
from member_v82_analysis import target_source
from approved_target_input import build_approved_target_view,enrich_document_target_view
from dated_document_target_source import ALIASES,approval_signature,replay,bind_producer_seed
from member_financial_producer import produce as produce_financial


def case(tmp_path):
    client='fam_'+'a'*32;old_at='2026-02-01T00:00:00Z';at='2026-03-10T00:00:00Z'
    dbpath=tmp_path/'SYNTHETIC_MEMBER.db'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE family_member_identity (client_id TEXT)')
        db.execute('INSERT INTO family_member_identity VALUES (?)',(client,))
        for table in TABLES:db.execute('CREATE TABLE '+table+' (client_id TEXT)')
    snapshot=read_snapshot(dbpath,expected_client_id=client)
    ids=['SYN_A','SYN_B','SYN_C','SYN_D','SYN_E','SYN_F','SGOV_BOND','SYN_G','SYN_H','SYN_I','SGOV_DRY','TWD_CASH']
    percentages=['20','10','10','10','10','10','5','5','5','5','5','5']
    rows=[{'source_line':'| '+iid+' | '+pct+'% | '+str(Decimal(pct)*9)+' |','weight':str(Decimal(pct)/100)}
        for iid,pct in zip(ids,percentages)]
    path=tmp_path/'SYNTHETIC_APPROVED_DOCUMENT.md'
    path.write_text('| 標的 | 目標比例 | 目標台幣 |\n|---|---|---|\n'+'\n'.join(r['source_line'] for r in rows)+'\n')
    doc={'client_id':client,'source_path':str(path),'source_reference':'SYNTHETIC_APPROVED_DOCUMENT',
        'source_available_at':'2026-01-01T00:00:00Z','target_version':1,'allocation_version':'SYNTHETIC_APPROVED_V1',
        'sha256':sha256(path.read_bytes()).hexdigest(),'rows':rows,
        'mappings':[{'instrument_id':iid,'ticker':'SGOV' if iid.startswith('SGOV_') else iid,
            'asset_type':'CASH' if iid=='TWD_CASH' else '股票ETF'} for iid in ids]}
    config={'client_id':client,'source_db_sha256':snapshot['source_sha256'],'document_target':deepcopy(doc)}
    prior_target=target_source(snapshot,config,old_at)
    owner={'client_id':client,'account':'SYNTHETIC_ACCOUNT','broker':'SYNTHETIC_BROKER','currency':'TWD','funding_domain':'SYNTHETIC_DOMAIN'}
    prior={'client_id':client,'run_id':'SYNTHETIC_ORIGINAL','evaluation_at':old_at,'owner':owner,
        'client_snapshot':{'payload':snapshot},'confirmed_target':prior_target,'trade_authorization':'NONE','macro_snapshot':None}
    reverse={v:k for k,v in ALIASES.items()}
    pool={'schema':'Family.PM.H32.ReportedAssetPoolCalculation.v1','scope':'SYNTHETIC_REPORTED_ASSETS_ONLY',
        'taiwan_securities':{'amount_twd':'1000','source_time':at},'ib_nav_usd':'100',
        'ib_cash_usd_already_in_nav':'10','ib_nav_includes_cash':True,'USD_TWD_rate':'2','rate_time':at,
        'pool_twd_exact':'1200','new_trade_authorization':'NONE','formal_db_writes':0,'formal_ledger_writes':0,
        'target_rows':[{'role':reverse.get(iid,iid),'weight_percent':pct,
            'target_twd_exact':str(Decimal(1200)*Decimal(pct)/100)} for iid,pct in zip(ids,percentages)]}
    intake={'schema':'Family.PM.H32Menu04InputProjection.v1','original_source':deepcopy(pool),
        'denominator':{'value_state':'KNOWN','amount':'1200','currency':'TWD','scope':pool['scope']},
        'preserved_original_request':prior,'dated_source_review_request':{**deepcopy(prior),
            'run_id':'SYNTHETIC_DATED_REVIEW','evaluation_at':at},
        'request_binding':{'client_id':client,'official_db_sha256':snapshot['source_sha256'],
            'original_target_version':1,'original_approved_document':{'sha256':doc['sha256']},
            'role_aliases':deepcopy(ALIASES),'bindings':[]},'target_lines_by_source_role':[]}
    for line,row in zip(prior_target['payload']['draft']['target_lines'],pool['target_rows']):
        money={'value_state':'KNOWN','amount':row['target_twd_exact'],'currency':'TWD'}
        intake['request_binding']['bindings'].append({k:line[k] for k in ('instrument_id','ticker','asset_type')}|
            {'source_role':row['role'],'new_target_amount':deepcopy(money)})
        intake['target_lines_by_source_role'].append({'source_role':row['role'],
            'weight':{'value_state':'KNOWN','value':str(Decimal(row['weight_percent'])/100)},'target_amount':money})
    def save(path,data):
        path.write_text(json.dumps(data));return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_PINNED_ORIGINAL'}
    manifest={'schema_version':'Family.W8.DatedDocumentPoolSource.v1','client_id':client,
        'source_db_sha256':snapshot['source_sha256'],'document_sha256':doc['sha256'],
        'target_version':1,'allocation_version':doc['allocation_version'],'source_available_at':at,
        'member_db_source':{'local_path':str(dbpath),'sha256':snapshot['source_sha256'],'source_reference':'SYNTHETIC_MEMBER_DB'}}
    def bind():
        manifest['pool_source']={**save(tmp_path/'SYNTHETIC_POOL.json',pool),'available_at':at}
        intake['source_sha256']=manifest['pool_source']['sha256'];intake['original_source']=deepcopy(pool)
        manifest['intake_source']=save(tmp_path/'SYNTHETIC_INTAKE.json',intake)
        config['document_target']['dated_pool_source']=save(tmp_path/'SYNTHETIC_DATED_BINDING.json',manifest)
        return config
    def pack():
        args=deepcopy(config['document_target']);args.pop('sha256')
        return build_approved_target_view(**args,evaluation_at=at)
    bind()
    return snapshot,prior,config,pool,intake,manifest,bind,pack,at


def test_all_twelve_amounts_rebuild_and_approval_history_remains_unchanged(tmp_path):
    snapshot,prior,cfg,_,_,_,_,pack,at=case(tmp_path)
    before=deepcopy((snapshot,prior));actual=target_source(snapshot,cfg,at);p=pack()
    assert actual==p['target'] and len(actual['payload']['draft']['target_lines'])==12
    assert approval_signature(actual)==approval_signature(prior['confirmed_target'])
    assert sum(Decimal(r['target_amount']['amount']) for r in actual['payload']['draft']['target_lines'])==Decimal('1200')
    assert actual['payload']['draft']['target_lines'][0]['target_amount']['amount']=='240'
    assert all(r['original_document_target_amount']['value_state']=='KNOWN' for r in actual['payload']['draft']['target_lines'])
    assert actual['payload']['draft']['denominator']['settlement_qualified'] is False
    assert (snapshot,prior)==before


def test_two_role_aliases_remain_separate_and_nav_cash_is_not_added_again(tmp_path):
    snapshot,_,cfg,_,_,_,_,_,at=case(tmp_path)
    target=target_source(snapshot,cfg,at);rows={r['instrument_id']:r for r in target['payload']['draft']['target_lines']}
    assert rows['SGOV_BOND']['ticker']==rows['SGOV_DRY']['ticker']=='SGOV'
    assert rows['SGOV_DRY']['target_amount']['source_role']=='SGOV_DRY_POWDER'
    assert rows['TWD_CASH']['target_amount']['source_role']=='TWD_CASH_TARGET'
    assert target['payload']['draft']['denominator']['amount']=='1200'


def test_absent_optional_source_keeps_original_unknown_and_rejects_old_cutoff(tmp_path):
    snapshot,prior,cfg,_,_,_,_,_,at=case(tmp_path)
    with pytest.raises(PermissionError,match='SOURCE_AFTER_CUTOFF'):target_source(snapshot,cfg,prior['evaluation_at'])
    del cfg['document_target']['dated_pool_source']
    assert target_source(snapshot,cfg,at)==prior['confirmed_target']
    assert all(r['target_amount']['amount'] is None for r in prior['confirmed_target']['payload']['draft']['target_lines'])


@pytest.mark.parametrize('key,value,code',[
    ('client_id','fam_'+'b'*32,'MEMBER_DOCUMENT_OR_VERSION'),
    ('source_db_sha256','b'*64,'INTAKE_MEMBER_DB_DOCUMENT'),
    ('document_sha256','b'*64,'MEMBER_DOCUMENT_OR_VERSION'),
    ('target_version',2,'MEMBER_DOCUMENT_OR_VERSION'),
])
def test_wrong_member_db_document_or_version_is_rejected(tmp_path,key,value,code):
    snapshot,_,cfg,_,_,manifest,bind,_,at=case(tmp_path)
    manifest[key]=value;bind()
    with pytest.raises(PermissionError,match=code):target_source(snapshot,cfg,at)


def test_raw_hash_change_is_rejected_before_using_any_amount(tmp_path):
    snapshot,_,cfg,_,_,manifest,_,_,at=case(tmp_path)
    Path(manifest['pool_source']['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='SOURCE_BYTES_CHANGED'):target_source(snapshot,cfg,at)


def test_duplicate_source_role_or_wrong_alias_is_not_first_match(tmp_path):
    snapshot,_,cfg,pool,intake,_,bind,_,at=case(tmp_path)
    original=deepcopy(pool['target_rows']);pool['target_rows'][1]=deepcopy(pool['target_rows'][0]);bind()
    with pytest.raises(PermissionError,match='DUPLICATE_ROLE'):target_source(snapshot,cfg,at)
    pool['target_rows']=original;intake['request_binding']['role_aliases']['SGOV_DRY_POWDER']='SGOV_BOND';bind()
    with pytest.raises(PermissionError,match='ROLE_ALIASES'):target_source(snapshot,cfg,at)


@pytest.mark.parametrize('field',['pool_twd_exact','target_twd_exact'])
def test_original_components_are_recalculated_not_pasted_from_pm_view(tmp_path,field):
    snapshot,_,cfg,pool,_,_,bind,_,at=case(tmp_path)
    if field=='pool_twd_exact':pool[field]='1220'  # A second addition of cash already in NAV.
    else:pool['target_rows'][0][field]='241'
    bind()
    with pytest.raises(PermissionError,match='RECALCULATION_MISMATCH'):target_source(snapshot,cfg,at)


def test_enrichment_and_boundary_replay_original_sources_and_refuse_rehashed_tamper(tmp_path):
    snapshot,prior,cfg,_,_,_,_,pack,at=case(tmp_path)
    p=pack();target=p['target'];proof=p['trusted_approved_target_source']
    assert enrich_document_target_view(target,proof)==(target,proof)
    assert validate_target(target,prior['client_id'],datetime.fromisoformat(at.replace('Z','+00:00')),
        approved_document_source=proof,snapshot=snapshot)==target
    target=deepcopy(target);proof=deepcopy(proof);draft=target['payload']['draft']
    draft['target_lines'][0]['target_amount']['amount']='241'
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    target['target_hash']=target['payload']['target_hash']=draft['draft_hash'];proof['target_view_digest']=digest(target)
    with pytest.raises(PermissionError,match='SOURCE_REPLAY_MISMATCH'):
        validate_target(target,prior['client_id'],datetime.fromisoformat(at.replace('Z','+00:00')),
            approved_document_source=proof,snapshot=snapshot)
    del proof['dated_pool_binding']
    with pytest.raises(PermissionError,match='REPLAY_PROOF_REQUIRED'):enrich_document_target_view(target,proof)


def test_replay_checks_new_snapshot_and_future_component_without_relabelling_time(tmp_path):
    snapshot,_,_,pool,_,_,bind,pack,at=case(tmp_path)
    p=pack();wrong=deepcopy(snapshot);wrong['source_sha256']='b'*64
    with pytest.raises(PermissionError,match='CURRENT_MEMBER_SNAPSHOT'):
        replay(p['target'],p['trusted_approved_target_source'],evaluation_at=at,snapshot=wrong)
    pool['rate_time']='2026-03-11T00:00:00Z';bind()
    with pytest.raises(PermissionError,match='COMPONENT_AFTER_SOURCE_AVAILABILITY'):pack()


def test_decimal_precision_is_local_and_source_approval_is_never_recreated(tmp_path):
    snapshot,_,cfg,_,_,_,_,pack,at=case(tmp_path)
    with localcontext() as c:
        c.prec=6;p=pack();assert c.prec==6
    assert target_source(snapshot,cfg,at)==p['target']
    assert p['trusted_approved_target_source']['dated_pool_binding']['approval_created'] is False


def test_original_producer_rebinds_money_and_stops_at_real_missing_macro(tmp_path):
    snapshot,prior,cfg,_,_,_,_,pack,at=case(tmp_path);p=pack()
    request={**deepcopy(prior),'run_id':'SYNTHETIC_NEW_RUN','evaluation_at':at,'question':'SYNTHETIC_TARGET_SOURCE_REVIEW',
        'confirmed_target':target_source(snapshot,cfg,at)}
    configuration={'request_seed':{**deepcopy(prior),'confirmed_target':p['target']},'context_seed':{'client_id':prior['client_id'],
        'family_c7_profile':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1',
        'approved_document_target_source':p['trusted_approved_target_source']}}
    original=deepcopy(configuration);rebound,receipt=bind_producer_seed(configuration,request)
    assert rebound['request_seed']['confirmed_target']==request['confirmed_target']
    assert configuration==original and not receipt['approval_created']
    payload={'schema_version':'Family.W8.MemberFinancialProducer.v1','client_id':prior['client_id'],
        'asset_id':'SYN_A','source_db_sha256':snapshot['source_sha256'],'target_version':1,
        'source_reference':'SYNTHETIC_PRODUCER_INPUT','configuration':configuration,
        'artifact_directory':str(tmp_path/'artifacts')}
    path=tmp_path/'SYNTHETIC_PRODUCER.json';path.write_text(json.dumps(payload))
    def forbidden(**kwargs):pytest.fail('Missing macro must not enter the native financial producer')
    result,financial=produce_financial(ROOT,request,'SYN_A',{'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()},
        producer_factory=forbidden)
    assert financial is None and not result['qualified_financial_pack']
    assert result['issues'][0]['code']=='MEMBER_PRODUCER_PRECAPTURED_MACRO_REQUIRED'
    assert 'dated_target_source_binding' in result


def test_older_bootstrap_capture_cannot_replace_current_source_or_change_weights(tmp_path):
    snapshot,prior,cfg,_,_,_,_,pack,at=case(tmp_path)
    args=deepcopy(cfg['document_target']);args.pop('sha256');args.pop('dated_pool_source')
    old_path=tmp_path/'SYNTHETIC_OLDER_CAPTURE.md'
    old_path.write_bytes(Path(args['source_path']).read_bytes()+b'\nSYNTHETIC_OLDER_CAPTURE_METADATA\n')
    args.update(source_path=str(old_path),source_available_at='2025-12-31T00:00:00Z')
    older=build_approved_target_view(**args)
    request={**deepcopy(prior),'evaluation_at':at,'run_id':'SYNTHETIC_NEW_REVIEW','confirmed_target':pack()['target']}
    configuration={'request_seed':{**deepcopy(prior),'confirmed_target':older['target']},
        'context_seed':{'approved_document_target_source':older['trusted_approved_target_source']}}
    normalized={'original_target_sources':{'document_target':cfg['document_target']}}
    result,receipt=bind_producer_seed(configuration,request,normalized)
    assert result['request_seed']['confirmed_target']==request['confirmed_target']
    assert result['request_seed']['confirmed_target']['payload']['confirmation_evidence']==prior['confirmed_target']['payload']['confirmation_evidence']
    assert receipt['historical_seed_source']['proof']==older['trusted_approved_target_source']
    configuration['request_seed']['confirmed_target']['payload']['draft']['target_lines'][0]['weight']['value']=0.21
    configuration['context_seed']['approved_document_target_source']['target_view_digest']=digest(configuration['request_seed']['confirmed_target'])
    with pytest.raises(PermissionError,match='PRODUCER_APPROVAL_CHANGED'):
        bind_producer_seed(configuration,request,normalized)


def test_bootstrap_target_of_another_member_cannot_be_rebound_by_matching_weights(tmp_path):
    _,prior,cfg,_,_,_,_,pack,at=case(tmp_path);p=pack()
    request={**deepcopy(prior),'evaluation_at':at,'confirmed_target':p['target']}
    wrong=deepcopy(p['target']);wrong['payload']['draft']['identity']['client_id']='fam_'+'b'*32
    proof=deepcopy(p['trusted_approved_target_source']);proof['target_view_digest']=digest(wrong)
    configuration={'request_seed':{**deepcopy(prior),'confirmed_target':wrong},
        'context_seed':{'approved_document_target_source':proof}}
    with pytest.raises(PermissionError,match='PRODUCER_APPROVAL_CHANGED'):
        bind_producer_seed(configuration,request,{'original_target_sources':{'document_target':cfg['document_target']}})

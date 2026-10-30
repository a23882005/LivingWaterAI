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

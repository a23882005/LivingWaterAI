from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from test_v10_stock_integration import adopted_case,bind_context
from stock_engine import run_stock_engine,_plain
from v82_approved_context import build,read_source
from current_analysis_delivery import current_judgment


def case(tmp_path,**updates):
    req,facts,contract=adopted_case();out=run_stock_engine(ROOT,req,facts,contract)
    context=facts['approved_v10_context'];identity=context['identity']
    request={'client_id':identity['client_id'],'run_id':identity['run_id'],'owner':identity['owner'],
        'evaluation_at':identity['evaluation_at'],'client_snapshot':{'payload':{'source_sha256':identity['snapshot_id']}}}
    data={'schema_version':'Family.W8.V82ApprovedSource.v1','client_id':request['client_id'],
        'owner':request['owner'],'asset_id':'QQQ','source_db_sha256':identity['snapshot_id'],
        'source_reference':'SYNTHETIC_SAME_RUN_SOURCE','available_at':identity['evaluation_at'],
        'right_event_dependency_scope_verified':True,'right_event_dependencies':[],
        'macro_pressure_inputs':{'inflation_chain_accelerating':'FALSE','real_yield_rising_fast':'FALSE'},
        'market_identity':context['market_identity'],'high_beta':'FALSE',**updates}
    path=tmp_path/'SYNTHETIC_APPROVED_SOURCE.json';path.write_text(json.dumps(data))
    descriptor={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    row={'symbol':'QQQ','native_product_identity':{'primary_class':'科技／AI／高成長ETF','asset_type':'BROAD_ETF'},
        'primary_framework':'SYNTHETIC_QUALIFIED_FRAMEWORK','core_observation':{'result':_plain(out['core_state']),'actual_inputs':facts['core']},
        'macro_observations':{'credit':{'risk_level':0}},'market':{'approved_technical':{'off_low':'TRUE','left_maturity_signals':[]}}}
    return request,row,descriptor,req,facts,contract


def test_report_and_native_share_complete_right_stage_and_maturity(tmp_path):
    request,row,source,req,facts,contract=case(tmp_path)
    context,analysis=build(ROOT,row,request,fundamental=True,price_conditions={'value':True},left_safety=True,source_descriptor=source)
    context['native_owner']=deepcopy(req['work3_handoff']['owner'])
    context['cycle_snapshot']=deepcopy(facts['approved_v10_context']['cycle_snapshot'])
    context['session']=deepcopy(facts['approved_v10_context']['session'])
    context['execution_costs']=deepcopy(facts['approved_v10_context']['execution_costs'])
    context['shared_allocation_request']=deepcopy(facts['approved_v10_context']['shared_allocation_request'])
    facts['approved_v10_context']=context;bind_context(facts,contract)
    result=run_stock_engine(ROOT,req,facts,contract)
    assert result['approved_v10_analysis']['market_predicates']==analysis['market_predicates']
    assert result['deployment'].stage==analysis['formal_stage']=='STAGE_8'
    row['formal_conclusion']={'approved_v10_analysis':analysis,'approved_project_target':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}
    displayed=current_judgment(row,ROOT)
    assert displayed['mode']==result['deployment'].mode.value
    assert displayed['target_rate_reference']==str(result['deployment'].target_rate)
    assert analysis['maturity']['state']=='UNKNOWN' and analysis['speed']['mode_rate']=='0.25'


def test_required_t_plus_1_pending_is_not_a_technical_right_or_a_ready_stage(tmp_path):
    request,row,source,*_=case(tmp_path,right_event_dependencies=[{
        'event_id':'SYNTHETIC_EVENT','depends_on_event_gap':'TRUE','recheck_state':'PENDING'}])
    context,analysis=build(ROOT,row,request,fundamental=True,price_conditions={'value':True},left_safety=True,source_descriptor=source)
    assert row['core_observation']['result']['technical']['right_confirmation']=='TRUE'
    assert analysis['right_entry']['truth']=='FALSE' and analysis['selected_mode']=='Left Overweight'
    assert analysis['formal_stage']=='UNKNOWN'
    assert analysis['qV']['reason_codes']==['OWN_METRIC_COMPARABLE_PIT_HISTORY_SOURCE_UNAVAILABLE']


def test_supplementary_source_hash_owner_and_time_are_checked_each_read(tmp_path):
    request,row,source,*_=case(tmp_path)
    assert read_source(source,request,'QQQ')['asset_id']=='QQQ'
    Path(source['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='HASH_MISMATCH'):read_source(source,request,'QQQ')
    request,row,source,*_=case(tmp_path,available_at='2027-01-01T00:00:00Z')
    with pytest.raises(PermissionError,match='NOT_AVAILABLE'):read_source(source,request,'QQQ')
    request,row,source,*_=case(tmp_path,owner={'account':'OTHER'})
    with pytest.raises(PermissionError,match='IDENTITY_MISMATCH'):read_source(source,request,'QQQ')

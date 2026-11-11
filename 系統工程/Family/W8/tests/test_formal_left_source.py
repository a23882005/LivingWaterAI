"""H33 B: original source assertions reach Work41; no research thresholds."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys

import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from test_v82_approved_context import case as approved_case
from formal_mode_analysis import build_formal_conclusion,left_entry_sources,native
from v82_core_source import read,arguments,left_inputs,LEFT_PRICE,LEFT_EVENT


def case(tmp_path,**approved_updates):
    request,row,approved,*_=approved_case(tmp_path,fundamentals_viable='TRUE',**approved_updates)
    request.update(trade_authorization='NONE',confirmed_target={'target_version':1,'payload':{'draft':{
        'target_lines':[{'ticker':'QQQ','target_amount':{'value_state':'UNKNOWN','amount':None,'currency':None}}]}}})
    request['client_snapshot']['payload']['tables']={'portfolio_snapshot_item':[]}
    row.update(scenario_class={'formal_v82_class':'LARGE_MATURE_HIGH_QUALITY_STOCK'},
        holding={'quantity_state':'KNOWN','quantity':'0'},valuation_observations=[],position_valuation_allowed=False)
    row['native_product_identity'].update(asset_type='INDIVIDUAL_STOCK',primary_class='大型成熟／高品質個股')
    row['market'].update(source_path='SYNTHETIC_COMPLETED_HISTORY',observed_close='100',source_sha256='b'*64,
        market_identity={'exchange':'SYNTHETIC_EXCHANGE','currency':'USD','provider_symbol':'QQQ','provider_type':'EQUITY'},
        completed_session_close_at=request['evaluation_at'],history_quality={'price_basis':'SYNTHETIC_RAW_UNADJUSTED'})
    row['market']['approved_technical'].update(off_low='FALSE',left_maturity_signals=[
        {'id':'M'+str(i),'truth':'FALSE'} for i in range(1,9)])
    row['core_observation']['result']['technical'].update(runaway_up='FALSE',right_confirmation='FALSE',runaway_down='FALSE')
    # No legal valuation vote: any positive price OR below must come from the
    # named original source leaf, independently of M1..M8 or qP/qV.
    row['core_observation']['result']['valuation']['formal_output_eligible']=False
    at=request['evaluation_at'];until='2027-01-01T00:00:00Z'
    source={'schema_version':'Family.W8.V82CoreSource.v1','client_id':request['client_id'],
        'owner':request['owner'],'asset_id':'QQQ','source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'available_at':at,'source_reference':'SYNTHETIC_CORE_SOURCE','leaves':{}}

    def leaf(name,value,change=None):
        field='left.'+name
        definition={'approval_state':'APPROVED_EXISTING_RULE','authority_reference':'SYNTHETIC_EXISTING_OWNER_DEFINITION',
            'methodology_reference':'SYNTHETIC_APPROVED_ASSET_LOCAL_METHOD',
            'rule_reference':'V82 Work41-D / Work34' if name==LEFT_EVENT else 'V82 Work41-A'}
        original={**{k:request[k] for k in ('client_id','owner','run_id','evaluation_at')},
            'asset_id':'QQQ','source_db_sha256':source['source_db_sha256'],
            'schema_version':'Family.W8.VerifiedLeftAssertion.v1','field_path':field,'value':value,
            'validation_status':'VERIFIED','rule_definition':definition,
            'as_of':at,'available_at':at,'retrieved_at':at,'valid_until':until,
            'observation_scope':'COMPLETED_SESSION','session_close_at':at,'price_basis':'SYNTHETIC_RAW_UNADJUSTED',
            'market_source_sha256':row['market']['source_sha256'],'market_identity':deepcopy(row['market']['market_identity']),
            'coverage':{'required_domains':['SYNTHETIC_REGISTERED_DOMAIN'],
                'checked_domains':['SYNTHETIC_REGISTERED_DOMAIN'],
                'required_domain_scope_reference':'SYNTHETIC_APPROVED_EVENT_SCOPE',
                'event_registry_checkpoint':'SYNTHETIC_REGISTRY_CHECKPOINT','coverage_cutoff':at,
                'active_event_registry_reviewed':True},
            'event_dependency_scope_verified':True,'event_dependencies':[]}
        if change:change(original)
        path=tmp_path/(field+'.original.json');path.write_text(json.dumps(original))
        proof={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_SOURCE_OWNER_ASSERTION',
            'methodology_reference':'SYNTHETIC_APPROVED_ASSET_LOCAL_METHOD',
            'as_of':at,'available_at':at,'retrieved_at':at,'valid_until':until,
            'pit_status':'VERIFIED','pit_receipt_reference':'SYNTHETIC_PIT_RECEIPT'}
        source['leaves'][field]={'value':value,'proof':proof}

    def bind():
        p=tmp_path/'SYNTHETIC_LEFT_CORE_SOURCE.json';p.write_text(json.dumps(source))
        qualified=read({'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()},request,'QQQ')
        row['core_observation']['qualified_core_source']=qualified
        return qualified

    def run():
        return build_formal_conclusion(ROOT,row,request,approved_source_descriptor=approved)

    return request,row,source,leaf,bind,run


@pytest.mark.parametrize('name',LEFT_PRICE)
def test_each_original_price_leaf_reaches_real_conclusion_without_maturity_gate(tmp_path,name):
    request,row,source,leaf,bind,run=case(tmp_path)
    leaf(name,'TRUE');leaf(LEFT_EVENT,'TRUE');qualified=bind()
    before=deepcopy((request,row,qualified));out=run()
    assert out['left_inputs']['price_conditions'][name]=='TRUE'
    assert out['left_inputs']['price_condition_at_least_one']=='TRUE'
    assert all(v=='UNKNOWN' for k,v in out['left_inputs']['price_conditions'].items() if k!=name)
    assert out['market_predicates']['left']=='TRUE' and out['selected_mode']=='Left Overweight'
    assert out['approved_v10_analysis']['maturity']['true_count']==0
    assert out['left_entry_source_audit'][name]['status']=='BOUND_ORIGINAL_SOURCE'
    assert out['event_coverage']['confirmed_no_uncontrollable_event_gap']=='TRUE'
    assert out['formal_stage']=='UNKNOWN' and out['canonical_target_rate'] is None
    assert out['trade_action']=='NO_TRADE' and out['deployment_status']=='NOT_RUN'
    assert (request,row,qualified)==before
    # These facts are not a second Core engine or extra safety kwargs.
    native(ROOT);kwargs,resolved=arguments(qualified,broad_etf=False)
    assert not any(k.startswith('left.') for k in kwargs) and not set(resolved)&set(source['leaves'])


def test_no_source_has_exact_spec_and_source_gaps_and_news_is_not_clearance(tmp_path):
    request,row,_,_,_,run=case(tmp_path)
    request['macro_snapshot']={'payload':{'news':[]}}
    out=run()
    assert out['left_inputs']['price_condition_at_least_one']=='UNKNOWN'
    assert out['left_safety_inputs']['uncontrollable_event_gap_negations_absent']=='UNKNOWN'
    assert out['event_coverage']['confirmed_no_active_event'] is None
    assert out['left_entry_source_audit']['price_map_zone']['status']=='SOURCE_GAP'
    assert all(out['left_entry_source_audit'][name]['status']=='SPEC_GAP' for name in LEFT_PRICE[1:])


def test_known_price_true_does_not_fill_absent_event_or_fundamental_sources(tmp_path):
    _,row,_,leaf,bind,run=case(tmp_path)
    leaf('price_map_zone','TRUE');bind();out=run()
    assert out['left_inputs']['price_condition_at_least_one']=='TRUE'
    assert out['market_predicates']['left']=='UNKNOWN'
    leaf(LEFT_EVENT,'TRUE');bind()
    # ETF structure is evaluated by its original producer, separately from the
    # existing source's individual-stock thesis. No ETF assertions are supplied.
    row['native_product_identity']['asset_type']='BROAD_ETF'
    out=run();assert out['left_inputs']['fundamentals_long_term_viable']=='UNKNOWN'
    assert out['market_predicates']['left']=='UNKNOWN'


@pytest.mark.parametrize('state',['PENDING','FAILED','PASSED'])
def test_event_dependency_reuses_original_work34_recheck(tmp_path,state):
    _,_,_,leaf,bind,run=case(tmp_path)
    leaf('price_map_zone','TRUE')
    leaf(LEFT_EVENT,'TRUE',lambda o:o.update(event_dependencies=[
        {'event_id':'SYNTHETIC_EVENT','depends_on_event_gap':'TRUE','recheck_state':state}]))
    bind();out=run();expected='TRUE' if state=='PASSED' else 'FALSE'
    assert out['left_safety_inputs']['uncontrollable_event_gap_negations_absent']==expected
    assert out['market_predicates']['left']==expected


@pytest.mark.parametrize('change',[
    lambda o:o.update(owner={'account':'OTHER'}),
    lambda o:o.update(run_id='OTHER'),
    lambda o:o.update(asset_id='OTHER'),
    lambda o:o.update(source_db_sha256='OTHER'),
    lambda o:o.update(value='FALSE'),
    lambda o:o.update(as_of='2027-01-01T00:00:00Z'),
    lambda o:o['rule_definition'].update(approval_state='CANDIDATE'),
    lambda o:o['rule_definition'].update(authority_reference=None),
    lambda o:o['rule_definition'].update(rule_reference='Issue69 EARLY_LEFT_MIN_VERIFIED'),
    lambda o:o['rule_definition'].update(methodology_reference='UNRELATED'),
])
def test_cross_scope_pasted_vote_or_unapproved_definition_is_rejected(tmp_path,change):
    _,_,_,leaf,bind,_=case(tmp_path)
    leaf('near_confirmed_low','TRUE',change)
    with pytest.raises(PermissionError,match='V82_LEFT_ORIGINAL_ASSERTION'):bind()


@pytest.mark.parametrize('change',[
    lambda o:o.update(observation_scope='INTRADAY_CANDIDATE'),
    lambda o:o.update(session_close_at='2027-01-01T00:00:00Z'),
    lambda o:o.update(price_basis=None),
])
def test_intraday_or_future_session_cannot_replace_completed_price_evidence(tmp_path,change):
    _,_,_,leaf,bind,_=case(tmp_path)
    leaf('price_map_zone','TRUE',change)
    with pytest.raises(PermissionError,match='COMPLETED_SESSION_AND_BASIS'):bind()


@pytest.mark.parametrize('change',[
    lambda o:o['coverage'].update(checked_domains=[]),
    lambda o:o['coverage'].update(required_domain_scope_reference=None),
    lambda o:o['coverage'].update(event_registry_checkpoint=None),
    lambda o:o['coverage'].update(active_event_registry_reviewed=False),
    lambda o:o['coverage'].update(coverage_cutoff='2027-01-01T00:00:00Z'),
    lambda o:o.update(event_dependency_scope_verified=False),
])
def test_news_or_incomplete_domain_registry_cannot_supply_event_clearance(tmp_path,change):
    _,_,_,leaf,bind,_=case(tmp_path)
    leaf(LEFT_EVENT,'TRUE',change)
    with pytest.raises(PermissionError,match='EVENT_COVERAGE_AND_DEPENDENCIES'):bind()


def test_each_read_rechecks_proof_bytes_and_derived_projection(tmp_path):
    request,row,source,leaf,bind,_=case(tmp_path)
    leaf('price_map_zone','TRUE');qualified=bind()
    Path(source['leaves']['left.price_map_zone']['proof']['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='HASH_MISMATCH'):left_inputs(qualified,request,'QQQ')
    leaf('price_map_zone','TRUE');qualified=bind()
    qualified['leaves']['left.price_map_zone']['value']='FALSE'
    with pytest.raises(PermissionError,match='SOURCE_REPLAY_MISMATCH'):left_inputs(qualified,request,'QQQ')


def test_event_veto_and_core_gate_cannot_silently_disagree(tmp_path):
    _,row,_,leaf,bind,run=case(tmp_path)
    leaf('price_map_zone','TRUE');leaf(LEFT_EVENT,'FALSE');bind()
    with pytest.raises(PermissionError,match='VETO_CORE_GATE_CONFLICT'):run()
    row['core_observation']['result']['permission']['hard_gate']='TRIGGERED'
    out=run();assert out['market_predicates']['left']=='FALSE'


def test_unknown_assertion_has_approved_definition_but_remains_a_source_gap(tmp_path):
    request,row,_,leaf,bind,_=case(tmp_path)
    leaf('near_confirmed_low','UNKNOWN');bind()
    _,_,_,audit=left_entry_sources(row,request)
    assert audit['near_confirmed_low']['status']=='SOURCE_GAP'
    assert audit['near_confirmed_low']['truth']=='UNKNOWN'


@pytest.mark.parametrize('change',[
    lambda o:o['market_identity'].update(exchange='OTHER'),
    lambda o:o['market_identity'].update(currency='TWD'),
    lambda o:o.update(market_source_sha256='c'*64),
    lambda o:o.update(price_basis='ADJUSTED_OTHER_BASIS'),
    lambda o:o.update(session_close_at='2026-09-25T00:00:00Z'),
])
def test_other_listing_currency_basis_or_previous_session_cannot_vote(tmp_path,change):
    _,_,_,leaf,bind,run=case(tmp_path)
    leaf('price_map_zone','TRUE',change);bind()
    with pytest.raises(PermissionError,match='MARKET_IDENTITY_BASIS_OR_COMPLETED_SESSION'):run()


def test_replay_preserves_original_maturity_core_and_does_not_open_a_cycle(tmp_path):
    request,row,_,leaf,bind,run=case(tmp_path)
    leaf('price_map_zone','TRUE');leaf(LEFT_EVENT,'TRUE');bind()
    before=deepcopy((request,row));first=run()
    assert all(run()==first for _ in range(4))
    assert (request,row)==before
    assert first['buy_permission']['value']==row['core_observation']['result']['permission']['new_buy_order_permission']
    assert first['trade_action']=='NO_TRADE' and 'cycle_snapshot' not in request


def test_maturity_changes_speed_without_becoming_b2_or_first_left_entry_ticket(tmp_path):
    _,row,_,leaf,bind,run=case(tmp_path)
    row['core_observation']['result']['valuation']['formal_output_eligible']=True
    leaf('price_map_zone','TRUE');leaf(LEFT_EVENT,'TRUE');bind()
    slow=run()
    row['market']['approved_technical']['left_maturity_signals']=[
        {'id':'M'+str(i),'truth':'TRUE'} for i in range(1,9)]
    fast=run()
    for out in (slow,fast):
        assert out['market_predicates']['left']=='TRUE'
        assert out['approved_v10_analysis']['left_stage_profile']['eligible']['2']=='TRUE'
    assert slow['approved_v10_analysis']['left_stage_profile']==fast['approved_v10_analysis']['left_stage_profile']
    assert slow['approved_v10_analysis']['speed']!=fast['approved_v10_analysis']['speed']
    assert slow['formal_stage']==fast['formal_stage']


@pytest.mark.parametrize('base,extra,expected',[(None,'TRUE','UNKNOWN'),(False,'TRUE','FALSE'),(True,'FALSE','FALSE')])
def test_supplemental_aggregate_cannot_replace_missing_or_negative_left_safety(tmp_path,base,extra,expected):
    _,row,_,leaf,bind,run=case(tmp_path,left_safety=extra)
    leaf('price_map_zone','TRUE')
    if base is not None:leaf(LEFT_EVENT,'TRUE')
    if base is False:row['core_observation']['result']['permission']['hard_gate']='TRIGGERED'
    bind();out=run()
    assert out['approved_v10_context']['left_safety']==expected
    assert out['left_inputs']['left_safety_negations_absent']==expected

"""Approved v1.0 profile acceptance, using original enums and selector."""
from copy import deepcopy
from decimal import Decimal
import sys
import pytest
from test_native_adapters import ROOT
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.approved_profiles import (P,CUTS,absolute_range,left_profile,
    _select,right_entry,resolve_approved_stage,select_with_entries)

AT='2026-10-30T00:00:00Z';SNAP='SYNTHETIC-SNAPSHOT'


def range_proof(profile='GLOBAL_EQUITY_ETF',**updates):
    return {'profile':profile,'snapshot_id':SNAP,'source_reference':'SYNTHETIC_APPROVED_RANGE',
        'product_type_verified':True,'applicability':'TRUE','range_id':profile+'_FORWARD_PE',
        'range_version':'V82.1.21.0','effective_from':'2026-10-27T00:00:00Z',**updates}


def pv(qp='80',qv='30',depth='.1',metric='FORWARD_PE',current='10',proof=None,profile='GLOBAL_EQUITY_ETF'):
    r=absolute_range(profile=profile,metric=metric,current=current,proof=proof or range_proof(profile),
        snapshot_id=SNAP,decision_at=AT)
    return left_profile(price_entry='TRUE',valuation_legal='TRUE',depth=depth,q_price=qp,
        q_value=qv,metric=metric,current=current,range_result=r)


@pytest.mark.parametrize('qp,qv,expected',[('50','80',2),('80','50',3),('80','30',4),
    ('95','30',5),('95','10',6),('99','10',7),('80','40',3),('75','59.999',3),('75','60',2)])
def test_approved_strict_stage_boundaries(qp,qv,expected):
    result=pv(qp,qv);assert result['stage']=='STAGE_'+str(expected)


def test_stage2_has_no_new_percentile_ticket_and_zero_depth_short_circuits():
    out=pv(None,None,'0')
    assert out['stage']=='STAGE_2'
    assert out['eligible']['3']=='FALSE'
    out=pv(None,None)
    assert out['stage'] is None and out['known_lower_bound']==2 and out['possible_upper_bound']==7


@pytest.mark.parametrize('profile',list(CUTS))
def test_eleven_profile_supported_path_with_explicit_range_evidence(profile):
    proof=range_proof(profile,applicability='TRUE' if CUTS[profile] else 'FALSE',no_applicable_range_verified=True)
    assert pv('99','10',proof=proof,profile=profile)['stage']=='STAGE_7'


def test_non_pe_and_verified_na_are_neutral_but_unknown_range_is_not_na():
    assert pv(metric='PB',proof={})['stage']=='STAGE_4'
    no_range=range_proof(applicability='FALSE',no_applicable_range_verified=True)
    assert pv(proof=no_range)['stage']=='STAGE_4'
    assert pv(proof=range_proof(applicability='UNKNOWN'))['stage'] is None
    assert pv(proof=range_proof(product_type_verified=False))['stage'] is None
    assert pv(proof=range_proof(override_requested=True))['stage'] is None


def test_nesting_conflict_is_rejected_instead_of_publishing_a_deeper_stage():
    assert _select({2:P.TRUE,3:P.FALSE,4:P.TRUE},nested=True)['status']=='NESTING_OR_INPUT_CONFLICT'


def complete_right(**updates):
    args=dict(off_low='TRUE',right_confirmation='TRUE',fundamentals_viable='TRUE',credit_allows='TRUE',
        runaway_down='FALSE',valuation_condition='TRUE',event_dependencies=[],dependency_scope_verified=True)
    args.update(updates);return right_entry(**args)


def test_complete_right_does_not_equal_the_technical_r_subcondition():
    assert complete_right()['truth']=='TRUE'
    assert complete_right(off_low='FALSE')['truth']=='FALSE'
    assert complete_right(fundamentals_viable='UNKNOWN')['truth']=='UNKNOWN'
    assert complete_right(credit_allows='FALSE')['truth']=='FALSE'
    assert complete_right(valuation_condition='FALSE')['truth']=='FALSE'
    assert complete_right(dependency_scope_verified=False)['truth']=='UNKNOWN'
    event={'event_id':'SYNTHETIC_GAP','depends_on_event_gap':'TRUE','recheck_state':'PENDING'}
    assert complete_right(event_dependencies=[event])['truth']=='FALSE'
    event['recheck_state']='PASSED';assert complete_right(event_dependencies=[event])['truth']=='TRUE'
    event['depends_on_event_gap']='FALSE';event['recheck_state']='UNKNOWN'
    assert complete_right(event_dependencies=[event])['truth']=='TRUE'


def resolve(mode='Trend Deployment',qv='59.999',normal='TRUE',required=None,restrictions=()):
    return resolve_approved_stage(mode=mode,left_result=pv(),q_value=qv,range_result={'normal':normal},
        required_facts=required or dict.fromkeys(('asset_identity','primary_framework','fundamentals_viable','valuation_legal'),'TRUE'),
        restrictions=restrictions,snapshot_id=SNAP)


def test_trend_8_9_boundary_and_short_circuit_preserve_unknown_evidence():
    assert resolve()[0].stage=='STAGE_9'
    assert resolve(qv='60')[0].stage=='STAGE_8'
    assert resolve(qv=None,normal='FALSE')[0].stage=='STAGE_8'
    d,a=resolve(qv=None);assert d.stage=='UNKNOWN' and a['selection']['known_lower_bound']==8


def test_base_right_reference_cannot_publish_when_stage_necessary_facts_are_unknown():
    for mode in ('Base Deployment','Right Confirmation'):
        result,a=resolve(mode=mode,required={'asset_identity':'TRUE','primary_framework':'TRUE','fundamentals_viable':'UNKNOWN','valuation_legal':'TRUE'})
        assert result.mode.value==mode and result.target_rate is None
        assert a['required_unknown_fields']==['fundamentals_viable']


def test_named_constraints_are_applied_and_unresolved_constraints_remain_named():
    restriction={'restriction_id':'SYNTHETIC_APPROVED_CAP','authority':'SYNTHETIC_OWNER',
        'source':'SYNTHETIC_CONTRACT','snapshot_id':SNAP,'applies_when':'TRUE',
        'expression':{'field':'qV','operator':'LT','value':'60'},'effect':{'kind':'MAX_STAGE','stage':8}}
    assert resolve(restrictions=[restriction])[0].stage=='STAGE_8'
    restriction['effect']={'kind':'OPAQUE_POLICY','stage':8}
    d,a=resolve(restrictions=[restriction]);assert d.target_rate is None
    assert a['stage_restrictions'][0]['reason']=='NAMED_STAGE_CONSTRAINT_UNRESOLVED'
    assert a['stage_restrictions'][0]['restriction_id']=='SYNTHETIC_APPROVED_CAP'
    restriction.update(expression='OPAQUE_POLICY_TRUE',expression_truth='TRUE',effect={'kind':'MAX_STAGE','stage':8})
    assert resolve(restrictions=[restriction])[0].target_rate is None


def test_gate_is_absent_from_right_analysis_and_up_down_conflict_preempts_normal_mode():
    assert complete_right()['hard_gate_is_not_a_right_analysis_dependency']
    mode,reasons=select_with_entries(runaway_up='FALSE',runaway_down='FALSE',right='TRUE',left='FALSE')
    assert mode.value=='Right Confirmation' and not reasons
    mode,reasons=select_with_entries(runaway_up='TRUE',runaway_down='TRUE',right='TRUE',left='TRUE')
    assert mode.value=='UNKNOWN' and reasons

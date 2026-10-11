from datetime import datetime, timezone
from decimal import Decimal
import itertools
import pytest
from v75_runtime.constants import PREDICATE_VERSION, PREDICATE_STATE_PRECEDENCE
from v75_runtime.enums import FreshnessState, PredicateAssessmentStatus, DeploymentState, ExistingPositionAction
from v75_runtime.models import PredicateResult, Money, PerAssetDeploymentInput
from v75_runtime.work4 import *

NOW=datetime(2026,9,25,tzinfo=timezone.utc)
def pr(pid,state):
 return PredicateResult(predicate_id=pid,predicate_version=PREDICATE_VERSION,aggregate_state=state,sub_states=[state],assessment_status=PredicateAssessmentStatus.VALID,as_of=NOW,source_lineage=['test'],input_freshness_state=FreshnessState.FRESH)
def base(**kw):
 s={'PRED-001':'NEUTRAL','PRED-002':'NO_HAWKISH_REPRICING','PRED-003':'NORMALIZING','PRED-004':'HY_NORMAL','PRED-005':'NORMAL','PRED-006':'NO_INFLATION_ALERT','PRED-007':'NORMAL','PRED-008':'ATTRACTIVE','PRED-009':'LEFT_MATURE','PRED-010':'ETF_QUALITY_NORMAL'};s.update(kw);return [pr(k,v) for k,v in s.items()]
def ev(states=None,credit='TREASURY',d='1',policy=None):
 return evaluate_step10(predicate_results=states or base(),asset_credit_class=credit,effective_duration_years=Decimal(d),existing_policy=policy or ExistingPositionPolicy(Decimal('0')))

def test_review_unknown_valid_pause():
 for s in ['ETF_QUALITY_REVIEW_REQUIRED','ETF_QUALITY_UNKNOWN']:
  assert ev(base(**{'PRED-010':s})).deployment_state==DeploymentState.PAUSE

def test_credit_class_behavior():
 assert ev(base(**{'PRED-004':'CREDIT_CRISIS'}),'TREASURY').deployment_state!=DeploymentState.HARD_WAIT
 for c in ['CORPORATE','MIXED']: assert ev(base(**{'PRED-004':'CREDIT_CRISIS'}),c).deployment_state==DeploymentState.HARD_WAIT

def test_liquidity_inflation_move():
 assert ev(base(**{'PRED-007':'SEVERE_ABNORMAL'})).deployment_state==DeploymentState.HARD_WAIT
 assert ev(base(**{'PRED-007':'ABNORMAL'})).deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-007':'MIXED','PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==25
 assert ev(base(**{'PRED-006':'LOSS_OF_CONTROL'})).deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-006':'INFLATION_REACCELERATION','PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==25
 assert ev(base(**{'PRED-005':'EXTREME'})).deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-005':'SURGE','PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==25

def test_duration_cases():
 assert ev(base(**{'PRED-002':'LARGE_HAWKISH_REPRICING','PRED-003':'SUSTAINED_SHARP_RISE'}),d='2').deployment_pct==25
 assert ev(base(**{'PRED-002':'EXTREME_HAWKISH_REPRICING','PRED-003':'EXTREME_RISE'}),d='2').deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-001':'HIGH','PRED-002':'LARGE_HAWKISH_REPRICING','PRED-003':'SUSTAINED_SHARP_RISE'}),d='5').deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-001':'HIGH','PRED-002':'LARGE_HAWKISH_REPRICING','PRED-003':'SUSTAINED_SHARP_RISE','PRED-006':'INFLATION_REACCELERATION'}),d='10').deployment_state==DeploymentState.HARD_WAIT

def test_base_matrix_key_cases():
 assert ev(base(**{'PRED-009':'TECHNICAL_NEUTRAL','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==25
 assert ev(base(**{'PRED-009':'LEFT_MATURE','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==75
 assert ev(base(**{'PRED-009':'RIGHT_CONFIRM','PRED-008':'ATTRACTIVE'})).deployment_pct==75
 assert ev(base(**{'PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_pct==100
 for y in PREDICATE_STATE_PRECEDENCE['PRED-008']:
  assert ev(base(**{'PRED-009':'TRIM_WATCH','PRED-008':y})).deployment_state==DeploymentState.PAUSE

def test_caps_and_directs():
 t=ev(base(**{'PRED-007':'MIXED','PRED-003':'SUSTAINED_SHARP_RISE'}),d='5')
 assert t.deployment_pct==25
 assert ev(base(**{'PRED-006':'LOSS_OF_CONTROL','PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_state==DeploymentState.PAUSE
 assert ev(base(**{'PRED-007':'SEVERE_ABNORMAL','PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})).deployment_state==DeploymentState.HARD_WAIT

def test_existing_null_no_sell_and_no_churn():
 p=ExistingPositionPolicy(Decimal('10'))
 assert ev(policy=p).existing_position_action==ExistingPositionAction.HOLD
 p=ExistingPositionPolicy(Decimal('10'),investment_logic_invalidated=True)
 t=ev(policy=p); assert t.existing_position_action==ExistingPositionAction.TRUE_RISK_REDUCTION and t.deployment_state==DeploymentState.HARD_WAIT
 p=ExistingPositionPolicy(Decimal('10'),capital_gain_harvest_eligible=True)
 t=ev(base(**{'PRED-009':'TRIM_WATCH','PRED-008':'LOW_ATTRACTIVENESS'}),policy=p); assert t.existing_position_action==ExistingPositionAction.TECHNICAL_TRIM and t.deployment_state==DeploymentState.PAUSE
 p=ExistingPositionPolicy(Decimal('10'),rebound_reduction_eligible=True)
 t=ev(base(**{'PRED-009':'RIGHT_CONFIRM'}),policy=p); assert t.existing_position_action==ExistingPositionAction.REBOUND_SMALL_SELL and t.deployment_state==DeploymentState.PAUSE

def test_existing_reduction_pct_null():
 inp=PerAssetDeploymentInput(asset_id='X',remaining_target_gap_amount=Money(amount=100,currency='USD'),existing_position_amount=Money(amount=0,currency='USD'),currency='USD')
 d=build_decision(inp,ev(),['test']); assert d.existing_reduction_pct is None

def test_all_legal_step10_components_are_total_and_exactly_one():
    # Formal totality proof by finite contract components: all 864 duration rows are unique,
    # every safety table covers every canonical state, and all 16 base cells resolve to one state.
    assert len(CONTRACT["duration_matrix"]) == 864
    keys={(r["duration_bucket"],r["PRED-001"],r["PRED-002"],r["PRED-003"],r["PRED-006"]) for r in CONTRACT["duration_matrix"]}
    assert len(keys)==864
    for credit in AssetCreditClass:
      for pid in ("PRED-010","PRED-007","PRED-006","PRED-005","PRED-004"):
        assert set(CONTRACT["safety_action_tables"][credit.value][pid]) == set(PREDICATE_STATE_PRECEDENCE[pid])
    for tech in PREDICATE_STATE_PRECEDENCE["PRED-009"]:
      for yld in PREDICATE_STATE_PRECEDENCE["PRED-008"]:
        assert DeploymentState(CONTRACT["yield_technical_base_matrix"][tech][yld])
    # Cross-product smoke over all safety classes, duration buckets, base cells.
    for credit,dur,tech,yld in itertools.product(AssetCreditClass,['.5','2','5','10','15','20'],PREDICATE_STATE_PRECEDENCE['PRED-009'],PREDICATE_STATE_PRECEDENCE['PRED-008']):
      t=ev(base(**{'PRED-009':tech,'PRED-008':yld}),credit.value,dur)
      assert isinstance(t.deployment_state,DeploymentState)

def test_invalid_step10_inputs_fail_closed():
 bad=base()[:-1]
 with pytest.raises(ValueError): ev(bad)
 with pytest.raises(ValueError): ev(credit='BOGUS')
 with pytest.raises(ValueError): ev(d='-1')

def test_proportional_scaling_and_sgov_residual():
 def dec(asset,amt):
  inp=PerAssetDeploymentInput(asset_id=asset,remaining_target_gap_amount=Money(amount=amt,currency='USD'),existing_position_amount=Money(amount=0,currency='USD'),currency='USD')
  return build_decision(inp,ev(base(**{'PRED-009':'RIGHT_CONFIRM','PRED-008':'VERY_ATTRACTIVE'})),['test'])
 ds=proportional_scale_decisions([dec('A',80),dec('B',40)],Money(amount=60,currency='USD'))
 assert [d.deploy_amount.amount for d in ds]==[Decimal('40'),Decimal('20')]
 assert calculate_v75_undeployed_to_sgov(broker_domain='US_BROKER',currency='USD',bond_executable_budget=Money(amount=100,currency='USD'),decisions=ds).amount==40
 assert calculate_v75_undeployed_to_sgov(broker_domain='TW_LOCAL_BROKER',currency='TWD',bond_executable_budget=Money(amount=100,currency='TWD'),decisions=[]) is None

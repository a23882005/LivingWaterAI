"""Synthetic inputs, actual frozen predicate and deployment computation."""
from copy import deepcopy
from decimal import Decimal
import pytest
from test_native_adapters import ROOT, request
from bond_engine import BondEvidenceError, run_bond_engine


def evidence():
    metrics = {
        'PRED-001': {'effr_pct': '5', 'sep_long_run_median_pct': '3', 'core_pce_yoy_pct': '3'},
        'PRED-002': {'next_fomc_expected_rate_delta_5bd_bps': '0'},
        'PRED-003': {'yield_delta_5bd_bps': '0', 'yield_delta_10bd_bps': '0', 'yield_up_days_last5': 0},
        'PRED-004': {'hy_oas_bps': '300'},
        'PRED-005': {'move': '80', 'move_pct_change_5bd': '0'},
        'PRED-006': {'core_pce_ann3_pct': '2', 'core_pce_ann6_pct': '2'},
        'PRED-007': {'sofr_ois_bps': '0', 'fra_ois_bps': '0', 'srf_usage_usd': '0'},
        'PRED-008': {'yield_percentile_pct': '95', 'history_years': '10'},
        'PRED-009': {'low_td_count': 6, 'k': '10', 'rsi14': '20',
                     'kd_golden_cross_k_le_35': True, 'macd_hist_improving_3d': True,
                     'reclaimed_ma20_last3d': True},
        'PRED-010': {'structure_state': 'NORMAL', 'liquidity_state_etf': 'NORMAL',
                     'distribution_quality_state': 'NORMAL'},
    }
    return {asset: {'asset_id': asset, 'run_id': 'w5-run-001',
        'broker_account_id': 'QA_ACCOUNT', 'currency': 'USD',
        'producer': 'W5_SYNTHETIC_TEST', 'version': '1', 'source_reference': 'SYNTHETIC:' + asset,
        'as_of': '2026-09-26T13:55:00+08:00', 'available_at': '2026-09-26T14:00:00+08:00',
        'asset_credit_class': credit, 'effective_duration_years': duration,
        'existing_policy': {'current_position_quantity': quantity}, 'metrics': deepcopy(metrics)}
        for asset, credit, duration, quantity in [('SGOV','TREASURY','0.1','1'),('SPSB','CORPORATE','2','0')]}


def test_real_predicates_deployment_and_canonical_preservation():
    req, facts = request(5), evidence()
    before = deepcopy((req, facts))
    result = run_bond_engine(ROOT, req, facts)
    assert result['status'] == 'COMPLETE'
    assert result['runtime_ready']['runtime_ready'] is True
    wire = result['runtime_ready']['output']
    amounts = [Decimal(x['deploy_amount']['amount']) for x in wire['per_asset_decisions']]
    assert all(x > 0 for x in amounts)
    assert sum(amounts) + Decimal(wire['v75_undeployed_to_sgov']['amount']) == Decimal('350')
    assert result['canonical']['canonical_v75_output'] == wire
    assert (req, facts) == before
    assert 'V75.evaluate_step10:SPSB' in result['call_trace']


def test_credit_crisis_uses_native_veto_and_preserves_treasury_branch():
    facts = evidence()
    for item in facts.values(): item['metrics']['PRED-004']['hy_oas_bps'] = '900'
    result = run_bond_engine(ROOT, request(5), facts)
    traces = result['native_step10_traces']
    assert traces['SPSB']['deployment_state'] == 'HARD_WAIT'
    assert traces['SGOV']['deployment_state'] != 'HARD_WAIT'


def test_missing_metric_is_not_fabricated_pause():
    facts = evidence(); facts['SPSB']['metrics']['PRED-005'] = {}
    result = run_bond_engine(ROOT, request(5), facts)
    assert result['status'] == 'INSUFFICIENT_DATA'
    assert result['canonical'] is None
    assert not any('assemble_final_snapshot' in x for x in result['call_trace'])


@pytest.mark.parametrize('field,value,reason', [
    ('broker_account_id','OTHER','EVIDENCE_IDENTITY'),
    ('asset_id','OTHER','EVIDENCE_IDENTITY'),
    ('available_at','2026-09-27T00:00:00Z','FUTURE_EVIDENCE'),
    ('version','','EVIDENCE_PROVENANCE'),
])
def test_evidence_rejection(field,value,reason):
    facts=evidence(); facts['SGOV'][field]=value
    with pytest.raises(BondEvidenceError,match=reason): run_bond_engine(ROOT,request(5),facts)


def test_empty_account_failure_preserves_native_account_state():
    req=request(5)
    req['v75_source_context']['authorized_universe'].remove('SPSB')
    result=run_bond_engine(ROOT,req,{})
    assert result['status']=='INVALID_INPUT'
    assert result['runtime_ready']['output']['per_asset_decisions']==[]
    assert result['canonical']['canonical_v75_output']['evaluation_state']=='INVALID_INPUT'


def test_zero_budget_has_zero_actual_deployment():
    req=request(5)
    req['c7_funding_context']['contexts'][2]['executable_budget']['bond']['amount']=0
    req['work3_handoff']['funding_context']['executable_budget']['bond']['amount']=0
    result=run_bond_engine(ROOT,req,evidence())
    assert all(Decimal(d['deploy_amount']['amount'])==0
        for d in result['runtime_ready']['output']['per_asset_decisions'])


def test_existing_position_native_risk_is_not_discarded():
    facts=evidence()
    facts['SGOV']['existing_policy']['investment_logic_invalidated']=True
    result=run_bond_engine(ROOT,request(5),facts)
    decision=result['runtime_ready']['output']['per_asset_decisions'][0]
    assert decision['asset_id']=='SGOV'
    assert decision['existing_position_action']=='TRUE_RISK_REDUCTION'
    assert decision['deploy_amount']['amount']=='0.00'

"""W5 orchestration of unchanged V75 evaluators; no execution side effects.

Metric evidence must already be normalized by an identified producer. This
module is not a market-data producer and does not calculate technical indicators.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys

from runtime_loader import load_c_module
from family_input import digest

V75_PATH = Path('系統工程/債券V75/正式Runtime/V75_Work6_RuntimeReady_2026-09-25/runtime')


class BondEvidenceError(ValueError):
    pass


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise BondEvidenceError('TIMEZONE_REQUIRED')
    return result


def run_bond_engine(repo_path, adapter_request, asset_evidence):
    """Return original canonical output plus exact inputs and native call trace.

    This component accepts a C8C9 request, not a public Family request. The
    Family boundary and permission bridges remain mandatory before dispatch.
    Missing predicates return an explicit incomplete component result, never
    a fabricated COMPLETE/PAUSE decision.
    """
    source = (Path(repo_path).resolve() / V75_PATH).resolve()
    sys.path.insert(0, str(source))
    import v75_runtime
    if Path(v75_runtime.__file__).resolve().parent != source / 'v75_runtime':
        raise BondEvidenceError('RUNTIME_SOURCE_MISMATCH')
    from v75_runtime.validation import validate_v75_run_input
    from v75_runtime.predicates import EVALUATORS
    from v75_runtime.work3 import build_work3_state
    from v75_runtime.work4 import (ExistingPositionPolicy, evaluate_step10,
        build_decision, proportional_scale_decisions, calculate_v75_undeployed_to_sgov)
    from v75_runtime.work5 import assemble_final_snapshot
    from v75_runtime.work6 import evaluate_runtime_ready

    request, evidence = deepcopy(adapter_request), deepcopy(asset_evidence)
    adapter = load_c_module(repo_path, 5)
    built = adapter.build_v75_runtime_input(request)
    trace = ['C8C9.Work5.build_v75_runtime_input', 'V75.validate_v75_run_input']
    checked = validate_v75_run_input(built['v75_runtime_input'])
    result = {'input_digest': digest({'request': request, 'evidence': evidence}),
              'built_input': built, 'call_trace': trace, 'predicate_results': {},
              'native_step10_traces': {}, 'production': 'HOLD', 'trade_authorization': 'NONE'}
    if not checked.accepted:
        return {**result, 'status': checked.disposition.value,
                'issues': [vars(issue) for issue in checked.issues], 'canonical': None}
    run = checked.model
    state = build_work3_state(run)
    trace.append('V75.build_work3_state')
    result['work3_state'] = state.model_dump(mode='json')
    decisions = []
    if state.work3_complete:
        expected = {item.asset_id for item in state.per_asset_inputs}
        if set(evidence) != expected:
            raise BondEvidenceError('ASSET_EVIDENCE_COVERAGE')
        for item in state.per_asset_inputs:
            facts = evidence[item.asset_id]
            for key, value in [('asset_id', item.asset_id), ('run_id', run.run_id),
                               ('broker_account_id', run.broker_account_id), ('currency', run.currency)]:
                if facts.get(key) != value:
                    raise BondEvidenceError('EVIDENCE_IDENTITY:' + key)
            if not all(isinstance(facts.get(k), str) and facts[k].strip()
                       for k in ('producer', 'version', 'source_reference')):
                raise BondEvidenceError('EVIDENCE_PROVENANCE')
            observed, available = _time(facts['as_of']), _time(facts['available_at'])
            if observed > available or available > run.analysis_timestamp:
                raise BondEvidenceError('FUTURE_EVIDENCE')
            if set(facts['metrics']) != set(EVALUATORS):
                raise BondEvidenceError('PREDICATE_COVERAGE')
            predicates = [fn(facts['metrics'][pid], observed, [facts['source_reference']])
                          for pid, fn in EVALUATORS.items()]
            trace.append('V75.predicates.PRED-001..010:' + item.asset_id)
            result['predicate_results'][item.asset_id] = [p.model_dump(mode='json') for p in predicates]
            if any(p.assessment_status.value != 'VALID' for p in predicates):
                return {**result, 'status': 'INSUFFICIENT_DATA', 'canonical': None,
                        'issues': ['PREDICATES_NOT_VALID:' + item.asset_id]}
            raw_quantity = facts['existing_policy']['current_position_quantity']
            if isinstance(raw_quantity, (bool, float)):
                raise BondEvidenceError('EXACT_QUANTITY_REQUIRED')
            quantity = Decimal(raw_quantity)
            if not quantity.is_finite() or quantity < 0:
                raise BondEvidenceError('INVALID_QUANTITY')
            if (quantity > 0) != (item.existing_position_amount.amount > 0):
                raise BondEvidenceError('POSITION_QUANTITY_VALUE_MISMATCH')
            policy = ExistingPositionPolicy(**{**facts['existing_policy'], 'current_position_quantity': quantity})
            for name in ('capital_gain_harvest_eligible', 'rebound_reduction_eligible', 'investment_logic_invalidated'):
                flag = getattr(policy, name)
                if flag is not None and type(flag) is not bool:
                    raise BondEvidenceError('BOOLEAN_POLICY_REQUIRED:' + name)
            duration = Decimal(facts['effective_duration_years'])
            if not duration.is_finite() or duration < 0:
                raise BondEvidenceError('INVALID_DURATION')
            native_trace = evaluate_step10(predicate_results=predicates,
                asset_credit_class=facts['asset_credit_class'],
                effective_duration_years=duration, existing_policy=policy)
            result['native_step10_traces'][item.asset_id] = {
                'deployment_state': native_trace.deployment_state.value,
                'deployment_pct': str(native_trace.deployment_pct),
                'rule_ids': list(native_trace.step10_rule_ids)}
            decisions.append(build_decision(item, native_trace, [facts['source_reference']]))
            trace.extend(['V75.evaluate_step10:' + item.asset_id, 'V75.build_decision:' + item.asset_id])
        decisions = proportional_scale_decisions(decisions, run.bond_executable_budget)
        trace.append('V75.proportional_scale_decisions')
        undeployed = calculate_v75_undeployed_to_sgov(broker_domain=run.broker_domain_type.value,
            currency=run.currency, bond_executable_budget=run.bond_executable_budget, decisions=decisions)
        trace.append('V75.calculate_v75_undeployed_to_sgov')
    else:
        undeployed = None
    snapshot = assemble_final_snapshot(run=run, work3_state=state, decisions=decisions,
                                      v75_undeployed_to_sgov=undeployed)
    ready = evaluate_runtime_ready(snapshot)
    wire = ready.model_dump(mode='json')
    trace.extend(['V75.assemble_final_snapshot', 'V75.evaluate_runtime_ready'])
    canonical = adapter.consume_v75_runtime_ready(wire, built['integration_binding'])
    trace.append('C8C9.Work5.consume_v75_runtime_ready')
    return {**result, 'status': wire['output']['evaluation_state'],
            'runtime_ready': wire, 'canonical': canonical}

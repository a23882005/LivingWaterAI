"""Original Work21 synthetic positive adapter cases; not a Family E2E run."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
from decimal import Decimal
import pytest
from jsonschema import Draft202012Validator
from runtime_loader import C_PATH, load_c_module, check_c_dependencies

ROOT = Path(os.environ.get('W5_SOURCE_ROOT', Path(__file__).resolve().parents[4])).resolve()
FIXTURES = Path(__file__).parent / 'fixtures'


def request(work):
    return json.loads((FIXTURES / f'work{work}_adapter_request.json').read_text())


def test_all_schema_dependencies():
    rows=check_c_dependencies(ROOT)
    assert len(rows)==26
    assert all(r['status']=='SCHEMA_VALID' for r in rows)


def test_stock_adapter_positive_input():
    adapter=load_c_module(ROOT,4)
    req=request(4);before=deepcopy(req)
    built=adapter.build_v82_runtime_input(req)
    sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
    from livingwater_v82_runtime import compile_schema,validate_and_bind_funding
    compile_schema('runtime_input').validate(built['v82_runtime_input'])
    bound=validate_and_bind_funding(built['v82_runtime_input'])
    assert bound.bound_equity_budget.amount==Decimal('450')
    assert req==before


def test_bond_adapter_positive_input_and_output():
    adapter=load_c_module(ROOT,5)
    req=request(5);before=deepcopy(req)
    built=adapter.build_v75_runtime_input(req)
    sys.path.insert(0,str(ROOT/'系統工程/債券V75/正式Runtime/V75_Work6_RuntimeReady_2026-09-25/runtime'))
    from v75_runtime import V75RunInput
    from v75_runtime.enums import DeploymentState,EvaluationState,ExistingPositionAction,GateState,NewMoneyAction
    from v75_runtime.models import Money,PerAssetDecision,PercentValue
    from v75_runtime.work3 import build_work3_state
    from v75_runtime.work5 import assemble_final_snapshot
    from v75_runtime.work6 import evaluate_runtime_ready
    run=V75RunInput.model_validate(built['v75_runtime_input'])
    state=build_work3_state(run)
    assert state.work3_complete
    # Original Work21 adapter fixture uses explicit no-action decisions.
    decisions=[PerAssetDecision(asset_id=p.asset_id,deployment_state=DeploymentState.PAUSE,
        deployment_pct=PercentValue(value=Decimal('0')),deploy_amount=Money(amount=Decimal('0'),currency=run.currency),
        new_money_action=NewMoneyAction.PAUSE,existing_position_action=ExistingPositionAction.HOLD,
        existing_reduction_pct=None,classification=[],gate_state=GateState.PASS,
        evaluation_state=EvaluationState.COMPLETE,reason_codes=['C8C9_WORK5_QA_NO_ACTION'],
        source_lineage=['C8C9_WORK5_QA']) for p in state.per_asset_inputs]
    snap=assemble_final_snapshot(run=run,work3_state=state,decisions=decisions,
        v75_undeployed_to_sgov=Money(amount=run.bond_executable_budget.amount,currency=run.currency))
    ready=evaluate_runtime_ready(snap)
    assert ready.runtime_ready
    wire=ready.model_dump(mode='json')
    integrated=adapter.consume_v75_runtime_ready(wire,built['integration_binding'])
    assert integrated['canonical_v75_runtime_ready_snapshot']==wire
    assert integrated['canonical_v75_output']==wire['output']
    assert req==before


@pytest.mark.parametrize('work',[4,5])
def test_adapter_still_rejects_invalid_schema(work):
    adapter=load_c_module(ROOT,work)
    req=request(work);req['unexpected_field']=True
    build=adapter.build_v82_runtime_input if work==4 else adapter.build_v75_runtime_input
    with pytest.raises(Exception,match='INPUT_SCHEMA'):build(req)


def test_stock_adapter_positive_output():
    adapter=load_c_module(ROOT,4)
    built=adapter.build_v82_runtime_input(request(4))
    wire=json.loads((FIXTURES/'work4_adapter_output.json').read_text())
    schema=json.loads((ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src/livingwater_v82_runtime/schema/runtime_output.schema.json').read_text())
    Draft202012Validator(schema).validate(wire)
    integrated=adapter.consume_v82_runtime_output(wire,built['integration_binding'])
    assert integrated['canonical_v82_output']==wire
    assert integrated['canonical_v82_output']['canonical_analysis']['execution_action']['value']=='NO_NEW_BUY'


@pytest.mark.parametrize('work',[4,5])
@pytest.mark.parametrize('mutation',['owner','required_field'])
def test_adapter_owner_and_required_fields(work,mutation):
    adapter=load_c_module(ROOT,work)
    req=request(work)
    if mutation=='owner':
        req['c7_funding_context']['contexts'][2]['executable_budget']['equity' if work==4 else 'bond']['source_account']='OTHER'
    else:
        req.pop('c7_funding_context')
    build=adapter.build_v82_runtime_input if work==4 else adapter.build_v75_runtime_input
    expected = 'CROSS_OWNER_FUNDING' if mutation=='owner' else ('C8C9.W4.SHAPE' if work==4 else 'INPUT_SCHEMA')
    with pytest.raises(Exception,match=expected):build(req)

from copy import deepcopy
import pytest
from family_input import digest
from family_runner import FamilyRunner
from family_boundary import BoundaryError
from target_source_bridge import bind_target_source
from test_family_runner import runner_case
from test_native_adapters import ROOT
from test_stock_source_bridge import refresh


def test_historical_money_and_weight_are_preserved_separately():
    req, _ = runner_case(); before = deepcopy(req)
    result = bind_target_source(req)
    assert result['stock_target_amount']['amount'] == '1000.0'
    assert next(x for x in result['source_target_lines'] if x['instrument_id']=='QQQ')['weight']['value'] == .05
    assert req == before
    result['source_target_lines'].clear()
    assert req == before


@pytest.mark.parametrize('kind,code',[
    ('empty','TARGET_LINES_REQUIRED'),('duplicate','TARGET_INSTRUMENT_AMBIGUOUS'),
    ('coverage','TARGET_FRAMEWORK_COVERAGE_MISMATCH'),('weight','TARGET_C7_WEIGHT_MISMATCH'),
    ('unknown','TARGET_WEIGHT_UNAVAILABLE'),('range','TARGET_WEIGHT_RANGE'),
    ('currency','TARGET_FX_SOURCE_REQUIRED'),('money','TARGET_V82_AMOUNT_MISMATCH'),
    ('bond_copy','TARGET_V82_AMOUNT_MISMATCH'),('pointer','TARGET_STOCK_POINTER_MISMATCH'),
    ('nan','TARGET_NUMBER_INVALID'),('boolean','TARGET_NUMBER_INVALID')])
def test_invalid_semantics_blocks_even_with_reviewed_digests(kind,code,monkeypatch):
    req,ctx=runner_case();draft=req['confirmed_target']['payload']['draft'];lines=draft['target_lines']
    stock=next(row for row in lines if row['instrument_id']=='QQQ')
    if kind=='empty':lines.clear()
    elif kind=='duplicate':lines.append(deepcopy(stock))
    elif kind=='coverage':lines.pop()
    elif kind=='weight':stock['weight']['value']=.06
    elif kind=='unknown':stock['weight']['value_state']='UNKNOWN'
    elif kind=='range':stock['weight']['value']=2
    elif kind=='currency':stock['target_amount']['currency']='TWD'
    elif kind=='money':stock['target_amount']['amount']='50'
    elif kind=='nan':stock['target_amount']['amount']='NaN'
    elif kind=='boolean':stock['target_amount']['amount']=True
    elif kind=='pointer':req['native_bundle']['stock_request']['asset_context']['project_target_pointer']='/instrument_targets/BOND/project_target_position'
    else:req['native_bundle']['bond_request']['work3_handoff']['final_target']['payload']['instrument_targets']['QQQ']['project_target_position']=999
    # Synthetic re-signing only: prove a trusted digest cannot hide semantic drift.
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    req['confirmed_target']['target_hash']=req['confirmed_target']['payload']['target_hash']=ctx['target_hash']=draft['draft_hash']
    from family_boundary import prepare_input
    ctx['native_binding']['target_binding_digest']=prepare_input(req,trusted_context=ctx).payload['target_binding']['binding_digest']
    refresh(req,ctx)
    calls=[];monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['issue_codes'][0]['code']==code
    assert calls==[] and result['canonical_result'] is None and result['mentor'] is None


def test_c7_protected_integrated_weight_is_not_overwritten():
    req,_=runner_case();rows=req['native_bundle']['asset_framework']['integrated_asset_framework']['instrument_targets']
    row=next(x for x in rows if x['instrument_id']=='QQQ')
    row.update(protected=True,integrated_weight=.03)
    before=deepcopy(req)
    bind_target_source(req)
    assert req==before

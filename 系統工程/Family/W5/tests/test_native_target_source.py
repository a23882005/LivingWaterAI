from copy import deepcopy
from decimal import Decimal
import pytest
from family_input import digest
from family_boundary import BoundaryError,prepare_input
from family_runner import FamilyRunner
from native_target_source import produce,bind
from test_family_runner import runner_case
from test_stock_source_bridge import refresh
from test_native_adapters import ROOT


def case():
    req,ctx=runner_case();draft=req['confirmed_target']['payload']['draft']
    req['client_snapshot']['payload']['source_sha256']='a'*64
    for line in draft['target_lines']:
        if line['instrument_id']=='QQQ':line.update(instrument_id='OPAQUE_APPROVAL_QQQ',ticker='QQQ')
        line['target_amount']['amount']=str(Decimal(line['target_amount']['amount'])*32)
        line['target_amount']['currency']='TWD'
    draft['draft_hash']=digest({k:v for k,v in draft.items() if k!='draft_hash'})
    req['confirmed_target']['target_hash']=req['confirmed_target']['payload']['target_hash']=ctx['target_hash']=draft['draft_hash']
    fx={'base_currency':'USD','quote_currency':'TWD','quote_per_base':'32',
        'as_of':req['evaluation_at'][:10],'source_url':'https://source.example/SYNTHETIC_FX'}
    source=produce(req,fx);framework=req['native_bundle']['asset_framework']
    for rows in (framework['integrated_asset_framework']['instrument_targets'],framework['drift_snapshot']['items']):
        for row in rows:
            if row['instrument_id']!='QQQ':row['instrument_id']=source['source_to_native'][row['instrument_id']]
    ctx['native_target_source']=source;req['native_target_source_digest']=digest(source)
    refresh(req,ctx)
    ctx['native_binding']['target_binding_digest']=prepare_input(req,trusted_context=ctx).payload['target_binding']['binding_digest']
    refresh(req,ctx)
    return req,ctx,source


def test_native_family_boundary_consumes_opaque_targets_and_exact_fx_without_resigning():
    req,ctx,source=case();before=deepcopy((req,ctx))
    prepared,_=FamilyRunner(ROOT,context_provider=lambda:ctx)._validate(req)
    projected=prepared.payload['family_sources']['target']
    assert projected['stock_target_amount']['amount']=='1000.00'
    assert projected['original_stock_target_amount']['amount']=='32000.00'
    assert source['source_to_native']['OPAQUE_APPROVAL_QQQ']=='QQQ'
    bonds=prepared.payload['family_sources']['bond_targets']['items']
    assert bonds['SGOV']['target_line']['target_amount']['currency']=='TWD'
    assert bonds['SGOV']['native_target']['target_amount']['currency']=='USD'
    assert bonds['SGOV']['native_target_instrument_id']=='SGOV'
    assert (req,ctx)==before


def test_no_absent_holding_defaults_and_sgov_roles_stay_distinct():
    req,ctx,source=case();draft=req['confirmed_target']['payload']['draft']
    template=deepcopy(draft['target_lines'][0])
    for name in ('SGOV_BOND','SGOV_DRY'):
        row=deepcopy(template);row.update(instrument_id=name,ticker='SGOV');draft['target_lines'].append(row)
    out=produce(req,source['fx_observation'])
    assert out['source_to_native']['SGOV_BOND']=='SGOV_BOND'
    assert out['source_to_native']['SGOV_DRY']=='SGOV_DRY'
    assert 'ABSENT_ASSET' not in out['targets']


@pytest.mark.parametrize('kind',['amount','owner','db','run'])
def test_rehashed_projection_cannot_change_bound_approval_or_member(kind):
    req,ctx,source=case()
    if kind=='amount':source['targets']['QQQ']['target_amount']['amount']='999'
    elif kind=='owner':source['owner']['account']='OTHER'
    elif kind=='db':source['source_db_sha256']='b'*64
    else:source['run_id']='OTHER'
    source['digest']=digest({k:v for k,v in source.items() if k!='digest'})
    req['native_target_source_digest']=digest(source)
    with pytest.raises(BoundaryError,match='REPLAY_MISMATCH'):bind(req,ctx)


def test_missing_or_future_fx_cannot_become_native_money():
    req,ctx,source=case();missing=produce(req,None)
    assert missing['targets']['QQQ']['target_amount']['value_state']=='UNKNOWN'
    fx=deepcopy(source['fx_observation']);fx['as_of']='2099-01-01'
    with pytest.raises(BoundaryError,match='FUTURE_SOURCE'):produce(req,fx)


def test_native_amount_mismatch_still_stops_before_pipeline(monkeypatch):
    req,ctx,source=case()
    req['native_bundle']['stock_request']['work3_handoff']['final_target']['payload']['instrument_targets']['QQQ']['project_target_position']='999'
    refresh(req,ctx);calls=[]
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['status']=='BLOCKED'
    assert out['issue_codes'][0]['code']=='TARGET_V82_AMOUNT_MISMATCH'
    assert calls==[]

from copy import deepcopy
from decimal import Decimal
import json
import pytest
from family_input import digest
from c7_engine import run_c7_engine
from native_pipeline import run_native_pipeline
from stock_engine import run_stock_engine,assemble_stock_output
from mentor_bridge import explain_native
from test_c7_engine import original_case
from test_native_pipeline import pipeline_case
from test_native_adapters import ROOT


def bound_case():
    # Explicit synthetic source variant: preserve the original frozen files.
    # $1,000 NAV; QQQ $100; bond target SGOV $140 + SPSB $60 (native 70/30).
    # Current SGOV bond-role/physical $40, QQQ $100, residual CORE $860.
    b=pipeline_case();source,_=original_case()
    final=source['work6_result']['final_target']['snapshot']
    sgov=next(r for r in final['positions'] if r['instrument_id']=='SGOV')
    spsb=deepcopy(sgov);spsb.update(instrument_id='SPSB',ticker='SPSB',display_name='Synthetic SPSB')
    sgov['weight']['value']=0.14;sgov['portfolio_amount']['amount']=140
    spsb['weight']['value']=0.06;spsb['portfolio_amount']['amount']=60;final['positions'].append(spsb)
    engine=source['work6_result']['final_target_engine_result']
    engine['allocations']['final_target']['snapshot']=deepcopy(final)
    current=engine['allocations']['current_allocation']['snapshot']
    for row in current['positions']:
        if row['instrument_id']=='SGOV':row['weight']['value']=0.04;row['portfolio_amount']['amount']=40
        if row['instrument_id']=='CORE.US':row['weight']['value']=0.86;row['portfolio_amount']['amount']=860
    drift=source['work6_result']['drift_snapshot']['items']
    extra=deepcopy(next(r for r in drift if r['instrument_id']=='SGOV'));extra['instrument_id']='SPSB';drift.append(extra)
    for row in drift:
        cw,tw={'QQQ':(0.1,0.1),'CORE.US':(0.86,0.7),'SGOV':(0.04,0.14),'SPSB':(0,0.06)}[row['instrument_id']]
        row['current_weight']['value']=cw;row['final_target_weight']['value']=tw
        row['drift']['value']=float(Decimal(str(tw))-Decimal(str(cw)))
        row['client_facing_action']='HOLD' if cw==tw else ('INCREASE_TARGET_WEIGHT' if tw>cw else 'DECREASE_TARGET_WEIGHT')
    b=json.loads(json.dumps(b).replace('client-w5','qa-client').replace('w5-run-001','qa-run-3').replace('C-W6-FINAL-W5-001','C-W6-FINAL-QA-003'))
    source['evaluated_at']=b['stock_evidence']['evaluated_at']
    b['asset_framework']=run_c7_engine(ROOT,source)['result']
    for branch in ('stock_request','bond_request'):
        req=b[branch];w=req['work3_handoff']
        w['final_target']['payload']['instrument_targets']['QQQ']['project_target_position']=100
        w['final_target']['payload']['instrument_targets']['BOND']['project_target_position']=200
        w['funding_context']['remaining_target_gap']['v75']['payload']['remaining_target_gap_amount']['amount']='160.00'
        w['funding_context']['sgov_boundary']['sgov_dry_powder_bucket_amount']['amount']='0'
        req['c7_funding_context']=deepcopy(source['funding_context'])
        for bind in w['engine_bindings'].values():bind['shared_context_digest_sha256']=digest(w['shared_decision_context'])
    b['stock_request']['asset_context']['confirmed_position_snapshot']['quantity']=10
    bond=b['bond_request']['v75_source_context'];bond['strategic_bond_weight_b0']['value']='20'
    bond['target_bond_holdings'][0]['target_amount']['amount']='140.00'
    bond['target_bond_holdings'][1]['target_amount']['amount']='60.00'
    bond['sgov_dry_powder_bucket_amount']['value']['amount']='0'
    b['physical_sgov']['physical_market_value']='40'
    return b,source


def test_actual_c7_stock_bond_work9_and_mentor_complete():
    bundle,source=bound_case();before=deepcopy((bundle,source))
    result=run_native_pipeline(ROOT,bundle,c7_source=source)
    assert result['status']=='NATIVE_PIPELINE_COMPLETE'
    projection=result['target_unit_projection']
    assert Decimal(projection['native_target_amount'])==100
    assert Decimal(projection['native_confirmed_amount'])==100
    assert projection['canonical_target_weight']==pytest.approx(0.1)
    assert result['funding_aggregate']['equity_used']=='0'
    assert Decimal(result['funding_aggregate']['bond_used'])==160
    assert result['call_trace'][0]=='C.Work7.run_asset_framework_integration'
    u=result['unified_result']
    explained=explain_native(ROOT,result['work9_request'],u,trusted_context={
        'client_id':'qa-client','run_id':'qa-run-3','owner':u['owner'],'currency':u['currency'],
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE',
        'runtime_mode':'REAL_DETERMINISTIC','data_provenance':'SYNTHETIC',
        'expected_result_digest':digest(u)})
    assert explained and result['trade_action']=='NO_TRADE'
    assert (bundle,source)==before
    assert run_native_pipeline(ROOT,bundle,c7_source=source)==result


@pytest.mark.parametrize('kind,code',[
    ('money','NATIVE_AMOUNT_MISMATCH'),('current','CURRENT_AMOUNT_MISMATCH'),
    ('currency','FX_REQUIRED'),('weight','AMOUNT_WEIGHT_MISMATCH'),
    ('denominator','RANGE'),('unknown','SOURCE_UNKNOWN')])
def test_money_weight_mapping_requires_consistent_explicit_source(kind,code):
    b,s=bound_case();computed=run_c7_engine(ROOT,s)
    calculation=run_stock_engine(ROOT,b['stock_request'],b['stock_evidence'],b['producer_contract'])
    source=computed['original_source'];snapshot=source['work6_result']['final_target']['snapshot']
    row=next(r for r in snapshot['positions'] if r['instrument_id']=='QQQ')
    if kind=='money':
        row['portfolio_amount']['amount']=200;row['weight']['value']=0.2
        next(r for r in computed['result']['integrated_asset_framework']['instrument_targets'] if r['instrument_id']=='QQQ')['integrated_weight']=0.2
    elif kind=='current':
        source['work6_result']['final_target_engine_result']['allocations']['current_allocation']['snapshot']['positions'][0]['portfolio_amount']['amount']=99
    elif kind=='currency':row['portfolio_amount']['currency']='TWD'
    elif kind=='weight':row['weight']['value']=0.3
    elif kind=='denominator':snapshot['denominator']['amount']=0
    else:row['portfolio_amount']['value_state']='UNKNOWN'
    computed['source_digest']=digest(source)
    with pytest.raises(ValueError,match='TARGET_UNIT_'+code):
        assemble_stock_output(ROOT,calculation,b['stock_source_fields'],computed)


def test_native_bond_invalid_input_does_not_publish_unified_result():
    b,s=bound_case();context=b['bond_request']['v75_source_context']
    context['authorized_universe']=['SGOV']
    context['target_bond_holdings']=context['target_bond_holdings'][:1]
    context['existing_bond_holdings']=context['existing_bond_holdings'][:1]
    b['bond_evidence']={'SGOV':b['bond_evidence']['SGOV']}
    result=run_native_pipeline(ROOT,b,c7_source=s)
    assert result['status']=='INVALID_INPUT'
    assert result['unified_result'] is None
    assert 'US_GENERIC_CORE_TARGET_RATIO_MISMATCH' in result['bond_result']['runtime_ready']['output']['reason_codes']


def test_native_hard_wait_reaches_original_work9_and_mentor_without_cutover():
    b,s=bound_case()
    for item in b['bond_evidence'].values():
        item['metrics']['PRED-004']['hy_oas_bps']='900'
    before=deepcopy((b,s))
    result=run_native_pipeline(ROOT,b,c7_source=s)
    assert result['status']=='NATIVE_PIPELINE_COMPLETE'
    assert result['read_only_native_wait_review'] is True
    assert result['formal_deployment_ready'] is False
    ready=result['bond_runtime_readiness']
    assert ready['runtime_ready'] is False and ready['cutover_state']=='BLOCKED'
    assert set(ready['blocking_reason_codes'])=={
        'WORK6_UPSTREAM_GATE_NOT_PASS','WORK6_BLOCKING_CLASSIFICATION:HARD_WAIT'}
    decisions={d['asset_id']:d for d in ready['output']['per_asset_decisions']}
    assert decisions['SPSB']['new_money_action']=='WAIT'
    assert Decimal(decisions['SPSB']['deploy_amount']['amount'])==0
    assert decisions['SGOV']['deployment_state']!='HARD_WAIT'
    assert result['funding_aggregate']['equity_used']=='0'
    assert Decimal(result['funding_aggregate']['bond_used'])==100
    # The remaining $250 is a native undeployed contribution, not a $250 SGOV
    # buy or an addition to today's existing $40 defensive SGOV holding.
    assert Decimal(ready['output']['v75_undeployed_to_sgov']['amount'])==250
    assert result['sgov_reconciliation']['contribution_applied_to_holdings'] is False
    u=result['unified_result']
    explained=explain_native(ROOT,result['work9_request'],u,trusted_context={
        'client_id':'qa-client','run_id':'qa-run-3','owner':u['owner'],'currency':u['currency'],
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE',
        'runtime_mode':'REAL_DETERMINISTIC','data_provenance':'SYNTHETIC',
        'expected_result_digest':digest(u)})
    assert explained and 'C8C9.Work9.build_unified_deployment' in result['call_trace']
    assert result['production']=='HOLD' and result['trade_action']=='NO_TRADE'
    assert (b,s)==before


def test_missing_predicate_does_not_become_a_native_wait_or_fund_sgov():
    b,s=bound_case();b['bond_evidence']['SPSB']['metrics']['PRED-008']={}
    result=run_native_pipeline(ROOT,b,c7_source=s)
    assert result['status']=='INSUFFICIENT_DATA' and result['unified_result'] is None
    bond=result['bond_result']
    assert bond['canonical'] is None
    assert bond['independent_asset_evaluations']['undeployed_amount'] is None
    assert bond['independent_asset_evaluations']['incomplete_assets']==['SPSB']
    assert result['stock_result']


def test_native_wait_review_never_ignores_additional_cutover_blockers():
    from bond_engine import run_bond_engine
    from native_pipeline import _native_wait_review
    b,_=bound_case()
    for item in b['bond_evidence'].values():item['metrics']['PRED-004']['hy_oas_bps']='900'
    bond=run_bond_engine(ROOT,b['bond_request'],b['bond_evidence'])
    assert _native_wait_review(bond)
    bond['runtime_ready']['blocking_reason_codes'].append('WORK6_RULE_VERSION_MISMATCH')
    assert not _native_wait_review(bond)

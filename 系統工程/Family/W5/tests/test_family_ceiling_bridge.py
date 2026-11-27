"""Synthetic source-bound C7 -> native MIN and original portfolio allocator."""
from copy import deepcopy
from decimal import Decimal
import pytest
from test_native_adapters import ROOT
from test_c7_family_ceiling import family_case
from test_c7_engine import original_case
from test_v10_stock_integration import adopted_case,bind_context
from family_input import digest
from c7_engine import load_original_configuration_module,run_c7_engine
from family_ceiling_bridge import allocate,CeilingBindingError
from stock_engine import run_stock_engine


def test_canonical_float_view_does_not_change_native_exact_gap_money():
    from target_units import same_canonical_money
    exact=Decimal('837000')/Decimal('32.452')
    assert same_canonical_money(float(exact),exact)
    assert not same_canonical_money(float(exact)+.01,exact)
    assert not same_canonical_money(str(float(exact)),exact)  # No approximate string source.
    assert not same_canonical_money(True,1) and not same_canonical_money(float('nan'),exact)


def test_sqlite_planning_projection_does_not_apply_one_release_twice():
    from family_ceiling_bridge import planning_exposures
    m,ci,scope,at=family_case()
    buy=next(r for r in scope['exposures'] if r['kind']=='ACTIVE_BUY_RESERVATION')
    release={**deepcopy(buy),'event_id':'SYNTHETIC_RELEASE_ACK_ONE','kind':'RELEASE','amount':'5',
        'economic_effect_ids':['SYNTHETIC_ONE_CANCEL_EFFECT'],'release_confirmed':True,
        'releases_event_id':buy['event_id'],'release_state':'CANCELLED'}
    scope['exposures'] += [release,{**deepcopy(release),'event_id':'SYNTHETIC_RELEASE_ACK_TWO'}]
    cap=m.capacity(scope,ci,at)
    result=planning_exposures(scope,cap)
    assert next(r for r in result if r['event_id']==buy['event_id'])['amount']=='5'
    assert cap['confirmed_release_deducted']=='5'


def allocation_binding():
    m,ci,scope,at=family_case()
    return m,{'scope':scope,'canonical_input':ci,'input_scope_digest':m.digest(scope),
        'evaluation_at':at,'amount':Decimal(25),'currency':'TWD','capacity':m.capacity(scope,ci,at)}


def portfolio_case():
    m,b=allocation_binding();s=b['scope'];o=s['family_owner'];other={**o,'account':'SECOND_REAL_SYNTHETIC_ACCOUNT'}
    s['account_owners'].append(other)
    cash=deepcopy(s['funding_buckets'][0]);cash.update(owner=other,bucket_id='SECOND_CASH',cash_amount='20')
    s['funding_buckets'].append(cash);b['capacity']=m.capacity(s,b['canonical_input'],b['evaluation_at']);b['input_scope_digest']=m.digest(s)
    group={'schema_version':'V82.FamilyPortfolioSliceAllocation.v1','profile':m.PROFILE,
        'identity':s['identity'],'budget_currency':'TWD','input_scope_digest':b['input_scope_digest'],
        'complete_universe':True,'receipt':deepcopy(s['approval_receipt']),'pool_id':'SYNTHETIC_ONE_GLOBAL_STOCK_POOL',
        'slices':[], 'buckets':[]}
    for owner,asset,unit,bid,value in [(o,'SAME_SYMBOL','FIRST:SAME_SYMBOL','SYNTHETIC_CASH','75'),(other,'SAME_SYMBOL','SECOND:SAME_SYMBOL','SECOND_CASH','25')]:
        group['slices'].append({'owner':owner,'asset_id':asset,'unit_id':unit,'bucket_id':bid,'currency':'TWD',
            'slice':value,'fx_to_bucket':'1','fx_bucket_to_budget':'1'})
    for cash in s['funding_buckets']:
        group['buckets'].append({'owner':cash['owner'],'bucket_id':cash['bucket_id'],'currency':'TWD',
            'available_authorized_notional_cash':cash['cash_amount'],'funding_source_ids':[cash['bucket_id']]})
    return b,group


def test_cross_account_identical_symbols_share_one_capacity_and_keep_own_cash():
    b,g=portfolio_case();before=deepcopy((b,g));out=allocate(ROOT,b,g,asset_id='SAME_SYMBOL',daily_cap='75')
    assert sum(map(Decimal,out['allocations'].values()))<=25
    assert set(out['allocations'])=={'FIRST:SAME_SYMBOL','SECOND:SAME_SYMBOL'}
    assert Decimal(out['allocations']['FIRST:SAME_SYMBOL'])<=50 and Decimal(out['allocations']['SECOND:SAME_SYMBOL'])<=20
    assert out['selected_unit_id']=='FIRST:SAME_SYMBOL' and (b,g)==before


def test_unknown_competing_account_slice_stays_unknown_without_reallocating_it():
    b,g=portfolio_case();g['slices'][1]['slice']=None
    out=allocate(ROOT,b,g,asset_id='SAME_SYMBOL',daily_cap='75')
    assert all(v is None for v in out['allocations'].values())
    b['amount']=Decimal(0);assert set(allocate(ROOT,b,g,asset_id='SAME_SYMBOL',daily_cap='75')['allocations'].values())=={'0'}


@pytest.mark.parametrize('change',['cash','owner','duplicate','scope','time','fx'])
def test_portfolio_allocation_rejects_source_substitution(change):
    b,g=portfolio_case()
    if change=='cash':g['buckets'][0]['available_authorized_notional_cash']='100000'
    elif change=='owner':g['slices'][1]['owner']={**g['slices'][1]['owner'],'client_id':'FOREIGN'}
    elif change=='duplicate':g['slices'][1]['unit_id']=g['slices'][0]['unit_id']
    elif change=='scope':g['input_scope_digest']='0'*64
    elif change=='time':g['receipt']['available_at']='2099-01-01T00:00:00Z'
    else:g['slices'][1]['fx_bucket_to_budget']='2'
    with pytest.raises(ValueError):allocate(ROOT,b,g,asset_id='SAME_SYMBOL',daily_cap='75')


def stock_bound_case(monkeypatch):
    """Labelled construction: original Work5 output mocked, real V82 math."""
    req,facts,contract=adopted_case();m,ci,s,at=family_case();old,_=original_case()
    at=facts['evaluated_at'];owner=facts['approved_v10_context']['identity']['owner']
    ci['identity']['run_id']=req['run_id'];ci['identity']['client_id']=owner['client_id']
    ci['v70_asset_framework']['run_id']=req['run_id']
    ci['v70_asset_framework']['upstream_v70_snapshot_id']=req['work3_handoff']['v70_runtime_context']['upstream_v70_snapshot_id']
    ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='USD')
    current=deepcopy(old['work6_result']['final_target_engine_result']['allocations']['current_allocation']['snapshot'])
    ci['allocations']['current_allocation']['snapshot']=current
    for row in current['positions']:
        if row['instrument_id']=='QQQ':row['weight']['value']=0;row['portfolio_amount']['amount']=0
        if row['instrument_id']=='CORE.US':row['weight']['value']=.06;row['portfolio_amount']['amount']=60
    cashrow=deepcopy(current['positions'][-1]);cashrow.update(instrument_id='SYNTHETIC_CASH_HOLDING',ticker=None,asset_type='cash')
    cashrow['weight']['value']=.9;cashrow['portfolio_amount']['amount']=900;current['positions'].append(cashrow)
    s.update(identity=deepcopy(ci['identity']),family_owner=owner,account_owners=[owner],budget_currency='USD',current_nav=deepcopy(current['denominator']))
    approved=s['approved_long_term_target'];approved['denominator'].update(currency='USD',amount=10000)
    for row in approved['positions']:
        row['portfolio_amount']['currency']='USD';row['portfolio_amount']['amount']*=10
    req['work3_handoff']['final_target']['allocation_id']=approved['allocation_id']
    req['work3_handoff']['final_target']['authorization_reference']=approved['allocation_id']
    for entry in req['work3_handoff']['engine_bindings'].values():
        if 'authorization_reference' in entry:entry['authorization_reference']=approved['allocation_id']
    req['work3_handoff']['final_target']['confirmation_proof'].update(confirmed_at=approved['confirmed_at'],confirmed_by=approved['confirmed_by'])
    s['approved_target_digest']=m.digest(approved)
    s['total_stock_ceiling'].update(currency='USD',receipt={**s['approval_receipt'],'as_of':at,'available_at':at})
    s['total_stock_ceiling']['accounting_base']['currency']='USD'
    for row in s['exposures']:row.update(owner=owner,currency='USD',asset_id='CORE.US')
    for row in s['funding_buckets']:row.update(owner=owner,currency='USD',cash_amount='800',reserved_amount='100')
    s['exposures'][0]['amount']='60'
    group=facts['approved_v10_context']['shared_allocation_request'];group['remaining_tactical_room']='25'
    group['buckets'][0].update(bucket_id='SYNTHETIC_CASH',available_authorized_notional_cash='50')
    group['slices'][0]['bucket_id']='SYNTHETIC_CASH'
    req['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']='100'
    w6=load_original_configuration_module(ROOT,'work6.family_long_term_read')
    def original_engine(canonical,**kwargs):
        out=deepcopy(old['work6_result']['final_target_engine_result']);out['allocations']=deepcopy(canonical['allocations'])
        out['formal_output_eligibility']['eligible']=True;return out
    monkeypatch.setattr(w6,'run_configuration_engine',original_engine)
    from test_c7_family_ceiling import read_case
    # Reuse the request shape only; no source or household identity is borrowed.
    _,_,_,_,adjustment,_,_=read_case(monkeypatch)
    base=ROOT/'系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/contracts_c7'
    result=w6.run_existing_long_term(ci,family_scope=s,adjustment_request=adjustment,benchmark_path='SYNTHETIC',binding_path='SYNTHETIC',
        input_schema_path=base/'05_C_Canonical_Input.schema.json',output_schema_path=base/'06_C_Canonical_Output.schema.json',
        work6_request_schema_path=base/'56_C_Work6_Adjustment_Request.schema.json',work6_output_schema_path=base/'84_Family_Existing_LongTerm_Work6_Result.schema.json',evaluated_at=at)
    source={'schema_version':'Family.W5.C7Source.v2','canonical_input':ci,'work6_result':result,
        'funding_context':{**old['funding_context'],'run_id':req['run_id']},'evaluated_at':at,'family_scope':s}
    computed=run_c7_engine(ROOT,source)
    bind_context(facts,contract)
    return req,facts,contract,computed


def test_real_stock_min_consumes_incremental_25_instead_of_gross_100(monkeypatch):
    req,facts,contract,c7=stock_bound_case(monkeypatch);before=deepcopy((req,facts,contract,c7))
    out=run_stock_engine(ROOT,req,facts,contract,c7_computation=c7)
    assert out['position_gap'].positive_deployment_gap==950
    assert Decimal(out['daily_slice']['cap'])==Decimal('237.5') and out['execution'].maximum_allowed_buy_amount==25
    assert out['execution'].execution_amount==20 and out['execution'].execution_quantity==2
    assert req['work3_handoff']['v70_runtime_context']['payload']['stock_tactical_amount']=='100'
    assert out['family_ceiling_binding']['pm_gate_released'] is False
    assert (req,facts,contract,c7)==before


def test_long_term_money_and_effective_weight_reach_original_work8_without_gate_release(monkeypatch):
    from stock_engine import assemble_stock_output
    from test_stock_engine import source_fields
    from runtime_loader import load_c_module
    req,facts,contract,c7=stock_bound_case(monkeypatch)
    out=run_stock_engine(ROOT,req,facts,contract,c7_computation=c7)
    wire=assemble_stock_output(ROOT,out,source_fields(),c7)
    assert len(wire['canonical_v82_output']['canonical_analysis'])==49
    assert len(wire['canonical_v82_output']['fields_1_to_13'])==13
    from target_units import project_target_units
    projected=project_target_units(out,c7)
    assert Decimal(projected['native_target_amount'])==1000
    assert Decimal(projected['denominator']['amount'])==10000
    assert Decimal(projected['effective_weight_base']['amount'])==1000
    w8=load_c_module(ROOT,8)
    result=w8.protect_client_action({'contract_name':w8.INPUT_CONTRACT_NAME,'contract_version':w8.INPUT_CONTRACT_VERSION,
        'baseline_id':w8.BASELINE_ID,'run_id':req['run_id'],'c_work7_asset_framework_result':c7['result'],
        'work4_v82_integration_result':wire})
    assert result and c7['result']['pm_gate']['work8_released'] is False
    changed=deepcopy(c7['result']);changed['family_scope_evidence']['occupancy_and_capacity']['incremental_capacity']='100'
    with pytest.raises(ValueError,match='CAPACITY_REPLAY_MISMATCH'):
        w8.protect_client_action({'contract_name':w8.INPUT_CONTRACT_NAME,'contract_version':w8.INPUT_CONTRACT_VERSION,
            'baseline_id':w8.BASELINE_ID,'run_id':req['run_id'],'c_work7_asset_framework_result':changed,
            'work4_v82_integration_result':wire})


def test_new_profile_atomic_plan_replay_and_stale_competing_plan_cannot_reuse_capacity(monkeypatch,tmp_path):
    from v82_slice_bridge import commit_local_plan
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore,open_cycle
    req,facts,contract,c7=stock_bound_case(monkeypatch)
    calculation=run_stock_engine(ROOT,req,facts,contract,c7_computation=c7)
    source=deepcopy(facts['approved_v10_context']);cycle=source['cycle_snapshot']['cycle']
    path=tmp_path/'SYNTHETIC_PORTFOLIO_LEDGER.sqlite3';store=CycleLedgerStore(path,create=True)
    source['cycle_snapshot'].update(status='PROPOSED',ledger_path=str(path))
    source['planning_ledger_source']={'planning_write_authorized':True,'owner':source['identity']['owner'],
        'local_path':str(path),'source_reference':'SYNTHETIC_AUTHORIZED_LOCAL_PLANNING_ONLY'}
    source['portfolio_cycle_baseline']={'complete':True,'cycles':[],'cycles_digest':digest([]),
        'input_scope_digest':calculation['family_ceiling_binding']['input_scope_digest']}
    receipt=commit_local_plan(source,calculation,request_digest='SYNTHETIC_REQUEST_ONE')
    saved=store.get(cycle['slice_cycle_id'])
    assert receipt['new_commitment']=='20' and receipt['broker_cash_reserved'] is False
    assert saved['G0']==cycle['G0'] and saved['B0']==cycle['B0']
    replay=commit_local_plan(source,calculation,request_digest='SYNTHETIC_REQUEST_ONE')
    assert replay['already_committed'] and replay['new_commitment']=='0'
    competing=deepcopy(source);competing['identity']['asset_id']='CORE.US'
    competing['cycle_snapshot']['cycle']=open_cycle(owner=competing['identity']['owner'],session_id=source['session']['session_id'],
        exchange=source['session']['exchange'],asset_id='CORE.US',opened_at=source['identity']['evaluation_at'],
        gap='950',speed_result=calculation['approved_v10_analysis']['speed'],permission=True,exposure_reconciled=True,session_open=True)
    competing['shared_allocation_request']['slices'][0]['asset_id']='CORE.US'
    with pytest.raises(CeilingBindingError,match='LEDGER_CHANGED_REBUILD_REQUIRED'):
        commit_local_plan(competing,calculation,request_digest='SYNTHETIC_COMPETITOR')
    assert store.get(competing['cycle_snapshot']['cycle']['slice_cycle_id']) is None
    # Merely copying the updated ledger into a new baseline is insufficient:
    # its existing intent must also appear in the new C7 occupancy calculation.
    competing['portfolio_cycle_baseline'].update(cycles=[saved],cycles_digest=digest([saved]))
    with pytest.raises(CeilingBindingError,match='EXPOSURE_RECONCILIATION_REQUIRED'):
        commit_local_plan(competing,calculation,request_digest='SYNTHETIC_COMPETITOR')

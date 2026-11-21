"""Native dual-price invariants; every input and fee reserve is synthetic."""
from copy import deepcopy
from decimal import Decimal as D,localcontext
import sys
import pytest
from test_native_adapters import ROOT
from test_stock_engine import stock_case,source_fields
from stock_engine import run_stock_engine,assemble_stock_output
sys.path.insert(0,str(ROOT/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'))
from livingwater_v82_runtime.deployment import calculate_position_gap,build_buy_execution_plan,ActiveOrderExposure
from livingwater_v82_runtime.enums import FundingDomain,CashBasis,HardGateState,OrderLifecycleState
from livingwater_v82_runtime.models import BoundEquityBudgetView
from livingwater_v82_runtime.core_rules import PermissionResult


def core_plan(**changes):
    gap=changes.pop('gap',None) or calculate_position_gap(project_target_position_amount='100',target_rate='.95',
        confirmed_position_qty='9.4',canonical_valuation_price='10')
    cash=D(str(changes.pop('cash','1000')))
    args=dict(gap=gap,permission=PermissionResult(HardGateState.NOT_TRIGGERED,True,()),
        bound_equity_budget=BoundEquityBudgetView(FundingDomain.US_BROKER,'SYNTHETIC','SYNTHETIC',cash,'USD',CashBasis.AVAILABLE,'SYNTHETIC',('SYNTHETIC',)),
        order_working_price='9.9',normalized_order_price='9.9',minimum_lot='.001',
        canonical_valuation_price='10',fee_reserve='0',execution_currency='USD',order_intent_id='SYNTHETIC_ORDER')
    args.update(changes);return gap,build_buy_execution_plan(**args)


@pytest.mark.parametrize('price,expected_qty,expected_cash,expected_post',[
    ('9.9','.100','.99','.95'),('10','.100','1','.95'),('10.1','.099','.9999','.9499')])
def test_pm_low_equal_high_price_quantity_and_estimated_completion(price,expected_qty,expected_cash,expected_post):
    gap,plan=core_plan(order_working_price=price,normalized_order_price=price)
    assert plan.execution_quantity==D(expected_qty) and plan.execution_amount==D(expected_cash)
    assert plan.projected_post_fill_completion_rate==D(expected_post)
    assert plan.execution_quantity*10<=gap.positive_deployment_gap
    assert gap.projected_position_amount+plan.execution_quantity*10<=gap.target_amount
    assert plan.residual_gap_amount==gap.positive_deployment_gap-plan.execution_quantity*10
    if price!='10.1':assert plan.residual_gap_amount==0 and not plan.residual_gap_amount.is_signed()


def test_legal_tick_can_allow_a_lot_discarded_by_the_unrounded_working_price():
    _,plan=core_plan(order_working_price='10.01',normalized_order_price='10',minimum_lot='.1')
    assert plan.execution_quantity==D('.1') and plan.execution_amount==1


@pytest.mark.parametrize('lot,qty',[('.001','.1'),('.01','.1'),('.1','.1'),('1','0')])
def test_fractional_and_whole_lot_floor_preserves_valuation_gap(lot,qty):
    gap,p=core_plan(minimum_lot=lot)
    assert p.execution_quantity==D(qty) and p.execution_quantity%D(lot)==0
    if p.action=='NO_NEW_BUY':assert p.residual_gap_amount==gap.positive_deployment_gap


@pytest.mark.parametrize('basis,expected_qty',[
    ('cash_total','.2'),('valuation','.1'),('order_notional','.2'),('shared_both','.1')])
def test_cap_producers_are_not_coerced_to_one_price_basis(basis,expected_qty):
    gap=calculate_position_gap(project_target_position_amount='100',target_rate='1',confirmed_position_qty='0',canonical_valuation_price='10')
    extra={'cash_total':{'required_cash_use_caps':['1']},'valuation':{'required_valuation_caps':['1']},
        'order_notional':{'required_known_caps':['1']},'shared_both':{'required_cash_use_caps':['1'],'required_valuation_caps':['1']}}[basis]
    _,p=core_plan(gap=gap,order_working_price='5',normalized_order_price='5',**extra)
    assert p.execution_quantity==D(expected_qty)


@pytest.mark.parametrize('cash,fee,caps,expected_qty',[
    ('1','.1',[],'.090'),('1','.1',['.8'],'.070'),('1','1',[],'0'),('1','1.1',[],'0')])
def test_cash_reserve_and_shared_cash_include_verified_fees_once(cash,fee,caps,expected_qty):
    _,p=core_plan(cash=cash,fee_reserve=fee,required_cash_use_caps=caps)
    assert p.execution_quantity==D(expected_qty)
    if p.execution_quantity>0:
        assert p.execution_amount+D(fee)<=min([D(cash),*map(D,caps)])


@pytest.mark.parametrize('rate,reserve',[('.01','.01'),('.05','.05')])
def test_source_adapter_percentage_fee_reserve_is_a_cash_bound_not_a_valuation_bound(rate,reserve):
    # The adapter supplied an explicit conservative reserve for at most $1
    # notional. V82 does not invent the rate or replace it with a zero fee.
    gap,p=core_plan(cash='1',fee_reserve=reserve)
    assert p.execution_amount+p.execution_amount*D(rate)<=1
    assert p.execution_amount+D(reserve)<=1 and p.execution_quantity*10<=gap.positive_deployment_gap


def test_source_adapter_tiered_minimum_fee_reserve_is_retained_after_lot_floor():
    # Synthetic adapter tariff: max(0.02, notional*0.01), known reserve 0.02.
    _,p=core_plan(cash='1',fee_reserve='.02')
    applicable=max(D('.02'),p.execution_amount*D('.01'))
    assert p.execution_amount+applicable<=1 and p.execution_quantity==D('.098')


@pytest.mark.parametrize('field,value,reason',[
    ('canonical_valuation_price',None,'VALUATION_PRICE'),('canonical_valuation_price','0','VALUATION_PRICE'),
    ('canonical_valuation_price','NaN','VALUATION_PRICE'),('fee_reserve',None,'FEE_RESERVE'),
    ('fee_reserve','-1','FEE_RESERVE'),('fee_reserve','NaN','FEE_RESERVE'),
    ('normalized_order_price',None,'NORMALIZED_LIMIT_PRICE'),('minimum_lot',None,'ORDER_PRICE_OR_LOT'),
    ('required_valuation_caps',[None],'REQUIRED_CAP'),('required_cash_use_caps',[None],'REQUIRED_CAP')])
def test_missing_or_invalid_price_fee_lot_and_cap_stay_unknown(field,value,reason):
    _,p=core_plan(**{field:value});assert p.action=='BLOCKED_UNKNOWN' and p.execution_quantity is None
    assert any(reason in r for r in p.reason_codes)


@pytest.mark.parametrize('kind',['cash','valuation','notional'])
def test_known_zero_cap_is_no_new_buy(kind):
    changes={'cash':{'cash':'0'},'valuation':{'required_valuation_caps':['0']},'notional':{'required_known_caps':['0']}}[kind]
    gap,p=core_plan(**changes);assert p.execution_quantity==0 and p.residual_gap_amount==gap.positive_deployment_gap


@pytest.mark.parametrize('state',['OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING','CANCELLED'])
def test_existing_buy_commitment_is_valued_at_valuation_price_until_confirmed_release(state):
    active=ActiveOrderExposure('SYNTHETIC_EXISTING','BUY',OrderLifecycleState(state),D('.2'),D('.1'))
    gap=calculate_position_gap(project_target_position_amount='100',target_rate='.95',confirmed_position_qty='9.3',canonical_valuation_price='10',active_orders=[active])
    _,p=core_plan(gap=gap)
    assert gap.active_buy_exposure_amount==(D(0) if state=='CANCELLED' else D(1))
    assert gap.projected_position_amount+p.execution_quantity*10<=95
    assert p.projected_post_fill_completion_rate==(gap.projected_position_amount+p.execution_quantity*10)/100


def test_high_precision_valuation_cap_does_not_round_up_a_fractional_lot():
    cap='0.999999999999999999999999999999999999999999999'
    with localcontext() as ctx:
        ctx.prec=12;_,p=core_plan(required_valuation_caps=[cap]);assert ctx.prec==12
    assert p.execution_quantity==D('.099')
    assert p.execution_quantity*10<=D(cap)


def test_fee_and_valuation_accounting_sidecar_keeps_source_precision_and_context():
    from livingwater_v82_runtime.deployment import execution_price_basis
    with localcontext() as ctx:
        ctx.prec=12;_,p=core_plan(fee_reserve='1e-50')
        basis=execution_price_basis(execution_plan=p,canonical_valuation_price='10',fee_reserve='1e-50')
        assert ctx.prec==12
    assert basis['required_cash_amount']==D('.99'+'0'*47+'1')
    assert basis['valuation_increment']==1


@pytest.mark.parametrize('new_target',['100','125'])
def test_same_session_target_change_and_replay_cannot_expand_initial_B0(tmp_path,new_target):
    from test_v10_daily_slice import new_cycle,rates,event,room
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore
    cycle=new_cycle(gap='25.25',speed_result=rates(mode='Right Confirmation'))
    cycle=event(cycle,state='PARTIAL_FILL',filled='.25',remaining='.5')
    before=deepcopy(cycle);store=CycleLedgerStore(tmp_path/'SYNTHETIC.sqlite',create=True);store.save(cycle,expected_revision=None)
    available=room(cycle,speed_result=rates(mode='Right Confirmation'))['cycle_room']
    gap=calculate_position_gap(project_target_position_amount=new_target,target_rate='.95',
        confirmed_position_qty='9.375',canonical_valuation_price='10',active_orders=[
            ActiveOrderExposure('SYNTHETIC_EXISTING','BUY',OrderLifecycleState.PARTIAL_FILL,D('.075'),D('.025'))])
    _,p=core_plan(gap=gap,required_known_caps=[available]);_,replay=core_plan(gap=gap,required_known_caps=[available])
    assert p==replay and p.execution_amount<=D(available)
    assert gap.projected_position_amount+p.execution_quantity*10<=gap.target_amount
    assert store.get(cycle['slice_cycle_id'])==before and cycle['G0']=='25.25' and D(cycle['B0'])==D('6.3125')


def test_shared_bucket_allocation_cannot_spend_two_fee_reserves_outside_its_cash():
    from livingwater_v82_runtime.slice_allocation import allocate
    from test_v10_daily_slice import OWNER
    group=allocate(owner=OWNER,pool_id='SYNTHETIC_SHARED',remaining_tactical_room='2',
        slices=[dict(owner=OWNER,asset_id=s,bucket_id='CASH',currency='USD',slice='2',fx_to_bucket='1',fx_bucket_to_budget='1') for s in ('A','B')],
        buckets=[dict(owner=OWNER,bucket_id='CASH',currency='USD',available_authorized_notional_cash='1',funding_source_ids=['ONE_CASH'])])
    plans=[]
    for allocation in group['allocations'].values():
        _,p=core_plan(fee_reserve='.1',required_valuation_caps=[allocation],required_cash_use_caps=[allocation]);plans.append(p)
        assert p.execution_quantity*10<=D(allocation) and p.execution_amount+D('.1')<=D(allocation)
    assert sum((p.execution_amount+D('.1') for p in plans),D(0))<=1


def family_case():
    req,facts,contract=stock_case();w3=req['work3_handoff']
    w3['final_target']['payload']['instrument_targets']['QQQ']['project_target_position']='100'
    req['asset_context']['confirmed_position_snapshot']['quantity']='9.4'
    facts.update(valuation_price='10',order_working_price='9.9',normalized_order_price='9.9',minimum_lot='.001')
    return req,facts,contract


def test_family_49_13_and_native_evidence_use_correct_completion_and_keep_cash_notional():
    req,facts,contract=family_case();before=deepcopy((req,facts,contract));out=run_stock_engine(ROOT,req,facts,contract)
    assert out['execution'].execution_quantity==D('.100') and out['execution'].execution_amount==D('.99')
    assert out['execution_basis']['valuation_increment']==1 and out['execution_basis']['required_cash_amount']==D('.99')
    wire=assemble_stock_output(ROOT,out,source_fields())['canonical_v82_output']
    assert len(wire['canonical_analysis'])==49 and len(wire['fields_1_to_13'])==13
    assert D(str(wire['canonical_analysis']['projected_post_fill_completion_rate']['value']))==D('.95')
    view={row['display_label']:row['value'] for row in wire['fields_1_to_13']}
    assert D(str(view['成交後完成率']))==D('.95') and D(str(view['執行金額']['amount']))==D('.99')
    assert (req,facts,contract)==before


def test_family_missing_fee_source_blocks_positive_buy_without_changing_gap():
    req,facts,contract=family_case();facts.pop('execution_costs');out=run_stock_engine(ROOT,req,facts,contract)
    assert out['execution'].action=='BLOCKED_UNKNOWN' and out['position_gap'].positive_deployment_gap==1


def test_family_fee_currency_mismatch_is_rejected():
    req,facts,contract=family_case();facts['execution_costs']['currency']='TWD'
    from stock_engine import StockEvidenceError
    with pytest.raises(StockEvidenceError,match='FEE_CURRENCY'):run_stock_engine(ROOT,req,facts,contract)


def fee_pipeline_case():
    from test_target_units import bound_case
    from c7_engine import run_c7_engine
    b,s=bound_case();b['stock_request']['asset_context']['confirmed_position_snapshot']['quantity']='9.4'
    f=b['stock_evidence'];f.update(order_working_price='9.9',normalized_order_price='9.9',minimum_lot='.001')
    f['execution_costs'].update(fee_reserve='.01')
    current=s['work6_result']['final_target_engine_result']['allocations']['current_allocation']['snapshot']
    for row in current['positions']:
        if row['instrument_id']=='QQQ':row['weight']['value']=.094;row['portfolio_amount']['amount']=94
        if row['instrument_id']=='CORE.US':row['weight']['value']=.866;row['portfolio_amount']['amount']=866
    for row in s['work6_result']['drift_snapshot']['items']:
        if row['instrument_id'] in ('QQQ','CORE.US'):
            cw={'QQQ':D('.094'),'CORE.US':D('.866')}[row['instrument_id']]
            row['current_weight']['value']=float(cw);row['drift']['value']=float(D(str(row['final_target_weight']['value']))-cw)
            row['client_facing_action']='INCREASE_TARGET_WEIGHT' if row['instrument_id']=='QQQ' else 'DECREASE_TARGET_WEIGHT'
    b['asset_framework']=run_c7_engine(ROOT,s)['result']
    return b,s


def test_original_work6_cash_claim_includes_fee_while_work9_and_mentor_keep_notional():
    from native_pipeline import run_native_pipeline
    from family_input import digest
    from mentor_bridge import explain_native
    b,s=fee_pipeline_case();before=deepcopy((b,s));out=run_native_pipeline(ROOT,b,c7_source=s)
    assert out['status']=='NATIVE_PIPELINE_COMPLETE' and D(out['funding_aggregate']['equity_used'])==1
    wire=out['stock_result']['canonical_v82_output'];fields=wire['canonical_analysis']
    assert D(str(fields['execution_amount']['value']['amount']))==D('.99')
    assert D(str(fields['execution_quantity']['value']))==D('.1')
    assert D(str(fields['projected_post_fill_completion_rate']['value']))==D('.95')
    u=out['unified_result'];item=next(v for v in u['canonical_deployment_result']['items'] if v['source_engine']=='V82')
    assert D(str(item['deployment_amount']['value']['amount']))==D('.99')
    assert item['source_snapshot_digest_sha256']==digest(wire)
    mentor=explain_native(ROOT,out['work9_request'],u,trusted_context={
        'client_id':'qa-client','run_id':'qa-run-3','owner':u['owner'],'currency':u['currency'],
        'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','runtime_mode':'REAL_DETERMINISTIC',
        'data_provenance':'SYNTHETIC','expected_result_digest':digest(u)})
    assert mentor and out['trade_action']=='NO_TRADE' and (b,s)==before

"""Same-source PV2 -> Entry -> Stage4 -> Gap -> slice -> original MIN.

All calendars, prices, fees and authorizations here are labelled SYNTHETIC.
Reference stress is used to construct a boundary fixture, not as market data.
"""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,localcontext
from test_v10_stock_integration import adopted_case,bind_context
from test_v10_own_history import complete_price,iso,month
from test_v10_profiles import range_proof
from test_native_adapters import ROOT
from stock_engine import run_stock_engine
from livingwater_v82_runtime.own_history import price_percentile,own_wealth
from livingwater_v82_runtime.approved_decision import evaluate
from livingwater_v82_runtime.daily_slice import open_cycle
from livingwater_v82_runtime.validation import validate_and_bind_funding
from livingwater_v82_runtime.deployment import build_buy_execution_plan


def own_sources(asset='QQQ'):
    p=complete_price();last=date.fromisoformat(p['bars'][-1]['session_id']);offset=date(2026,9,25)-last
    for row in p['bars']:
        day=date.fromisoformat(row['session_id'])+offset;row.update(session_id=day.isoformat(),as_of=iso(day,20),available_at=iso(day,21),retrieved_at=iso(day,21))
    for row in p['calendar']['sessions']:
        day=date.fromisoformat(row['session_id'])+offset;row.update(session_id=day.isoformat(),close_at=iso(day,20),knowledge_at=iso(day,21))
    p['decision_at']='2026-09-26T06:06:00Z';p['actions'].update(coverage_start=p['bars'][0]['session_id'],coverage_end=p['bars'][-1]['session_id'])
    p['actions']['available_at']=p['decision_at']
    p['calendar'].update(coverage_cutoff=p['decision_at'],last_completed_session=p['bars'][-1]['session_id'])
    p['calendar']['completed_periods']=[];day=date.fromisoformat(p['bars'][0]['session_id']).replace(day=1)
    while day<date(2026,10,1):
        end=month(day);p['calendar']['completed_periods'].append({'period_id':day.isoformat()[:7],'cadence':'MONTHLY','start':iso(day),'end':iso(end)})
        day=end
    p['identity']['asset_id']=p['actions']['asset_id']=asset
    for row in p['bars']:row['asset_id']=asset
    comparable=iso(date.fromisoformat(p['bars'][0]['session_id']).replace(day=1))
    with localcontext() as ctx:
        ctx.prec=40
        initial=price_percentile(**p,comparable_from=comparable)
        selected=set(initial['audit']['reference_periods'])
        zs=sorted(Decimal(r['z']) for r in initial['monthly_stress'] if r['period_id'] in selected)
        index=int(len(zs)*.8);wanted=(zs[index-1]+zs[index])/2
        wealth=own_wealth(**p)['rows'];window=wealth[-252:-1]
        high=max(Decimal(r['wealth']) for r in window)
        anchor=max(i for i in range(len(wealth)-252,len(wealth)-1) if Decimal(wealth[i]['wealth'])==high)
        returns=[Decimal(r['log_return']) for r in wealth[anchor-62:anchor+1]]
        mean=sum(returns)/63;sigma=(sum((x-mean)**2 for x in returns)/62).sqrt()
        target_close=Decimal(p['bars'][-2]['close'])*high/Decimal(wealth[-2]['wealth'])*(-wanted*sigma*Decimal(252).sqrt()).exp()
        p['bars'][-1]['close']=str(target_close);scale=Decimal(100)/target_close
        for row in p['bars']:row['close']=str(Decimal(row['close'])*scale)
    p.pop('decision_at');p['comparable_from']=comparable
    ident={**p['identity'],'unit':'MULTIPLE','method_id':'OWN_FORWARD_PE','metric_name':'FORWARD_PE'}
    ident.pop('price_basis');history=[];periods=[];day=date(2016,9,1)
    for i in range(120):
        end=month(day);observed=day+timedelta(days=14)
        periods.append({'period_id':day.isoformat()[:7],'cadence':'MONTHLY','start':iso(day),'end':iso(end)})
        history.append({**ident,'source_hash':'SYNTHETIC_VALUATION_HASH','revision_id':'1',
            'as_of':iso(observed),'available_at':iso(observed+timedelta(days=1)),
            'retrieved_at':iso(observed+timedelta(days=1)),
            'value':str(i%30+1),'freshness':'FRESH','pit_status':'VERIFIED','economic_meaningful':True})
        day=end
    current={**history[-1],'value':'10','as_of':'2026-09-25T00:00:00Z',
        'available_at':'2026-09-25T01:00:00Z','retrieved_at':'2026-09-25T02:00:00Z'}
    v={'identity':ident,'current':current,'history':history,'cadence':'MONTHLY',
        'calendar':{'approved':True,'calendar_id':'SYNTHETIC_UTC_MONTHS','version':'1','timezone':'UTC','completed_periods':periods},
        'comparable_from':'2016-09-01T00:00:00Z'}
    return p,v


def stage4_case(cash=100000,mature=True):
    req,facts,contract=adopted_case();w3=req['work3_handoff'];source=facts['approved_v10_context']
    req['asset_context']['confirmed_position_snapshot']['quantity']=2500
    w3['final_target']['payload']['instrument_targets']['QQQ']['project_target_position']=1000000
    c7=req['c7_funding_context'];c7['total_new_investment_amount']=cash+200
    account=c7['contexts'][2];account['bucket_new_investment_amount']=cash
    account['brokerage_cash_state']={'total':cash,'available':cash,'unsettled':0,'reserved':0}
    account['executable_budget']['equity']['amount']=cash;account['executable_budget']['bond']['amount']=0
    w3['funding_context']['settlement']['cash_state']=deepcopy(account['brokerage_cash_state'])
    w3['funding_context']['executable_budget']['equity']['amount']=str(cash)
    w3['funding_context']['executable_budget']['bond']['amount']='0'
    w3['v70_runtime_context']['payload']['stock_tactical_amount']=str(cash)
    facts.update(valuation_price='100',order_working_price='100',normalized_order_price='100',minimum_lot='1',
        required_known_caps=[str(cash)],active_orders=[{'order_intent_id':'SYNTHETIC_EXISTING_BUY','side':'BUY',
            'state':'OPEN','order_qty':'500','confirmed_filled_qty':'0'}])
    facts['core']['right_signals']=['FALSE']*3
    p,v=own_sources();source.update(price_history=p,valuation_history=v,
        market_identity={k:p['identity'][k] for k in ('listing','share_class')},
        absolute_range_proof=range_proof('TECH_AI_HIGH_GROWTH_ETF',snapshot_id=source['identity']['snapshot_id'],
            effective_from='2026-09-01T00:00:00Z'),
        maturity_signals=[{'id':'M'+str(i+1),'truth':'TRUE' if mature and i<3 else 'FALSE'} for i in range(8)])
    # This source row is the original core's actual valuation/fundamental/
    # technical result, evaluated once by the original engine below.
    from stock_engine import _plain
    from livingwater_v82_runtime.core_rules import EvidenceFact,evaluate_core_rule_state
    from livingwater_v82_runtime.enums import RequirementLevel,DataQuality,Freshness,PitStatus,PredicateTruth
    core=deepcopy(facts['core'])
    core['safety_facts']=[EvidenceFact(**{**r,'requirement':RequirementLevel(r['requirement']),
        'data_quality':DataQuality(r['data_quality']),'freshness':Freshness(r['freshness']),'pit_status':PitStatus(r['pit_status'])}) for r in core['safety_facts']]
    for k in ('right_signals','up_price','up_confirm','down_break','down_accel','hard_gate_predicates'):core[k]=[PredicateTruth(x) for x in core[k]]
    for k in ('structural_confirmation','ma20_ok'):core[k]=PredicateTruth(core[k])
    state=evaluate_core_rule_state(**core);analysis=evaluate(source,_plain(state))
    assert analysis['formal_stage']=='STAGE_4',analysis['left_stage_profile']
    cycle=open_cycle(owner=source['identity']['owner'],session_id=source['session']['session_id'],exchange='NASDAQ',asset_id='QQQ',
        opened_at=facts['evaluated_at'],gap='150000',speed_result=analysis['speed'],permission=True,
        exposure_reconciled=True,session_open=True)
    source['cycle_snapshot']={'status':'VERIFIED','cycle':cycle}
    allocation=source['shared_allocation_request'];allocation['remaining_tactical_room']=str(cash)
    allocation['slices'][0]['slice']=cycle['B0'];allocation['buckets'][0]['available_authorized_notional_cash']=str(cash)
    bind_context(facts,contract)
    return req,facts,contract


def test_same_input_37500_slice_and_legacy_100000_150000_probe_use_legal_price_lot_and_explicit_fees():
    req,facts,contract=stage4_case();out=run_stock_engine(ROOT,req,facts,contract)
    assert out['position_gap'].target_amount==450000 and out['position_gap'].projected_position_amount==300000
    assert out['position_gap'].final_deployment_gap_amount==150000
    assert out['deployment'].stage=='STAGE_4' and out['execution'].execution_amount==37500
    assert out['execution'].execution_quantity==375 and Decimal(out['daily_slice']['cycle']['B0'])==37500
    bound=validate_and_bind_funding(out['built_input']['v82_runtime_input'])
    legacy=build_buy_execution_plan(gap=out['position_gap'],permission=out['core_state'].permission,
        bound_equity_budget=bound.bound_equity_budget,order_working_price='100',minimum_lot='1',
        required_known_caps=['100000'],normalized_order_price='100',execution_currency='USD',order_intent_id='SYNTHETIC_OLD_PROBE')
    assert legacy.execution_amount==100000
    req,facts,contract=stage4_case(200000);out=run_stock_engine(ROOT,req,facts,contract)
    bound=validate_and_bind_funding(out['built_input']['v82_runtime_input'])
    legacy=build_buy_execution_plan(gap=out['position_gap'],permission=out['core_state'].permission,
        bound_equity_budget=bound.bound_equity_budget,order_working_price='100',minimum_lot='1',
        required_known_caps=['200000'],normalized_order_price='100',execution_currency='USD',order_intent_id='SYNTHETIC_OTHER_OLD_PROBE')
    assert legacy.execution_amount==150000 and out['execution'].execution_amount==37500


def test_immature_slice_22500_and_20000_settled_limit_preserve_stage_target():
    r,f,c=stage4_case(mature=False);out=run_stock_engine(ROOT,r,f,c)
    assert out['execution'].execution_amount==22500 and out['deployment'].stage=='STAGE_4'
    r,f,c=stage4_case(20000);out=run_stock_engine(ROOT,r,f,c)
    assert out['execution'].execution_amount==20000 and Decimal(out['daily_slice']['cap'])==37500


def test_high_precision_cap_cannot_round_up_across_a_legal_lot_boundary():
    r,f,c=stage4_case(20000)
    f['required_known_caps']=['19999.99999999999999999999999999999999999999']
    out=run_stock_engine(ROOT,r,f,c)
    assert out['execution'].execution_quantity==199 and out['execution'].execution_amount==19900
    assert out['execution'].execution_amount<=out['execution'].maximum_allowed_buy_amount


def test_authorized_sgov_is_visible_in_planning_but_never_added_to_settled_execution_cash():
    r,f,c=stage4_case(20000);source=f['approved_v10_context']
    source['funding_layers']={'available_cash':'20000','settled_cash':'20000','sgov_sources':[{
        'source_id':'SYNTHETIC_SGOV','physical_value':'120000','defensive_bond_role':'40000','dry_powder_role':'80000',
        'retained_dry_floor':'0','other_dry_commitments':'0','sale_authorized':True,'role_source_reference':'SYNTHETIC_ROLE_SOURCE'}]}
    bind_context(f,c);out=run_stock_engine(ROOT,r,f,c)
    assert out['approved_v10_analysis']['funding_layers']['planning_pool']=='100000'
    assert out['approved_v10_analysis']['funding_layers']['settled_execution_cash']=='20000'
    assert out['execution'].execution_amount==20000

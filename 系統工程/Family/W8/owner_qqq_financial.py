"""Scoped Menu04 adapter to original V82 gap/plan, funding guard and test ledger.

The Owner requests QQQ only. No independent bond strategy is run or invented.
Positive plans still require the original additional caps and execution inputs.
"""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
import sqlite3
from family_input import digest
from funding_guard import check_aggregate
from native_funding_advice import plain


def calculate(root,request,context,analysis,proof):
    from owner_qqq_scope import read
    if read(proof['source_descriptor'],request,'QQQ')!=proof:
        raise PermissionError('OWNER_QQQ_FINANCIAL_RULE_REPLAY_MISMATCH')
    rows=analysis['analysis_result']['positions']
    if len(rows)!=1 or rows[0]['symbol']!='QQQ' or analysis['owner']!=request['owner']:
        raise PermissionError('OWNER_QQQ_FINANCIAL_ANALYSIS_SCOPE_MISMATCH')
    row=rows[0];conclusion=row['formal_conclusion'];stage=conclusion['canonical_target_rate']
    out={'schema_version':'Family.W8.OwnerQQQFinancial.v1','rule_id':proof['rule_id'],
        **{k:deepcopy(request[k]) for k in ('client_id','run_id','evaluation_at','owner')},
        'asset_id':'QQQ','source_db_sha256':proof['source_db_sha256'],
        'owner_rule':deepcopy(proof),'status':'SOURCE_INCOMPLETE','missing_inputs':[],
        'cash_by_currency':deepcopy(proof['cash_by_currency']),
        'fund_structure_applicability':'NOT_APPLICABLE','interest_futures_applicability':'NOT_APPLICABLE',
        'selected_cash_currency':'USD','selected_net_cash':proof['cash_by_currency']['USD'],
        'bond_strategy_requested':False,'bond_cash_separate_pool_created':False,
        'SGOV_added_to_cash':False,'full_family_native_pipeline_complete':False,
        'formal_deployment_ready':False,'trade_action':'NO_TRADE','production':'HOLD',
        'call_trace':['W8.owner_qqq_financial','V82.CMR7.resolve_approved_stage']}
    if stage is None:
        out['missing_inputs']=[{'field':'canonical_target_rate','reasons':conclusion['stage_required_unknown_fields']}]
        return out
    from native_target_source import bind
    source=bind(request,context)
    target=(source or {}).get('targets',{}).get('QQQ',{}).get('target_amount',{})
    if target.get('value_state')!='KNOWN' or target.get('currency')!='USD':
        out['missing_inputs']=[{'field':'native_target_source.targets.QQQ.target_amount.USD'}];return out
    market=row['market'];identity=market.get('market_identity') or {}
    price_allowed=row.get('position_valuation_allowed') and identity.get('currency')=='USD'
    quantity = row['holding'].get('quantity') if row['holding'].get('quantity_state') == 'KNOWN' else None
    valuation_price = market.get('observed_close')
    scoped = context.get('owner_qqq_account_valuation')
    if scoped:
        from member_reconciliation_source import read as read_same_run
        verified = read_same_run(root, context['owner_qqq_target_fx_source'], request)
        if (scoped != verified.get('registered_broker_valuations', {}).get('QQQ')
                or scoped['position']['owner'] != request['owner'] or scoped['valuation']['currency'] != 'USD'):
            raise PermissionError('OWNER_QQQ_CURRENT_ACCOUNT_VALUATION_MISMATCH')
        quantity = scoped['position']['quantity']
        valuation_price = scoped['valuation']['observed_close']
        price_allowed = True
        out['canonical_quote_proof'] = deepcopy(scoped)
    if not price_allowed and context.get('qualified_equity_source_manifest') is not None:
        from qualified_equity_inputs import read as read_equities
        pool=read_equities(context['qualified_equity_source_manifest'],request['evaluation_at'],root,symbol='QQQ')
        equity=(pool or {}).get('items',{}).get('QQQ') or {}
        metadata=equity.get('technical_source_template',{}).get('metadata',{})
        holding=row['holding'].get('source_reference') or {}
        broker_position=holding.get('broker_position') or {}
        price_allowed=(equity.get('status')=='FRESH' and metadata.get('currency')=='USD'
            and market.get('qualified_equity_market_digest')==equity.get('digest')
            and market.get('formal_identity_verified') is True
            and market.get('observed_date')==equity.get('observed_date')
            and holding.get('account_key')==request['owner']['account']
            and broker_position.get('currency')=='USD'
            and broker_position.get('contract_id')==equity.get('contract',{}).get('underlying_contract_id')
            and Decimal(str(market['observed_close']))==Decimal(equity['rows'][-1]['Close']))
        if price_allowed:
            out['canonical_quote_proof']={'scope':'OWNER_QQQ_CURRENT_POSITION_VALUATION_ONLY',
                'qualification_sha256':equity['qualification_sha256'],'raw_source_sha256':equity['source_sha256'],
                'observed_date':equity['observed_date'],'contract_id':broker_position['contract_id'],
                'currency':'USD','held_account':holding['account_key'],
                'historical_PIT_or_execution_price_qualification_added':False}
    if not price_allowed or quantity is None:
        out['missing_inputs']=[{'field':'qualified_USD_valuation_price_and_confirmed_quantity'}];return out
    orders=conclusion['order_source']
    if not (orders.get('status')=='VERIFIED' or orders.get('complete_for_open_order_exposure')):
        out['missing_inputs']=[{'field':'active_orders_and_fill_reconciliation'}];return out
    from formal_mode_analysis import native_orders
    from livingwater_v82_runtime.deployment import calculate_position_gap,build_buy_execution_plan
    from livingwater_v82_runtime.models import BoundEquityBudgetView
    from livingwater_v82_runtime.enums import FundingDomain,CashBasis,HardGateState
    from livingwater_v82_runtime.core_rules import PermissionResult
    gap=calculate_position_gap(project_target_position_amount=target['amount'],target_rate=stage,
        confirmed_position_qty=quantity,canonical_valuation_price=valuation_price,
        active_orders=native_orders(root,orders,'QQQ'))
    permission=row['core_observation']['result']['permission'];cash=Decimal(proof['cash_by_currency']['USD'])
    bound=BoundEquityBudgetView(FundingDomain.US_BROKER,request['owner']['broker'],request['owner']['account'],
        cash,'USD',CashBasis.AVAILABLE,'OWNER_RECONCILED_SHARED_CASH__NOT_NEW_EXTERNAL_MONEY',
        ('SHA256:'+proof['cash_source']['sha256'],))
    # A positive request cannot skip the original missing per-position cap,
    # fee/tick/lot and daily-slice source requirements. A closed permission or
    # no positive gap already bounds the original recommendation to zero.
    caps=[None] if gap.positive_deployment_gap>0 and permission['new_buy_order_permission'] else []
    plan=build_buy_execution_plan(gap=gap,permission=PermissionResult(HardGateState(permission['hard_gate']),
        permission['new_buy_order_permission'],tuple(permission['reason_codes'])),bound_equity_budget=bound,
        order_working_price=None,minimum_lot=None,required_known_caps=caps,execution_currency='USD')
    out.update(selected_stage=conclusion['formal_stage'],target_rate=stage,
        approved_target_USD=deepcopy(target),position_gap=plain(gap),execution_plan=plain(plan),
        bound_shared_cash=plain(bound))
    out['call_trace']+=['V82.calculate_position_gap','V82.build_buy_execution_plan']
    if plan.execution_amount is None or plan.execution_quantity is None:
        out['missing_inputs']=[{'field':'original_execution_inputs','reasons':list(plan.reason_codes)}];return out
    if plan.execution_amount!=0 or plan.execution_quantity!=0:
        raise PermissionError('OWNER_QQQ_POSITIVE_PLAN_REQUIRES_ORIGINAL_SLICE_FINALIZATION')
    claims=[{'claim_id':'V82:QQQ','owner':deepcopy(request['owner']),'run_id':request['run_id'],
        'asset_class':'EQUITY','amount':str(plan.execution_amount),'source_engine':'V82','asset_id':'QQQ'}]
    shared=check_aggregate(owner=request['owner'],run_id=request['run_id'],available=str(cash),
        equity_budget=str(cash),bond_budget=str(cash),claims=claims)
    ledger=Path(proof['test_ledger_path']).resolve()
    if (ledger.is_relative_to(Path(root).resolve()) or ledger.suffix not in ('.sqlite','.sqlite3')
        or ledger.parent!=Path(proof['source_descriptor']['local_path']).resolve().parent):
        raise PermissionError('OWNER_QQQ_ISOLATED_LEDGER_REQUIRED')
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore
    CycleLedgerStore(ledger,create=True)
    def counts():
        with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
            return {name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('cycles','intent_owner')}
    before=counts();after=counts();assert before==after
    out.update(status='SCOPED_FINANCIAL_COMPLETE_NO_NEW_BUY',final_amount={'amount':'0','currency':'USD'},
        final_quantity='0',shared_funding=shared,
        known_zero_basis='NO_POSITIVE_DEPLOYMENT_GAP' if gap.positive_deployment_gap==0 else 'ORIGINAL_BUY_PERMISSION_CLOSED',
        test_ledger={'local_path':str(ledger),'before':before,'after':after,'new_cycles':0,'new_intents':0,
            'result':'NOOP_ZERO_PLAN_READBACK_VERIFIED','broker_cash_reserved':False},
        missing_inputs=[])
    out['call_trace']+=['W5.funding_guard.check_aggregate','V82.CycleLedgerStore:isolated_zero_plan_readback']
    out['result_digest']=digest(out);return out

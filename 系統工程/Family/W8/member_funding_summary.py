"""Reconcile original native claims once per real account and shared pool.

This consumer does not allocate cash or alter native Mentor/canonical output.
Unknown sources stay unknown; different currencies are never added together.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest
from funding_guard import check_aggregate,owner_key,amount,FundingError


def reconcile(request,positions):
    groups={};pools={};missing=[];issues=[]
    for row in positions:
        financial=row.get('financial_chain') or {}
        if not financial.get('full_native_pipeline_complete'):
            missing.append(row['symbol']);continue
        try:
            owner=financial['owner'];key=owner_key(owner)
            native=financial['native_result']['native_result']
            if (owner['client_id']!=request['client_id'] or financial['run_id']!=request['run_id']
                or native['client_id']!=request['client_id'] or native['run_id']!=request['run_id']):
                raise FundingError('MEMBER_FUNDING_OWNER_OR_RUN_MISMATCH')
            cash=native['work9_request']['work6_funding_account_isolation_result']['cash_eligibility']
            caps={k:str(amount(cash[k])) for k in ('available','equity_executable_budget','bond_executable_budget')}
            canonical=financial['canonical_amount']
            if canonical['currency']!=owner['currency']:raise FundingError('MEMBER_FUNDING_CURRENCY_MISMATCH')
            equity=amount(native['funding_aggregate']['equity_used'])
            if isinstance(canonical['amount'],bool) or equity!=amount(Decimal(str(canonical['amount']))):
                raise FundingError('MEMBER_FUNDING_CANONICAL_AMOUNT_MISMATCH')
            stock=native['stock_result']
            if stock['asset_id']!=row['symbol']:raise FundingError('MEMBER_FUNDING_ASSET_MISMATCH')
            claims=[{'claim_id':'V82:'+row['symbol'],'owner':owner,'run_id':request['run_id'],
                'asset_class':'EQUITY','amount':str(equity),'source_engine':'V82','asset_id':row['symbol']}]
            for decision in native['bond_result']['canonical_v75_output']['per_asset_decisions']:
                value=decision['deploy_amount']
                if value['currency']!=owner['currency']:raise FundingError('MEMBER_FUNDING_CURRENCY_MISMATCH')
                claims.append({'claim_id':'V75:'+decision['asset_id'],'owner':owner,'run_id':request['run_id'],
                    'asset_class':'BOND','amount':str(amount(value['amount'])),
                    'source_engine':'V75','asset_id':decision['asset_id'],
                    'native_decision_digest':digest(decision)})
            replay=check_aggregate(owner=owner,run_id=request['run_id'],claims=claims,
                available=caps['available'],equity_budget=caps['equity_executable_budget'],bond_budget=caps['bond_executable_budget'])
            if replay!=native['funding_aggregate']:raise FundingError('MEMBER_FUNDING_NATIVE_REPLAY_MISMATCH')
            group=groups.setdefault(key,{'owner':deepcopy(owner),'cash_limits':caps,'claims':{},'duplicate_decisions':[]})
            if group['cash_limits']!=caps:raise FundingError('MEMBER_FUNDING_CASH_SOURCE_CONFLICT')
            # Repeated bond decisions in individual stock reports refer to one
            # native owner/asset decision. Only an identical claim is reused.
            for claim in claims:
                identity=(claim['source_engine'],claim['asset_id']);old=group['claims'].get(identity)
                if old is not None and old!=claim:raise FundingError('MEMBER_FUNDING_NATIVE_DECISION_CONFLICT')
                if old is not None:group['duplicate_decisions'].append(claim['claim_id'])
                else:group['claims'][identity]=deepcopy(claim)
            binding=(native.get('stock_local_plan') or {}).get('family_ceiling_binding')
            if binding is not None:
                pool_key=(binding['scope']['identity']['portfolio_id'],binding['budget_currency'])
                pool=pools.setdefault(pool_key,{'portfolio_id':pool_key[0],'currency':pool_key[1],
                    'capacity':str(amount(binding['budget_amount'])),'capacity_digest':digest(binding['capacity']),
                    'claims':{}})
                if pool['capacity_digest']!=digest(binding['capacity']) or amount(pool['capacity'])!=amount(binding['budget_amount']):
                    raise FundingError('MEMBER_FUNDING_PORTFOLIO_CAPACITY_SOURCE_CONFLICT')
                identity=(key,row['symbol']);value=equity*amount(binding['selected_account_fx_to_budget'])
                if identity in pool['claims'] and pool['claims'][identity]!=value:
                    raise FundingError('MEMBER_FUNDING_PORTFOLIO_DECISION_CONFLICT')
                pool['claims'][identity]=value
        except (KeyError,TypeError,ValueError) as error:
            issues.append({'asset_id':row['symbol'],'code':str(error),
                'kind':'ORIGINAL_NATIVE_FUNDING_RECONCILIATION_FAILED'})
    accounts=[]
    for group in groups.values():
        caps=group['cash_limits'];claims=list(group['claims'].values())
        try:
            result=check_aggregate(owner=group['owner'],run_id=request['run_id'],claims=claims,
                available=caps['available'],equity_budget=caps['equity_executable_budget'],bond_budget=caps['bond_executable_budget'])
            accounts.append({'owner':group['owner'],'cash_limits':caps,'native_claims':claims,
                'duplicate_native_decisions_counted_once':group['duplicate_decisions'],'aggregate':result})
        except FundingError as error:issues.append({'owner':group['owner'],'code':str(error),'kind':'SHARED_ACCOUNT_BUDGET_FAILED'})
    shared=[]
    for pool in pools.values():
        used=sum(pool['claims'].values(),Decimal(0));capacity=amount(pool['capacity'])
        if used>capacity:issues.append({'portfolio_id':pool['portfolio_id'],
            'code':'MEMBER_SHARED_STOCK_CAPACITY_EXCEEDED','kind':'SHARED_PORTFOLIO_BUDGET_FAILED'})
        shared.append({k:v for k,v in pool.items() if k!='claims'}|{'new_stock_amount':str(used)})
    complete=bool(positions) and not missing and not issues
    return {'schema_version':'Family.W8.MemberFundingSummary.v1','client_id':request['client_id'],
        'run_id':request['run_id'],'status':'RECONCILED' if complete else 'BLOCKED' if issues else 'SOURCE_INCOMPLETE',
        'conserved':complete,'accounts':accounts,'shared_stock_pools':shared,
        'unresolved_assets':missing,'issues':issues,'unavailable_amounts_defaulted_to_zero':False,
        'cross_currency_total':None,'source':'ORIGINAL_NATIVE_WORK6_AND_FUNDING_AGGREGATE',
        'trade_action':'NO_TRADE'}

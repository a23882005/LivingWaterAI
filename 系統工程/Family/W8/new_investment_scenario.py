"""Read confirmed contributions, or apply the Owner's no-external-money trial.

Contribution amounts are not cash balances. This module never changes source
rows, creates an account, allocates a positive budget, or authorizes an order.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest


def build_plan(snapshot,owner,policy=None):
    if snapshot['client_id']!=owner['client_id']:
        raise PermissionError('NEW_INVESTMENT_CLIENT_MISMATCH')
    tables=snapshot['tables'];client=snapshot['client_id'];currency=owner['currency']
    sources=[];issues=[];by_account={};total=Decimal('0');seen=set()
    for row in tables.get('funding_source',[]):
        if row.get('client_id')!=client:raise PermissionError('NEW_INVESTMENT_SOURCE_CLIENT_MISMATCH')
        if row.get('source_state')!='CONFIRMED_IN_ACCOUNT' or row.get('evidence_state')!='VERIFIED':continue
        key=row.get('source_id')
        if not key or key in seen:raise ValueError('NEW_INVESTMENT_SOURCE_AMBIGUOUS')
        seen.add(key);sources.append(deepcopy(row))
        if row.get('source_kind') not in ('CASH_DEPOSIT','TRANSFER_IN','PLANNED_CONTRIBUTION'):
            issues.append('confirmed_source_new_contribution_classification');continue
        if row.get('currency_code')!=currency:
            issues.append('confirmed_contribution_currency_FX');continue
        minor=row.get('amount_minor')
        digits=[c.get('minor_digits') for c in tables.get('currency_registry',[]) if c.get('currency_code')==currency]
        if (len(digits)!=1 or not isinstance(digits[0],int) or isinstance(digits[0],bool)
                or not isinstance(minor,int) or isinstance(minor,bool) or minor<0):
            issues.append('confirmed_contribution_amount_or_currency_precision');continue
        amount=Decimal(minor)/(Decimal(10)**digits[0]);total+=amount
        account=row.get('account_key')
        if not account:issues.append('confirmed_contribution_account');continue
        by_account[account]=by_account.get(account,Decimal('0'))+amount
    assumed=False
    if sources:
        status='CONFIRMED_SOURCE' if not issues else 'PARTIAL_CONFIRMED_SOURCE'
        value=None if issues else str(total)
    elif policy is not None:
        if (policy.get('schema_version')!='Family.W8.NewInvestmentTrialPolicy.v1'
            or policy.get('client_id')!=client or policy.get('new_external_money')!='0'
            or not policy.get('source_reference')):
            raise ValueError('EXPLICIT_NO_EXTERNAL_MONEY_POLICY_REQUIRED')
        status='NO_EXTERNAL_MONEY_TRIAL';value='0';assumed=True
    else:status='UNKNOWN';value=None;issues.append('confirmed_new_investment_amount_or_trial_policy')
    result={'schema_version':'Family.W8.NewInvestmentScenario.v1','client_id':client,
        'source_db_sha256':snapshot['source_sha256'],'currency':currency,'status':status,
        'total_new_investment_amount':value,
        'account_contributions':{k:str(v) for k,v in by_account.items()},
        'confirmed_source_rows':sources,'assumed_zero':assumed,
        'assumption':({'label':'本輪不新增外部資金，新增投入為 0',
            'source_reference':policy['source_reference'],'scope':'RECOMMENDATION_TRIAL_ONLY'} if assumed else None),
        'cash_balance_unchanged':True,'official_db_changed':False,
        'existing_positions_may_still_have_deployment_gaps':True,
        'issues':sorted(set(issues)),'trade_authorization':'NONE'}
    result['digest']=digest(result)
    return result


def wire_number(value):
    if value is None:return None
    amount=Decimal(str(value))
    return int(amount) if amount==amount.to_integral_value() else float(amount)


def apply_plan(contexts,plan):
    """Fill missing contribution slots; retain all existing amounts and cash."""
    out=deepcopy(contexts)
    for row in out:
        if row.get('bucket_new_investment_amount') is not None:continue
        if plan['total_new_investment_amount']=='0':
            row['bucket_new_investment_amount']=0
        elif row.get('account') in plan['account_contributions']:
            row['bucket_new_investment_amount']=wire_number(plan['account_contributions'][row['account']])
        if row.get('bucket_new_investment_amount')==0:
            # Only missing external-contribution budget slots become zero.
            # Positive cash remains cash; it is not silently reassigned here.
            for leg in row.get('executable_budget',{}).values():
                if leg.get('amount') is None:leg['amount']=0
    return out

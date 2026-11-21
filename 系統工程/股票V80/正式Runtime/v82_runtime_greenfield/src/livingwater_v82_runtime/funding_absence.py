"""C7 v1.1: a source-confirmed absent funding domain is not an account.

The original three domains and all present-account funding checks remain.
An absent context must have null identities, exact zero money and an explicit
source reference. No sentinel account, budget or investment rule is invented.
"""
from copy import deepcopy
from decimal import Decimal,InvalidOperation

VERSION='C-W7-FUND-v1.1.0-ABSENT'
PRESENCE='OWNER_CONFIRMED_ABSENT'
DOMAINS={'TW_LOCAL_BROKER','TW_SUB_BROKERAGE','US_BROKER'}


def is_extended(value):
    if isinstance(value,dict):
        return value.get('contract_version')==VERSION or any(is_extended(v) for v in value.values())
    return isinstance(value,(list,tuple)) and any(is_extended(v) for v in value)


def validate_absent(context,version):
    if context.get('account_presence')!=PRESENCE:return False
    def fail():raise ValueError('CONFIRMED_ABSENT_CONTEXT_REQUIRES_NULL_IDENTITY_ZERO_MONEY_AND_OWNER_SOURCE')
    if version!=VERSION or context.get('domain') not in DOMAINS:fail()
    if context.get('broker') is not None or context.get('account') is not None:fail()
    source=context.get('account_presence_source')
    if not isinstance(source,str) or not source.strip() or source not in context.get('source_reference_ids',[]):fail()
    def zero(v):
        try:return not isinstance(v,bool) and v is not None and Decimal(str(v)).is_finite() and Decimal(str(v))==0
        except (InvalidOperation,ValueError):return False
    if not zero(context.get('bucket_new_investment_amount')):fail()
    if set(context.get('brokerage_cash_state',{}))!={'total','available','unsettled','reserved'}:fail()
    if not all(zero(v) for v in context['brokerage_cash_state'].values()):fail()
    if set(context.get('executable_budget',{}))!={'equity','bond'}:fail()
    for leg in context['executable_budget'].values():
        if (not zero(leg.get('amount')) or leg.get('cash_basis')!='AVAILABLE'
            or leg.get('source_domain')!=context['domain'] or leg.get('source_broker') is not None
            or leg.get('source_account') is not None):fail()
    return True


def extend_schema(schema):
    """Use a versioned additive schema; never mutate the frozen v1.0 schema."""
    def walk(node):
        if isinstance(node,list):return [walk(v) for v in node]
        if not isinstance(node,dict):return node
        if node.get('const')=='C-W7-FUND-v1.0.0':return {'enum':['C-W7-FUND-v1.0.0',VERSION]}
        props=node.get('properties',{})
        if {'domain','broker','account','bucket_new_investment_amount','executable_budget'}.issubset(props):
            original=deepcopy(node);absent=deepcopy(node);p=absent['properties']
            p['broker']={'type':'null'};p['account']={'type':'null'}
            p['bucket_new_investment_amount']={'type':'number','const':0}
            p['account_presence']={'const':PRESENCE}
            p['account_presence_source']={'type':'string','minLength':1}
            p['brokerage_cash_state']={'type':'object','additionalProperties':False,
                'required':['total','available','unsettled','reserved'],
                'properties':{k:{'type':'number','const':0} for k in ('total','available','unsettled','reserved')}}
            leg={'type':'object','additionalProperties':False,
                'required':['amount','cash_basis','source_domain','source_broker','source_account'],
                'properties':{'amount':{'type':'number','const':0},'cash_basis':{'const':'AVAILABLE'},
                    'source_domain':{'enum':sorted(DOMAINS)},'source_broker':{'type':'null'},'source_account':{'type':'null'}}}
            p['executable_budget']={'type':'object','additionalProperties':False,'required':['equity','bond'],
                'properties':{k:deepcopy(leg) for k in ('equity','bond')}}
            absent['required']=list(dict.fromkeys(absent.get('required',[])+['account_presence','account_presence_source','source_reference_ids']))
            return {'oneOf':[original,absent]}
        result={k:walk(v) for k,v in node.items()}
        if {'boundary_contract','contexts','total_new_investment_amount','base_currency'}.issubset(props):
            result['properties']['contract_version']={'const':VERSION}
            result['required']=list(dict.fromkeys(result.get('required',[])+['contract_version']))
        return result
    return walk(deepcopy(schema))

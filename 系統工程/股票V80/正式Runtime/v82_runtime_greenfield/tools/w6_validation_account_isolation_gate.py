#!/usr/bin/env python3
from __future__ import annotations
import copy, json, math, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from livingwater_v82_runtime.validation import validate_and_bind_funding, V82InputValidationError

def base():
    ids=[('TW_LOCAL_BROKER','tw','A'),('TW_SUB_BROKERAGE','sub','B'),('US_BROKER','ib','C')]
    ctx=[]
    for d,b,a in ids:
        ctx.append({'domain':d,'broker':b,'account':a,'bucket_new_investment_amount':100,
          'brokerage_cash_state':{'total':150,'available':100,'unsettled':20,'reserved':10},
          'executable_budget':{
            'equity':{'amount':60,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a},
            'bond':{'amount':40,'cash_basis':'AVAILABLE','source_domain':d,'source_broker':b,'source_account':a}},
          'source_reference_ids':[f'{d}-ref']})
    return {'contract_name':'LivingWaterAI.V82.RuntimeInput','contract_version':'V82-INPUT-v1.0.1-W2-RECHECK2','run_id':'R1',
      'client_project_version':'P1',
      'asset':{'asset_id':'QQQ','asset_type':'BROAD_ETF','asset_grade':'A','portfolio_role':'CORE'},
      'execution_account':{'domain':'US_BROKER','broker':'ib','account':'C'},
      'client_target':{'project_target_position':100,'authorization_reference':'AUTH1'},
      'upstream_v70_snapshot':{'run_id':'R1','upstream_v70_snapshot_id':'V70-1','v70_stock_tactical_budget_amount':100,'v70_stock_tactical_budget_currency':'USD','v70_stock_tactical_budget_status':'KNOWN','v70_stock_tactical_budget_data_as_of':'2026-09-25','v70_original_dry_powder_amount':100,'v70_original_dry_powder_currency':'USD','v70_budget_source_reference':'v70','v70_budget_data_quality':'OK','v70_budget_issue_codes':[]},
      'confirmed_position_snapshot':{},'source_lineage':['source'],
      'c7_funding_context':{'contract_name':'LivingWaterAI.C.Work7.FundingContext','contract_version':'C-W7-FUND-v1.0.0','run_id':'R1','base_currency':'USD','bank_cash_scope':'OUT_OF_SCOPE','total_new_investment_amount':300,'contexts':ctx,'source_reference_ids':['c7']}}

def mutate(path,value):
    x=base(); cur=x
    for p in path[:-1]: cur=cur[p]
    cur[path[-1]]=value; return x

def expect_fail(name,obj,code):
    try: validate_and_bind_funding(obj)
    except V82InputValidationError as e:
        got=e.issues[0].code
        if got!=code: return (name,False,f'expected {code}, got {got}: {e}')
        return (name,True,got)
    except Exception as e: return (name,False,f'unexpected {type(e).__name__}: {e}')
    return (name,False,'unexpected PASS')

def main():
    tests=[]
    def ok(name,obj= None):
        try:
            r=validate_and_bind_funding(base() if obj is None else obj)
            tests.append((name,True,f'{r.bound_equity_budget.domain}/{r.bound_equity_budget.broker}/{r.bound_equity_budget.account}/{r.bound_equity_budget.amount}'))
        except Exception as e: tests.append((name,False,str(e)))
    def bad(name,obj,code): tests.append(expect_fail(name,obj,code))
    ok('happy_path')
    z=base(); z['c7_funding_context']['contexts'][2]['executable_budget']['equity']['amount']='60.00'; bad('string_amount_rejected_by_schema',z,'V82E_CONTRACT_CONFLICT')
    z=base(); z['c7_funding_context']['contexts'][0]['brokerage_cash_state']['unsettled']=100; ok('unsettled_fact_not_subtracted',z)
    z=base(); z['c7_funding_context']['contexts'][0]['brokerage_cash_state']['reserved']=100; ok('reserved_fact_not_subtracted',z)
    for key in ['contract_name','contract_version','run_id','execution_account','upstream_v70_snapshot','c7_funding_context','asset','client_target','confirmed_position_snapshot','source_lineage','client_project_version']:
        z=base(); del z[key]; bad('missing_'+key,z,'V82E_REQUIRED_FIELD_MISSING')
    bad('input_contract_name',mutate(['contract_name'],'bad'),'V82E_CONTRACT_CONFLICT')
    bad('input_contract_version',mutate(['contract_version'],'bad'),'V82E_CONTRACT_CONFLICT')
    bad('illegal_execution_domain',mutate(['execution_account','domain'],'EU_BROKER'),'V82E_ILLEGAL_FUNDING_DOMAIN')
    bad('missing_execution_broker',mutate(['execution_account','broker'],''),'V82E_REQUIRED_FIELD_MISSING')
    bad('account_not_found',mutate(['execution_account','account'],'Z'),'V82E_EXECUTION_ACCOUNT_NOT_FOUND')
    bad('v70_run_mismatch',mutate(['upstream_v70_snapshot','run_id'],'R2'),'V82E_RUN_ID_MISMATCH')
    bad('c7_run_mismatch',mutate(['c7_funding_context','run_id'],'R2'),'V82E_RUN_ID_MISMATCH')
    bad('c7_contract_name',mutate(['c7_funding_context','contract_name'],'bad'),'V82E_FUNDING_CONTEXT_CONTRACT_MISMATCH')
    bad('c7_contract_version',mutate(['c7_funding_context','contract_version'],'bad'),'V82E_FUNDING_CONTEXT_CONTRACT_MISMATCH')
    bad('bad_currency',mutate(['c7_funding_context','base_currency'],'usd'),'V82E_EXECUTABLE_CURRENCY_MISSING')
    bad('bank_cash_scope',mutate(['c7_funding_context','bank_cash_scope'],'IN_SCOPE'),'V82E_BANK_CASH_FORBIDDEN')
    for val in [-1,float('nan'),float('inf'),'NaN']:
        bad('bad_total_'+repr(val),mutate(['c7_funding_context','total_new_investment_amount'],val),'V82E_FUNDING_TOTAL_INVALID')
    z=base(); z['c7_funding_context']['contexts']=z['c7_funding_context']['contexts'][:2]; bad('only_two_domains',z,'V82E_FUNDING_DOMAIN_SET_INVALID')
    z=base(); z['c7_funding_context']['contexts'][2]['domain']='TW_LOCAL_BROKER'; z['c7_funding_context']['contexts'][2]['executable_budget']['equity']['source_domain']='TW_LOCAL_BROKER'; z['c7_funding_context']['contexts'][2]['executable_budget']['bond']['source_domain']='TW_LOCAL_BROKER'; bad('duplicate_domain',z,'V82E_FUNDING_DOMAIN_SET_INVALID')
    z=base(); z['c7_funding_context']['contexts'][2]['broker']='tw'; z['c7_funding_context']['contexts'][2]['account']='A'; bad('duplicate_broker_account',z,'V82E_DUPLICATE_BROKER_ACCOUNT_CONTEXT')
    z=base(); z['c7_funding_context']['contexts'][1]=copy.deepcopy(z['c7_funding_context']['contexts'][0]); bad('duplicate_full_context',z,'V82E_DUPLICATE_ACCOUNT_CONTEXT')
    for val in [-1,float('nan'),float('inf')]: bad('bad_bucket_'+repr(val),mutate(['c7_funding_context','contexts',0,'bucket_new_investment_amount'],val),'V82E_FUNDING_BUCKET_AMOUNT_INVALID')
    for fld in ['total','available','unsettled','reserved']:
        bad('cash_nan_'+fld,mutate(['c7_funding_context','contexts',0,'brokerage_cash_state',fld],float('nan')),'V82E_BROKERAGE_CASH_STATE_INVALID')
    bad('available_gt_total',mutate(['c7_funding_context','contexts',0,'brokerage_cash_state','available'],151),'V82E_BROKERAGE_CASH_STATE_INCONSISTENT')
    bad('unsettled_gt_total',mutate(['c7_funding_context','contexts',0,'brokerage_cash_state','unsettled'],151),'V82E_BROKERAGE_CASH_STATE_INCONSISTENT')
    bad('reserved_gt_total',mutate(['c7_funding_context','contexts',0,'brokerage_cash_state','reserved'],151),'V82E_BROKERAGE_CASH_STATE_INCONSISTENT')
    bad('equity_nan',mutate(['c7_funding_context','contexts',0,'executable_budget','equity','amount'],float('nan')),'V82E_EXECUTABLE_BUDGET_AMOUNT_INVALID')
    bad('bond_inf',mutate(['c7_funding_context','contexts',0,'executable_budget','bond','amount'],float('inf')),'V82E_EXECUTABLE_BUDGET_AMOUNT_INVALID')
    bad('cash_basis_unsettled',mutate(['c7_funding_context','contexts',0,'executable_budget','equity','cash_basis'],'UNSETTLED'),'V82E_CASH_BASIS_NOT_AVAILABLE')
    bad('cross_domain_owner',mutate(['c7_funding_context','contexts',0,'executable_budget','equity','source_domain'],'US_BROKER'),'V82E_CROSS_DOMAIN_FUNDING')
    bad('cross_broker_owner',mutate(['c7_funding_context','contexts',0,'executable_budget','equity','source_broker'],'other'),'V82E_CROSS_BROKER_FUNDING')
    bad('cross_account_owner',mutate(['c7_funding_context','contexts',0,'executable_budget','equity','source_account'],'other'),'V82E_CROSS_ACCOUNT_FUNDING')
    z=base(); z['c7_funding_context']['contexts'][0]['executable_budget']['equity']['amount']=61; bad('budget_exceeds_available',z,'V82E_EXECUTABLE_BUDGET_EXCEEDS_AVAILABLE')
    z=base(); z['c7_funding_context']['contexts'][0]['brokerage_cash_state']['available']=150; z['c7_funding_context']['contexts'][0]['executable_budget']['equity']['amount']=61; bad('budget_exceeds_bucket',z,'V82E_EXECUTABLE_BUDGET_EXCEEDS_ACCOUNT_BUCKET')
    bad('bucket_total_mismatch',mutate(['c7_funding_context','total_new_investment_amount'],301),'V82E_FUNDING_BUCKET_TOTAL_MISMATCH')
    z=base(); z['c7_funding_context']['contexts'][2]['source_reference_ids']=[]; bad('missing_source_refs',z,'V82E_REQUIRED_FIELD_MISSING')
    z=base(); z['c7_funding_context']['contexts'][2]['source_reference_ids']=['x','x']; bad('duplicate_source_refs',z,'V82E_REQUIRED_FIELD_MISSING')
    # Explicitly prove V82 binds equity only and does not expose bond/SGOV/bank cash.
    r=validate_and_bind_funding(base()); tests.append(('equity_only_bound_amount',r.bound_equity_budget.amount==60,str(r.bound_equity_budget.amount)))
    tests.append(('bound_cash_basis_available',r.bound_equity_budget.cash_basis.value=='AVAILABLE',r.bound_equity_budget.cash_basis.value))
    tests.append(('bound_currency_from_c7',r.bound_equity_budget.currency=='USD',r.bound_equity_budget.currency))
    tests.append(('no_funding_mutator_api',not any(hasattr(__import__('livingwater_v82_runtime.validation',fromlist=['x']),n) for n in ['allocate_funding','sweep','net','transfer','route_sgov']), 'consumer guard only'))
    passed=sum(1 for _,p,_ in tests if p)
    out={'gate':'W6 Input Validation + Funding/Account Isolation','passed':passed,'total':len(tests),'status':'PASS' if passed==len(tests) else 'FAIL','tests':[{'name':n,'pass':p,'detail':d} for n,p,d in tests]}
    (ROOT.parent/'QA_Results').mkdir(exist_ok=True)
    (ROOT.parent/'QA_Results'/'A78_W06_VALIDATION_ACCOUNT_ISOLATION_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':passed,'total':len(tests),'status':out['status']},ensure_ascii=False))
    if out['status']!='PASS':
        for n,p,d in tests:
            if not p: print('FAIL',n,d)
        raise SystemExit(1)
if __name__=='__main__': main()

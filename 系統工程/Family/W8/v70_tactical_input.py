"""Reuse original V70 numerical components with an explicit approved base."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib,json,subprocess


def calculate(root,request,policy,fx_observation=None):
    if not policy:return None
    if policy.get('client_id')!=request['client_id'] or not policy.get('source_reference'):
        raise PermissionError('V70_STRATEGIC_POLICY_OWNER_REQUIRED')
    stock=policy['stock_percent'];bond=policy['bond_percent']
    root=Path(root);html=root/'系統工程/總經V70/V70-3-27.html';feed=root/'系統工程/總經V70/V70_macro_latest.json'
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (html,feed)]
    args={'repo_root':str(root),'stock_percent':stock,'bond_percent':bond,'html_sha256':hashes[0],'feed_sha256':hashes[1]}
    run=subprocess.run(['node',str(Path(__file__).with_name('v70_component_runtime.cjs'))],input=json.dumps(args),capture_output=True,text=True,timeout=15)
    if run.returncode:raise RuntimeError('V70_COMPONENT_EXECUTION_FAILED:'+run.stderr[-350:])
    result=json.loads(run.stdout)
    if hashes!=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (html,feed)]:raise RuntimeError('V70_SOURCE_CHANGED')
    base=request['confirmed_target']['payload']['draft']['denominator']
    if base.get('value_state')!='KNOWN':raise ValueError('V70_APPROVED_ALLOCATION_BASE_REQUIRED')
    amounts={k:str(Decimal(base['amount'])*Decimal(str(result['allocation'][field]))/100)
        for k,field in [('stock','sTot'),('bond','bTot'),('dry_powder','cTot')]}
    from fx_conversion import convert
    converted={k:convert(v,base['currency'],request['owner']['currency'],fx_observation) for k,v in amounts.items()}
    native_amounts={k:str(v) for k,v in converted.items()} if all(v is not None for v in converted.values()) else None
    result.update(approved_strategic_source=deepcopy(policy),allocation_base=deepcopy(base),
        amount_basis='APPROVED_ALLOCATION_BASE__NOT_CURRENT_MARKET_NAV',currency=base['currency'],amounts=amounts,
        native_execution_currency=request['owner']['currency'],
        native_currency_amounts=native_amounts,fx_observation=deepcopy(fx_observation),
        native_currency_issue=None if native_amounts is not None else 'V70_TACTICAL_BUDGET_FX_REQUIRED')
    return result

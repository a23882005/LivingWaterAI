"""Reuse original V70 numerical components with an explicit approved base."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib,json,subprocess,sys


def calculate(root,request,policy,fx_observation=None,*,feed_source=None):
    if not policy:return None
    if policy.get('client_id')!=request['client_id'] or not policy.get('source_reference'):
        raise PermissionError('V70_STRATEGIC_POLICY_OWNER_REQUIRED')
    stock=policy['stock_percent'];bond=policy['bond_percent']
    current=None
    if any(k in policy for k in ('current_stock_percent','current_bond_percent')):
        values=[policy.get(k) for k in ('current_stock_percent','current_bond_percent')]
        if any(isinstance(v,bool) or v is None for v in values):raise ValueError('V70_CURRENT_ALLOCATION_INVALID')
        values=[Decimal(str(v)) for v in values]
        if any(not v.is_finite() or not 0<=v<=100 for v in values) or sum(values)!=100:
            raise ValueError('V70_CURRENT_ALLOCATION_INVALID')
        current={'stock_percent':deepcopy(policy['current_stock_percent']),
            'bond_percent':deepcopy(policy['current_bond_percent']),
            'source_reference':policy['source_reference'],'basis':'OWNER_STATED_CURRENT_REFERENCE__NOT_DB_REVALUATION'}
    root=Path(root);html=root/'系統工程/總經V70/V70-3-27.html';feed=root/'系統工程/總經V70/V70_macro_latest.json'
    if feed_source is not None:
        w5=Path(__file__).resolve().parents[1]/'W5'
        if str(w5) not in sys.path:sys.path.insert(0,str(w5))
        from market_bridge import resolve_macro_feed
        feed=resolve_macro_feed(root,feed_source)
        if request.get('macro_snapshot',{}).get('source_sha256')!=feed_source['sha256']:
            raise PermissionError('V70_MACRO_SOURCE_BINDING_MISMATCH')
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (html,feed)]
    args={'repo_root':str(root),'stock_percent':stock,'bond_percent':bond,
        'life_stage_code':policy.get('life_stage_code'),'html_sha256':hashes[0],'feed_sha256':hashes[1]}
    if feed_source is not None:args['feed_path']=str(feed)
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
    result.update(approved_strategic_source=deepcopy(policy),current_stock_bond_reference=current,allocation_base=deepcopy(base),
        amount_basis='APPROVED_ALLOCATION_BASE__NOT_CURRENT_MARKET_NAV',currency=base['currency'],amounts=amounts,
        native_execution_currency=request['owner']['currency'],
        native_currency_amounts=native_amounts,fx_observation=deepcopy(fx_observation),
        native_currency_issue=None if native_amounts is not None else 'V70_TACTICAL_BUDGET_FX_REQUIRED')
    return result

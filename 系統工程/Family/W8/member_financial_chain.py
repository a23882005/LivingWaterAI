"""Member Menu04 -> existing native FamilyRunner, with no financial defaults.

Trusted upstream producers supply their original request/context/source pack.
This seam checks member/run/approval identity then uses the original assembler,
all original financial guards and Work9/Mentor. It never repairs C7 results.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from decimal import Decimal
import json
from family_input import digest
from member_market_source import time


def _lines(target):
    lines=target.get('payload',{}).get('draft',{}).get('target_lines',[])
    result={}
    for r in lines:
        key=r['instrument_id']
        if key in result:raise PermissionError('MEMBER_FINANCIAL_DUPLICATE_APPROVED_LINE')
        result[key]=(r.get('ticker'),Decimal(str(r['weight']['value'])),r['target_amount'])
    return result


def read(descriptor,request,symbol):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('MEMBER_FINANCIAL_SOURCE_HASH_MISMATCH')
    data=json.loads(raw)
    if (data.get('schema_version')!='Family.W8.MemberV82FinancialSource.v1'
        or any(data.get(k)!=request.get(k) for k in ('client_id','run_id','evaluation_at'))
        or data.get('asset_id')!=symbol
        or data.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
        or not data.get('source_reference') or time(data['available_at'])>time(request['evaluation_at'])):
        raise PermissionError('MEMBER_FINANCIAL_SOURCE_SCOPE_OR_TIME_MISMATCH')
    pack=deepcopy(data['pack']);child=pack['request']
    if (any(child.get(k)!=request[k] for k in ('client_id','run_id','evaluation_at'))
        or child.get('client_snapshot',{}).get('payload')!=request['client_snapshot']['payload']
        or child.get('owner',{}).get('client_id')!=request['client_id']
        or any(not child['owner'].get(k) for k in ('account','broker','currency','funding_domain'))
        or child.get('trade_authorization')!='NONE'
        or any(k in pack for k in ('member_v82_report','analysis_report'))):
        raise PermissionError('MEMBER_FINANCIAL_REQUEST_BINDING_MISMATCH')
    original,actual=_lines(request['confirmed_target']),_lines(child['confirmed_target'])
    if set(original)!=set(actual) or child['confirmed_target'].get('target_version')!=request['confirmed_target'].get('target_version'):
        raise PermissionError('MEMBER_FINANCIAL_APPROVAL_VERSION_MISMATCH')
    for key,(ticker,weight,money) in original.items():
        supplied=actual[key]
        if (supplied[:2]!=(ticker,weight) or money.get('value_state')!='KNOWN'
            or supplied[2].get('value_state')!='KNOWN' or money.get('currency')!=supplied[2].get('currency')
            or Decimal(str(money['amount']))!=Decimal(str(supplied[2]['amount']))):
            raise PermissionError('MEMBER_FINANCIAL_APPROVED_MONEY_BASE_UNBOUND_OR_CHANGED')
    bundle=pack.get('native_bundle') or pack.get('native_sources',{}).get('native_bundle') or child.get('native_bundle') or {}
    if bundle.get('stock_request',{}).get('asset_context',{}).get('asset',{}).get('asset_id')!=symbol:
        raise PermissionError('MEMBER_FINANCIAL_NATIVE_ASSET_MISMATCH')
    return pack


def calculate(root,descriptor,request,symbol,*,runner_factory=None,delivery=None):
    from on_demand_analysis import OnDemandAnalysisProvider
    pack=read(descriptor,request,symbol)
    provider=OnDemandAnalysisProvider(lambda *_:deepcopy(pack),repo_root=root,runner_factory=runner_factory)
    child,runner=provider(request['client_snapshot']['payload'],{'question':request['question']})
    # Original validation still decides C7, target, orders, cash, MIN/lot and
    # eligibility. An input source being present never implies a successful run.
    result=runner.analyze(child)
    native=result.get('native_result') or {}
    complete=result.get('status')=='OK' and native.get('status')=='NATIVE_PIPELINE_COMPLETE'
    actual=(native.get('stock_result') or {}).get('canonical_v82_output',{})
    canonical=(actual.get('canonical_analysis') or {})
    amount=(canonical.get('execution_amount') or {}).get('value')
    receipt=result.get('daily_slice_ledger_receipt')
    positive=isinstance(amount,dict) and Decimal(str(amount['amount']))>0
    if positive and delivery is not None:
        if not receipt:raise PermissionError('MEMBER_FINANCIAL_NATIVE_LOCAL_LEDGER_RECEIPT_REQUIRED')
        from on_demand_drive_io import Binding
        from v82_ledger_drive import verify_planning_readback
        receipt=verify_planning_readback(delivery['member_db_path'],Binding(**delivery['member_drive_binding']),
            delivery['descriptor'],child,receipt)
        result['daily_slice_ledger_receipt']=receipt
    persisted=not positive or bool(delivery is not None and receipt and receipt.get('status')=='PERSISTED_REMOTE_VERIFIED')
    ready=complete and persisted and native.get('formal_deployment_ready') is True
    return {'schema_version':'Family.W8.MemberFinancialChain.v1','status':result.get('status'),
        'client_id':child['client_id'],'run_id':child['run_id'],'owner':child['owner'],'asset_id':symbol,
        'evaluation_at':child['evaluation_at'],'request_digest':digest(child),
        'source_descriptor_digest':digest(descriptor),'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'full_native_pipeline_complete':complete,'formal_deployment_ready':ready,
        'drive_persistence_status':'PENDING_DRIVE_BACKUP_UPDATE_READBACK' if positive and not persisted else
            'NOT_REQUIRED_NO_POSITIVE_PLAN' if not positive else 'PERSISTED_REMOTE_VERIFIED',
        'canonical_v82_output':actual or None,'canonical_amount':amount,
        'mentor':result.get('mentor') if complete else None,'native_result':result,
        'issue_codes':deepcopy(result.get('issue_codes',[])),
        'call_trace':['W8.member_financial_chain','W8.OnDemandAnalysisProvider','W5.FamilyRunner.analyze',*result.get('call_trace',[])],
        'trade_authorization':'NONE','trade_action':'NO_TRADE'}


def complete_report(report,request,config,root):
    """Called after immutable component-source replay, once per requested run."""
    descriptors=config.get('financial_sources') or {}
    if not descriptors:return deepcopy(report)
    symbols={r['symbol'] for r in report['positions']}
    if set(descriptors)-symbols:raise PermissionError('MEMBER_FINANCIAL_ASSET_OUTSIDE_APPROVED_UNIVERSE')
    out=deepcopy(report);out['component_report_digest']=report['report_digest']
    for row in out['positions']:
        descriptor=descriptors.get(row['symbol'])
        if descriptor is None:continue
        readback=(config.get('ledger_delivery_sources') or {}).get(row['symbol'])
        delivery={'member_db_path':config['member_db_path'],'member_drive_binding':config['member_drive_binding'],
            'descriptor':readback} if readback is not None else None
        financial=calculate(root,descriptor,request,row['symbol'],delivery=delivery)
        row['financial_chain']=financial
        row['full_native_pipeline_complete']=financial['full_native_pipeline_complete']
        row['full_native_mentor_reached']=financial['mentor'] is not None
        row['call_trace']+=financial['call_trace']
        row['missing_inputs']=[m for m in row['missing_inputs'] if m['field']!='work3/C7/funding/execution_constraints']
        if not financial['formal_deployment_ready']:
            for issue in financial['issue_codes'] or [{'code':financial['drive_persistence_status'],'field_path':'daily_slice_ledger_receipt'}]:
                row['missing_inputs'].append({'field':issue.get('field_path'),'producer':'ORIGINAL_FAMILY_FINANCIAL_CHAIN',
                    'reason':issue.get('code'),'kind':'NATIVE_CONTRACT_OR_PERSISTENCE_REQUIREMENT',
                    'affects':['canonical deployment readiness'],'original_issue':issue})
        else:
            row['proposed_amount']=financial['canonical_amount']
        row['result_digest']=digest({k:v for k,v in row.items() if k!='result_digest'})
    financial=[r.get('financial_chain') or {} for r in out['positions']]
    all_complete=bool(financial) and all(f.get('formal_deployment_ready') and f.get('mentor') is not None for f in financial)
    # Native shared cash is conserved in the single member ledger; positive
    # plans stay pending until original-ID remote readback has been verified.
    out['full_native_pipeline_complete']=all_complete
    out['full_native_mentor_reached']=all_complete
    out['summary']['full_financial_native_completed']=sum(bool(f.get('full_native_pipeline_complete')) for f in financial)
    out['summary']['formal_financial_ready']=sum(bool(f.get('formal_deployment_ready')) for f in financial)
    if all_complete:
        out['status']='FINANCIAL_PIPELINE_COMPLETE'
        out['canonical_result']={r['symbol']:r['financial_chain']['canonical_v82_output'] for r in out['positions']}
        out['mentor']={r['symbol']:r['financial_chain']['mentor'] for r in out['positions']}
    out['report_digest']=digest({k:v for k,v in out.items() if k!='report_digest'})
    return out

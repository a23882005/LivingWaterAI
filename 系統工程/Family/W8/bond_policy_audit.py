"""Read existing owner records without promoting dated SGOV roles to cash.

The independently trusted document proof owns this evidence. Current W1
targets remain authoritative when they supersede an older document allocation.
Neither the source excerpts nor a policy exception is a native runtime input.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re

from family_input import digest


def _time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('BOND_POLICY_SOURCE_TIMEZONE_REQUIRED')
    return at


def _read(proof,at):
    if not proof.get('source_reference') or _time(proof['source_available_at'])>at:
        raise PermissionError('BOND_POLICY_SOURCE_REFERENCE_OR_TIME_MISMATCH')
    raw=Path(proof['local_source_path']).read_bytes()
    if sha256(raw).hexdigest()!=proof['source_sha256']:
        raise PermissionError('BOND_POLICY_SOURCE_CHANGED')
    return raw.decode('utf-8-sig').splitlines()


def build(request,context):
    proof=context.get('approved_document_target_source')
    if proof is None:return None
    # Some legacy analysis contexts carry only a valuation excerpt. They do
    # not establish a member-scoped owner-policy source.
    if proof.get('schema_version')!='Family.W5.ApprovedDocumentTargetSource.v1':return None
    if proof.get('client_id')!=request['client_id']:
        raise PermissionError('BOND_POLICY_CLIENT_MISMATCH')
    at=_time(request['evaluation_at']);lines=_read(proof,at)
    evidence=[];explicit_ammo=[]
    for number,line in enumerate(lines,1):
        if re.search(r'IBKR內SGOV定位[：:].*美元股票ETF買點彈藥庫',line):
            explicit_ammo.append(number)
        if ('SGOV' in line and any(token in line for token in (
            'SGOV_BOND_BUCKET','SGOV_DRY_POWDER_BUCKET','內部同輪拆分',
            'IBKR內SGOV定位','禁止跨口徑','不得把長期目標'))):
            evidence.append({'line_number':number,'text':line,
                'scope':'DOCUMENTED_ROLE_POLICY_OR_DATED_RECORD__NOT_CURRENT_ROLE_VALUATION'})
    has_bond=any('SGOV_BOND_BUCKET' in r['text'] for r in evidence)
    has_dry=any('SGOV_DRY_POWDER_BUCKET' in r['text'] for r in evidence)
    policy=('EXPLICIT_IBKR_STOCK_OPPORTUNITY_RESERVE' if explicit_ammo else
        'SEPARATE_DEFENSIVE_AND_OPPORTUNITY_ROLES' if has_bond and has_dry else
        'NO_EXPLICIT_SGOV_ROLE_POLICY_FOUND')
    out={'schema_version':'Family.W8.BondPolicyAudit.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'source_target_digest':digest(request['confirmed_target']),
        'project_source':{k:deepcopy(proof[k]) for k in
            ('source_reference','source_sha256','source_available_at')},
        'owner_role_policy':policy,'explicit_ammo_policy_lines':explicit_ammo,
        'role_evidence':evidence,
        'current_role_valuation_status':'NOT_ESTABLISHED_BY_HISTORICAL_DOCUMENT',
        'funding_authority':'NONE__DO_NOT_CONVERT_DEFENSIVE_SGOV_TO_STOCK_CASH',
        'historical_amounts_applied_to_current_holdings':False,
        'target_amounts_applied_to_current_roles':False,
        'current_target_source_kind':request['confirmed_target'].get('source_kind'),
        'rule_exception_evidence':None,'database_written':False,'trade_action':'NO_TRADE'}
    rule=context.get('bond_rule_source')
    if rule is not None:
        rule_lines=_read(rule,at)
        matches=[{'line_number':i,'text':line} for i,line in enumerate(rule_lines,1)
            if '明確帳戶／市場限制' in line and '記錄原因' in line]
        out['rule_exception_evidence']={k:deepcopy(rule[k]) for k in
            ('source_reference','source_sha256','source_available_at')}
        out['rule_exception_evidence'].update(source_lines=matches,
            scope='RULE_ALLOWS_DOCUMENTED_ACCOUNT_OR_MARKET_LIMITATION__NOT_CLIENT_APPROVAL',
            client_exception_approved=False)
    return out


def validate(request,context,report):
    if report.get('bond_policy_audit')!=build(request,context):
        raise PermissionError('BOND_POLICY_AUDIT_REPLAY_MISMATCH')

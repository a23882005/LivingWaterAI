"""Read existing approved document targets into a native analysis input view.

This is not W2 proposal signing or a database mutation. The trusted operator
binds a downloaded, reviewed source and explicit instrument/role mappings.
Original approval timing and capital remain unknown when the source lacks them.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import re


def _digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,
        separators=(',', ':'),allow_nan=False).encode()).hexdigest()


def build_approved_target_view(*, client_id, source_path, source_reference,
        source_available_at, target_version, allocation_version, rows, mappings):
    """Return a lossless target view plus independently trusted source proof.

    rows contain exact original Markdown source_line, source_columns and weight;
    mappings explicitly name instrument_id/ticker/asset_type per original row.
    No amount is calculated from an incomplete investment-pool denominator.
    """
    if not re.fullmatch(r'fam_[0-9a-f]{32}',str(client_id)):
        raise ValueError('TARGET_CLIENT_REQUIRED')
    when=datetime.fromisoformat(source_available_at.replace('Z','+00:00'))
    if when.utcoffset() is None:
        raise ValueError('TARGET_SOURCE_TIMEZONE_REQUIRED')
    if type(target_version) is not int or target_version < 1:
        raise ValueError('TARGET_VERSION_REQUIRED')
    if not source_reference or not allocation_version or not rows or len(rows)!=len(mappings):
        raise ValueError('TARGET_SOURCE_AND_EXPLICIT_MAPPING_REQUIRED')
    path=Path(source_path).resolve(strict=True);raw=path.read_bytes();text=raw.decode('utf-8')
    source_sha=sha256(raw).hexdigest();lines=[];ids=set();total=Decimal(0)
    for row,mapping in zip(rows,mappings):
        line=row['source_line']
        if line not in text.splitlines():raise ValueError('TARGET_ROW_NOT_IN_SOURCE')
        cells=[c.strip().replace('**','') for c in line.strip().strip('|').split('|')]
        weight=Decimal(cells[1].rstrip('%'))/100
        if weight!=Decimal(row['weight']) or not weight.is_finite() or not 0<=weight<=1:
            raise ValueError('TARGET_WEIGHT_SOURCE_MISMATCH')
        if any(not isinstance(mapping.get(k),str) or not mapping[k].strip()
               for k in ('instrument_id','ticker','asset_type')):
            raise ValueError('TARGET_INSTRUMENT_MAPPING_REQUIRED')
        if mapping['instrument_id'] in ids:raise ValueError('TARGET_DUPLICATE_INSTRUMENT_ROLE')
        ids.add(mapping['instrument_id']);total+=weight
        lines.append({**deepcopy(mapping),'weight':{'value':float(weight),'value_state':'KNOWN'},
            'target_amount':{'value_state':'UNKNOWN','amount':None,'currency':None,
                'reason':'CURRENT_COMPLETE_INVESTMENT_POOL_NAV_REQUIRED'},
            'source_reference_ids':[source_reference],
            'original_document_row':line})
    if total!=1:raise ValueError('TARGET_DOCUMENT_TOTAL_NOT_ONE')
    confirmation_run='APPROVED-DOC-'+source_sha[:24]
    allocation_id='DOC-TARGET-'+_digest({'client':client_id,'source':source_sha,'version':allocation_version})[:24]
    draft={'identity':{'client_id':client_id,'run_id':confirmation_run},
        'allocation_id':allocation_id,'target_lines':lines,
        'denominator':{'value_state':'UNKNOWN','amount':None,'currency':None},
        'is_trade_authorized':False,'original_allocation_version':allocation_version}
    draft['draft_hash']=_digest(draft)
    evidence={'action':'READ_EXISTING_APPROVAL','approval_origin':'EXISTING_APPROVED_DOCUMENT',
        'original_confirmed_at':None,'original_confirmed_by':None,
        'confirmed_at':source_available_at,'confirmed_by':'DOCUMENTED_OWNER_DECISION',
        'time_basis':'APPROVAL_RECORD_AVAILABLE_BY__NOT_ORIGINAL_SIGNING_TIME',
        'source_reference_ids':[source_reference]}
    record={'version':target_version,'target_id':allocation_id,'target_hash':draft['draft_hash'],
        'status':'APPROVED_DOCUMENT_VIEW','draft':draft,'confirmation_evidence':evidence,
        'confirmation_evidence_hash':_digest(evidence),'source_reference_ids':[source_reference]}
    view={'source_kind':'EXISTING_APPROVED_DOCUMENT','payload':record,
        'target_hash':record['target_hash'],'target_version':target_version,
        'confirmation_run_id':confirmation_run}
    proof={'schema_version':'Family.W5.ApprovedDocumentTargetSource.v1','client_id':client_id,
        'local_source_path':str(path),'source_sha256':source_sha,
        'source_reference':source_reference,'source_available_at':source_available_at,
        'target_view_digest':_digest(view),'data_provenance':'SOURCE_BACKED'}
    return {'target':view,'trusted_approved_target_source':proof,
        'trade_authorization':'NONE','database_written':False}


def bind_document_account_scope(snapshot, target_pack, *, account_key, broker,
                                broker_source_label, currency, funding_domain):
    """Bind an existing member-local brokerage category for analysis only.

    This never asserts a full brokerage account number, cash availability,
    holdings completeness or authority to read a connected broker account.
    """
    proof=deepcopy(target_pack['trusted_approved_target_source'])
    if snapshot['client_id']!=proof['client_id']:
        raise PermissionError('ACCOUNT_DOCUMENT_CLIENT_MISMATCH')
    matches=[r for r in snapshot['tables']['portfolio_account'] if r['account_key']==account_key]
    if len(matches)!=1:raise ValueError('ACCOUNT_CATEGORY_MISSING_OR_AMBIGUOUS')
    text=Path(proof['local_source_path']).read_text()
    if not broker_source_label or broker_source_label not in text:
        raise ValueError('ACCOUNT_BROKER_NOT_IN_APPROVED_SOURCE')
    if any(not isinstance(v,str) or not v.strip() for v in (broker,currency,funding_domain)):
        raise ValueError('ACCOUNT_CATEGORY_MAPPING_REQUIRED')
    owner={'client_id':snapshot['client_id'],'funding_domain':funding_domain,
        'broker':broker,'account':account_key,'currency':currency}
    return {'schema_version':'Family.W5.DocumentAccountScope.v1','owner':owner,
        'source':proof,'source_snapshot_digest':snapshot['payload_digest'],
        'original_account_row':deepcopy(matches[0]),
        'scope_kind':'MEMBER_LOCAL_BROKER_CATEGORY_ANALYSIS_ONLY',
        'external_broker_account_id':None,'cash_verified':False,
        'holdings_completeness_verified':False,'trade_authorization':'NONE'}

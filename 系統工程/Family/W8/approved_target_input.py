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


def read_document_target_money(text,source_line):
    """Read only the exact approved table row and its currency-labelled header.

    A displayed approximate conversion remains secondary evidence. An absent
    row/amount never becomes zero; no current NAV or FX is manufactured.
    """
    lines=text.splitlines();found=[]
    for index,line in enumerate(lines):
        if line!=source_line:continue
        cells=[v.strip().replace('**','') for v in line.strip().strip('|').split('|')]
        header=None
        for prior in reversed(lines[max(0,index-30):index]):
            if not prior.strip():break
            cols=[v.strip().replace('**','') for v in prior.strip().strip('|').split('|')]
            if len(cols)==len(cells) and any('目標' in c for c in cols) and not any(re.fullmatch(r':?-+:?',c) for c in cols):
                # Skip other data rows; a header must name the asset and amount.
                if any(c in ('標的','子桶','資產') for c in cols):header=cols;break
        if header is None:continue
        for position,(label,value) in enumerate(zip(header,cells)):
            if not ('目標金額' in label or '目標台幣' in label or '目標美元' in label):continue
            currency='TWD' if 'NT$' in label or '台幣' in label or 'NT$' in value else 'USD' if 'US$' in label or '美元' in label or 'US$' in value else None
            if currency is None:continue
            cleaned=value.replace('NT$','').replace('US$','').replace(',','').strip()
            if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',cleaned):continue
            amount=Decimal(cleaned)
            if not amount.is_finite() or amount<0:continue
            found.append({'value_state':'KNOWN','amount':str(amount),'currency':currency,
                'source_row':source_line,'source_column':label,'source_column_index':position,
                'scope':'EXISTING_APPROVED_TARGET__NOT_CURRENT_NAV'})
    unique={(r['amount'],r['currency']) for r in found}
    if len(unique)==1:return found[0]
    return {'value_state':'UNKNOWN','amount':None,'currency':None,
        'reason':'APPROVED_TABLE_AMOUNT_OR_CURRENCY_MISSING' if not unique else 'APPROVED_TABLE_AMOUNT_AMBIGUOUS'}


def enrich_document_target_view(target,proof):
    """Repair a read-only source mapping, retaining the same approved weights.

    No signing event, approval version or DB row is created. The new view hash
    is derived from the unchanged source; the old view is retained in lineage.
    """
    if target.get('source_kind')!='EXISTING_APPROVED_DOCUMENT':return deepcopy(target),deepcopy(proof)
    path=Path(proof['local_source_path']);raw=path.read_bytes()
    if sha256(raw).hexdigest()!=proof['source_sha256'] or _digest(target)!=proof['target_view_digest']:
        raise PermissionError('APPROVED_TARGET_SOURCE_OR_VIEW_CHANGED')
    text=raw.decode('utf-8-sig');view=deepcopy(target);record=view['payload'];draft=record['draft'];changed=False
    for line in draft['target_lines']:
        original=line.get('original_document_row')
        if not original or original not in text.splitlines():raise PermissionError('APPROVED_TARGET_ROW_NOT_IN_SOURCE')
        money=read_document_target_money(text,original)
        current=line.get('target_amount',{})
        if current.get('value_state')=='KNOWN':
            if money.get('value_state')=='KNOWN' and (Decimal(str(current['amount']))!=Decimal(money['amount']) or current['currency']!=money['currency']):
                raise ValueError('APPROVED_TARGET_AMOUNT_SOURCE_CONFLICT')
            continue
        if money['value_state']=='KNOWN':line['target_amount']=money;changed=True
    amounts=[r['target_amount'] for r in draft['target_lines']]
    currencies={a.get('currency') for a in amounts}
    if all(a.get('value_state')=='KNOWN' for a in amounts) and len(currencies)==1:
        denominator={'value_state':'KNOWN','amount':str(sum((Decimal(a['amount']) for a in amounts),Decimal(0))),
            'currency':next(iter(currencies)),'scope':'SUM_OF_APPROVED_TARGET_AMOUNTS__NOT_CURRENT_MARKET_NAV'}
        if draft.get('denominator')!=denominator:draft['denominator']=denominator;changed=True
    if not changed:return view,deepcopy(proof)
    draft['source_mapping_lineage']={'previous_view_digest':_digest(target),'previous_target_hash':target['target_hash'],
        'source_sha256':proof['source_sha256'],'operation':'READ_EXISTING_EXPLICIT_AMOUNTS','approval_unchanged':True}
    draft['draft_hash']=_digest({k:v for k,v in draft.items() if k!='draft_hash'})
    record['target_hash']=view['target_hash']=draft['draft_hash']
    mapped=deepcopy(proof);mapped['target_view_digest']=_digest(view)
    return view,mapped


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
            'target_amount':read_document_target_money(text,line),
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


def bind_official_holdings(snapshot, *, official_file_id, account_key,
                          owner_decision, evaluation_at):
    """Apply an operator-recorded Owner decision to the existing official DB.

    The decision is trusted executor context, not a menu payload. It accepts
    existing holdings as the analysis baseline, without creating a portfolio,
    changing quantities, dating old observations anew, or asserting cash.
    The receipt is bound to one member, official File ID and exact DB bytes.
    """
    client=snapshot.get('client_id')
    decision=deepcopy(owner_decision)
    if (snapshot.get('schema_version')!='Family.W5.W1Snapshot.v1'
        or snapshot.get('data_provenance')!='SOURCE_BACKED'
        or snapshot.get('payload_digest')!=_digest(snapshot.get('tables'))
        or not re.fullmatch(r'[0-9a-f]{64}',str(snapshot.get('source_sha256','')))):
        raise ValueError('OFFICIAL_HOLDINGS_SNAPSHOT_REQUIRED')
    if (decision.get('schema_version')!='Family.W8.OwnerOfficialHoldingsDecision.v1'
        or decision.get('action')!='ACCEPT_EXISTING_OFFICIAL_HOLDINGS'
        or not decision.get('source_reference') or not decision.get('statement')
        or decision.get('client_id')!=client
        or decision.get('official_file_id')!=official_file_id
        or decision.get('source_db_sha256')!=snapshot['source_sha256']):
        raise PermissionError('OFFICIAL_HOLDINGS_OWNER_DECISION_MISMATCH')
    at=datetime.fromisoformat(evaluation_at.replace('Z','+00:00'))
    decided=datetime.fromisoformat(decision['recorded_at'].replace('Z','+00:00'))
    if at.utcoffset() is None or decided.utcoffset() is None or decided>at:
        raise ValueError('OFFICIAL_HOLDINGS_DECISION_TIME_INVALID')
    accounts=snapshot['tables'].get('portfolio_account',[])
    if sum(r.get('account_key')==account_key and r.get('client_id')==client for r in accounts)!=1:
        raise ValueError('OFFICIAL_HOLDINGS_ACCOUNT_REQUIRED')
    return {'state':'COMPLETE','account_key':account_key,
        'snapshot_digest':snapshot['payload_digest'],
        'as_of':decision['recorded_at'],
        'as_of_basis':'OWNER_ACCEPTANCE_RECORDED_AT__POSITION_OBSERVATIONS_UNCHANGED',
        'source_reference':decision['source_reference'],
        'schema_version':'Family.W8.OfficialHoldingsAcceptance.v1',
        'client_id':client,'official_file_id':official_file_id,
        'source_db_sha256':snapshot['source_sha256'],
        'owner_decision':decision,'owner_decision_digest':_digest(decision),
        'holdings_status':'OFFICIAL','cash_settlement_asserted':False,
        'database_written':False,'trade_authorization':'NONE'}

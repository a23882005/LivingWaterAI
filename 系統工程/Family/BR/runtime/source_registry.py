"""Pinned W5 snapshot registry. Archival reads are distinct from decision data.

All paths are relative to the W5 market_intake directory. The registry digest
is supplied by the release manifest, never accepted from the replay request.
Historical per-bar publication evidence remains an explicit upstream gap.
"""
from pathlib import Path
import hashlib
import json
import csv
from copy import deepcopy
from replay import ReplayError, digest, instant, verify_lineage


def _path(root, name):
    base=Path(root).resolve();p=(base/name).resolve()
    if Path(name).is_absolute() or not p.is_relative_to(base):
        raise ReplayError('REGISTRY_PATH_OUTSIDE_ROOT')
    return p


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build_registry(root, audit, *, trusted_audit_sha256):
    if digest(audit)!=trusted_audit_sha256:raise ReplayError('AUDIT_DIGEST_MISMATCH')
    if not audit.get('entries'):raise ReplayError('EMPTY_AUDIT')
    entries=[];seen=set()
    for row in audit['entries']:
        if row['status']!='PASS':raise ReplayError('AUDIT_NOT_PASSED')
        file=row['file'];csv_path=_path(root,file)
        receipt_name=file+'.result.json';receipt_path=_path(root,receipt_name)
        context_name=Path(file).stem+'.family_context.json';context_path=_path(root,context_name)
        if _sha(csv_path)!=row['sha256'] or _sha(receipt_path)!=row['receipt_sha256']:
            raise ReplayError('REGISTRY_SOURCE_CHANGED')
        receipt=json.loads(receipt_path.read_text());meta=receipt['source_metadata']
        context=json.loads(context_path.read_text())
        if context['technical_source']['sha256']!=row['sha256']:
            raise ReplayError('REGISTRY_RAW_BINDING')
        parsed=list(csv.DictReader(csv_path.read_text(encoding='utf-8-sig').splitlines()))
        if digest(parsed)!=row['canonical_history_sha256'] or parsed!=receipt['source_history']:
            raise ReplayError('REGISTRY_ROWS_CHANGED')
        if meta.get('artifact_written_at')!=row['snapshot_available_at'] or meta.get('symbol')!=row['symbol']:
            raise ReplayError('REGISTRY_METADATA_MISMATCH')
        instant(row['snapshot_available_at'])
        key=(row['symbol'],row['snapshot_available_at'])
        if key in seen:raise ReplayError('DUPLICATE_REGISTRY_ENTRY')
        seen.add(key)
        # Derive gaps from original metadata rather than accepting audit labels.
        gaps=[]
        if meta.get('split_basis_verified') is not True:gaps.append('SPLIT_BASIS_UNVERIFIED')
        if not meta.get('historical_publication_evidence'):gaps.append('PER_BAR_PUBLICATION_UNPROVEN')
        if not meta.get('dividend_return_convention'):gaps.append('DIVIDEND_RETURN_CONVENTION_UNCONFIRMED')
        entries.append({'symbol':row['symbol'],'file':file,'sha256':row['sha256'],
            'canonical_history_sha256':row['canonical_history_sha256'],
            'receipt_file':receipt_name,'receipt_sha256':row['receipt_sha256'],
            'context_file':context_name,'context_sha256':_sha(context_path),
            'available_at':row['snapshot_available_at'],'row_count':len(parsed),
            'source_reference':meta.get('source_reference'),'data_kind':'SOURCE_BACKED',
            'availability_kind':'CAPTURE_COMPLETION_UPPER_BOUND',
            'history_gaps':gaps,'decision_basis_review':'NOT_REVIEWED',
            'price_field':meta.get('price_field'),'auto_adjust':meta.get('auto_adjust')})
    return {'schema_version':'Family.BR.SourceRegistry.v1','audit_sha256':trusted_audit_sha256,
        'entries':sorted(entries,key=lambda e:(e['symbol'],e['available_at'])),
        'per_bar_historical_evidence':'OPEN','trade_authorization':'NONE'}


def read_snapshot(root, registry, *, trusted_registry_sha256, symbol, cutoff,
                  purpose='DECISION_INPUT'):
    if digest(registry)!=trusted_registry_sha256:raise ReplayError('REGISTRY_DIGEST_MISMATCH')
    if registry.get('schema_version')!='Family.BR.SourceRegistry.v1':raise ReplayError('REGISTRY_SCHEMA')
    if purpose not in ('ARCHIVE_READ_ONLY','DECISION_INPUT','HISTORICAL_REPLAY'):
        raise ReplayError('UNKNOWN_SOURCE_PURPOSE')
    limit=instant(cutoff)
    choices=[e for e in registry['entries'] if e['symbol']==symbol and instant(e['available_at'])<=limit]
    if not choices:raise ReplayError('NO_SOURCE_AVAILABLE_AT_CUTOFF')
    choices.sort(key=lambda e:instant(e['available_at']))
    selected=choices[-1]
    if len(choices)>1 and instant(choices[-2]['available_at'])==instant(selected['available_at']):
        raise ReplayError('AMBIGUOUS_SOURCE_REVISION')
    # Registry v1 only implements reviewed artifact identity, not approval of
    # investment conventions or historical per-bar availability.
    if purpose=='HISTORICAL_REPLAY':raise ReplayError('PER_BAR_PUBLICATION_UNPROVEN')
    if purpose=='DECISION_INPUT':raise ReplayError('DECISION_BASIS_REVIEW_REQUIRED')
    for name,key in [('file','sha256'),('receipt_file','receipt_sha256'),('context_file','context_sha256')]:
        if _sha(_path(root,selected[name]))!=selected[key]:raise ReplayError('REGISTERED_SOURCE_CHANGED')
    rows=list(csv.DictReader(_path(root,selected['file']).read_text(encoding='utf-8-sig').splitlines()))
    if digest(rows)!=selected['canonical_history_sha256'] or len(rows)!=selected['row_count']:
        raise ReplayError('REGISTERED_ROWS_CHANGED')
    def node(payload,parents):
        body={'payload':payload,'parents':parents};return {**body,'sha256':digest(body)}
    nodes={'registry':node({'sha256':trusted_registry_sha256},[]),
           'source':node(deepcopy(selected),['registry']),
           'selection':node({'symbol':symbol,'cutoff':cutoff,'purpose':purpose,
               'row_hash':digest(rows)},['source'])}
    verify_lineage(nodes,'selection')
    return {'schema_version':'Family.BR.SelectedSnapshot.v1','symbol':symbol,
        'purpose':purpose,'decision_eligible':False,'historical_pit_verified':False,
        'available_at':selected['available_at'],'rows':rows,'history_gaps':deepcopy(selected['history_gaps']),
        'lineage':nodes,'lineage_root':'selection','trade_authorization':'NONE'}

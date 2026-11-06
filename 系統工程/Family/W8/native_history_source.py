"""Replay source-owner native history arguments from pinned original files.

This is an optional transport for the existing approved-source input route.
It checks provenance bytes and run scope, without approving publication/PIT,
calendar or event semantics. The unchanged native producers still decide
qP/qV and the unchanged PV2 consumer still checks listing/currency/primary.
Public-history observations are never promoted into this route.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

from family_input import digest
from member_market_source import time


def _read(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('NATIVE_HISTORY_SOURCE_BYTES_CHANGED')
    return json.loads(raw)


def read(descriptor,request,symbol):
    data=_read(descriptor)
    expected={k:request[k] for k in ('client_id','run_id','evaluation_at','owner')}
    expected.update(asset_id=symbol,source_db_sha256=request['client_snapshot']['payload']['source_sha256'])
    if (data.get('schema_version')!='Family.W8.NativeHistorySource.v1'
        or any(data.get(k)!=v for k,v in expected.items())
        or not data.get('source_reference')
        or time(data['available_at'])>time(request['evaluation_at'])):
        raise PermissionError('NATIVE_HISTORY_MEMBER_RUN_DB_OWNER_OR_TIME_MISMATCH')
    sources=data.get('original_sources');histories=data.get('histories')
    if (not isinstance(sources,list) or not sources or not isinstance(histories,dict)
        or not histories or set(histories)-{'price_history','valuation_history'}):
        raise PermissionError('NATIVE_HISTORY_ORIGINALS_AND_NAMED_INPUTS_REQUIRED')
    pinned={}
    for source in sources:
        raw=Path(source['local_path']).read_bytes();actual=sha256(raw).hexdigest()
        if (actual!=source['sha256'] or not source.get('source_reference')
            or time(source['retrieved_at'])>time(request['evaluation_at'])):
            raise PermissionError('NATIVE_HISTORY_ORIGINAL_BYTES_OR_ACQUISITION_MISMATCH')
        pinned[actual]=deepcopy(source)
    result={};hashes=set()
    def check(value):
        if isinstance(value,dict):
            if 'source_hash' in value:
                fingerprint=value['source_hash']
                if not isinstance(fingerprint,str) or fingerprint not in pinned:
                    raise PermissionError('NATIVE_HISTORY_REFERENCED_ORIGINAL_NOT_PINNED')
                if value.get('retrieved_at') and time(value['retrieved_at'])>time(request['evaluation_at']):
                    raise PermissionError('NATIVE_HISTORY_ROW_ACQUISITION_AFTER_CUTOFF')
                hashes.add(fingerprint)
            for child in value.values():check(child)
        elif isinstance(value,list):
            for child in value:check(child)
    for key,source in histories.items():
        arguments=_read(source)
        if (arguments.get('identity',{}).get('asset_id')!=symbol
            or arguments.get('decision_at')!=request['evaluation_at']):
            raise PermissionError('NATIVE_HISTORY_ARGUMENT_ASSET_OR_CUTOFF_MISMATCH')
        check(arguments)
        # Externally pinned calendar and normalized arguments are replayed
        # exactly. No missing approval, knowledge time, receipt or action
        # coverage flag is inserted here, even when hashes match.
        result[key]=arguments
    if not hashes:
        raise PermissionError('NATIVE_HISTORY_REFERENCED_ORIGINAL_REQUIRED')
    receipt=dict(schema_version='Family.W8.NativeHistoryReadback.v1',**expected,
        source_descriptor=deepcopy(descriptor),argument_sources=deepcopy(histories),
        original_sources=[pinned[k] for k in sorted(pinned)],referenced_original_sha256=sorted(hashes),
        argument_digests={k:digest(v) for k,v in result.items()},
        original_publication_semantics_independently_verified=False,
        native_qualification_replay_required=True,financial_gate_released=False,trade_action='NO_TRADE')
    receipt['digest']=digest(receipt)
    return result,receipt

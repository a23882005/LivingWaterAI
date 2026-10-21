"""Offline replay guards. No network, database writes, or trading side effects.

Trusted callers supply the source lock and an isolated engine adapter. A data
checksum establishes integrity, not historical publication time or authority.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


class ReplayError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def instant(value):
    if not isinstance(value, str):
        raise ReplayError('INVALID_TIME')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ReplayError('INVALID_TIME') from exc
    if dt.tzinfo is None:
        raise ReplayError('TIMEZONE_REQUIRED')
    return dt.astimezone(timezone.utc)


def verify_files(root, manifest):
    """Manifest must be pinned by the caller independently of replay input."""
    root = Path(root).resolve()
    if not manifest:
        raise ReplayError('EMPTY_SOURCE_LOCK')
    for relative, expected in manifest.items():
        path = (root / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(root):
            raise ReplayError('PATH_OUTSIDE_ROOT')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ReplayError('SOURCE_HASH_MISMATCH:' + relative)
    return len(manifest)


def select_vintage(rows, cutoff):
    """Latest available revision per series; cutoff inclusive; ties fail closed.

    Rows: series_id, available_at, observation_at, revision, evidence_ref, value.
    One observation per series per call; callers group an entire time series by
    observation first. Mixing observations is rejected rather than dropping one.
    Evidence references must be substantiated by the upstream source registry.
    No value from a future publication is returned.
    """
    limit = instant(cutoff)
    selected = {}
    for row in rows:
        required = {'series_id','available_at','observation_at','revision','evidence_ref','value'}
        if not required <= row.keys() or not all(row[k] for k in required - {'value'}):
            raise ReplayError('VINTAGE_METADATA_REQUIRED')
        available, observation = instant(row['available_at']), instant(row['observation_at'])
        if observation > available:
            raise ReplayError('OBSERVATION_AFTER_PUBLICATION')
        if available > limit:
            continue
        key = row['series_id']
        previous = selected.get(key)
        if previous and instant(previous['observation_at']) != observation:
            raise ReplayError('MIXED_OBSERVATIONS_GROUP_REQUIRED')
        if previous and instant(previous['available_at']) == available and previous != row:
            raise ReplayError('AMBIGUOUS_VINTAGE')
        if previous is None or instant(previous['available_at']) < available:
            selected[key] = deepcopy(row)
    return selected


def verify_lineage(nodes, root_id):
    """Hash and traverse all ancestors. Nodes carry payload and parent IDs."""
    if root_id not in nodes:
        raise ReplayError('MISSING_LINEAGE_ROOT')
    visiting, done = set(), set()
    def visit(key):
        if key in visiting:
            raise ReplayError('LINEAGE_CYCLE')
        if key in done:
            return
        if key not in nodes:
            raise ReplayError('BROKEN_LINEAGE')
        node = nodes[key]
        if set(node) != {'payload','parents','sha256'} or not isinstance(node['parents'], list):
            raise ReplayError('LINEAGE_SCHEMA')
        if digest({'payload':node['payload'],'parents':node['parents']}) != node['sha256']:
            raise ReplayError('LINEAGE_HASH_MISMATCH')
        visiting.add(key)
        for parent in node['parents']:
            visit(parent)
        visiting.remove(key)
        done.add(key)
    visit(root_id)
    if done != set(nodes):
        raise ReplayError('UNREFERENCED_LINEAGE')
    return len(done)


def validate_event(event, expected_client, expected_versions, mode='SYNTHETIC'):
    required = {'schema_version','event_id','client_id','account_id','funding_domain_id',
        'event_time','snapshot_id','data_kind','versions','input','input_sha256',
        'portfolio_before','portfolio_after','value_state','issue_codes','sources'}
    if not required <= event.keys():
        raise ReplayError('EVENT_FIELDS_REQUIRED')
    for key in ('event_id','account_id','funding_domain_id','snapshot_id'):
        if not isinstance(event[key], str) or not event[key].strip():
            raise ReplayError('EVENT_IDENTITY_REQUIRED')
    if event['schema_version'] != 'Family.BR.Event.v1':
        raise ReplayError('EVENT_VERSION')
    if event['client_id'] != expected_client:
        raise ReplayError('CLIENT_MISMATCH')
    if not expected_versions or event['versions'] != expected_versions:
        raise ReplayError('ENGINE_VERSION_MISMATCH')
    if mode not in ('SYNTHETIC','HISTORICAL') or event['data_kind'] != mode:
        raise ReplayError('DATA_KIND_MISMATCH')
    instant(event['event_time'])
    if digest(event['input']) != event['input_sha256']:
        raise ReplayError('INPUT_HASH_MISMATCH')
    if event['value_state'] != 'KNOWN' or event['issue_codes'] != []:
        raise ReplayError('INPUT_QUALITY_BLOCK')
    for side in ('portfolio_before','portfolio_after'):
        if not isinstance(event[side], list):
            raise ReplayError('PORTFOLIO_SCHEMA')
        for row in event[side]:
            for key in ('client_id','account_id','funding_domain_id'):
                if row.get(key) != event[key]:
                    raise ReplayError('PORTFOLIO_SCOPE_MISMATCH')
    if not isinstance(event['sources'], list) or not event['sources']:
        raise ReplayError('SOURCES_REQUIRED')
    for row in event['sources']:
        if not {'source_id','sha256','payload','basis','evidence_ref'} <= row.keys():
            raise ReplayError('SOURCE_FIELDS_REQUIRED')
        if not row['source_id'] or not row['evidence_ref']:
            raise ReplayError('SOURCE_EVIDENCE_REQUIRED')
        if digest(row['payload']) != row['sha256']:
            raise ReplayError('SOURCE_PAYLOAD_MISMATCH')
        # The upstream provider defines the basis, never inferred from prices.
        if row['basis'] not in ('RAW','SPLIT_ADJUSTED','TOTAL_RETURN','NOT_APPLICABLE'):
            raise ReplayError('UNKNOWN_PRICE_BASIS')
        if mode == 'HISTORICAL':
            if not row.get('available_at') or not row.get('publication_evidence'):
                raise ReplayError('HISTORICAL_AVAILABILITY_UNPROVEN')
            if instant(row['available_at']) > instant(event['event_time']):
                raise ReplayError('LOOK_AHEAD')
    return deepcopy(event)


def differences(expected, actual, path='$'):
    if type(expected) is not type(actual):
        return [{'path':path,'expected':expected,'actual':actual}]
    if isinstance(expected, dict):
        result = []
        for key in sorted(expected.keys() | actual.keys()):
            child = path + '[' + json.dumps(key) + ']'
            if key not in expected or key not in actual:
                result.append({'path':child,'expected_present':key in expected,
                    'actual_present':key in actual})
            else:
                result.extend(differences(expected[key], actual[key], child))
        return result
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [{'path':path,'expected_length':len(expected),'actual_length':len(actual)}]
        return [d for i,(a,b) in enumerate(zip(expected,actual))
            for d in differences(a,b,f'{path}[{i}]')]
    return [] if expected == actual else [{'path':path,'expected':expected,'actual':actual}]


def replay(event, *, engine, expected_client, expected_versions, source_root,
           source_lock, golden, mode='SYNTHETIC'):
    """Two fresh computations, not a cached result. Engine must be side-effect-free.

    Golden is independently pinned; no output is learned as its own expected.
    This function deliberately does not claim OS-level sandboxing of callbacks.
    """
    verify_files(source_root, source_lock)
    clean = validate_event(event, expected_client, expected_versions, mode)
    before = digest(clean)
    first = engine(deepcopy(clean['input']))
    second = engine(deepcopy(clean['input']))
    verify_files(source_root, source_lock)
    if digest(clean) != before:
        raise ReplayError('EVENT_MUTATED')
    diff = differences(golden, first)
    repeat_diff = differences(first, second)
    return {'schema_version':'Family.BR.Replay.v1','event_id':clean['event_id'],
        'data_kind':mode,'status':'PASS' if not diff and not repeat_diff else 'FAIL',
        'golden_diff':diff,'repeat_diff':repeat_diff,'result':first,
        'result_sha256':digest(first),'executions':2,'trade_authorization':'NONE'}

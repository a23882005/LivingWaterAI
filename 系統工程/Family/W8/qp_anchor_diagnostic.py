"""Read-only qP explanation from two pinned, saved native snapshots.

This sidecar is never a decision input. It replays the existing own-history
producer; it neither qualifies new sources nor calculates an alternative qP.
Snapshot descriptors must come from the caller's trusted evidence inventory.
A file hash proves integrity, not provider authenticity or historical custody.
"""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / '系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
from livingwater_v82_runtime.own_history import (  # noqa: E402
    IDENTITY, own_wealth, price_percentile, time,
)

SCHEMA = 'Family.W8.QPAnchorSnapshot.v1'
METHOD = 'V82_QP_ANCHOR_DIAGNOSTIC_V1'
INSUFFICIENT = 'INSUFFICIENT_OR_INCOMPARABLE_SOURCE'


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def capture_snapshot(price_history_input, *, run_id, saved_at, source_reference):
    """Build an artifact for immediate persistence; never backfill a prior run."""
    source = deepcopy(price_history_input)
    result = price_percentile(**source) if source is not None else None
    body = dict(schema_version=SCHEMA, run_id=run_id, saved_at=saved_at,
                source_reference=source_reference, price_history_input=source,
                input_digest=digest(source), qP_result=result)
    return {**body, 'snapshot_digest': digest(body)}


def _read(descriptor):
    raw = Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest() != descriptor['sha256']:
        raise ValueError('SNAPSHOT_FILE_HASH_MISMATCH')
    artifact = json.loads(raw)
    body = {k: v for k, v in artifact.items() if k != 'snapshot_digest'}
    if (artifact.get('schema_version') != SCHEMA
            or artifact.get('snapshot_digest') != digest(body)
            or not artifact.get('run_id') or not artifact.get('source_reference')):
        raise ValueError('SNAPSHOT_ENVELOPE_INVALID')
    source = artifact.get('price_history_input')
    if artifact.get('input_digest') != digest(source):
        raise ValueError('SNAPSHOT_INPUT_HASH_MISMATCH')
    if not source:
        raise ValueError('CURRENT_OR_PREVIOUS_PRICE_HISTORY_UNAVAILABLE')
    saved, cutoff = time(artifact['saved_at']), time(source['decision_at'])
    if saved < cutoff:
        raise ValueError('SNAPSHOT_SAVED_BEFORE_DECISION')
    def retrievals(value):
        if isinstance(value, dict):
            if value.get('retrieved_at'):
                yield time(value['retrieved_at'])
            for child in value.values():
                yield from retrievals(child)
        elif isinstance(value, list):
            for child in value:
                yield from retrievals(child)
    if any(retrieved > saved for retrieved in retrievals(source)):
        raise ValueError('SOURCE_RETRIEVED_AFTER_SNAPSHOT_WAS_SAVED')
    qp = price_percentile(**source)
    if qp != artifact.get('qP_result'):
        raise ValueError('SAVED_NATIVE_QP_REPLAY_MISMATCH')
    if qp.get('status') != 'COMPLETE':
        raise ValueError('NATIVE_QP_UNKNOWN:' + ','.join(qp.get('reason_codes', [])))
    wealth = own_wealth(**{k: source[k] for k in
                          ('identity', 'bars', 'actions', 'calendar', 'decision_at')})
    if wealth['status'] != 'COMPLETE':
        raise ValueError('NATIVE_WEALTH_INCOMPLETE')
    rows = wealth['rows']
    window = rows[-252:]
    if len(window) != 252:
        raise ValueError('CONTIGUOUS_252_SESSIONS_REQUIRED')
    high = max(Decimal(r['wealth']) for r in window)
    anchor = next(r['session_id'] for r in reversed(window) if Decimal(r['wealth']) == high)
    if qp['current_stress']['anchor'] != anchor:
        raise ValueError('NATIVE_ANCHOR_CONFLICT')
    summary = dict(anchor_session=anchor, H=str(high), W=rows[-1]['wealth'],
                   decision_at=source['decision_at'], saved_at=artifact['saved_at'],
                   window_start_session=window[0]['session_id'],
                   window_end_session=window[-1]['session_id'],
                   window_session_ids=[r['session_id'] for r in window],
                   window_session_ids_digest=digest([r['session_id'] for r in window]),
                   snapshot_digest=artifact['snapshot_digest'],
                   source_digest=artifact['input_digest'], file_sha256=descriptor['sha256'],
                   run_id=artifact['run_id'], source_reference=artifact['source_reference'])
    return dict(artifact=artifact, source=source, qp=qp, rows=rows, window=window,
                summary=summary, wealth_method=wealth['method_id'],
                profile_version=wealth['profile_version'])


def _comparable(previous, current):
    p, c = previous['source'], current['source']
    if time(p['decision_at']) >= time(c['decision_at']):
        raise ValueError('PREVIOUS_DECISION_NOT_EARLIER')
    if time(previous['artifact']['saved_at']) > time(c['decision_at']):
        raise ValueError('PREVIOUS_SNAPSHOT_NOT_SAVED_BY_CURRENT_DECISION')
    if any(p['identity'].get(k) != c['identity'].get(k) for k in (*IDENTITY, 'price_basis')):
        raise ValueError('IDENTITY_OR_WEALTH_METHOD_CONFLICT')
    if (previous['wealth_method'], previous['profile_version']) != (
            current['wealth_method'], current['profile_version']):
        raise ValueError('NATIVE_WEALTH_METHOD_CONFLICT')
    if p['comparable_from'] != c['comparable_from']:
        raise ValueError('COMPARABLE_REGIME_CONFLICT')
    if any(p['calendar'].get(k) != c['calendar'].get(k)
           for k in ('calendar_id', 'version', 'timezone')):
        raise ValueError('CALENDAR_LINEAGE_CONFLICT')
    # Full prefix equality prevents seed changes, revisions, omitted sessions or
    # changed events from being mistaken for economic reanchoring. Receipt hashes
    # and retrieval times may legitimately change in a later acquisition.
    prows, crows = previous['rows'], current['rows']
    keys = ('session_id', 'close', 'wealth', 'log_return', 'segment', 'knowledge_at')
    if len(crows) < len(prows) or any(
            any(a.get(k) != b.get(k) for k in keys) for a, b in zip(prows, crows)):
        raise ValueError('HISTORICAL_WEALTH_PREFIX_CONFLICT')
    def sessions(source):
        return [{k: r[k] for k in ('session_id', 'close_at', 'knowledge_at')}
                for r in source['calendar']['sessions'][:len(prows)]]
    ps, cs = sessions(p), sessions(c)
    if ps != cs:
        raise ValueError('HISTORICAL_SESSION_PREFIX_CONFLICT')
    cutoff = time(p['decision_at'])
    def periods(source):
        return [{k: r[k] for k in ('period_id', 'cadence', 'start', 'end')}
                for r in source['calendar']['completed_periods'] if time(r['end']) <= cutoff]
    if periods(p) != periods(c):
        raise ValueError('HISTORICAL_PERIOD_PREFIX_CONFLICT')
    last = prows[-1]['session_id']
    def events(source):
        receipt_keys = {'source_hash', 'retrieved_at', 'source_reference', 'revision_id'}
        return sorted(({k: v for k, v in r.items() if k not in receipt_keys}
                       for r in source['actions'].get('events', []) if r['ex_session'] <= last),
                      key=lambda r: r['event_id'])
    if events(p) != events(c):
        raise ValueError('HISTORICAL_EVENT_PREFIX_CONFLICT')


def diagnose(current, previous=None):
    """Read pinned files and return an explanation, without mutating either run."""
    out = dict(method_id=METHOD, status='UNKNOWN', reason_code=INSUFFICIENT,
               warning_codes=[], previous=None, current=None,
               identity_method_lineage={}, reason_evidence=[], missing_inputs=[],
               anchor_change_is_recovery_evidence=False,
               legacy_anchor_changed=None,
               interpretation='來源不足或不可比較，無法判定換錨原因；診斷不改任何正式決策。')
    try:
        c = _read(current)
        out['current'] = c['summary']
        out['legacy_anchor_changed'] = c['qp']['anchor_changed']
        identity = c['source']['identity']
        calendar = c['source']['calendar']
        out['identity_method_lineage'] = {
            **{k: identity[k] for k in IDENTITY}, 'quote_currency': identity['currency'],
            'wealth_method_id': c['wealth_method'],
            'wealth_method_version': c['profile_version'],
            'calendar_id': calendar['calendar_id'], 'calendar_version': calendar['version'],
            'calendar_timezone': calendar['timezone'],
        }
        if previous is None:
            out.update(reason_code='PREVIOUS_ANCHOR_UNKNOWN',
                       missing_inputs=['TRUSTED_PREVIOUS_SNAPSHOT_WITH_ANCHOR_H_W'],
                       interpretation='本輪資料有效，但缺可信前輪錨、H、W快照，換錨原因未知。')
            return out
        p = _read(previous)
        out['previous'] = p['summary']
        _comparable(p, c)
        ph, ch = Decimal(p['summary']['H']), Decimal(c['summary']['H'])
        pw, cw = Decimal(p['summary']['W']), Decimal(c['summary']['W'])
        pa, ca = p['summary']['anchor_session'], c['summary']['anchor_session']
        window_ids = {r['session_id'] for r in c['window']}
        if pa == ca and ph == ch:
            reason, evidence = 'UNCHANGED', ['same_verified_anchor_and_H']
            text = '兩輪可比含息財富序列的高點與錨均相同。'
        elif ch > ph and ca > p['rows'][-1]['session_id']:
            reason, evidence = 'NEW_HIGH', ['current_H_gt_previous_H', 'new_completed_session_high']
            text = '新增合法交易日的含息財富W創新高；此診斷不表示可交易。'
        elif pa not in window_ids and ch < ph:
            reason = 'OLD_HIGH_EXPIRED_ROLLDOWN'
            evidence = ['previous_anchor_not_in_current_252_sessions', 'current_H_lt_previous_H']
            text = '舊高點退出252日視窗，新的H較低。'
            if cw <= pw:
                out['warning_codes'] = ['NO_PRICE_RECOVERY_OBSERVED']
                text += '本輪含息財富W未較前輪上升；未另驗原始市價C，不能據此判定市價復甦或安全改善。'
            else:
                text += '含息財富W有所回升，但降錨原因仍為舊峰退出；未另驗原始市價C。'
        elif pa != ca and ph == ch and ca > pa:
            reason, evidence = 'EQUAL_HIGH_REANCHOR', ['same_H', 'latest_equal_high_session_selected_by_native']
            text = '含息財富W出現同高點，依正式同高取最新交易日規則換錨。'
        else:
            # No verified named residual mechanism is supported yet. In
            # particular a still-present high cannot simply disappear.
            raise ValueError('UNEXPLAINED_OR_CONTRADICTORY_ANCHOR_CHANGE')
        out.update(status='KNOWN', reason_code=reason, reason_evidence=evidence,
                   interpretation=text)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        out['missing_inputs'] = [str(error)]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', required=True)
    parser.add_argument('--current-sha256', required=True)
    parser.add_argument('--previous')
    parser.add_argument('--previous-sha256')
    args = parser.parse_args()
    if bool(args.previous) != bool(args.previous_sha256):
        parser.error('previous path and SHA-256 must be supplied together')
    previous = dict(local_path=args.previous, sha256=args.previous_sha256) if args.previous else None
    print(json.dumps(diagnose(dict(local_path=args.current, sha256=args.current_sha256), previous),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Read a confirmed W1 allocation without creating a W2 signing event.

The current official snapshot owns weights and confirmation history. An
independently bound approved investment-pool statement owns the money base;
neither current holdings nor available cash is substituted for that base.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re

from family_input import digest


def _time(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('OFFICIAL_TARGET_TIMEZONE_REQUIRED')
    return value


def read_base(source):
    """Validate an exact approved source line with an explicit money unit."""
    if not source or not source.get('source_reference'):
        raise ValueError('OFFICIAL_TARGET_APPROVED_BASE_REQUIRED')
    raw = Path(source['local_source_path']).read_bytes()
    if sha256(raw).hexdigest() != source['source_sha256']:
        raise PermissionError('OFFICIAL_TARGET_BASE_SOURCE_CHANGED')
    line = source['source_line']
    if line not in raw.decode('utf-8-sig').splitlines():
        raise PermissionError('OFFICIAL_TARGET_BASE_LINE_CHANGED')
    currency = source['currency']
    marker = {'TWD': r'NT\$', 'USD': r'US\$'}.get(currency)
    if marker is None:
        raise ValueError('OFFICIAL_TARGET_BASE_CURRENCY_UNSUPPORTED')
    # A following semicolon may describe expenses explicitly outside the
    # investment pool. Bind the labelled pool clause, retaining the full line.
    clause = line.split('；', 1)[0]
    if '投資池' not in clause:
        raise ValueError('OFFICIAL_TARGET_BASE_POOL_LABEL_REQUIRED')
    matches = re.findall(marker + r'\s*([0-9][0-9,]*(?:\.[0-9]+)?)', clause)
    values = {Decimal(v.replace(',', '')) for v in matches}
    amount = Decimal(str(source['amount']))
    if not amount.is_finite() or amount <= 0 or values != {amount}:
        raise ValueError('OFFICIAL_TARGET_BASE_AMOUNT_MISMATCH')
    return {'value_state': 'KNOWN', 'amount': str(amount), 'currency': currency,
            'scope': 'APPROVED_ALLOCATION_BASE__NOT_CURRENT_MARKET_NAV',
            'source_reference': source['source_reference'], 'source_row': line,
            'source_sha256': source['source_sha256']}


def build(snapshot, *, evaluation_at, base_source):
    if (snapshot.get('data_provenance') != 'SOURCE_BACKED'
            or snapshot.get('payload_digest') != digest(snapshot['tables'])):
        raise PermissionError('OFFICIAL_TARGET_SNAPSHOT_MISMATCH')
    at = _time(evaluation_at)
    tables = snapshot['tables']; client = snapshot['client_id']
    versions = tables.get('final_target_version', [])
    if not versions:
        return None
    # Do not fall back to an older confirmed version if a later version is
    # incomplete. Multiple target keys require an explicit upstream selection.
    if len({r['target_key'] for r in versions}) != 1:
        raise ValueError('OFFICIAL_TARGET_KEY_AMBIGUOUS')
    latest = max(r['version_no'] for r in versions)
    candidates = [r for r in versions if r['version_no'] == latest]
    if len(candidates) != 1:
        raise ValueError('OFFICIAL_TARGET_VERSION_AMBIGUOUS')
    version = candidates[0]
    if (version.get('client_id') != client
            or version.get('lifecycle_state') != 'CONFIRMED'
            or version.get('completeness_state') != 'COMPLETE'
            or not version.get('confirmed_by')
            or not version.get('confirmation_source_ref')
            or _time(version['confirmed_at_utc']) > at
            or _time(version['created_at_utc']) > at):
        raise ValueError('OFFICIAL_TARGET_NOT_CURRENT_COMPLETE_CONFIRMED')
    base = read_base(base_source)
    if _time(base_source['source_available_at']) > at:
        raise ValueError('OFFICIAL_TARGET_FUTURE_BASE')
    rows = [r for r in tables.get('final_target_allocation', [])
            if r['target_key'] == version['target_key'] and r['version_no'] == latest]
    if (not rows or any(r.get('client_id') != client
            or r.get('allocation_state') != 'ACCEPTED'
            or type(r.get('weight_units')) is not int
            or not 0 <= r['weight_units'] <= 1000000
            or not r.get('allocation_source_ref')
            or _time(r['created_at_utc']) > at for r in rows)
            or sum(r['weight_units'] for r in rows) != 1000000
            or len({r['instrument_key'] for r in rows}) != len(rows)):
        raise ValueError('OFFICIAL_TARGET_ALLOCATION_INVALID')
    lines = []
    for row in sorted(rows, key=lambda r: r['instrument_key']):
        matches = [r for r in tables['portfolio_instrument']
                   if r['instrument_key'] == row['instrument_key']]
        if (len(matches) != 1 or matches[0].get('client_id') != client
                or matches[0].get('identity_state') != 'KNOWN'
                or not matches[0].get('ticker')):
            raise ValueError('OFFICIAL_TARGET_INSTRUMENT_AMBIGUOUS')
        instrument = matches[0]
        weight = Decimal(row['weight_units']) / Decimal(1000000)
        lines.append({'instrument_id': row['instrument_key'], 'ticker': instrument['ticker'],
            'asset_type': instrument['instrument_type'],
            'weight': {'value_state': 'KNOWN', 'value': str(weight)},
            'target_amount': {'value_state': 'KNOWN',
                'amount': str(Decimal(base['amount']) * weight), 'currency': base['currency'],
                'scope': 'CURRENT_W1_CONFIRMED_WEIGHT_TIMES_APPROVED_ALLOCATION_BASE',
                'source_reference': row['allocation_source_ref'], 'base_source': deepcopy(base)},
            'source_allocation_row': deepcopy(row),
            'source_instrument_row': deepcopy(instrument)})
    allocation_id = 'W1-TARGET-' + digest({'client': client, 'version': version})[:24]
    confirmation_run = 'W1-EXISTING-' + digest(version)[:24]
    draft = {'identity': {'client_id': client, 'run_id': confirmation_run},
        'allocation_id': allocation_id, 'target_lines': lines, 'denominator': base,
        'is_trade_authorized': False, 'original_allocation_version': str(latest)}
    draft['draft_hash'] = digest(draft)
    evidence = {'action': 'READ_EXISTING_APPROVAL',
        'approval_origin': 'OFFICIAL_W1_CONFIRMED_ALLOCATION',
        'confirmed_at': version['confirmed_at_utc'], 'confirmed_by': version['confirmed_by'],
        'source_reference_ids': [version['confirmation_source_ref']],
        'original_confirmation_row': deepcopy(version)}
    record = {'version': latest, 'target_id': allocation_id, 'target_hash': draft['draft_hash'],
        'status': 'W1_CONFIRMED_TARGET_VIEW', 'draft': draft, 'confirmation_evidence': evidence,
        'confirmation_evidence_hash': digest(evidence),
        'source_reference_ids': evidence['source_reference_ids']}
    view = {'source_kind': 'OFFICIAL_W1_CONFIRMED_ALLOCATION', 'payload': record,
        'target_hash': draft['draft_hash'], 'target_version': latest,
        'confirmation_run_id': confirmation_run}
    proof = {'schema_version': 'Family.W8.OfficialTargetSource.v1', 'client_id': client,
        'source_db_sha256': snapshot['source_sha256'], 'snapshot_digest': digest(snapshot),
        'base_source': deepcopy(base_source), 'target_view_digest': digest(view),
        'data_provenance': 'SOURCE_BACKED', 'approval_created': False, 'database_written': False}
    return view, proof


def validate(target, proof, snapshot, evaluation_at):
    if not isinstance(proof, dict) or proof.get('schema_version') != 'Family.W8.OfficialTargetSource.v1':
        raise PermissionError('OFFICIAL_TARGET_TRUSTED_SOURCE_REQUIRED')
    expected = build(snapshot, evaluation_at=evaluation_at, base_source=proof['base_source'])
    if expected != (target, proof):
        raise PermissionError('OFFICIAL_TARGET_SOURCE_REPLAY_MISMATCH')
    return deepcopy(target)

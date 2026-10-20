"""W5 read-only W1 snapshot seam. No database migration or inferred cash."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import sqlite3


class InputError(ValueError):
    pass


TABLES = (
    'portfolio_account', 'portfolio_instrument', 'portfolio_position',
    'account_broker_link', 'account_ownership', 'broker_registry',
    'cash_account_scope', 'cash_balance_snapshot', 'currency_registry',
    'funding_domain', 'funding_account_domain_link', 'funding_evaluation',
    'funding_assignment', 'final_target_version', 'final_target_allocation',
    'universe_membership', 'universe_confirmation',
    'protected_funding_claim', 'protected_funding_confirmation',
    'sgov_role_proposal', 'sgov_role_confirmation',
)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_snapshot(db_path, *, expected_client_id):
    if not isinstance(expected_client_id, str) or not expected_client_id.strip():
        raise InputError('CLIENT_REQUIRED')
    path = Path(db_path).resolve(strict=True)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        identities = [dict(r) for r in conn.execute('SELECT * FROM family_member_identity')]
        if len(identities) != 1 or identities[0]['client_id'] != expected_client_id:
            raise InputError('CLIENT_MISMATCH')
        payload = {}
        for table in TABLES:
            columns = [r[1] for r in conn.execute('PRAGMA table_info(' + table + ')')]
            if not columns:
                raise InputError('SCHEMA_MISSING:' + table)
            if 'client_id' in columns:
                if conn.execute('SELECT 1 FROM ' + table + ' WHERE client_id <> ? LIMIT 1',
                                (expected_client_id,)).fetchone():
                    raise InputError('CROSS_CLIENT_ROWS:' + table)
                rows = conn.execute('SELECT * FROM ' + table + ' WHERE client_id=?',
                                    (expected_client_id,))
            else:
                rows = conn.execute('SELECT * FROM ' + table)
            payload[table] = sorted((dict(r) for r in rows), key=lambda r: json.dumps(r, sort_keys=True))
        conn.rollback()
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise InputError('SNAPSHOT_CHANGED_DURING_READ')
    # Preserve the full histories and original integer/decimal fields. Selecting
    # an evaluation instant and normalizing owner budgets belong to later seams.
    return {'schema_version': 'Family.W5.W1Snapshot.v1', 'client_id': expected_client_id,
            'source_sha256': before, 'data_provenance': 'SOURCE_BACKED',
            'identity': identities[0], 'tables': payload, 'payload_digest': digest(payload),
            'trade_authorization': 'NONE', 'trade_action': 'NO_TRADE'}

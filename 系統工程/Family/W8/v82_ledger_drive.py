"""Member-bound transport for the existing native planning-cycle SQLite store.

Native SQLite CAS and commitment rules remain authoritative. Drive writes use
the existing backup/source-recheck/original-ID/readback bridge and require a
serialized caller. That bridge does not provide a distributed remote CAS lock.
An initialized resource has no cycles and makes no claim about broker orders.
"""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import sqlite3

from family_input import digest as object_digest
from on_demand_drive_io import Binding, OnDemandWriteback, inspect, seal_working_copy

ROOT = Path(__file__).resolve().parents[3]
KIND = 'V82_DAILY_PLANNING_LEDGER'
SCHEMA = 'Family.W8.V82LedgerResource.v1'
TABLES = {'family_member_identity', 'v82_ledger_resource', 'cycles', 'intent_owner'}
IMMUTABLE = ('schema_version', 'resource_kind', 'member_db_file_id',
    'member_db_sha256_at_creation', 'created_at', 'creation_authority', 'account_keys_json')


def _runtime(root=ROOT):
    from formal_mode_analysis import native
    native(root)
    from livingwater_v82_runtime.daily_slice import CycleLedgerStore, validate_cycle
    return CycleLedgerStore, validate_cycle


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('LEDGER_TIMEZONE_REQUIRED')
    return result


def create_resource(member_db, destination, member_binding, require_login, *, authority, created_at):
    """Create only the typed container from the exact member's official DB.

    No G0/B0, cycle, intent, cash or broker-order state is initialized here.
    """
    OnDemandWriteback(member_binding, require_login)._admit()
    source = inspect(member_db, member_binding)
    if not authority or not isinstance(authority, str):
        raise ValueError('LEDGER_CREATION_AUTHORITY_REQUIRED')
    _time(created_at)
    with sqlite3.connect(Path(member_db).resolve().as_uri()+'?mode=ro', uri=True) as db:
        accounts = [r[0] for r in db.execute(
            'SELECT account_key FROM portfolio_account WHERE client_id=? ORDER BY account_key',
            (member_binding.client_id,))]
    if not accounts or len(accounts) != len(set(accounts)):
        raise ValueError('LEDGER_MEMBER_ACCOUNT_REGISTRY_REQUIRED')
    path = Path(destination).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
    store, _ = _runtime(); store(path, create=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE family_member_identity (client_id TEXT PRIMARY KEY, family_alias TEXT NOT NULL)')
        db.execute('INSERT INTO family_member_identity VALUES (?,?)',
                   (member_binding.client_id, member_binding.family_alias))
        db.execute('''CREATE TABLE v82_ledger_resource (
            schema_version TEXT NOT NULL, resource_kind TEXT NOT NULL,
            member_db_file_id TEXT NOT NULL, member_db_sha256_at_creation TEXT NOT NULL,
            created_at TEXT NOT NULL, creation_authority TEXT NOT NULL,
            account_keys_json TEXT NOT NULL, sync_revision INTEGER NOT NULL,
            parent_sha256 TEXT, updated_at TEXT NOT NULL)''')
        db.execute('INSERT INTO v82_ledger_resource VALUES (?,?,?,?,?,?,?,?,?,?)',
            (SCHEMA, KIND, member_binding.file_id, source['sha256'], created_at,
             authority, json.dumps(accounts, separators=(',', ':')), 0, None, created_at))
    return inspect_ledger(path, member_binding)


def inspect_ledger(path, binding):
    base = inspect(path, binding)
    _, validate_cycle = _runtime()
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != TABLES:
            raise ValueError('LEDGER_RESOURCE_TABLE_SET_MISMATCH')
        headers = [dict(r) for r in db.execute('SELECT * FROM v82_ledger_resource')]
        if len(headers) != 1:
            raise ValueError('LEDGER_RESOURCE_HEADER_REQUIRED')
        header = headers[0]
        if header['schema_version'] != SCHEMA or header['resource_kind'] != KIND:
            raise ValueError('LEDGER_RESOURCE_KIND_OR_VERSION_MISMATCH')
        accounts = json.loads(header['account_keys_json'])
        if (not isinstance(accounts, list) or not accounts or len(set(accounts))!=len(accounts)
                or any(not isinstance(a,str) or not a for a in accounts)):
            raise ValueError('LEDGER_ACCOUNT_REGISTRY_INVALID')
        if type(header['sync_revision']) is not int or header['sync_revision'] < 0:
            raise ValueError('LEDGER_SYNC_REVISION_INVALID')
        if (not header['member_db_file_id'] or not header['creation_authority']
                or not re.fullmatch('[0-9a-f]{64}',header['member_db_sha256_at_creation'])
                or header['sync_revision']==0 and header['parent_sha256'] is not None
                or header['sync_revision']>0 and not re.fullmatch('[0-9a-f]{64}',header['parent_sha256'] or '')):
            raise ValueError('LEDGER_RESOURCE_LINEAGE_INVALID')
        if _time(header['updated_at']) < _time(header['created_at']):
            raise ValueError('LEDGER_SYNC_TIME_REVERSED')
        cycles = {}; expected_intents = {}
        for row in db.execute('SELECT cycle_id,revision,payload FROM cycles ORDER BY cycle_id'):
            cycle = json.loads(row['payload']); validate_cycle(cycle)
            owner = cycle['owner']
            if (owner.get('client_id') != binding.client_id or owner.get('account') not in accounts
                    or any(not owner.get(k) for k in ('broker','currency','funding_domain'))):
                raise PermissionError('LEDGER_CYCLE_OWNER_ACCOUNT_MISMATCH')
            if row['cycle_id'] != cycle['slice_cycle_id'] or row['revision'] != cycle['revision']:
                raise ValueError('LEDGER_CYCLE_INDEX_MISMATCH')
            cycles[row['cycle_id']] = cycle
            for iid in cycle['intents']:
                scope = object_digest({'owner':owner,'asset_id':cycle['asset_id'],'intent_id':iid})
                if scope in expected_intents and expected_intents[scope]!=row['cycle_id']:
                    raise ValueError('LEDGER_INTENT_SCOPE_DUPLICATED')
                expected_intents[scope] = row['cycle_id']
        actual_intents = dict(db.execute('SELECT scope,cycle_id FROM intent_owner'))
        if actual_intents != expected_intents:
            raise ValueError('LEDGER_INTENT_INDEX_MISMATCH')
    return {**base, 'resource_kind':KIND, 'header':header, 'cycles':cycles,
        'cycle_count':len(cycles), 'financial_cycle_initialized':bool(cycles),
        'broker_orders_complete_asserted':False, 'trade_authorization':'NONE'}


def stage_sync(original, working, destination, binding, *, updated_at):
    """Seal the native working copy and stamp transport lineage separately."""
    before = inspect_ledger(original, binding)
    inspect_ledger(working, binding)
    seal_working_copy(working, destination)
    if _time(updated_at) < _time(before['header']['updated_at']):
        raise ValueError('LEDGER_SYNC_TIME_REVERSED')
    with sqlite3.connect(destination) as db:
        db.execute('UPDATE v82_ledger_resource SET sync_revision=?,parent_sha256=?,updated_at=?',
            (before['header']['sync_revision']+1, before['sha256'], updated_at))
    return inspect_ledger(destination, binding)


def _check_transition(before, after):
    if any(before['header'][k]!=after['header'][k] for k in IMMUTABLE):
        raise ValueError('LEDGER_RESOURCE_IDENTITY_IMMUTABLE')
    if (after['header']['sync_revision']!=before['header']['sync_revision']+1
            or after['header']['parent_sha256']!=before['sha256']):
        raise ValueError('LEDGER_SOURCE_REVISION_CONFLICT')
    if _time(after['header']['updated_at']) < _time(before['header']['updated_at']):
        raise ValueError('LEDGER_SYNC_TIME_REVERSED')
    if not set(before['cycles']) <= set(after['cycles']):
        raise ValueError('LEDGER_CYCLE_HISTORY_CANNOT_BE_DELETED')
    # Replay candidate transitions through the native SQLite CAS validator;
    # direct edits cannot bypass pending commitment, initial-fact or history guards.
    store, _ = _runtime()
    with TemporaryDirectory() as folder:
        replay = Path(folder)/'native-cas.db'
        seal_working_copy(before['path'], replay)
        db = store(replay)
        for key, cycle in after['cycles'].items():
            old = before['cycles'].get(key)
            if old == cycle:
                continue
            db.save(cycle, expected_revision=old['revision'] if old else None)


class LedgerWriteback(OnDemandWriteback):
    """Existing transport with typed ledger and native transition validation."""
    def prepare(self, original, candidate):
        plan = super().prepare(original, candidate)
        before, after = inspect_ledger(original,self.binding), inspect_ledger(candidate,self.binding)
        if before['header']['member_db_file_id']==self.binding.file_id:
            raise PermissionError('LEDGER_RESOURCE_MUST_NOT_OVERWRITE_MEMBER_DB')
        _check_transition(before,after)
        return {**plan, 'resource_kind':KIND,
            'ledger_before_digest':object_digest(before['cycles']),
            'ledger_after_digest':object_digest(after['cycles']),
            'sync_revision':after['header']['sync_revision']}

    def _plan(self, plan):
        super()._plan(plan)
        if plan.get('resource_kind')!=KIND:
            raise ValueError('LEDGER_PLAN_KIND_MISMATCH')
        before=inspect_ledger(plan['source']['path'],self.binding)
        after=inspect_ledger(plan['candidate']['path'],self.binding)
        _check_transition(before,after)
        if (plan.get('ledger_before_digest')!=object_digest(before['cycles'])
                or plan.get('ledger_after_digest')!=object_digest(after['cycles'])
                or plan.get('sync_revision')!=after['header']['sync_revision']):
            raise ValueError('LEDGER_PLAN_CONTENT_MISMATCH')

    def authorize_update(self, plan, fresh_remote, backup_remote, backup_file_id,
                         *, serialized_writer=False, **kwargs):
        if serialized_writer is not True:
            raise PermissionError('LEDGER_SERIALIZED_WRITER_REQUIRED')
        inspect_ledger(fresh_remote,self.binding); inspect_ledger(backup_remote,self.binding)
        ready=super().authorize_update(plan,fresh_remote,backup_remote,backup_file_id,**kwargs)
        return {**ready,'resource_kind':KIND,'requires_serialized_writer':True,
                'distributed_remote_cas_provided':False,'native_sqlite_cas_replayed':True}

    def verify_readback(self, plan, remote, remote_file_id, checks=None):
        candidate=inspect_ledger(plan['candidate']['path'],self.binding)
        observed=inspect_ledger(remote,self.binding)
        own_checks=[('SELECT sync_revision,parent_sha256 FROM v82_ledger_resource',(),
            [(candidate['header']['sync_revision'],candidate['header']['parent_sha256'])]),
            ('SELECT cycle_id,revision,payload FROM cycles ORDER BY cycle_id',(),
             [(k,c['revision'],json.dumps(c,ensure_ascii=False,sort_keys=True,separators=(',',':')))
              for k,c in sorted(candidate['cycles'].items())])]
        receipt=super().verify_readback(plan,remote,remote_file_id,own_checks+list(checks or []))
        if observed['cycles']!=candidate['cycles']:
            raise ValueError('LEDGER_REMOTE_CYCLE_CONTENT_MISMATCH')
        return {**receipt,'resource_kind':KIND,'cycle_count':observed['cycle_count'],
            'sync_revision':observed['header']['sync_revision'],
            'broker_orders_complete_asserted':False,'distributed_remote_cas_provided':False}


def register_reference(member_candidate, member_binding, resource_path, resource_file_id,
                       *, authority, verified_at):
    """Stage a pointer in a member DB copy; official save remains the old IO flow."""
    inspect(member_candidate,member_binding)
    resource_binding=Binding(member_binding.account,member_binding.client_id,resource_file_id,member_binding.family_alias)
    resource=inspect_ledger(resource_path,resource_binding)
    if resource_file_id==member_binding.file_id or not authority:
        raise ValueError('LEDGER_DISTINCT_RESOURCE_AND_AUTHORITY_REQUIRED')
    if resource['header']['member_db_file_id']!=member_binding.file_id:
        raise PermissionError('LEDGER_MEMBER_DB_BINDING_MISMATCH')
    _time(verified_at)
    with sqlite3.connect(member_candidate) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS v82_planning_ledger_binding (
            client_id TEXT PRIMARY KEY, file_id TEXT NOT NULL, resource_kind TEXT NOT NULL,
            schema_version TEXT NOT NULL, registered_at TEXT NOT NULL,
            authority TEXT NOT NULL, initial_verified_sha256 TEXT NOT NULL)''')
        old=db.execute('SELECT file_id FROM v82_planning_ledger_binding WHERE client_id=?',
                       (member_binding.client_id,)).fetchone()
        if old is not None:
            if old[0]!=resource_file_id:
                raise PermissionError('LEDGER_RESOURCE_ALREADY_BOUND')
            return read_reference(member_candidate,member_binding)
        db.execute('INSERT INTO v82_planning_ledger_binding VALUES (?,?,?,?,?,?,?)',
            (member_binding.client_id,resource_file_id,KIND,SCHEMA,verified_at,authority,resource['sha256']))
    return read_reference(member_candidate,member_binding)


def read_reference(member_db, member_binding):
    source=inspect(member_db,member_binding)
    with sqlite3.connect(Path(member_db).resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v82_planning_ledger_binding'").fetchone():
            return None
        rows=[dict(r) for r in db.execute('SELECT * FROM v82_planning_ledger_binding')]
    if (len(rows)!=1 or rows[0]['client_id']!=member_binding.client_id
            or rows[0]['resource_kind']!=KIND or rows[0]['schema_version']!=SCHEMA
            or not rows[0]['file_id'] or rows[0]['file_id']==member_binding.file_id):
        raise PermissionError('LEDGER_REGISTRY_MEMBER_OR_RESOURCE_MISMATCH')
    return {**rows[0],'source_member_db_sha256':source['sha256'],
            'ledger_current_sha256_asserted':False,'requires_fresh_drive_read':True}


def resolve_resource(member_db, member_binding, descriptor, *, evaluation_at):
    """Read the registered, separately downloaded resource before calculation.

    The registry's creation hash is deliberately not used as a current ledger
    hash. Each executor must fetch the registered ID again and supply its new
    immutable download descriptor; analysis never creates or updates it.
    """
    reference=read_reference(member_db,member_binding)
    if reference is None:
        if descriptor is not None:
            raise PermissionError('LEDGER_UNREGISTERED_RESOURCE_REJECTED')
        return {'status':'MEMBER_LEDGER_NOT_REGISTERED','cycle_count':None,
                'resource_initialized':False,'financial_cycle_initialized':False}
    if descriptor is None:
        return {'status':'REGISTERED_LEDGER_FRESH_DOWNLOAD_REQUIRED','reference':reference,
                'cycle_count':None,'resource_initialized':True,'financial_cycle_initialized':False}
    if (descriptor.get('file_id')!=reference['file_id']
            or descriptor.get('source_reference')!='drive:'+reference['file_id']
            or descriptor.get('downloaded_from_drive') is not True
            or _time(descriptor['retrieved_at'])>_time(evaluation_at)):
        raise PermissionError('LEDGER_DOWNLOAD_BINDING_OR_TIME_MISMATCH')
    binding=Binding(member_binding.account,member_binding.client_id,reference['file_id'],member_binding.family_alias)
    info=inspect_ledger(descriptor['local_path'],binding)
    if info['sha256']!=descriptor.get('sha256'):
        raise PermissionError('LEDGER_DOWNLOAD_HASH_MISMATCH')
    if info['header']['member_db_file_id']!=member_binding.file_id:
        raise PermissionError('LEDGER_MEMBER_DB_BINDING_MISMATCH')
    if _time(info['header']['updated_at'])>_time(evaluation_at):
        raise PermissionError('LEDGER_NOT_AVAILABLE_AT_EVALUATION')
    return {**info,'status':'VERIFIED_REGISTERED_DRIVE_RESOURCE','reference':reference,
        'resource_initialized':True,'source_descriptor_digest':object_digest(descriptor),
        'requires_serialized_writer':True,'distributed_remote_cas_provided':False}


def cycle_snapshot(resource, *, owner, asset_id, exchange, session_id):
    """Return only the native exact-scope cycle; never aggregate member cash."""
    if resource.get('status')!='VERIFIED_REGISTERED_DRIVE_RESOURCE':
        return {'status':resource['status'],'cycle':None}
    from livingwater_v82_runtime.daily_slice import cycle_id
    if owner.get('client_id')!=resource['reference']['client_id']:
        raise PermissionError('LEDGER_CYCLE_CLIENT_MISMATCH')
    if owner.get('account') not in json.loads(resource['header']['account_keys_json']):
        raise PermissionError('LEDGER_CYCLE_ACCOUNT_NOT_REGISTERED')
    key=cycle_id(owner=owner,asset_id=asset_id,exchange=exchange,session_id=session_id)
    cycle=resource['cycles'].get(key)
    return {'status':'VERIFIED' if cycle is not None else 'QUALIFIED_GAP_REQUIRED_FOR_CYCLE_INITIALIZATION',
        'cycle':cycle,'cycle_digest':object_digest(cycle),'ledger_path':resource['path'],
        'source_reference':'drive:'+resource['reference']['file_id'],
        'ledger_file_id':resource['reference']['file_id'],'ledger_sha256':resource['sha256']}

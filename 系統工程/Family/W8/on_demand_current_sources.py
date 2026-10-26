"""Read current W1 target/funding facts and execute original V70 on demand.

This produces source inputs and V70 planning percentages. It does not invent a
W2 confirmation, C7 investment-pool NAV, settled cash, or a complete native bundle.
Install jsdom@26.1.0 in the executor; NODE_PATH may point to its node_modules.
"""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import closing
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def _module(name):
    spec=importlib.util.spec_from_file_location('current_sources_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(db,sql,params=()):
    return [dict(r) for r in db.execute(sql,params)]


def _time(value):
    out=datetime.fromisoformat(value.replace('Z','+00:00'))
    if out.utcoffset() is None:raise ValueError('SOURCE_TIMEZONE_REQUIRED')
    return out.astimezone(timezone.utc)


def read_official_holdings(snapshot):
    """Read existing ledger and sealed source quantities without a new DB.

    Keep source layers explicit: a screenshot intake time is not an observation
    time, and an instrument absent from the old registry is still a real source
    holding. No absent position, cash balance or account mapping becomes zero.
    """
    tables=snapshot['tables'];client=snapshot['client_id']
    instruments={r['instrument_key']:r for r in tables['portfolio_instrument']}
    ledger=[]
    for row in tables.get('portfolio_position',[]):
        instrument=instruments.get(row['instrument_key'],{})
        ledger.append({'symbol':instrument.get('ticker'),
            'instrument_key':row['instrument_key'],'account_key':row['account_key'],
            'quantity':row.get('quantity_decimal'),'observed_at':row.get('as_of_utc'),
            'source_kind':'PORTFOLIO_POSITION','source_row':deepcopy(row)})
    runs=[r for r in tables.get('portfolio_snapshot_run',[])
          if r.get('run_state')=='SEALED' and r.get('source_kind')!='USER_HYPOTHETICAL']
    runs.sort(key=lambda r:(r['as_of_utc'],r.get('version_no',0)),reverse=True)
    source=[];corrections=[]
    if runs:
        run=runs[0]
        items=[r for r in tables.get('portfolio_snapshot_item',[]) if r['run_id']==run['run_id']]
        for item in items:
            if item.get('client_id')!=client:raise PermissionError('OFFICIAL_HOLDINGS_CLIENT_MISMATCH')
            field=item['field_key']
            if field=='quantity' and item.get('domain_code')=='OWNER_SCREENSHOT_SOURCE':
                source.append({'symbol':item['entity_key'],
                    'quantity':item.get('value_text') if item['value_state']=='KNOWN' else None,
                    'quantity_state':item['value_state'],'source_row':deepcopy(item),
                    'observed_at':item.get('source_observed_at_utc'),
                    'received_at':run['as_of_utc'],'source_run_id':run['run_id']})
            elif field=='accepted_W6_broker_holdings_json' and item['value_state']=='KNOWN':
                for row in json.loads(item['value_text']):
                    source.append({**deepcopy(row),'source_row':deepcopy(item),
                        'observed_at':item.get('source_observed_at_utc'),
                        'received_at':run['as_of_utc'],'source_run_id':run['run_id']})
            elif field=='owner_correction_json' and item['value_state']=='KNOWN':
                corrections.append({'payload':json.loads(item['value_text']),
                    'source_row':deepcopy(item)})
    registered={r.get('ticker') for r in instruments.values()}
    return {'client_id':client,'source_db_sha256':snapshot['source_sha256'],
        'ledger_positions':ledger,'latest_sealed_source_positions':source,
        'owner_corrections':corrections,
        'source_symbols_missing_from_instrument_registry':sorted({r['symbol'] for r in source}-registered),
        'source_layers_preserved':True,'database_written':False}


def run_original_v70(repo_root,strategic,*,evaluation_at):
    """Execute original scoring/allocation JS; retain original candidate status."""
    _time(evaluation_at)
    root=Path(repo_root).resolve()
    files=[root/'系統工程/總經V70'/name for name in ('V70-3-27.html','V70_macro_latest.json')]
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    request={'repo_root':str(root),'stock_percent':strategic['stock_percent'],
             'bond_percent':strategic['bond_percent'],'evaluation_at':evaluation_at,
             'html_sha256':before[0],'feed_sha256':before[1]}
    run=subprocess.run(['node',str(HERE/'v70_original_runtime.cjs')],
        input=json.dumps(request),capture_output=True,text=True,timeout=30,env=os.environ.copy())
    if run.returncode:
        if "Cannot find module 'jsdom'" in run.stderr:
            raise RuntimeError('V70_JSDOM_RUNTIME_REQUIRED')
        raise RuntimeError('V70_ORIGINAL_RUNTIME_FAILED:'+run.stderr[:240])
    out=json.loads(run.stdout)
    if ([hashlib.sha256(p.read_bytes()).hexdigest() for p in files]!=before
        or out.get('source_html_sha256')!=before[0] or out.get('source_feed_sha256')!=before[1]
        or out.get('evaluation_at')!=evaluation_at):
        raise RuntimeError('V70_SOURCE_CHANGED')
    return out


def build_current_sources(snapshot,db_path,*,repo_root=REPO,evaluation_at=None):
    """The caller supplies the authenticated fixed DB path and original snapshot."""
    when=evaluation_at or datetime.now(timezone.utc).isoformat()
    _time(when)
    path=Path(db_path).resolve(strict=True)
    original_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    if (snapshot.get('schema_version')!='Family.W5.W1Snapshot.v1'
        or snapshot.get('data_provenance')!='SOURCE_BACKED'
        or snapshot.get('source_sha256')!=original_hash):
        raise PermissionError('CURRENT_SOURCE_DB_MISMATCH')
    client=snapshot['client_id'];missing=[]
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        ids=_rows(db,'SELECT client_id FROM family_member_identity')
        if ids!=[{'client_id':client}]:raise PermissionError('CURRENT_SOURCE_CLIENT_MISMATCH')
        facts=_module('confirmed_asset_facts').read_latest_confirmed_asset_facts(db,client)
        if facts.get('as_of_utc') and _time(facts['as_of_utc'])>_time(when):
            raise ValueError('CURRENT_SOURCE_FUTURE_FACTS')
        profile={}
        for row in facts['fields']:
            if row.get('domain_code')=='PROFILE' and row.get('entity_key')=='LONG_TERM' and row.get('value_state')=='KNOWN':
                key=row.get('field_key')
                if key in profile:raise ValueError('STRATEGIC_SOURCE_AMBIGUOUS')
                profile[key]=row
        strategic=None
        if {'stock_weight','bond_weight'}.issubset(profile):
            a,b=(Decimal(str(profile[k]['value_text'])) for k in ('stock_weight','bond_weight'))
            if not (a.is_finite() and b.is_finite() and 0<=a<=1 and 0<=b<=1 and a+b==1):
                raise ValueError('STRATEGIC_SOURCE_INVALID')
            strategic={'stock_percent':float(a*100),'bond_percent':float(b*100),
                       'source_snapshot_run':facts['run_id'],'source_as_of':facts['as_of_utc'],
                       'source_fields':[profile['stock_weight'],profile['bond_weight']]}
        else:missing.append('owner_confirmed_strategic_stock_bond_base')
        cash=_rows(db,'SELECT v.*,s.source_reference,s.data_state FROM cash_available_view v '
            'JOIN cash_balance_snapshot s ON s.cash_snapshot_id=v.cash_snapshot_id '
            'WHERE v.client_id=?',(client,))
        latest={}
        for row in cash:
            if _time(row['as_of_utc'])>_time(when):continue
            key=(row['account_key'],row['currency_code'])
            order=(row['as_of_utc'],row['version'])
            if key not in latest or order>latest[key][0]:latest[key]=(order,[row])
            elif order==latest[key][0]:latest[key][1].append(row)
        funding=[]
        for _,rows in latest.values():
            row=dict(rows[0])
            if len({(r['available_state'],r['available_minor']) for r in rows})!=1:
                row.update(available_state='NEEDS_REVIEW',available_minor=None)
            row['source_cash_snapshot_ids']=[r['cash_snapshot_id'] for r in rows]
            funding.append(row)
        funding.sort(key=lambda r:(r['account_key'],r['currency_code']))
        planning=_rows(db,'SELECT * FROM funding_planning_view WHERE client_id=?',(client,))
        db.rollback()
    # Reuse the existing target selector; retain original rows, never re-sign W2.
    targets=_module('formal_report_source')._confirmed_target_details(snapshot['tables'])
    if any(t.get('confirmed_at_utc') and _time(t['confirmed_at_utc'])>_time(when) for t in targets):
        raise ValueError('CURRENT_SOURCE_FUTURE_TARGET')
    if not targets:missing.append('complete_confirmed_final_target')
    if not funding or any(r['available_state']!='VERIFIED' for r in funding):
        missing.append('verified_settled_available_funding')
    w5=Path(repo_root)/'系統工程/Family/W5'
    if str(w5) not in sys.path:sys.path.insert(0,str(w5))
    from market_bridge import read_macro_snapshot
    try:
        git=subprocess.run(['git','rev-parse','HEAD'],cwd=repo_root,
                           capture_output=True,text=True,timeout=5)
        commit=git.stdout.strip() if git.returncode==0 else 'UNKNOWN'
    except (OSError,subprocess.TimeoutExpired):commit='UNKNOWN'
    macro=read_macro_snapshot(repo_root,source_commit=commit)
    if commit=='UNKNOWN':missing.append('macro_source_commit')
    v70=None
    if strategic:
        try:v70=run_original_v70(repo_root,strategic,evaluation_at=when)
        except (RuntimeError,OSError,subprocess.TimeoutExpired) as e:
            missing.append(str(e))
        if v70 and v70['status']!='V70_DATA_READY':missing.append('v70_original_data_validation')
    observations=None
    try:
        observations=_module('on_demand_market_observations').build_member_market_observations(
            snapshot,targets,macro,repo_root=repo_root,evaluation_at=when)
    except ImportError as e:
        missing.append('OBSERVATION_RUNTIME_DEPENDENCY_REQUIRED:'+str(e))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=original_hash:
        raise RuntimeError('CURRENT_SOURCE_DB_CHANGED_DURING_READ')
    return {'schema_version':'Family.W8.CurrentNativeSources.v1','status':'SOURCE_INPUTS_READ',
            'client_id':client,'source_db_sha256':original_hash,'evaluation_at':when,
            'confirmed_target_details':targets,'strategic':strategic,
            'official_asset_facts':facts,
            'official_holdings':read_official_holdings(snapshot),
            'funding_latest':funding,'funding_planning_rows':planning,'macro':macro,'v70':v70,
            'market_observations':observations,
            'monetary_tactical_amounts':None,'monetary_amount_reason':'C7_VERIFIED_INVESTMENT_POOL_BASE_REQUIRED',
            'missing':missing,'full_native_bundle_ready':False,
            'data_provenance':'SOURCE_BACKED','trade_authorization':'NONE'}

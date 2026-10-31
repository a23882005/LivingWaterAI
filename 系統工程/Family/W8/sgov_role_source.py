"""Source-derived SGOV accounting, independent of cash and target balances.

An ongoing documented use may classify current observed shares. A single
approved bond allocation protects SGOV as bond exposure; it never releases
defensive holdings for equity purchases. Neither is a new owner confirmation.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from family_input import digest


def _time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('SGOV_SOURCE_TIMEZONE_REQUIRED')
    return at


def physical_value(request,report,row):
    """Accounting reference only; no close/price-map attestation is created."""
    currency=request['owner']['currency']
    if row['holding'].get('quantity') is None:return None
    qty=Decimal(row['holding']['quantity'])
    broker=report.get('broker_readonly_source')
    if broker is not None:
        if any(broker.get(k)!=request[k] for k in ('client_id','run_id','owner')):
            raise PermissionError('SGOV_BROKER_OWNER_MISMATCH')
        matches=[p for p in broker['positions'] if p['symbol']=='SGOV']
        if len(matches)!=1 or Decimal(matches[0]['quantity'])!=qty:
            raise PermissionError('SGOV_BROKER_QUANTITY_MISMATCH')
        source=matches[0];price=Decimal(source['market_price'])
        at=broker['captured_at'];ref='BROKER-READONLY:'+broker['source_descriptor_digest']
        basis='BROKER_CAPTURED_MARKET_PRICE__ACCOUNTING_REFERENCE'
        price_date=at
    else:
        market=row.get('market') or {}
        if (market.get('observed_close') is None or row['current_analysis']['recommendation'].get('position_currency')!=currency):return None
        price=Decimal(str(market['observed_close']))
        at=request['evaluation_at'];price_date=market['observed_date']
        ref='MARKET-CACHE:'+market['source_sha256']
        basis='DATED_CLOSE_REFERENCE__CURRENT_CLOSE_FRESHNESS_NOT_ASSERTED'
    if (not qty.is_finite() or qty<0 or not price.is_finite() or price<=0
        or _time(at)>_time(request['evaluation_at'])):
        raise ValueError('SGOV_PHYSICAL_VALUE_INVALID')
    return {'quantity':str(qty),'valuation':{'amount':str(qty*price),'currency':currency},
        'valuation_as_of':at,'price_observation_date':price_date,'price':str(price),
        'price_basis':basis,'source_reference':ref,'available_cash_contribution':'0',
        'canonical_market_freshness_asserted':False}


def produce(request,context,report):
    rows=[r for r in report['analysis_result']['positions'] if r['symbol']=='SGOV']
    if not rows:return None
    if len(rows)!=1:raise ValueError('SGOV_POSITION_AMBIGUOUS')
    snapshot=request['client_snapshot']['payload'];target=request['confirmed_target']
    out={'schema_version':'Family.W8.SgovRoleSource.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
        'source_db_sha256':snapshot['source_sha256'],'source_target_digest':digest(target),
        'status':'ROLE_SOURCE_UNRESOLVED','evidence_state':'UNKNOWN','purpose':None,
        'owner_role_confirmation':None,'database_role_rows_created':False,
        'physical':physical_value(request,report,rows[0]),'roles':None,'source_basis':None,
        'target_amount_used_as_physical_balance':False,'physical_included_in_available_cash':False,
        'equity_cash_release_authorized':False,'trade_action':'NO_TRADE','issues':[]}
    def finish():
        out['digest']=digest(out);return out
    if out['physical'] is None:
        out['issues'].append('SGOV_PHYSICAL_VALUATION_SOURCE_REQUIRED');return finish()
    if any(snapshot['tables'].get(k) for k in ('sgov_role_proposal','sgov_role_confirmation')):
        out['issues'].append('EXISTING_ROLE_ROWS_REQUIRE_ACTIVE_VERSION_SELECTION');return finish()
    proof=context.get('approved_document_target_source')
    documented=None
    if proof is not None:
        if proof.get('client_id')!=request['client_id']:raise PermissionError('SGOV_DOCUMENT_CLIENT_MISMATCH')
        raw=Path(proof['local_source_path']).read_bytes()
        if sha256(raw).hexdigest()!=proof['source_sha256']:
            raise PermissionError('SGOV_DOCUMENT_BYTES_CHANGED')
        if _time(proof['source_available_at'])>_time(request['evaluation_at']):
            raise PermissionError('SGOV_DOCUMENT_FUTURE_SOURCE')
        # This ongoing instruction is independent of the dated target tables
        # and old balances elsewhere in the same approved source.
        lines=raw.decode('utf-8').splitlines();heading='## 暫時要求C｜IBKR SGOV角色'
        if heading in lines:
            start=lines.index(heading)+1;section=[]
            for line in lines[start:]:
                if line.startswith('#'):break
                section.append(line)
            required=['- IBKR內SGOV定位：**美元股票ETF買點彈藥庫**',
                '- 不把IBKR SGOV固定當成生活費安全墊',
                '- 實際可用金額以最新IBKR截圖／帳戶現金與已掛單需求為準']
            if all(line in section for line in required):
                documented={'kind':'EXISTING_DOCUMENT_ONGOING_ACCOUNT_USE',
                    'source_reference':proof['source_reference'],'source_sha256':proof['source_sha256'],
                    'heading':heading,'source_lines':required}
    purpose=None;basis=None
    if documented is not None and request['owner']['broker']=='IBKR':
        purpose='DRY_POWDER';basis=documented
    elif target.get('source_kind')=='OFFICIAL_W1_CONFIRMED_ALLOCATION':
        policy=context.get('sgov_role_strategic_policy') or {}
        lines=target['payload']['draft']['target_lines']
        sgov=[r for r in lines if r.get('ticker')=='SGOV']
        from native_asset_source import classification,FORMAL_CLASSES
        others=[r for r in lines if r.get('ticker')!='SGOV']
        classification_source=context.get('sgov_role_classification_source')
        products=context.get('sgov_role_product_sources') or {}
        classes=([classification(r['ticker'],classification_source,products.get(r['ticker']))
            for r in others] if classification_source is not None else [])
        equity=bool(others) and len(classes)==len(others) and all(
            c['primary_class'] in FORMAL_CLASSES or c['asset_type'] in
            ('BROAD_ETF','SECTOR_ETF','INDUSTRY_ETF','THEME_ETF','INDIVIDUAL_STOCK') for c in classes)
        weights=[Decimal(str(r['weight']['value'])) for r in lines if r['weight']['value_state']=='KNOWN']
        if (policy.get('client_id')==request['client_id'] and policy.get('source_reference')
            and len(sgov)==1 and equity and len(weights)==len(lines) and sum(weights)==1
            and Decimal(str(sgov[0]['weight']['value']))==Decimal(str(policy['bond_percent']))/100
            and Decimal(str(policy['stock_percent']))+Decimal(str(policy['bond_percent']))==100):
            purpose='BOND';basis={'kind':'CURRENT_APPROVED_SINGLE_BOND_ALLOCATION_PROTECTION',
                'source_target_digest':digest(target),'source_allocation_row':deepcopy(sgov[0]['source_allocation_row']),
                'other_target_classifications':{c['symbol']:{k:c[k] for k in
                    ('primary_class','asset_type','source_reference','source_sha256')} for c in classes},
                'strategic_policy':deepcopy(policy),
                'scope':'DEFENSIVE_ACCOUNTING__NO_DRY_POWDER_RELEASE_INFERRED'}
    if purpose is None:
        out['issues'].append('NO_UNAMBIGUOUS_EXISTING_ROLE_SOURCE');return finish()
    money=out['physical']['valuation'];zero={'amount':'0','currency':money['currency']}
    out.update(status='SOURCE_DERIVED_ACCOUNTING',evidence_state='SOURCE_DERIVED',purpose=purpose,
        source_basis=basis,roles={'sgov_bond_bucket_amount':deepcopy(money if purpose=='BOND' else zero),
            'sgov_dry_powder_bucket_amount':deepcopy(money if purpose=='DRY_POWDER' else zero)},
        physical_role_sum_reconciled=True,unallocated_amount=deepcopy(zero))
    return finish()


def validate(request,context,report):
    if report.get('sgov_role_source')!=produce(request,context,report):
        raise PermissionError('SGOV_ROLE_SOURCE_REPLAY_MISMATCH')

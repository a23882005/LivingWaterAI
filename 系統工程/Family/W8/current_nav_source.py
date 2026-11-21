"""Read PM-qualified project NAV sources without qualifying price history."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import json,re
from family_input import digest
from member_market_source import time


def read(source,request,contract):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('CURRENT_NAV_APPROVAL_BYTES_CHANGED')
    data=json.loads(raw);member=contract['member'];item=data.get('members',{}).get(member)
    if (data.get('schema_version')!='Family.PM.CurrentProjectNAVSourceQualification.v1'
        or data.get('qualification')!='APPROVED_PM_NAV_SOURCE_FOR_IMPLEMENTATION__NATIVE_C7_ACCEPTANCE_PENDING'
        or data.get('trade')!='NONE' or request.get('trade_authorization')!='NONE'
        or not re.fullmatch('[0-9a-f]{40}',data.get('accepted_code_baseline',''))
        or not source.get('source_reference') or not isinstance(item,dict)
        or item.get('client_id')!=request['client_id']
        or item.get('source_db_sha256')!=contract['source_db_sha256']
        or source.get('target_version')!=request['confirmed_target']['target_version']
        or item.get('qualification')!='PM_VERIFIED_SOURCE_FOR_CURRENT_PROJECT_NAV_INPUT'
        or any(item.get(k) is not True for k in ('all_positive_positions_valued',
            'unreported_positions_orders_and_commitments_absent_by_explicit_Owner_policy','cash_counted_once'))
        or any(item.get(k) is not False for k in ('new_buy_permission_created','approved_target_pool_rebased',
            'historical_PIT_or_qP_qV_qualified'))):
        raise PermissionError('CURRENT_NAV_APPROVAL_MEMBER_DB_TARGET_OR_SCOPE')
    at=data['source_availability_cutoff']
    if time(at)>time(request['evaluation_at']):return None
    if time(data['verified_at'])>time(at):raise PermissionError('CURRENT_NAV_APPROVAL_AVAILABILITY')
    receipt=data['official_TPEX_selected_receipt'];official=source['official_source']
    url=urlparse(receipt['source_url']);original=Path(official['local_path']).read_bytes()
    if (url.scheme!='https' or url.hostname!='www.tpex.org.tw'
        or url.path!='/openapi/v1/tpex_mainboard_daily_close_quotes'
        or official.get('source_reference')!=receipt['source_url']
        or official.get('sha256')!=receipt['raw_sha256']
        or sha256(original).hexdigest()!=receipt['raw_sha256'] or len(original)!=receipt['bytes']
        or time(receipt['retrieved_at'])>time(at)):
        raise PermissionError('CURRENT_NAV_OFFICIAL_ORIGINAL_HASH_IDENTITY_OR_TIME')
    rows=json.loads(original);selected={}
    for expected in receipt['selected_rows']:
        symbol=expected['SecuritiesCompanyCode']
        matches=[r for r in rows if r.get('SecuritiesCompanyCode')==symbol and r.get('Date')==expected['Date']]
        if len(matches)!=1 or symbol in selected:raise PermissionError('CURRENT_NAV_OFFICIAL_ROW_AMBIGUOUS')
        row=matches[0]
        if {k:str(v).strip() for k,v in row.items()}!={k:str(v).strip() for k,v in expected.items()}:
            raise PermissionError('CURRENT_NAV_OFFICIAL_SELECTED_ROW_CHANGED')
        date=row['Date']
        if not re.fullmatch(r'\d{7}',date):raise ValueError('CURRENT_NAV_OFFICIAL_ROC_DATE')
        day=f'{int(date[:3])+1911:04d}-{date[3:5]}-{date[5:]}'
        closed=datetime.fromisoformat(day+'T13:33:00').replace(tzinfo=ZoneInfo('Asia/Taipei'))
        price=Decimal(row['Close'])
        if not price.is_finite() or price<=0 or closed>time(receipt['retrieved_at']):
            raise PermissionError('CURRENT_NAV_OFFICIAL_CLOSE_OR_SESSION')
        selected[symbol]={'symbol':symbol,'price':row['Close'],'session_date':day,
            'source_sha256':receipt['raw_sha256'],'source_reference':receipt['source_url'],
            'source_path':official['local_path'],'available_at':receipt['retrieved_at'],
            'official_original_row':deepcopy(row)}
    if data['reporting_FX_original_reader_result']!=contract['official_bank_original_result']:
        raise PermissionError('CURRENT_NAV_REPORTING_BANK_FX_CHANGED')
    out={'schema_version':'Family.W8.ProjectNAVSourceQualification.v1',
        **{k:request[k] for k in ('client_id','run_id','evaluation_at')},
        'member':member,'source_db_sha256':contract['source_db_sha256'],
        'target_version':source['target_version'],'source_descriptor':deepcopy(source),
        'available_at':at,'approved_member_sources':deepcopy(item),'official_quotes':selected,
        'reporting_FX':deepcopy(data['reporting_FX_original_reader_result']),
        'historical_PIT_or_qP_qV_qualified':False,'new_buy_permission_created':False}
    out['digest']=digest(out);return out


def apply_official_quote(row,contract):
    qualification=contract.get('nav_source_qualification') if contract else None
    quote=(qualification or {}).get('official_quotes',{}).get(row['symbol'])
    if quote is None or row.get('issue') or row.get('amount') is None:return
    if row.get('currency')!='TWD' or row.get('observed_market_date')!=quote['session_date']:
        raise PermissionError('CURRENT_NAV_OFFICIAL_QUOTE_POSITION_CURRENCY_OR_DATE')
    row['previous_source_dated_quote']={k:deepcopy(row.get(k)) for k in
        ('observed_close','observed_market_date','market_source_sha256','amount','reporting_amount_TWD')}
    with localcontext() as numeric:
        numeric.prec=50;value=Decimal(row['quantity'])*Decimal(quote['price'])
    row.update(observed_close=quote['price'],observed_market_date=quote['session_date'],
        amount=str(value),reporting_amount_TWD=str(value),market_source_sha256=quote['source_sha256'],
        qualified_current_NAV_quote=deepcopy(quote))


def qualify(reference,accepted,current):
    contract=reference['contract'];approval=contract.get('nav_source_qualification')
    if approval is None:return
    selected=approval['approved_member_sources'];rows=reference['positions'];originals=selected['positions']
    if (len(rows)!=len(originals)
        or selected['owner_current_confirmation_source_sha256']!=current['source_sha256']
        or selected['accepted_funding_source_sha256']!=accepted['source']['source_sha256']
        or selected['accepted_net_cash_by_currency']!=reference['accepted_net_cash_by_currency']):
        raise PermissionError('CURRENT_NAV_ORIGINAL_OWNER_CASH_OR_COVERAGE_MISMATCH')
    if [(i, row['symbol']) for i, row in enumerate(rows)] != [
            (row['source_representation_index'], row['symbol']) for row in originals]:
        raise PermissionError('CURRENT_NAV_ORIGINAL_POSITION_OR_VALUE_MISMATCH')
    if reference['issues']:
        reference.update(formal_NAV_source_qualified=False,
            nav_qualification_status='CURRENT_MARKET_OR_ACCOUNT_INPUTS_REQUIRED')
        return
    with localcontext() as numeric:
        numeric.prec=50
        for i,(row,original) in enumerate(zip(rows,originals)):
            if (original['source_representation_index']!=i or row['symbol']!=original['symbol']
                or Decimal(row['quantity'])!=Decimal(original['quantity'])
                or row['quantity_source']!=original['original_position_source']
                or Decimal(row['reference_amount_TWD'])!=Decimal(original['security_value_TWD'])):
                raise PermissionError('CURRENT_NAV_ORIGINAL_POSITION_OR_VALUE_MISMATCH')
            if Decimal(row['quantity'])!=0 and (row['currency']!=original['currency']
                or row['observed_market_date']!=original['observed_market_date']
                or Decimal(row['observed_close'])!=Decimal(original['price'])
                or row['market_source_sha256']!=original['price_source_sha256']
                or Decimal(row['amount'])!=Decimal(original['security_value_native'])):
                raise PermissionError('CURRENT_NAV_ORIGINAL_PRICE_IDENTITY_MISMATCH')
        if (Decimal(reference['positions_plus_accepted_cash_TWD'])!=Decimal(selected['current_project_portfolio_NAV_TWD'])
            or Decimal(reference['cash_TWD'])!=Decimal(selected['cash_reporting_TWD'])
            or Decimal(reference['positions_plus_accepted_cash_TWD'])<=0):
            raise PermissionError('CURRENT_NAV_ORIGINAL_RECOMPUTED_TOTAL_MISMATCH')
    reference.update(project_NAV_source_qualification=deepcopy(approval),formal_NAV_source_qualified=True,
        formal_NAV_or_buy_permission_created=True,new_buy_permission_created=False,
        historical_PIT_or_qP_qV_qualified=False)

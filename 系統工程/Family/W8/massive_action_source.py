"""Receipt-bound issuer action observations, without native PIT qualification.

The original cash amount and single-event split ratio remain separate from
provider adjustment factors. Date-only declarations are not publication times;
an empty warning or a returned table is not complete event-book evidence.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
import csv,json,re

from family_input import digest
from member_market_source import time

SCHEMA='Family.W8.MassiveActionSources.v1'


def pinned(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('MASSIVE_ACTION_ORIGINAL_BYTES_CHANGED')
    return raw


def day(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\d',value):
        raise ValueError('MASSIVE_ACTION_EXACT_DATE_REQUIRED')
    return date.fromisoformat(value)


def number(value,positive=False):
    if not isinstance(value,str) or not value:
        raise ValueError('MASSIVE_ACTION_ORIGINAL_DECIMAL_REQUIRED')
    try:value_=Decimal(value)
    except InvalidOperation:raise ValueError('MASSIVE_ACTION_ORIGINAL_DECIMAL_REQUIRED') from None
    if not value_.is_finite() or value_<0 or positive and value_==0:
        raise ValueError('MASSIVE_ACTION_INVALID_NUMBER')
    return value_


def original_table(source,kind,symbol,start,end,known_by):
    raw=pinned(source['source']);receipt=json.loads(pinned(source['acquisition_source']))
    column='ex_dividend_date' if kind=='dividends' else 'execution_date'
    expected=dict(ticker=symbol,**{column+'.gte':str(start),column+'.lte':str(end),
        'sort':column+'.asc','limit':5000})
    if (receipt.get('schema_version')!='Family.W8.MassiveActionAcquisition.v1'
        or receipt.get('tool')!='Massive.call_api' or receipt.get('path')!='/stocks/v1/'+kind
        or receipt.get('params')!=expected or type(receipt['params'].get('limit')) is not int
        or receipt.get('response_is_error') is not False
        or receipt.get('response_sha256')!=source['source']['sha256']
        or not time(receipt['started_at'])<=time(receipt['retrieved_at'])<=time(known_by)):
        raise PermissionError('MASSIVE_ACTION_QUERY_BYTES_OR_CAPTURE_MISMATCH')
    original=json.loads(pinned(receipt['tool_response_source']))
    if (original.get('isError',False) is not False
        or original.get('structuredContent',{}).get('result')!=raw.decode('utf-8')):
        raise PermissionError('MASSIVE_ACTION_CONNECTOR_RESPONSE_MISMATCH')
    text=raw.decode('utf-8-sig')
    if text.startswith('Warning ['):
        return [],text,receipt['retrieved_at']
    reader=csv.DictReader(StringIO(text));fields=reader.fieldnames or []
    required={'id','ticker',column}|({'cash_amount','currency','declaration_date'} if kind=='dividends'
        else {'split_from','split_to','adjustment_type'})
    if len(fields)!=len(set(fields)) or not required<=set(fields):
        raise ValueError('MASSIVE_ACTION_ORIGINAL_COLUMNS_REQUIRED')
    rows=list(reader)
    if not rows or any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('MASSIVE_ACTION_ORIGINAL_ROW_COVERAGE')
    return rows,None,receipt['retrieved_at']


def compare_ibkr(observations,events,start,end):
    """Compare original event values; agreement never attests cash/split basis."""
    if not isinstance(events,list):raise ValueError('MASSIVE_ACTION_IBKR_EVENT_LIST_REQUIRED')
    massive={}
    for kind,result in observations.items():
        for row in result['records']:
            massive.setdefault((kind,row['session_id']),[]).append(row)
    seen=set();matched=[];different=[];missing=[];ambiguous=[]
    for event in events:
        kind={'CashDividends':'dividends','Splits':'splits'}.get(event.get('type'))
        stamp=event.get('date')
        if kind is None or not isinstance(stamp,str) or not re.fullmatch(r'\d{8}',stamp):
            raise ValueError('MASSIVE_ACTION_IBKR_EVENT_IDENTITY_REQUIRED')
        session=day(stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:]);value=number(event.get('value'),kind=='splits')
        if kind=='dividends' and event.get('currency')!='USD':
            raise PermissionError('MASSIVE_ACTION_IBKR_CURRENCY_CONFLICT')
        if not start<=session<=end:continue
        key=(kind,str(session))
        if key in seen:raise ValueError('MASSIVE_ACTION_IBKR_DUPLICATE_EVENT')
        seen.add(key);rows=massive.get(key,[])
        if not rows:
            missing.append(dict(kind=kind,session_id=str(session),original_IB_event=deepcopy(event)))
            continue
        if len(rows)!=1:
            ambiguous.append(dict(kind=kind,session_id=str(session),original_IB_event=deepcopy(event),
                Massive_original_rows=[deepcopy(r['original_row']) for r in rows],
                reason='MULTIPLE_EVENTS_SAME_DATE_REQUIRE_EXACT_EVENT_MATCH'))
            continue
        other=rows[0]
        observed=other['original_cash_amount'] if kind=='dividends' else other['new_per_old']
        row=dict(kind=kind,session_id=str(session),IB_original_value=event['value'],Massive_original_value=observed)
        (matched if value==Decimal(observed) else different).append(row)
    return dict(matching_numeric_observations=matched,differing_original_values=different,
        ambiguous_same_date_events=ambiguous,
        IB_events_not_observed_in_Massive=missing,
        Massive_events_not_observed_in_IB=[dict(kind=k,session_id=s,original_row=deepcopy(r['original_row']))
            for (k,s),rows in sorted(massive.items()) if (k,s) not in seen for r in rows],
        agreement_attests_complete_coverage=False,agreement_attests_historical_PIT=False,
        cash_or_split_basis_reconciled=False,original_values_repaired=False,
        quantities_or_prices_adjusted=False)


def read(descriptor,symbol,evaluation_at):
    manifest=json.loads(pinned(descriptor))
    if (manifest.get('schema_version')!=SCHEMA or manifest.get('symbol')!=symbol
        or manifest.get('provider')!='MASSIVE' or manifest.get('currency')!='USD'
        or not isinstance(symbol,str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]*',symbol)
        or not manifest.get('source_reference')
        or time(manifest['known_by'])>time(evaluation_at)):
        raise PermissionError('MASSIVE_ACTION_ASSET_PROVIDER_OR_TIME_MISMATCH')
    start=day(manifest['requested_start']);end=day(manifest['requested_end'])
    if start>end or end>time(evaluation_at).astimezone(ZoneInfo('America/New_York')).date():
        raise ValueError('MASSIVE_ACTION_REQUEST_DATE_ORDER')
    if set(manifest.get('sources',{}))!={'dividends','splits'}:
        raise ValueError('MASSIVE_ACTION_BOTH_ORIGINAL_ROUTES_REQUIRED')
    observations={};ids=set()
    for kind,column in (('dividends','ex_dividend_date'),('splits','execution_date')):
        rows,warning,captured=original_table(manifest['sources'][kind],kind,symbol,start,end,manifest['known_by'])
        records=[];dates=[]
        for row in rows:
            event=day(row[column]);eid=row['id']
            if not eid or eid in ids or row['ticker']!=symbol or not start<=event<=end:
                raise PermissionError('MASSIVE_ACTION_IDENTITY_DATE_OR_DUPLICATE_CONFLICT')
            ids.add(eid);dates.append(event)
            normalized={}
            if kind=='dividends':
                if row['currency']!='USD':raise PermissionError('MASSIVE_ACTION_CURRENCY_CONFLICT')
                number(row['cash_amount'])
                declared=day(row['declaration_date']) if row['declaration_date'] else None
                if declared is not None and declared>event:
                    raise ValueError('MASSIVE_ACTION_DECLARATION_AFTER_EX_DATE')
                normalized=dict(original_cash_amount=row['cash_amount'],currency=row['currency'],
                    declaration_date=row['declaration_date'] or None,
                    cash_per_old_share_basis_verified=False,
                    split_adjusted_cash_amount_not_used=row.get('split_adjusted_cash_amount'))
            else:
                old=number(row['split_from'],True);new=number(row['split_to'],True)
                if row['adjustment_type'] not in ('forward_split','reverse_split','stock_dividend'):
                    raise ValueError('MASSIVE_ACTION_UNSUPPORTED_ADJUSTMENT_TYPE')
                with localcontext() as ctx:
                    ctx.prec=max(50,len(old.as_tuple().digits)+len(new.as_tuple().digits)+12)
                    ratio=str(new/old)
                normalized=dict(split_from=row['split_from'],split_to=row['split_to'],new_per_old=ratio,
                    adjustment_type=row['adjustment_type'],pure_split_semantics_verified=False,
                    historical_adjustment_factor_not_used=row.get('historical_adjustment_factor'))
            records.append(dict(event_id=eid,session_id=str(event),original_row=deepcopy(row),
                **normalized,source_sha256=manifest['sources'][kind]['source']['sha256'],
                observed_at=captured,available_at=None,historical_PIT_verified=False,
                native_wealth_event_applied=False))
        if dates!=sorted(dates):raise ValueError('MASSIVE_ACTION_ORIGINAL_DATE_ORDER')
        observations[kind]=dict(records=records,warning=warning,
            original_response_status='PROVIDER_WARNING' if warning else 'RECORDS_OBSERVED',
            complete_event_coverage_verified=False,pagination_completeness_attested=False)
    comparison=None
    if manifest.get('ibkr_comparison_source') is not None:
        from pm_source_document import history
        source=manifest['ibkr_comparison_source']
        if source.get('symbol')!=symbol or time(source['retrieved_at'])>time(manifest['known_by']):
            raise PermissionError('MASSIVE_ACTION_IBKR_COMPARISON_ASSET_OR_TIME')
        original,proof=history(source)
        comparison={**compare_ibkr(observations,original.get('corp_actions'),start,end),
            'source_descriptor':deepcopy(source),'original_query_and_capture':proof}
    result=dict(schema_version='Family.W8.MassiveActionQualification.v1',symbol=symbol,
        evaluation_at=evaluation_at,source_descriptor=deepcopy(descriptor),provider='MASSIVE',currency='USD',
        requested_start=str(start),requested_end=str(end),known_by=manifest['known_by'],
        corporate_action_observations=observations,cross_provider_comparison=comparison,
        listing_and_share_class_history_verified=False,historical_publication_and_revision_verified=False,
        complete_corporate_action_coverage_verified=False,qualified_native_actions=None,
        qP_history_qualified=False,qV_history_qualified=False,
        issues=['ORIGINAL_ISSUER_LISTING_EVENT_COVERAGE_AND_VINTAGES_STILL_REQUIRED',
            'DATE_ONLY_DECLARATION_NOT_A_PUBLICATION_TIMESTAMP',
            'ADJUSTMENT_FACTORS_NOT_NATIVE_SPLIT_OR_CASH_BASIS',
            'RETURNED_RECORDS_OR_EMPTY_WARNING_NOT_COMPLETE_EVENT_BOOK'],trade_action='NO_TRADE')
    result['digest']=digest(result)
    return result

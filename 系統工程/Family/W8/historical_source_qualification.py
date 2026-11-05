"""Audit acquired raw history before it can become a native PV2 source.

Provider entitlement gaps, empty warning text and date-only declarations do
not become complete calendars, empty action books or historical PIT receipts.
No price substitution, adjusted-close wealth, qP/qV value or buy rule is made.
"""
from copy import deepcopy
from datetime import datetime,date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from io import StringIO
import csv,json,re
from family_input import digest
from sec_publication_source import instant


def pinned(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('HISTORY_INTAKE_ORIGINAL_BYTES_CHANGED')
    return raw.decode('utf-8-sig')


def nonnegative(value,*,positive=False):
    if value is None or isinstance(value,bool):raise ValueError('HISTORY_INTAKE_ORIGINAL_NUMBER_REQUIRED')
    result=Decimal(str(value))
    if not result.is_finite() or result<0 or positive and result==0:raise ValueError('HISTORY_INTAKE_INVALID_NUMBER')
    return result


def table(text,required):
    if text.startswith('Warning ['):
        return None,text.strip()
    reader=csv.DictReader(StringIO(text))
    if not set(required)<=set(reader.fieldnames or []):raise ValueError('HISTORY_INTAKE_ORIGINAL_COLUMNS_REQUIRED')
    rows=list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('HISTORY_INTAKE_CSV_ROW_COVERAGE')
    return rows,None


def read_market(descriptor,symbol,evaluation_at):
    manifest=json.loads(pinned(descriptor))
    if (manifest.get('schema_version')!='Family.W8.HistoricalMarketIntake.v1'
        or manifest.get('symbol')!=symbol or manifest.get('provider')!='MASSIVE'
        or manifest.get('exchange_timezone')!='America/New_York'
        or instant(manifest['known_by'])>instant(evaluation_at)):
        raise PermissionError('HISTORY_INTAKE_SYMBOL_PROVIDER_OR_TIME_MISMATCH')
    start=date.fromisoformat(manifest['requested_start']);end=date.fromisoformat(manifest['requested_end'])
    if start>end or end>instant(evaluation_at).astimezone(ZoneInfo('America/New_York')).date():
        raise ValueError('HISTORY_INTAKE_REQUEST_DATE_ORDER')
    price=manifest['prices'];query=price['query']
    expected='/v2/aggs/ticker/'+symbol+'/range/1/day/'+str(start)+'/'+str(end)
    if query.get('path')!=expected or query.get('params',{}).get('adjusted') is not False or query['params'].get('sort')!='asc':
        raise PermissionError('HISTORY_INTAKE_UNADJUSTED_EXACT_QUERY_REQUIRED')
    rows,warning=table(pinned(price['source']),('o','h','l','c','v','t'));bars=[];stamps=[];sessions=set();issues=[]
    if warning:issues.append({'field':'raw_prices','code':'PROVIDER_WARNING_NOT_A_HISTORY_DATASET','original':warning})
    for row in rows or []:
        if not re.fullmatch(r'\d+',row['t']):raise ValueError('HISTORY_INTAKE_BAR_TIMESTAMP_REQUIRED')
        stamp=int(row['t']);session=datetime.fromtimestamp(stamp/1000,ZoneInfo('America/New_York')).date()
        if not start<=session<=end or session in sessions:raise ValueError('HISTORY_INTAKE_DUPLICATE_OR_OUTSIDE_SESSION')
        values={k:nonnegative(row[k],positive=k!='v') for k in ('o','h','l','c','v')}
        if values['l']>min(values['o'],values['c']) or values['h']<max(values['o'],values['c']):
            raise ValueError('HISTORY_INTAKE_ORIGINAL_OHLC_CONFLICT')
        stamps.append(stamp);sessions.add(session)
        bars.append({'session_id':str(session),'timestamp':stamp,'open':str(values['o']),'high':str(values['h']),
            'low':str(values['l']),'close':str(values['c']),'volume':str(values['v']),
            'available_at':None,'historical_PIT_verified':False})
    if stamps!=sorted(stamps):raise ValueError('HISTORY_INTAKE_BAR_ORDER')
    if bars and bars[0]['session_id']!=str(start):issues.append({'field':'raw_prices.requested_start',
        'code':'REQUESTED_START_NOT_RETURNED__LISTING_CALENDAR_OR_ENTITLEMENT_PROOF_REQUIRED',
        'requested':str(start),'observed':bars[0]['session_id']})
    actions={}
    for kind,endpoint,date_column in (('dividends','/stocks/v1/dividends','ex_dividend_date'),('splits','/stocks/v1/splits','execution_date')):
        source=manifest[kind];args=source['query'];params=args.get('params',{})
        if (args.get('path')!=endpoint or params.get('ticker')!=symbol
            or params.get(date_column+'.gte')!=str(start) or params.get(date_column+'.lte')!=str(end)):
            raise PermissionError('HISTORY_INTAKE_ACTION_SCOPE_QUERY_MISMATCH')
        raw,warning=table(pinned(source['source']),('id','ticker',date_column));events=[];seen=set()
        if warning:issues.append({'field':kind,'code':'EMPTY_OR_OTHER_WARNING_IS_NOT_COMPLETE_ZERO_EVENTS','original':warning})
        for row in raw or []:
            day=date.fromisoformat(row[date_column]);identity=row['id']
            if not identity or identity in seen or row['ticker']!=symbol or not start<=day<=end:
                raise ValueError('HISTORY_INTAKE_ACTION_IDENTITY_OR_DATE_CONFLICT')
            seen.add(identity)
            if kind=='dividends':
                value={'original_cash_amount':str(nonnegative(row.get('cash_amount'))),'currency':row.get('currency'),
                    'declaration_date':row.get('declaration_date') or None,
                    'split_adjusted_cash_amount_not_used':row.get('split_adjusted_cash_amount')}
                if value['currency']!=manifest['quote_currency']:raise PermissionError('HISTORY_INTAKE_DIVIDEND_CURRENCY_CONFLICT')
            else:
                old=nonnegative(row.get('split_from'),positive=True);new=nonnegative(row.get('split_to'),positive=True)
                value={'new_per_old':str(new/old),'adjustment_type':row.get('adjustment_type'),
                    'historical_adjustment_factor_not_used':row.get('historical_adjustment_factor')}
            events.append({'event_id':identity,'session_id':str(day),**value,'source_row':deepcopy(row),
                'available_at':None,'historical_PIT_verified':False,'native_wealth_event_applied':False})
        actions[kind]={'records':events,'warning':warning,'complete_event_coverage_verified':False}
    issues.extend([{'field':'raw_prices.available_at/revision','code':'HISTORICAL_PRICE_PUBLICATION_AND_REVISION_RECEIPTS_REQUIRED'},
        {'field':'corporate_actions.available_at/coverage','code':'DATE_ONLY_DECLARATION_AND_QUERY_ROWS_DO_NOT_ATTEST_PIT_OR_EVENT_COMPLETENESS'},
        {'field':'calendar','code':'SOURCE_OWNED_COMPLETED_CALENDAR_AND_KNOWLEDGE_TIMES_REQUIRED'},
        {'field':'valuation_history','code':'CURRENT_PE_OR_RAW_PRICE_IS_NOT_OWN_PRIMARY_METRIC_HISTORY'}])
    out=dict(schema_version=manifest['schema_version'],symbol=symbol,evaluation_at=evaluation_at,
        source_descriptor=deepcopy(descriptor),provider='MASSIVE',requested_start=str(start),requested_end=str(end),
        query_requested_unadjusted=True,raw_observed_bars=bars,corporate_action_observations=actions,
        returned_bar_count=len(bars),known_by=manifest['known_by'],issues=issues,
        source_complete_for_requested_range=False,qualified_native_price_history=None,
        qP_history_qualified=False,qV_history_qualified=False,historical_price_PIT_verified=False,
        adjusted_close_or_split_adjusted_dividend_used=False,trade_action='NO_TRADE')
    out['digest']=digest(out);return out


def bind(sources,request,symbol):
    result={}
    if not isinstance(sources,dict) or not sources:raise ValueError('HISTORY_INTAKE_NAMED_SOURCE_REQUIRED')
    if set(sources)-{'sec_filings','market_acquisition','twse_own_history','ibkr_history','corporate_actions','issuer_distributions'}:raise ValueError('HISTORY_INTAKE_UNKNOWN_SOURCE_ROUTE')
    if sources.get('issuer_distributions') is not None:
        from ishares_distribution_source import read
        result['issuer_distributions']=read(sources['issuer_distributions'],symbol,request['evaluation_at'])
    if sources.get('corporate_actions') is not None:
        from massive_action_source import read
        result['corporate_actions']=read(sources['corporate_actions'],symbol,request['evaluation_at'])
    if sources.get('sec_filings') is not None:
        from sec_publication_source import read
        result['sec_filings']=read(sources['sec_filings'],symbol,request['evaluation_at'])
    if sources.get('market_acquisition') is not None:
        result['market_acquisition']=read_market(sources['market_acquisition'],symbol,request['evaluation_at'])
    if sources.get('twse_own_history') is not None:
        from twse_own_history_source import read
        result['twse_own_history']=read(sources['twse_own_history'],symbol,request['evaluation_at'])
    if sources.get('ibkr_history') is not None:
        from ibkr_daily_source import audit
        source=sources['ibkr_history']
        if source.get('symbol')!=symbol:raise PermissionError('HISTORY_INTAKE_IBKR_ASSET_MISMATCH')
        result['ibkr_history']=audit(source,request['evaluation_at'])
    out=dict(schema_version='Family.W8.AssetHistorySourceQualification.v1',client_id=request['client_id'],
        run_id=request['run_id'],asset_id=symbol,evaluation_at=request['evaluation_at'],
        source_db_sha256=request['client_snapshot']['payload']['source_sha256'],sources=result,
        qualified_qP_history=None,qualified_qV_history=None,financial_qualification_released=False,trade_action='NO_TRADE')
    out['digest']=digest(out);return out

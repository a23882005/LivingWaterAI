"""Pinned TWSE monthly originals, with independent market-date coverage.

STOCK_DAY is an exchange transaction record. FMTQIK dates independently
identify days on which the market traded; neither feed supplies historical
publication/revision receipts, listing suspensions or complete action books.
Missing pages and missing security bars stay visible and never become wealth,
zero events, a source-owned completed calendar or approved native qP/qV.
"""
from datetime import date, datetime
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo
import json, re

from family_input import digest
from member_market_source import time

PRICE_FIELDS=('日期','成交股數','成交金額','開盤價','最高價','最低價','收盤價','漲跌價差','成交筆數')
MARKET_FIELDS=('日期','成交股數','成交金額','成交筆數','發行量加權股價指數','漲跌點數')


def _bytes(source,base=None):
    path=Path(source['local_path'])
    if base is not None and not path.is_absolute():
        path=(base/path).resolve()
        if not path.is_relative_to(base):
            raise PermissionError('TWSE_HISTORY_PATH_OUTSIDE_CAPTURE')
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('TWSE_HISTORY_ORIGINAL_BYTES_CHANGED')
    return raw


def months(start,end):
    result=[];year,month=start.year,start.month
    while (year,month)<=(end.year,end.month):
        result.append(f'{year:04}{month:02}01')
        year,month=(year+1,1) if month==12 else (year,month+1)
    return result


def _day(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{3}/\d{2}/\d{2}',value):
        raise ValueError('TWSE_HISTORY_ORIGINAL_ROC_DATE_REQUIRED')
    year,month,day=map(int,value.split('/'))
    return date(year+1911,month,day)


def _number(value,*,integer=False):
    # Validate grouping rather than repairing malformed comma spellings.
    pattern=r'(?:\d+|\d{1,3}(?:,\d{3})+)' + ('' if integer else r'(?:\.\d+)?')
    if not isinstance(value,str) or not re.fullmatch(pattern,value):
        raise ValueError('TWSE_HISTORY_ORIGINAL_NUMBER_REQUIRED')
    result=Decimal(value.replace(',',''))
    if not result.is_finite() or result<0:
        raise ValueError('TWSE_HISTORY_INVALID_NUMBER')
    return result


def _page(page,kind,stamp,symbol,known_by,*,base=None):
    if page.get('status') not in ('ACQUIRED','NOT_ACQUIRED','UNAVAILABLE'):
        raise ValueError('TWSE_HISTORY_PAGE_STATUS_REQUIRED')
    if page['status']!='ACQUIRED':
        if page.get('source') is not None or page.get('receipt_source') is not None:
            raise PermissionError('TWSE_HISTORY_UNAVAILABLE_PAGE_CANNOT_SUPPLY_DATA')
        failure=page.get('failure_source')
        if failure is not None:
            record=json.loads(_bytes(failure,base))
            if (record.get('symbol')!=('CALENDAR' if kind=='market' else symbol)
                or record.get('month')!=stamp or record.get('status')!='SOURCE_UNAVAILABLE'):
                raise PermissionError('TWSE_HISTORY_FAILURE_RECEIPT_SCOPE')
        return None
    source=page['source'];raw=_bytes(source,base);receipt=json.loads(_bytes(page['receipt_source'],base))
    endpoint='FMTQIK' if kind=='market' else 'STOCK_DAY'
    params={'response':['json'],'date':[stamp]}
    if kind=='prices':params['stockNo']=[symbol]
    url=urlparse(receipt['source_url'])
    if (url.scheme!='https' or url.netloc!='www.twse.com.tw'
        or url.path!='/exchangeReport/'+endpoint or url.fragment
        or parse_qs(url.query,keep_blank_values=True)!=params
        or receipt.get('final_url',receipt['source_url'])!=receipt['source_url']
        or type(receipt.get('status')) is not int or receipt['status']!=200
        or receipt.get('sha256')!=source['sha256']
        or not time(receipt['started_at'])<=time(receipt['retrieved_at'])<=time(known_by)):
        raise PermissionError('TWSE_HISTORY_QUERY_RESPONSE_OR_TIME_MISMATCH')
    data=json.loads(raw)
    fields=PRICE_FIELDS if kind=='prices' else MARKET_FIELDS
    actual=data.get('fields',[])
    if (data.get('stat')!='OK' or data.get('date')!=stamp
        or not isinstance(actual,list) or len(actual)!=len(set(actual))
        or tuple(actual[:len(fields)])!=fields
        or actual[len(fields):] not in ([],['註記'])
        or not isinstance(data.get('data'),list) or not data['data']
        or ('rows' in receipt and (type(receipt['rows']) is not int or receipt['rows']!=len(data['data'])))):
        raise ValueError('TWSE_HISTORY_ORIGINAL_MONTH_TABLE_REQUIRED')
    prefix=str(int(stamp[:4])-1911)+'年'+stamp[4:6]+'月'
    title=data.get('title','')
    if not title.startswith(prefix) or (kind=='prices' and not re.match(re.escape(prefix)+r'\s+'+re.escape(symbol)+r'\s',title)):
        raise PermissionError('TWSE_HISTORY_ORIGINAL_TITLE_OR_SYMBOL_MISMATCH')
    result=[];seen=[]
    for index,row in enumerate(data['data']):
        if not isinstance(row,list) or len(row)!=len(actual):
            raise ValueError('TWSE_HISTORY_ORIGINAL_ROW_COVERAGE')
        day=_day(row[0])
        if day.strftime('%Y%m01')!=stamp:
            raise ValueError('TWSE_HISTORY_ROW_OUTSIDE_ORIGINAL_MONTH')
        seen.append(day.isoformat())
        item=dict(session_id=day.isoformat(),source_sha256=source['sha256'],
            original_row_index=index,observed_at=receipt['retrieved_at'],available_at=None,
            historical_PIT_verified=False)
        if kind=='prices':
            values={key:_number(row[column],integer=key=='volume') for key,column in
                    (('open',3),('high',4),('low',5),('close',6),('volume',1))}
            if (min(values[k] for k in ('open','high','low','close'))<=0
                or values['low']>min(values['open'],values['close'])
                or values['high']<max(values['open'],values['close'])):
                raise ValueError('TWSE_HISTORY_ORIGINAL_OHLC_CONFLICT')
            item.update({k:str(v) for k,v in values.items()})
            item['original_values']=dict(zip(actual,row))
        else:
            for column in (1,2,3):_number(row[column],integer=True)
            _number(row[4])
        result.append(item)
    if seen!=sorted(set(seen)):
        raise ValueError('TWSE_HISTORY_DUPLICATE_OR_UNSORTED_SESSION')
    return result


def read(descriptor,symbol,evaluation_at,*,session_closes=None):
    manifest=json.loads(_bytes(descriptor))
    base=Path(descriptor['local_path']).resolve().parent if session_closes is not None else None
    symbol_pattern=r'\d{4,5}' if session_closes is not None else r'\d{4}'
    if (manifest.get('schema_version')!='Family.W8.TwseOwnHistoryIntake.v1'
        or manifest.get('provider')!='TWSE' or manifest.get('symbol')!=symbol
        or not re.fullmatch(symbol_pattern,symbol) or manifest.get('currency')!='TWD'
        or manifest.get('exchange')!='XTAI' or manifest.get('timezone')!='Asia/Taipei'
        or not manifest.get('source_reference') or time(manifest['known_by'])>time(evaluation_at)):
        raise PermissionError('TWSE_HISTORY_IDENTITY_OR_TIME_MISMATCH')
    start=date.fromisoformat(manifest['requested_start']);end=date.fromisoformat(manifest['requested_end'])
    if start>end or end>time(evaluation_at).astimezone(ZoneInfo('Asia/Taipei')).date():
        raise ValueError('TWSE_HISTORY_REQUEST_DATE_ORDER')
    expected=months(start,end);pages=manifest['months']
    if not isinstance(pages,list) or [p.get('month') for p in pages]!=expected:
        raise ValueError('TWSE_HISTORY_ALL_REQUESTED_MONTHS_MUST_BE_ACCOUNTED_FOR')
    bars=[];sessions=[];gaps=[];comparisons=[];excluded=[]
    for page in pages:
        stamp=page['month'];observed={}
        for kind in ('prices','market'):
            records=_page(page[kind],kind,stamp,symbol,manifest['known_by'],base=base)
            if records is None:
                gaps.append(dict(month=stamp,source=kind,status=page[kind]['status']))
            else:
                outside=[r for r in records if not start.isoformat()<=r['session_id']<=end.isoformat()]
                excluded.extend(dict(source=kind,session_id=r['session_id'],reason='OUTSIDE_REQUESTED_DATE_RANGE') for r in outside)
                records=[r for r in records if start.isoformat()<=r['session_id']<=end.isoformat()]
                # Monthly pages can contain today's unfinished session. A
                # dated row is no evidence of final intraday publication.
                final=[]
                for row in records:
                    local=time(row['observed_at']).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()
                    close_at=(session_closes or {}).get(row['session_id'])
                    published_after_close=(row['session_id']==local and close_at is not None
                        and time(row['observed_at'])>=close_at)
                    if row['session_id']>=local and not published_after_close:
                        excluded.append(dict(source=kind,session_id=row['session_id'],reason='CURRENT_OR_FUTURE_CAPTURE_DATE_NOT_FINAL_ATTESTED'))
                    else:final.append(row)
                records=final
            observed[kind]=records
        prices=observed['prices'];market=observed['market']
        if session_closes is not None and prices is not None:
            unconfirmed_days={r['session_id'] for r in excluded if r['source']=='market'
                and r['reason']=='CURRENT_OR_FUTURE_CAPTURE_DATE_NOT_FINAL_ATTESTED'}
            prices=[r for r in prices if r['session_id'] not in unconfirmed_days]
        if prices is not None:bars.extend(prices)
        if market is not None:sessions.extend(market)
        if prices is not None and market is not None:
            price_dates={r['session_id'] for r in prices};market_dates={r['session_id'] for r in market}
            comparisons.append(dict(month=stamp,market_sessions=len(market_dates),price_sessions=len(price_dates),
                missing_security_bars=sorted(market_dates-price_dates),
                security_bars_without_market_day=sorted(price_dates-market_dates)))
    if any(row['security_bars_without_market_day'] for row in comparisons):
        raise PermissionError('TWSE_HISTORY_SECURITY_BAR_ON_UNOBSERVED_MARKET_DAY')
    issues=[dict(field='month_pages',code='REQUESTED_MONTH_ORIGINALS_UNAVAILABLE',detail=g) for g in gaps]
    missing=[day for row in comparisons for day in row['missing_security_bars']]
    if missing:issues.append(dict(field='security_sessions',code='MARKET_OPEN_WITHOUT_SECURITY_BAR__SUSPENSION_OR_MISSING_DATA_PROOF_REQUIRED',sessions=missing))
    issues.extend([
        dict(field='raw_prices.available_at/revision',code='HISTORICAL_ORIGINAL_VINTAGE_AND_PUBLICATION_RECEIPTS_REQUIRED'),
        dict(field='corporate_actions',code='COMPLETE_OWN_LISTING_DIVIDEND_SPLIT_AND_SUSPENSION_COVERAGE_REQUIRED'),
        dict(field='calendar',code='MARKET_TRANSACTION_DATES_DO_NOT_ATTEST_SESSION_KNOWLEDGE_TIMES'),
        dict(field='valuation_history',code='TRANSACTION_PRICES_ARE_NOT_OWN_PRIMARY_VALUATION_METRIC_HISTORY')])
    out=dict(schema_version='Family.W8.TwseOwnHistoryQualification.v1',symbol=symbol,
        evaluation_at=evaluation_at,source_descriptor=deepcopy(descriptor),provider='TWSE',currency='TWD',exchange='XTAI',
        requested_start=str(start),requested_end=str(end),known_by=manifest['known_by'],
        raw_observed_bars=bars,returned_bar_count=len(bars),market_transaction_dates=sessions,
        requested_month_count=len(expected),unavailable_month_sources=gaps,monthly_coverage=comparisons,
        requested_month_pages_complete=not gaps,missing_security_bars=missing,excluded_rows=excluded,
        historical_price_PIT_verified=False,complete_corporate_action_coverage_verified=False,
        completed_calendar_qualified=False,qP_history_qualified=False,qV_history_qualified=False,
        qualified_native_price_history=None,adjusted_close_or_split_reconstruction_used=False,
        issues=issues,trade_action='NO_TRADE')
    out['digest']=digest(out)
    return out


def load_daily(source,evaluation_at,sessions,*,is_etf):
    """Observe published TWSE ETF bars with an independent market-day record."""
    symbol=source['symbol']
    identity={'provider_symbol':symbol,'exchange':'XTAI','provider_exchange':'XTAI',
        'currency':'TWD','timezone':'Asia/Taipei'}
    if is_etf is not True or any(source.get(k)!=v for k,v in identity.items()):
        raise PermissionError('MEMBER_MARKET_TWSE_LISTING_IDENTITY')
    closes={r['session_id']:time(r['close_at']) for r in sessions}
    try:
        observed=read(source,symbol,evaluation_at,session_closes=closes)
    except ValueError as exc:
        raise ValueError('MEMBER_MARKET_TWSE_'+str(exc)) from exc
    if observed['known_by']!=source['retrieved_at']:
        raise PermissionError('MEMBER_MARKET_TWSE_CAPTURE_TIME_MISMATCH')
    market_days={r['session_id'] for r in observed['market_transaction_dates']}
    rows=[r for r in observed['raw_observed_bars'] if r['session_id'] in market_days]
    timestamps=[int(datetime.fromisoformat(r['session_id']).replace(tzinfo=ZoneInfo('Asia/Taipei')).timestamp())
        for r in rows]
    quotes={k:[r[k] for r in rows] for k in ('open','high','low','close','volume')}
    meta=dict(symbol=symbol,currency='TWD',exchangeTimezoneName='Asia/Taipei',
        exchangeName='XTAI',instrumentType='ETF')
    evidence=dict(provider='TWSE_STOCK_DAY',qualification_digest=observed['digest'],
        price_basis='EXCHANGE_PUBLISHED_TRANSACTION_OHLC__NOT_PIT_WEALTH',
        historical_PIT_attested=False,corporate_action_coverage_attested=False,
        independently_observed_market_days=True,excluded_rows=observed['excluded_rows'])
    return meta,quotes,timestamps,evidence

"""A complete dated Nasdaq historical response, separate from quote prices.

The market-closed quote identifies the latest dated daily record. Its OHLCV
always comes entirely from the historical response; no provider repairs occur.
This is an observation source, not historical PIT or raw-wealth attestation.
"""
from datetime import datetime, time as clock_time
from decimal import Decimal
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo
import re


def load(source, evaluation_at):
    from member_market_source import read_json,time
    symbol=source['provider_symbol'];url=urlparse(source['source_reference'])
    if (url.scheme!='https' or url.hostname!='api.nasdaq.com'
        or url.path!=f'/api/quote/{symbol}/historical' or parse_qs(url.query).get('assetclass')!=['etf']):
        raise PermissionError('MEMBER_MARKET_NASDAQ_ORIGINAL_ENDPOINT')
    history=read_json(source)
    if (not source.get('historical_retrieved_at') or
        time(source['historical_retrieved_at'])>time(source['retrieved_at'])):
        raise PermissionError('MEMBER_MARKET_NASDAQ_HISTORICAL_ACQUISITION_REQUIRED')
    info_source=source['completion_source'];identity_source=source['identity_source']
    for descriptor in (info_source,identity_source):
        if time(descriptor['retrieved_at'])>min(time(source['retrieved_at']),time(evaluation_at)):
            raise PermissionError('MEMBER_MARKET_NASDAQ_EVIDENCE_AVAILABILITY')
    info_url=urlparse(info_source['source_reference'])
    if (info_url.scheme!='https' or info_url.hostname!='api.nasdaq.com'
        or info_url.path!=f'/api/quote/{symbol}/info' or parse_qs(info_url.query).get('assetclass')!=['etf']):
        raise PermissionError('MEMBER_MARKET_NASDAQ_COMPLETION_ENDPOINT')
    raw_info=read_json(info_source);info=raw_info.get('data') or {};data=history.get('data') or {}
    if (history.get('status',{}).get('rCode')!=200 or raw_info.get('status',{}).get('rCode')!=200
        or data.get('symbol')!=symbol or info.get('symbol')!=symbol
        or info.get('exchange')!=source['provider_exchange'] or info.get('assetClass')!='ETF'):
        raise PermissionError('MEMBER_MARKET_NASDAQ_IDENTITY')
    if info.get('marketStatus')!='Closed':raise ValueError('MEMBER_MARKET_NASDAQ_CLOSED_SESSION_REQUIRED')
    identity_url=urlparse(identity_source['source_reference'])
    if (identity_url.scheme!='https' or identity_url.hostname not in ('query1.finance.yahoo.com','query2.finance.yahoo.com')
        or identity_url.path!=f'/v8/finance/chart/{symbol}'):
        raise PermissionError('MEMBER_MARKET_NASDAQ_IDENTITY_SOURCE_ENDPOINT')
    identity_chart=read_json(identity_source)['chart'];identity_rows=identity_chart.get('result') or []
    if identity_chart.get('error') or len(identity_rows)!=1:raise PermissionError('MEMBER_MARKET_NASDAQ_IDENTITY_SOURCE')
    identity=identity_rows[0]['meta']
    if (identity.get('symbol')!=symbol or identity.get('currency')!=source['currency']
        or identity.get('exchangeTimezoneName')!=source['timezone'] or identity.get('instrumentType')!='ETF'
        or source['currency']!='USD' or source['timezone']!='America/New_York'
        or source['provider_exchange'] not in ('NYSE','NYSEARCA','NASDAQ')):
        raise PermissionError('MEMBER_MARKET_NASDAQ_CURRENCY_OR_LISTING')
    venues={'NYQ':'NYSE','PCX':'NYSEARCA','NMS':'NASDAQ','NGM':'NASDAQ','NCM':'NASDAQ'}
    if venues.get(identity.get('exchangeName'))!=info['exchange']:
        raise PermissionError('MEMBER_MARKET_NASDAQ_INDEPENDENT_LISTING_CONFLICT')
    rows=(data.get('tradesTable') or {}).get('rows')
    if not isinstance(rows,list) or not rows or type(data.get('totalRecords')) is not int or len(rows)!=data['totalRecords']:
        raise ValueError('MEMBER_MARKET_NASDAQ_COMPLETE_RESPONSE_REQUIRED')
    try:
        dates=[datetime.strptime(r['date'],'%m/%d/%Y').date() for r in rows]
        quoted=datetime.strptime(info['primaryData']['lastTradeTimestamp'],'%b %d, %Y').date()
    except (ValueError,KeyError,TypeError):raise ValueError('MEMBER_MARKET_NASDAQ_DATED_DAILY_RECORD_REQUIRED') from None
    if dates!=sorted(set(dates),reverse=True) or dates[0]!=quoted:
        raise ValueError('MEMBER_MARKET_NASDAQ_DAILY_DATE_OR_ORDER')
    def number(value):
        if not isinstance(value,str):raise ValueError('MEMBER_MARKET_NASDAQ_SOURCE_NUMBER')
        value=value.removeprefix('$').replace(',','').strip()
        if value in ('N/A','--',''):return None
        if not re.fullmatch(r'\d+(?:\.\d+)?',value):raise ValueError('MEMBER_MARKET_NASDAQ_SOURCE_NUMBER')
        return Decimal(value)
    if number(rows[0]['close'])!=number(info['primaryData']['lastSalePrice']):
        raise ValueError('MEMBER_MARKET_NASDAQ_DATED_CLOSE_CONFLICT')
    zone=ZoneInfo(source['timezone']);stamps=[];quotes={k:[] for k in ('open','high','low','close','volume')}
    for day,row in reversed(list(zip(dates,rows))):
        # Noon is solely a date-key encoding for the common intake. It is not
        # an invented publication or last-trade time.
        stamps.append(int(datetime.combine(day,clock_time(12),zone).timestamp()))
        for key in quotes:quotes[key].append(number(row[key]))
    meta={'symbol':symbol,'currency':identity['currency'],'exchangeName':info['exchange'],
        'exchangeTimezoneName':identity['exchangeTimezoneName'],'instrumentType':'ETF'}
    evidence={'provider':'NASDAQ_HISTORICAL','latest_dated_daily_record':dates[0].isoformat(),
        'market_status':info['marketStatus'],'completion_source_sha256':info_source['sha256'],
        'identity_source_sha256':identity_source['sha256'],'historical_source_sha256':source['sha256'],
        'ohlcv_entirely_from_historical_response':True,'quote_volume_not_used_to_repair_daily_volume':True,
        'date_key_encoding_is_not_publication_time':True,'historical_PIT_attested':False}
    return meta,quotes,stamps,evidence

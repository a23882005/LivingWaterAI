"""Explicit raw daily OHLC intake, without historical PIT/wealth attestation.

The pinned connector response, query, security reference and acquisition clock
must agree. A completed snapshot supplies observations to existing producers;
it does not supply historical publication times or complete corporate actions.
"""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def _table(text, columns):
    if text.startswith('Warning ['):
        raise ValueError('MEMBER_MARKET_MASSIVE_PROVIDER_WARNING')
    table=csv.DictReader(StringIO(text));fields=table.fieldnames or []
    if len(fields)!=len(set(fields)) or not set(columns)<=set(fields):
        raise ValueError('MEMBER_MARKET_MASSIVE_ORIGINAL_COLUMNS_REQUIRED')
    rows=list(table)
    if not rows or any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('MEMBER_MARKET_MASSIVE_ORIGINAL_RECORD_COVERAGE')
    return rows


def _bytes(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('MEMBER_MARKET_MASSIVE_ORIGINAL_BYTES_CHANGED')
    return raw


def load(source,evaluation_at):
    from member_market_source import read_json,time
    symbol=source['provider_symbol'];zone=ZoneInfo('America/New_York')
    if source['symbol']!=symbol:
        raise PermissionError('MEMBER_MARKET_MASSIVE_ASSET_ALIAS_NOT_VERIFIED')
    acquisition=read_json(source['acquisition_source'])
    expected='/v2/aggs/ticker/'+symbol+'/range/1/day/'+source['requested_start']+'/'+source['requested_end']
    if (acquisition.get('schema_version')!='Family.W8.MassiveDailyAcquisition.v1'
        or acquisition.get('tool')!='Massive.call_api' or acquisition.get('symbol')!=symbol
        or acquisition.get('path')!=expected
        or acquisition.get('params')!={'adjusted':False,'sort':'asc','limit':50000}
        or acquisition.get('params',{}).get('adjusted') is not False
        or acquisition.get('response_is_error') is not False
        or acquisition.get('retrieved_at')!=source['retrieved_at']
        or source.get('source_reference')!='https://api.massive.com'+expected+'?adjusted=false&sort=asc&limit=50000'):
        raise PermissionError('MEMBER_MARKET_MASSIVE_RAW_QUERY_OR_RECEIPT_MISMATCH')
    started=time(acquisition['started_at']);retrieved=time(acquisition['retrieved_at'])
    if not started<=retrieved<=time(evaluation_at):
        raise PermissionError('MEMBER_MARKET_MASSIVE_ACQUISITION_TIME')
    raw=_bytes(source)
    if (sha256(raw).hexdigest()!=acquisition.get('response_sha256')
        or raw!=acquisition['response_csv'].encode('utf-8')):
        raise PermissionError('MEMBER_MARKET_MASSIVE_RESPONSE_BYTES_MISMATCH')
    reference=source['identity_source'];reference_rows=_table(_bytes(reference).decode('utf-8-sig'),
        ('ticker','market','locale','type','active','currency_name','primary_exchange','share_class_figi'))
    day=time(evaluation_at).astimezone(zone).date().isoformat()
    if (len(reference_rows)!=1 or reference.get('source_reference')!='https://api.massive.com/v3/reference/tickers/'+symbol+'?date='+day
        or time(reference['retrieved_at'])>retrieved):
        raise PermissionError('MEMBER_MARKET_MASSIVE_REFERENCE_SCOPE_OR_TIME')
    security=reference_rows[0]
    if (security['ticker']!=symbol or security['market']!='stocks' or security['locale']!='us'
        or security['active']!='true' or security['type'] not in ('ETF','CS','ADRC','ADRP')
        or security['currency_name']!='usd' or source['currency']!='USD'
        or source['timezone']!='America/New_York'
        or not re.fullmatch('[A-Z0-9]{4}',security['primary_exchange'])
        or not re.fullmatch('BBG[A-Z0-9]{9}',security['share_class_figi'])
        or source['provider_exchange']!=security['primary_exchange']
        or source['exchange']!=security['primary_exchange']):
        raise PermissionError('MEMBER_MARKET_MASSIVE_ORIGINAL_SECURITY_IDENTITY')
    rows=_table(raw.decode('utf-8-sig'),('o','h','l','c','v','t'))
    stamps=[];dates=[];quotes={k:[] for k in ('open','high','low','close','volume')}
    start=datetime.strptime(source['requested_start'],'%Y-%m-%d').date()
    end=datetime.strptime(source['requested_end'],'%Y-%m-%d').date()
    if start>end or end>time(evaluation_at).astimezone(zone).date():
        raise ValueError('MEMBER_MARKET_MASSIVE_REQUEST_DATE_ORDER')
    for row in rows:
        if not re.fullmatch('[0-9]+',row['t']) or int(row['t'])%1000:
            raise ValueError('MEMBER_MARKET_MASSIVE_ORIGINAL_TIMESTAMP_REQUIRED')
        stamp=int(row['t'])//1000;session=datetime.fromtimestamp(stamp,zone).date()
        if not start<=session<=end:
            raise ValueError('MEMBER_MARKET_MASSIVE_BAR_OUTSIDE_REQUEST')
        dates.append(session.isoformat());stamps.append(stamp)
        for name,column in (('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')):
            try:
                value=Decimal(row[column])
                if not value.is_finite():raise InvalidOperation()
            except (InvalidOperation,ValueError):
                raise ValueError('MEMBER_MARKET_MASSIVE_ORIGINAL_NUMBER_REQUIRED') from None
            # Keep incoherent OHLC values as original rows. The common intake
            # retains the gap and independent Close path; no price is repaired.
            quotes[name].append(value)
    if dates!=sorted(set(dates)):
        raise ValueError('MEMBER_MARKET_MASSIVE_DUPLICATE_OR_UNSORTED_SESSION')
    meta={'symbol':symbol,'currency':'USD','exchangeTimezoneName':'America/New_York',
        'exchangeName':security['primary_exchange'],'instrumentType':'ETF' if security['type']=='ETF' else 'EQUITY'}
    evidence={'provider':'MASSIVE_RAW_DAILY','raw_unadjusted_request_verified':True,
        'request_receipt_sha256':source['acquisition_source']['sha256'],
        'raw_response_sha256':source['sha256'],'identity_source_sha256':reference['sha256'],
        'listing':security['primary_exchange'],'share_class':security['share_class_figi'],'currency':'USD',
        'requested_start':source['requested_start'],'requested_end':source['requested_end'],
        'returned_start':dates[0],'returned_end':dates[-1],'returned_rows':len(rows),
        'requested_range_complete_attested':False,'historical_identity_coverage_attested':False,
        'corporate_action_coverage_attested':False,'historical_PIT_attested':False,
        'availability_basis':'OBSERVED_AT_ACQUISITION__NOT_HISTORICAL_PUBLICATION',
        'ohlcv_from_single_original_response':True,'other_provider_price_repairs':False}
    return meta,quotes,stamps,evidence

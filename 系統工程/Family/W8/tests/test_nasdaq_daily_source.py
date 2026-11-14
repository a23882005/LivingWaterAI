"""Synthetic coherent daily-history and actual-acquisition boundaries."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from member_market_source import read_market


def source_case(tmp_path):
    def save(name,data):
        p=tmp_path/name;p.write_text(json.dumps(data));return dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest())
    at='2026-11-03T00:00:00Z';rows=[];sessions=[]
    for day in ['2026-10-28','2026-10-29','2026-10-30','2026-11-02']:
        rows.append(dict(date=datetime.strptime(day,'%Y-%m-%d').strftime('%m/%d/%Y'),open='100',high='101',low='99',close='100',volume='1,000'))
        sessions.append(dict(session_id=day,open_at=day+'T13:30:00Z',close_at=day+'T21:00:00Z'))
    history=save('history.json',dict(status=dict(rCode=200),data=dict(symbol='TEST',totalRecords=len(rows),tradesTable=dict(rows=list(reversed(rows))))))
    info=save('info.json',dict(status=dict(rCode=200),data=dict(symbol='TEST',assetClass='ETF',exchange='NYSE',marketStatus='Closed',
        primaryData=dict(lastTradeTimestamp='Nov 2, 2026',lastSalePrice='$100',volume='DIFFERENT_QUOTE_SCOPE'))))
    identity=save('identity.json',dict(chart=dict(error=None,result=[dict(meta=dict(symbol='TEST',currency='USD',exchangeName='NYQ',exchangeTimezoneName='America/New_York',instrumentType='ETF'))])))
    calendar=save('calendar.json',dict(exchange='XNYS',timezone='America/New_York',provider='SYNTHETIC',version='1',coverage_cutoff='2026-11-04T00:00:00Z',sessions=sessions))
    info.update(source_reference='https://api.nasdaq.com/api/quote/TEST/info?assetclass=etf',retrieved_at=at)
    identity.update(source_reference='https://query1.finance.yahoo.com/v8/finance/chart/TEST',retrieved_at=at)
    return dict(**history,provider='NASDAQ_HISTORICAL',symbol='TEST',provider_symbol='TEST',currency='USD',timezone='America/New_York',
        provider_exchange='NYSE',exchange='XNYS',source_reference='https://api.nasdaq.com/api/quote/TEST/historical?assetclass=etf',
        historical_retrieved_at=at,retrieved_at=at,completion_source=info,identity_source=identity,calendar_source=calendar)


def read(source,at='2026-11-03T00:00:00Z'):
    return read_market(source,symbol='TEST',evaluation_at=at,repo_root=HERE.parents[2],profile=None,is_etf=True,observation_route='V75')


def change(descriptor,fn):
    path=Path(descriptor['local_path']);data=json.loads(path.read_bytes());fn(data);path.write_text(json.dumps(data));descriptor['sha256']=sha256(path.read_bytes()).hexdigest()


def test_whole_dated_daily_history_uses_no_quote_volume_or_other_price_repairs(tmp_path):
    source=source_case(tmp_path);out=read(source)
    assert out['observed_date']=='2026-11-02' and len(out['completed_rows'])==4
    assert out['completed_rows'][-1]['Volume']=='1000'
    evidence=out['provider_completion_evidence']
    assert evidence['ohlcv_entirely_from_historical_response'] and evidence['market_status']=='Closed'
    assert not evidence['historical_PIT_attested'] and not out['history_quality']['formal_deployment_eligible']


def test_later_closed_quote_does_not_certify_a_preclose_historical_capture(tmp_path):
    source=source_case(tmp_path);source['historical_retrieved_at']='2026-11-02T20:59:00Z'
    out=read(source)
    assert out['observed_date']=='2026-10-30' and out['latest_expected_completed_session']=='2026-11-02'


def test_incoherent_daily_ohlc_remains_a_gap_instead_of_borrowing_quote_values(tmp_path):
    source=source_case(tmp_path)
    change(source,lambda d:d['data']['tradesTable']['rows'][1].update(low='102'))
    out=read(source)
    assert len(out['completed_rows'])==1 and len(out['history_quality']['invalid_source_rows'])==1


@pytest.mark.parametrize('issue',['incomplete_page','wrong_symbol','open_market','wrong_day','changed_bytes','wrong_currency','wrong_listing','future_proof','wrong_close'])
def test_daily_publication_receipts_fail_closed(tmp_path,issue):
    source=source_case(tmp_path)
    if issue=='incomplete_page':change(source,lambda d:d['data'].update(totalRecords=999))
    elif issue=='wrong_symbol':change(source,lambda d:d['data'].update(symbol='OTHER'))
    elif issue=='open_market':change(source['completion_source'],lambda d:d['data'].update(marketStatus='Open'))
    elif issue=='wrong_day':change(source['completion_source'],lambda d:d['data']['primaryData'].update(lastTradeTimestamp='Oct 30, 2026'))
    elif issue=='changed_bytes':Path(source['local_path']).write_text('{}')
    elif issue=='wrong_currency':change(source['identity_source'],lambda d:d['chart']['result'][0]['meta'].update(currency='CAD'))
    elif issue=='wrong_listing':change(source['identity_source'],lambda d:d['chart']['result'][0]['meta'].update(exchangeName='NMS'))
    elif issue=='future_proof':source['completion_source']['retrieved_at']='2026-11-04T00:00:00Z'
    elif issue=='wrong_close':change(source['completion_source'],lambda d:d['data']['primaryData'].update(lastSalePrice='$101'))
    with pytest.raises((ValueError,PermissionError)):read(source)

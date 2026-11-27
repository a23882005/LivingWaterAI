"""Import factual public history-table receipts into an isolated analysis cache.

No network client, account data, repaired prices or formal freshness claims.
The connected executor saves the actual source table; this parser binds it.
"""
import csv
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import re


def parse_displayed_history(document, evaluation_at):
    symbol=document['symbol'];text=document['extracted_text'];url=document['source_url']
    if not re.fullmatch(r'[A-Z0-9.-]{1,32}',symbol):raise ValueError('SOURCE_SYMBOL_INVALID')
    if not url.startswith('https://stockanalysis.com/'):raise ValueError('SOURCE_PROVIDER_UNREVIEWED')
    if url not in (f'https://stockanalysis.com/stocks/{symbol.lower()}/history/',
                   f'https://stockanalysis.com/etf/{symbol.lower()}/history/',
                   f'https://stockanalysis.com/quote/lon/{symbol}/history/'):
        raise ValueError('SOURCE_URL_SYMBOL_MISMATCH')
    market=re.search(r'\b(NASDAQ|NYSEARCA|NYSE):\s*'+re.escape(symbol)+r'\b[^\n]*USD',text)
    london=('LON:'+symbol in text and 'Price in USD' in text)
    if not market and not london:raise ValueError('SOURCE_MARKET_CURRENCY_IDENTITY_REQUIRED')
    exchange=market.group(1) if market else 'XLON'
    now=datetime.fromisoformat(evaluation_at.replace('Z','+00:00'))
    if now.utcoffset() is None:raise ValueError('SOURCE_EVALUATION_TIMEZONE_REQUIRED')
    rows=[];excluded=[];seen=set();source_count=0
    for line in text.splitlines():
        line=re.sub(r'^L\d+:\s*','',line)
        if not re.match(r'^[A-Z][a-z]{2} \d{1,2}, \d{4}\s*\|',line):continue
        cells=[x.strip() for x in line.split('|')]
        if len(cells)!=8:raise ValueError('SOURCE_HISTORY_COLUMN_COUNT')
        day=datetime.strptime(cells[0],'%b %d, %Y').date();source_count+=1
        if day.isoformat() in seen:raise ValueError('SOURCE_HISTORY_DUPLICATE_DATE')
        seen.add(day.isoformat())
        if day>=now.astimezone(timezone.utc).date():
            excluded.append({'date':day.isoformat(),'reason':'FORMING_OR_FUTURE_BAR'});continue
        row={'Date':day.isoformat()}
        for key,index in [('Open',1),('High',2),('Low',3),('Close',4),('Adj Close',5),('Volume',7)]:
            raw=cells[index].replace(',','')
            try:value=Decimal(raw)
            except InvalidOperation:raise ValueError('SOURCE_HISTORY_NON_NUMERIC:'+key) from None
            if not value.is_finite() or value<0:raise ValueError('SOURCE_HISTORY_INVALID_VALUE:'+key)
            row[key]=raw
        rows.append(row)
    if not rows:raise ValueError('SOURCE_HISTORY_EMPTY')
    rows.sort(key=lambda r:r['Date'])
    return rows,{'exchange':exchange,'currency':'USD',
        'timezone':'Europe/London' if london else 'America/New_York',
        'source_url':url,'source_rows':source_count,'excluded_rows':excluded,
        'provider_currency_label_conflict':london and 'Currency is GBP' in text,
        'price_unit_evidence':'Price in USD' if london else market.group(0),
        'price_basis':'DISPLAYED_OHLC_CLOSE_AND_SEPARATE_ADJUSTED_CLOSE__NO_CORPORATE_ACTION_EVENT_LOG',
        'adjusted_close_difference_rows':sum(Decimal(r['Close'])!=Decimal(r['Adj Close']) for r in rows),
        'history_scope':'DISPLAYED_WINDOW_ONLY__NOT_FULL_HISTORY',
        'formal_deployment_eligible':False}


def import_receipts(directory, *, evaluation_at):
    folder=Path(directory).resolve();items={}
    for path in sorted(folder.glob('*.source.json')):
        raw=path.read_bytes();document=json.loads(raw)
        rows,metadata=parse_displayed_history(document,evaluation_at)
        symbol=document['symbol'];target=folder/(symbol+'.csv')
        with target.open('w',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=['Date','Open','High','Low','Close','Adj Close','Volume'])
            writer.writeheader();writer.writerows(rows)
        items[symbol]={'status':'OK','file_name':target.name,'rows':len(rows),
            'allow_close_only_analysis':True,
            'latest_observation':rows[-1]['Date'],'last_verified_utc':evaluation_at,
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'receipt_sha256':hashlib.sha256(raw).hexdigest(),
            'provider':'StockAnalysis.com displayed history table',**metadata}
    manifest={'schema_version':'Family.W8.AlternativeMarketHistory.v1','items':items}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    result=import_receipts(args.directory,evaluation_at=datetime.now(timezone.utc).isoformat())
    print(json.dumps({k:{'rows':r['rows'],'latest':r['latest_observation']} for k,r in result['items'].items()}))

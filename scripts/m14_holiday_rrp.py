"""Approved V70-M14-HOLIDAY-OUTSTANDING-20261117, fail-closed receipts.

NYFed's date-range API has no paging cursor. Check each calendar day's complete
response against the enclosing range, and require ON RRP results on every open
day. Anchor on TWO prior open days; validate Overnight maturities against the
same official calendar. Thus no earlier overnight contract can cross the anchor.
Unknown response envelopes / pagination fields are deliberately rejected.
"""
import base64
import csv
import datetime as dt
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
import re
from urllib.parse import urlencode, urlparse, parse_qs

RULE = 'V70-M14-HOLIDAY-OUTSTANDING-20261117'
HOLIDAYS = 'https://www.newyorkfed.org/aboutthefed/holiday_schedule.html'
OPERATIONS = 'https://markets.newyorkfed.org/api/rp/results/search.json'


def receipt(raw, url, checked):
    return dict(url=url, retrieved_at=checked, response_sha256=hashlib.sha256(raw).hexdigest(),
                response_bytes=len(raw), raw_gzip_b64=base64.b64encode(gzip.compress(raw,mtime=0)).decode())


def unpack(r, now=None):
    raw=gzip.decompress(base64.b64decode(r['raw_gzip_b64'],validate=True))
    if len(raw)!=r['response_bytes'] or hashlib.sha256(raw).hexdigest()!=r['response_sha256']:
        raise ValueError('m14 raw receipt hash mismatch')
    checked=dt.datetime.fromisoformat(r['retrieved_at'].replace('Z','+00:00'))
    if checked.tzinfo is None or (now is not None and checked>now):
        raise ValueError('m14 receipt clock invalid')
    return raw


def holiday_dates(raw, year):
    from html.parser import HTMLParser
    class Tables(HTMLParser):
        def __init__(self):
            super().__init__();self.stack=[];self.tables=[]
        def handle_starttag(self,tag,attrs):
            if tag=='table':self.stack.append({'rows':[],'row':None,'cell':None})
            elif self.stack:
                t=self.stack[-1]
                if tag=='tr':t['row']=[]
                elif tag in ('td','th'):t['cell']=[]
        def handle_data(self,data):
            if self.stack and self.stack[-1]['cell'] is not None:self.stack[-1]['cell'].append(data)
        def handle_endtag(self,tag):
            if not self.stack:return
            t=self.stack[-1]
            if tag in ('td','th') and t['cell'] is not None:
                if t['row'] is not None:t['row'].append(' '.join(t['cell']).strip())
                t['cell']=None
            elif tag=='tr' and t['row'] is not None:
                t['rows'].append(t['row']);t['row']=None
            elif tag=='table':self.tables.append(self.stack.pop()['rows'])
    parser=Tables();parser.feed(raw.decode('utf-8'))
    for rows in parser.tables:
        if not rows:continue
        headers=rows[0]
        if str(year) not in headers:continue
        col=headers.index(str(year)); found=set()
        for cells in rows[1:]:
            if len(cells)<=col:continue
            text=cells[col]
            match=re.match(r'([A-Za-z]+)\s+(\d{1,2})(?:\D|$)',text)
            if not match:raise ValueError('m14 unrecognized official holiday cell')
            day=dt.datetime.strptime(f'{year} {match[1]} {match[2]}','%Y %b %d').date()
            found.add(day)
            if day.weekday()==6:found.add(day+dt.timedelta(days=1))
        if len(found)<10:raise ValueError('m14 incomplete official holiday year')
        return found
    raise ValueError('m14 official holiday year unavailable')


def open_day(day,raw):
    return day.weekday()<5 and day not in holiday_dates(raw,day.year)


def next_open(day,raw,step=1):
    for _ in range(15):
        day+=dt.timedelta(days=step)
        if open_day(day,raw):return day
    raise ValueError('m14 business-calendar coverage unavailable')


def operations(raw):
    obj=json.loads(raw)
    if set(obj)!= {'repo'} or set(obj['repo'])!={'operations'} or not isinstance(obj['repo']['operations'],list):
        raise ValueError('m14 unknown/truncated/paginated NYFed response')
    return obj['repo']['operations']


def unique(ops):
    out={}
    for op in ops:
        key=op['operationId']
        if not isinstance(key,str) or not key.startswith('RP '):raise ValueError('m14 non-domestic operation identity')
        if key in out and out[key]!=op:raise ValueError('m14 contradictory duplicate operation')
        out[key]=op
    return out


def query_url(begin,end):
    return OPERATIONS+'?'+urlencode(dict(startDate=begin.isoformat(),endDate=end.isoformat()))


def derive(day, evidence, now=None):
    if evidence.get('rule_version')!=RULE:raise ValueError('m14 rule version')
    cal=evidence['holiday_calendar']
    if cal['url']!=HOLIDAYS:raise ValueError('m14 unofficial holiday source')
    raw=unpack(cal,now)
    if day not in holiday_dates(raw,day.year):raise ValueError('m14 official holiday not confirmed')
    anchor=next_open(next_open(day,raw,-1),raw,-1)
    range_r=evidence['range']
    if range_r['url']!=query_url(anchor,day):raise ValueError('m14 range does not cover prior overnight contracts')
    range_ops=unique(operations(unpack(range_r,now)))
    daily=evidence['daily']
    expected=[anchor+dt.timedelta(days=i) for i in range((day-anchor).days+1)]
    if set(daily)!={x.isoformat() for x in expected}:raise ValueError('m14 incomplete daily queries')
    combined=[]
    for d in expected:
        r=daily[d.isoformat()]
        if r['url']!=query_url(d,d):raise ValueError('m14 daily query mismatch')
        ops=operations(unpack(r,now))
        if any(op['operationDate']!=d.isoformat() for op in ops):raise ValueError('m14 daily response outside query')
        if open_day(d,raw) and not any(op.get('operationType')=='Reverse Repo' and op.get('term')=='Overnight' and op.get('auctionStatus')=='Results' for op in ops):
            raise ValueError('m14 missing business-day ON RRP results')
        combined.extend(ops)
    if unique(combined)!=range_ops:raise ValueError('m14 range/daily completeness mismatch')
    accepted=[]; total=Decimal(0)
    for op in range_ops.values():
        if not anchor<=dt.date.fromisoformat(op['operationDate'])<=day:raise ValueError('m14 operation outside range')
        if (op.get('operationType'),op.get('term'),op.get('auctionStatus'))!=('Reverse Repo','Overnight','Results'):continue
        start=dt.date.fromisoformat(op['settlementDate']);end=dt.date.fromisoformat(op['maturityDate'])
        operation=dt.date.fromisoformat(op['operationDate'])
        if start!=operation or not open_day(start,raw) or end!=next_open(start,raw):
            raise ValueError('m14 unsupported Overnight settlement/maturity')
        if operation>day or not start<=day<end:continue
        details=op['details']
        if len(details)!=1 or details[0]['securityType']!='Treasury':raise ValueError('m14 Treasury-only identity required')
        amount=Decimal(str(details[0]['amtAccepted'])); declared=Decimal(str(op['totalAmtAccepted']))
        if not amount.is_finite() or amount<0 or amount!=declared:raise ValueError('m14 Treasury/total amount mismatch')
        total+=amount;accepted.append(op)
    if not accepted:raise ValueError('m14 no outstanding contract; empty query is not zero')
    return dict(kind='HOLIDAY_OUTSTANDING_DERIVED',rule_version=RULE,observation_date=day.isoformat(),
                value_usd_bn=float(total/Decimal(10)**9),contracts=sorted(accepted,key=lambda x:x['operationId']),
                completeness='RANGE_EQUALS_DAILY_WITH_TWO_OPEN_DAY_ANCHOR',evidence=evidence)


def fetch_holiday(f,day):
    def get(url):
        response=f.s.get(url,timeout=f.timeout);response.raise_for_status()
        return receipt(response.content,url,dt.datetime.now(dt.timezone.utc).isoformat())
    cal=get(HOLIDAYS);raw=unpack(cal)
    if day not in holiday_dates(raw,day.year):raise ValueError('m14 official holiday not confirmed')
    anchor=next_open(next_open(day,raw,-1),raw,-1)
    ev=dict(rule_version=RULE,holiday_calendar=cal,range=get(query_url(anchor,day)),daily={})
    for i in range((day-anchor).days+1):
        d=anchor+dt.timedelta(days=i);ev['daily'][d.isoformat()]=get(query_url(d,d))
    return derive(day,ev)


def fred_values(receipt_,name,now=None):
    raw=unpack(receipt_,now);url=urlparse(receipt_['url'])
    if url.scheme!='https' or url.hostname not in ('fred.stlouisfed.org','api.stlouisfed.org'):
        raise ValueError('m14 unofficial FRED source')
    q=parse_qs(url.query)
    if q.get('id',q.get('series_id'))!=[name]:raise ValueError('m14 FRED series identity mismatch')
    if raw.lstrip().startswith(b'{'):
        data=json.loads(raw)
        if data.get('offset',0)!=0 or data.get('count',len(data['observations']))!=len(data['observations']):
            raise ValueError('m14 incomplete FRED observation page')
        rows=[(x['date'],x['value']) for x in data['observations']]
    else:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if name not in reader.fieldnames:raise ValueError('m14 FRED CSV series mismatch')
        rows=[(x.get('observation_date',x.get('DATE')),x[name]) for x in reader]
    result={}
    for d,v in rows:
        dt.date.fromisoformat(d)
        value=None if str(v).strip() in ('','.','NaN') else float(v)
        if value is not None and not math.isfinite(value):raise ValueError('m14 nonfinite FRED observation')
        if d in result and result[d]!=value:raise ValueError('m14 contradictory FRED dates')
        result[d]=value
    return result


def validate_item(item,now=None):
    """Recompute both endpoints from hash-bound original responses, not flags."""
    ev=item.get('source_evidence') or {}
    holiday=ev.get('holiday_outstanding')
    if holiday is None:
        if 'HOLIDAY_OUTSTANDING_DERIVED' in str(item.get('method','')):
            raise ValueError('m14 derived method missing receipts')
        return
    if holiday['rule_version']!=RULE:raise ValueError('m14 unapproved rule')
    end=dt.date.fromisoformat(item['observation_date']);begin=end-dt.timedelta(days=91)
    if end.weekday()!=2 or holiday['begin']!=begin.isoformat() or holiday['end']!=end.isoformat():
        raise ValueError('m14 Wednesday/91-day endpoints')
    values={name:fred_values(r,name,now) for name,r in holiday['fred_originals'].items()}
    if set(values)!={'WALCL','WDTGAL','RRPONTSYD'}:raise ValueError('m14 missing originals')
    endpoints={}
    used=set()
    for d in (begin,end):
        k=d.isoformat(); parts={n:values[n].get(k) for n in values}
        if parts['WALCL'] is None or parts['WDTGAL'] is None:raise ValueError('m14 missing weekly source')
        if parts['RRPONTSYD'] is None:
            # Explicit missing row, or bounded interval with observations on both sides.
            rr=values['RRPONTSYD']
            if k not in rr and not min(rr)<k<max(rr):raise ValueError('m14 FRED interval does not prove missing date')
            derived=holiday['endpoints'][k];recomputed=derive(d,derived['evidence'],now)
            if recomputed!=derived:raise ValueError('m14 derived receipt binding mismatch')
            parts['RRPONTSYD']=recomputed['value_usd_bn'];used.add(k)
        endpoints[k]=Decimal(str(parts['WALCL']))/1000-Decimal(str(parts['WDTGAL']))/1000-Decimal(str(parts['RRPONTSYD']))
    if not used or set(holiday['endpoints'])!=used:raise ValueError('m14 unused/normal-day derived endpoint')
    if item.get('unit')!='USD bn' or abs(float(endpoints[end.isoformat()]-endpoints[begin.isoformat()])-float(item['value']))>1e-8:
        raise ValueError('m14 value/unit does not match original receipts')

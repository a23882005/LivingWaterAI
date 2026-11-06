"""Read the TPEx stock-system annual schedule with its original receipts.

The published plan is useful for dated observations. It does not attest every
ad hoc closure, historical publication time, or an instrument's final bar.
"""
from datetime import date, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import re

from member_market_source import time

SCOPE = 'OFFICIAL_TPEX_STOCK_SYSTEM_ANNUAL_PLAN__ADHOC_CLOSURES_NOT_ATTESTED'


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.table=None;self.row=None;self.cell=None

    def handle_starttag(self, tag, attrs):
        if tag=='table':self.table=[]
        elif tag=='tr':self.row=[]
        elif tag in ('td','th'):
            if self.cell is not None:self.handle_endtag('td')
            attrs=dict(attrs)
            self.cell={'text':'','rows':int(attrs.get('rowspan','1')),'cols':int(attrs.get('colspan','1'))}
        elif tag=='br' and self.cell is not None:self.cell['text']+=' '

    def handle_data(self, data):
        if self.cell is not None:self.cell['text']+=data

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.cell['text']=''.join(self.cell['text'].split())
            self.row.append(self.cell);self.cell=None
        elif tag=='tr' and self.row is not None:
            # HTML permits an omitted </td> immediately before </tr>.
            if self.cell is not None:self.handle_endtag('td')
            self.table.append(self.row);self.row=None
        elif tag=='table' and self.table is not None:
            self.tables.append(self.table);self.table=None


def _expanded(table):
    held={};out=[]
    for original in table:
        row={i:text for i,(text,count) in held.items()}
        next_held={i:(text,count-1) for i,(text,count) in held.items() if count>1}
        col=0
        for cell in original:
            while col in row:col+=1
            if not 1<=cell['rows']<=40 or cell['cols']!=1:
                raise ValueError('TPEX_CALENDAR_UNSUPPORTED_TABLE_SPAN')
            row[col]=cell['text']
            if cell['rows']>1:next_held[col]=(cell['text'],cell['rows']-1)
            col+=1
        if sorted(row)!=list(range(len(row))):raise ValueError('TPEX_CALENDAR_TABLE_HOLE')
        out.append([row[i] for i in range(len(row))]);held=next_held
    if held:raise ValueError('TPEX_CALENDAR_UNFINISHED_ROWSPAN')
    return out


def _days(text, year):
    # Date cells enumerate days. Never silently reduce an unfamiliar range to
    # its two endpoints. ROC years can explicitly name the previous December.
    if any(x in text for x in ('至','～','~','-')):
        raise ValueError('TPEX_CALENDAR_DATE_RANGE_REQUIRES_EXPLICIT_DAYS')
    matches=list(re.finditer(r'(?:(\d{3,4})年)?(\d{1,2})月(\d{1,2})日',text))
    rest=re.sub(r'(?:(\d{3,4})年)?(\d{1,2})月(\d{1,2})日','',text)
    if not matches or rest.strip('、，,；;及 '):raise ValueError('TPEX_CALENDAR_DATE_CELL')
    result=[]
    for m in matches:
        y=int(m[1]) if m[1] else year
        if y<1911:y+=1911
        result.append(date(y,int(m[2]),int(m[3])))
    return result


def annual_plan(raw, year):
    data=json.loads(raw);parser=_Tables()
    if data.get('stat')!='ok' or not isinstance(data.get('data',{}).get('html'),str):
        raise ValueError('TPEX_CALENDAR_PROVIDER_RESPONSE')
    parser.feed(data['data']['html']);parser.close()
    title=f'中華民國{year-1911}年有價證券櫃檯買賣市場開（休）市日期表'
    if len(parser.tables)!=2 or _expanded(parser.tables[0])!=[[title]]:
        raise ValueError('TPEX_CALENDAR_YEAR_OR_VENUE')
    rows=_expanded(parser.tables[1])
    if not rows or rows[0]!=['紀念節日名稱','日期','星期','說明']:
        raise ValueError('TPEX_CALENDAR_FIELDS')
    closed=set();opened=set();ignored=[];stock_last=0
    for row in rows[1:]:
        if len(row)!=4:raise ValueError('TPEX_CALENDAR_ROW_WIDTH')
        name,day,weekday,note=row;dates=_days(day,year)
        if '最後交易日' in name:
            if '股票交易系統' in name:
                stock_last+=1
                if '市場無交易' not in note:raise ValueError('TPEX_CALENDAR_STOCK_CLOSURE_NOTE')
                closed.update(_days(note.split('市場無交易')[0],year))
            else:ignored.append(row)
        elif '開始交易' in name:
            opened.update(dates)
        elif any(x in name+note for x in ('放假','補假','不交易')):
            closed.update(dates)
        else:raise ValueError('TPEX_CALENDAR_UNCLASSIFIED_STOCK_SCHEDULE_ROW')
    if stock_last!=1 or not closed or not opened or opened&closed:
        raise ValueError('TPEX_CALENDAR_OPEN_CLOSED_CONFLICT')
    return {'year':year,'title':title,'closed_dates':sorted(d.isoformat() for d in closed),
        'explicit_open_dates':sorted(d.isoformat() for d in opened),
        'excluded_other_trading_system_rows':ignored,'source_rows':rows[1:]}


def _read(source, evaluation_at, path):
    url=urlparse(source['source_reference'])
    if (url.scheme!='https' or url.hostname!='www.tpex.org.tw' or url.path!=path
            or time(source['retrieved_at'])>time(evaluation_at)):
        raise PermissionError('TPEX_CALENDAR_SOURCE_IDENTITY_OR_AVAILABILITY')
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('TPEX_CALENDAR_SOURCE_HASH')
    return raw,url


def produce(year_sources, rules_source, *, start_date, end_date, evaluation_at):
    start=date.fromisoformat(start_date);end=date.fromisoformat(end_date)
    if start>end:raise ValueError('TPEX_CALENDAR_WINDOW')
    rules,_=_read(rules_source,evaluation_at,'/zh-tw/mainboard/trading/rules/system.html')
    if any(x not in rules.decode() for x in ('9:00','13:30','13:33')):
        raise ValueError('TPEX_CALENDAR_REGULAR_SESSION_RULES')
    plans=[];documents=[];seen=set()
    for source in year_sources:
        year=source['year'];raw,url=_read(source,evaluation_at,'/www/zh-tw/bulletin/tradingDate')
        if type(year) is not int or year in seen or parse_qs(url.query).get('date')!=[str(year)]:
            raise ValueError('TPEX_CALENDAR_SOURCE_YEAR')
        seen.add(year);plans.append(annual_plan(raw,year));documents.append(dict(source))
    if not set(range(start.year,end.year+1))<=seen:raise ValueError('TPEX_CALENDAR_YEAR_COVERAGE')
    closed={d for plan in plans for d in plan['closed_dates']}
    opened={d for plan in plans for d in plan['explicit_open_dates']}
    if closed&opened:raise ValueError('TPEX_CALENDAR_CROSS_YEAR_CONFLICT')
    sessions=[];day=start
    while day<=end:
        text=day.isoformat()
        if (day.weekday()<5 or text in opened) and text not in closed:
            sessions.append({'session_id':text,'open_at':text+'T09:00:00+08:00',
                'close_at':text+'T13:33:00+08:00'})
        day+=timedelta(days=1)
    return {'exchange':'ROCO','timezone':'Asia/Taipei','provider':'TPEx_OFFICIAL_ANNUAL_PLAN',
        'version':'Family.W8.TPExStockCalendarPlan.v1','coverage_cutoff':evaluation_at,
        'start_date':start_date,'end_date':end_date,'sessions':sessions,'scope':SCOPE,
        'session_close_basis':'CONSERVATIVE_LATEST_PUBLISHED_REGULAR_CLOSE_INCLUDING_DELAY_13_33',
        'actual_session_coverage_verified':False,'historical_pit_verified':False,
        'formal_deployment_eligible':False,'annual_plans':sorted(plans,key=lambda p:p['year']),
        'source_documents':documents,'trading_rules_source':dict(rules_source)}

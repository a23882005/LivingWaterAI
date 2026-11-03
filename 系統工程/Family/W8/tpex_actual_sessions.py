"""Bind published monthly index trading dates to the annual calendar plan.

An absent planned date is disclosed as absent from the official series, not
invented as a legal closure decree or a historical publication timestamp.
"""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import json

from member_market_source import time


def _month(day):return day.strftime('%Y-%m')


def produce(plan,sources,*,evaluation_at):
    start=date.fromisoformat(plan['start_date']);last=time(evaluation_at).astimezone(time(plan['sessions'][0]['open_at']).tzinfo).date()
    expected=set();day=start.replace(day=1)
    while day<=last:
        expected.add(_month(day));day=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
    months={};actual=set();completed=set();documents=[]
    for source in sources:
        month=source['month'];url=urlparse(source['source_reference']);raw=Path(source['local_path']).read_bytes()
        if (month in months or url.scheme!='https' or url.hostname!='www.tpex.org.tw'
            or url.path!='/www/zh-tw/indexInfo/inx' or parse_qs(url.query).get('date')!=[month.replace('-','/')+'/01']
            or sha256(raw).hexdigest()!=source['sha256'] or time(source['retrieved_at'])>time(evaluation_at)):
            raise PermissionError('TPEX_ACTUAL_MONTH_SOURCE_IDENTITY_HASH_OR_TIME')
        data=json.loads(raw);tables=data.get('tables') or []
        if data.get('stat')!='ok' or len(tables)!=1:raise ValueError('TPEX_ACTUAL_MONTH_RESPONSE')
        table=tables[0];year,m=map(int,month.split('-'));rows=table.get('data')
        if (table.get('title')!='櫃買指數(月查詢)' or table.get('date')!=f'{year-1911}/{m:02d}'
            or table.get('fields')!=['日期','開市','最高','最低','收市','漲/跌']
            or not isinstance(rows,list) or type(table.get('totalCount')) is not int or len(rows)!=table['totalCount'] or not rows):
            raise ValueError('TPEX_ACTUAL_COMPLETE_MONTH_REQUIRED')
        days=[]
        for row in rows:
            if len(row)!=6:raise ValueError('TPEX_ACTUAL_INDEX_ROW')
            day=date.fromisoformat(row[0].replace('/','-'))
            if _month(day)!=month or day>last:raise ValueError('TPEX_ACTUAL_INDEX_DATE')
            try:o,h,l,c=[Decimal(v.replace(',','')) for v in row[1:5]]
            except Exception:raise ValueError('TPEX_ACTUAL_INDEX_NUMBER') from None
            if any(not v.is_finite() or v<=0 for v in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:
                raise ValueError('TPEX_ACTUAL_INDEX_OHLC')
            days.append(day.isoformat())
            closed=time(day.isoformat()+'T13:33:00+08:00')
            if closed<=min(time(source['retrieved_at']),time(evaluation_at)):completed.add(day.isoformat())
        if days!=sorted(set(days)):raise ValueError('TPEX_ACTUAL_INDEX_ORDER')
        months[month]=days;actual.update(days);documents.append(deepcopy(source))
    if set(months)!=expected:raise ValueError('TPEX_ACTUAL_CONTIGUOUS_MONTH_COVERAGE_REQUIRED')
    if not completed:raise ValueError('TPEX_ACTUAL_COMPLETED_DATE_REQUIRED')
    watermark=max(completed);planned={r['session_id']:r for r in plan['sessions']}
    out=deepcopy(plan);sessions=[]
    for day in sorted(actual):
        if plan['start_date']<=day<=watermark:
            sessions.append(planned.get(day) or {'session_id':day,'open_at':day+'T09:00:00+08:00','close_at':day+'T13:33:00+08:00'})
    sessions.extend(r for r in plan['sessions'] if r['session_id']>watermark)
    out.update(sessions=sessions,coverage_cutoff=evaluation_at,
        provider='TPEx_OFFICIAL_MONTHLY_INDEX_DATES_AND_ANNUAL_PLAN',
        scope='OFFICIAL_TPEX_ACTUAL_DATE_WINDOW__FUTURE_PLAN_AND_HISTORICAL_PIT_NOT_ATTESTED',
        actual_session_window={'start_date':plan['start_date'],'through':watermark,'verified':True,
            'basis':'PUBLISHED_COMPLETE_MONTHLY_INDEX_DATE_LISTS__RETROSPECTIVE_OBSERVATION'},
        official_monthly_documents=documents,
        planned_dates_absent_from_official_index=sorted(d for d in planned if plan['start_date']<=d<=watermark and d not in actual),
        actual_dates_not_in_annual_plan=sorted(d for d in actual if plan['start_date']<=d<=watermark and d not in planned),
        missing_date_is_not_a_closure_decree=True,historical_pit_verified=False,formal_deployment_eligible=False)
    return out

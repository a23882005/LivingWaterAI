#!/usr/bin/env python3
"""Refresh V70.3 official evidence before deployment; preserve stale rows' real dates."""
import datetime as dt
import gzip
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
TPE = dt.timezone(dt.timedelta(hours=8))
P8 = ROOT/'data/8_macro_supplement_verified.json'
P18 = ROOT/'data/18_macro_verification.json'
PCAL = ROOT/'data/v703_official_monthly_release_calendar.json'
FED = 'https://www.federalreserve.gov/monetarypolicy/openmarket.htm'
ISM = 'https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/october/'
ISM_CAL = 'https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/'


def clean(b):
    s=b.decode('utf8','replace')
    s=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>',' ',s,flags=re.I|re.S)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',s)))


def fetch(session,url):
    r=session.get(url,timeout=(6,18))
    r.raise_for_status()
    if len(r.content)<100: raise ValueError('short response '+url)
    return r.content


def revise_candidate(row,site,stamp,value,date,note):
    for c in row['candidate_checks']:
        if c['site']==site:
            c.update(status='FOUND',checked_at=stamp,value=value,observation_date=date,notes=note)
            return
    raise ValueError('candidate site missing '+site)



def parse_mmfi_eod(raw, today):
    """Use dated INDEX/MMFI end-of-day Close, never a delayed intraday Last."""
    page=clean(raw)
    if not re.search(r'INDEX\s*,\s*MMFI\s*:\s*Percent of Stocks Above 50-Day Average',page,re.I):
        raise ValueError('EOD source is not exact INDEX/MMFI 50-day breadth')
    if 'RECENT END OF DAY PRICES' not in page:
        raise ValueError('EOD latest daily table missing')
    rows=page.split('RECENT END OF DAY PRICES',1)[1].split('SYMBOL HISTORY',1)[0]
    rows=rows[:1300]
    found=re.search(
        r'\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{2})\s+'
        r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+'
        r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+\d+\b',
        rows)
    if not found:
        raise ValueError('EOD dated table has no complete OHLC close')
    first_date=re.search(r'\b\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\b',rows)
    if not first_date or first_date.group(0)!=found.group(1):
        raise ValueError('EOD latest row lacks complete OHLC; decline older fallback')
    observed=dt.datetime.strptime(found.group(1),'%d %b %y').date()
    if observed>today:
        raise ValueError('EOD quote has future date')
    value=float(found.group(5))
    if not 0<=value<=100:
        raise ValueError('EOD MMFI close must be percent in 0..100')
    if not (float(found.group(4))<=value<=float(found.group(3))):
        raise ValueError('EOD close outside daily high/low')
    return value,observed.isoformat()


def main():
    session=requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0 (compatible; LivingWaterAI-V703/1.0)',
                            'Accept':'text/html,text/csv,*/*'})
    a=json.loads(P8.read_text(encoding='utf8'))
    b=json.loads(P18.read_text(encoding='utf8'))
    cal=json.loads(PCAL.read_text(encoding='utf8'))
    stamp=dt.datetime.now(TPE).isoformat(timespec='seconds')
    fed=fetch(session,FED)
    content=clean(fed)
    m=re.search(r'\b2026\s+Date\s+Increase\s+Decrease\s+Level\s*\(?%\)?\s+'
                r'([A-Z][a-z]+)\s+(\d{1,2})\s+\d+\s+\d+\s+'
                r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)',content)
    if not m: raise ValueError('Fed current-year target row not found')
    month,day,lo,hi=m.groups()
    lower,upper=float(lo),float(hi)
    effective=dt.datetime.strptime(f'{month} {day} 2026','%B %d %Y').date().isoformat()
    row=a['items']['m06_rate']
    if (effective!=row['effective_date'] or lower!=row['lower_bound']['value'] or
            upper!=row['upper_bound']['value']):
        raise ValueError('Fed policy changed; require new dated official publication evidence')
    now=dt.datetime.now(TPE).isoformat(timespec='seconds')
    audit=ROOT/'data/audit'/('fed_target_evidence_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.html.gz')
    audit.parent.mkdir(parents=True,exist_ok=True)
    audit.write_bytes(gzip.compress(fed,mtime=0))
    sha=hashlib.sha256(fed).hexdigest()
    row.update(value=(lower+upper)/2,retrieval_time=now,last_verified_at=now,
               detail=f'Fed官方當期目標{lo}–{hi}%，真實HTTP原文SHA256={sha}，稽核檔{audit.relative_to(ROOT)}')
    row['source_evidence'].update(url=FED,checked_at=now,result='CURRENT_CONFIRMED',
        excerpt=f'2026 official current target: {month} {day} {lo}-{hi}; original response archived',
        response_sha256=sha,effective_date=effective,publication_date=row['publication_date'],
        lower_bound=row['lower_bound'],upper_bound=row['upper_bound'],value=row['value'])
    revise_candidate(row,'Federal Reserve',now,f'{lo}-{hi}',effective,'原始官方HTTP已保存並實算SHA256')
    print('FED_SOURCE_PASS',sha,flush=True)

    # Newly released October PMI is necessary after the Nov 2 official publication.
    if dt.datetime.now(TPE).date()>=dt.date(2026,11,3) and dt.datetime.now(TPE).date()<dt.date(2026,12,1):
        source=clean(fetch(session,ISM))
        report_url=ISM
        def verified_headline(content):
            if 'October 2026' not in content:
                return None
            for pattern in (r'Manufacturing\s+PMI\s*®?\s*(?:at|registered)\s+(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)',
                            r'Manufacturing\s+PMI.{0,30}?(?:at|registered)\s+(\d{1,2}(?:\.\d+)?)\s*(?:%|percent)'):
                hit=re.search(pattern,content,re.I)
                if hit and float(hit.group(1))==55.5:
                    return 55.5
            return None
        pmi=verified_headline(source)
        if pmi is None:
            print('ISM_OFFICIAL_DIRECT_NOT_PARSED',source[:300],flush=True)
            report_url='https://www.prnewswire.com/news-releases/manufacturing-pmi-at-55-5-october-2026-ism-manufacturing-pmi-report-302925617.html'
            source=clean(fetch(session,report_url))
            pmi=verified_headline(source)
        cal_text=clean(fetch(session,ISM_CAL))
        if pmi!=55.5:
            raise ValueError('ISM October headline not independently verified at both official and distributed releases')
        if not re.search(r'December\s+2026\s+1\s+3',cal_text):
            raise ValueError('Official December ISM release calendar cannot be verified')
        b['items']['m04'].update(value=55.5,observation_date='2026-10-01',source_url=report_url,
            method='2026-11-02公布ISM官方10月製造業PMI',status='OK',
            detail='2026-10官方製造業PMI 55.5；前月54.5',attempted_at=now,
            last_verified_at=now,attempt_result='SUCCESS',cache_used=False,error='',retrieval_error='')
        b['items']['m04'].setdefault('source_attempts',{}).setdefault('ISM_m04',[]).append({
            'provider':'ISM_OFFICIAL','result':'OK','verified_at':now,'observation_date':'2026-10-01'})
        cal['items']['m04'].update(observation_month='2026-10',publication_date='2026-11-02',
                                  next_release_at_utc='2026-12-01T15:00:00Z')
        cal['checked_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        print('ISM_OCTOBER_PASS',flush=True)

    # Refresh NYSE MMFI only with actual dated source evidence.
    try:
        url='https://www.macroaxis.com/index/MMFI.INDX/Percent-Of-Stocks'
        source=clean(fetch(session,url))
        m=re.search(r'MMFI\s+Index\s+Updated\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\s+([0-9]+(?:\.[0-9]+)?)',source)
        if not m: raise ValueError('MMFI value/date missing')
        mon,day,year,num=m.groups()
        try: observed=dt.datetime.strptime(f'{mon} {day} {year}','%b %d %Y').date().isoformat()
        except ValueError: observed=dt.datetime.strptime(f'{mon} {day} {year}','%B %d %Y').date().isoformat()
        value=float(num)
        if not 0<=value<=100: raise ValueError('MMFI outside 0-100')
        row=a['items']['s05']
        row.update(value=value,observation_date=observed,status='USABLE',source_url=url,
            retrieval_time=now,publication_date=observed,
            detail=f'NYSE MMFI {value}%：Macroaxis頁面直接驗證觀測日{observed}')
        revise_candidate(row,'Macroaxis',now,value,observed,'頁面明示NYSE市場50日廣度')
        print('MMFI_PASS',value,observed,flush=True)
    except (requests.RequestException,ValueError) as exc:
        # Exact INDEX/MMFI EOD table is an authorized same-symbol fallback;
        # all-US or S&P500 breadth would be a different population.
        print('MMFI_MACROAXIS_UNAVAILABLE',str(exc)[:100],flush=True)
        try:
            url='https://www.eoddata.com/stockquote/INDEX/MMFI.htm'
            raw=fetch(session,url)
            value,observed=parse_mmfi_eod(raw,dt.datetime.now(TPE).date())
            original=a['items']['s05']
            prior_date=dt.date.fromisoformat(original['observation_date'])
            if dt.date.fromisoformat(observed)<prior_date:
                raise ValueError('EOD observation predates last verified MMFI')
            raw_sha=hashlib.sha256(raw).hexdigest()
            row=a['items']['s05']
            row.update(value=value,observation_date=observed,status='USABLE',
                source_url=url,method='EODData INDEX/MMFI：NYSE 50日廣度之最近完整交易日收盤',
                retrieval_time=now,publication_date=observed,
                detail=f'INDEX/MMFI 日期{observed}收盤{value}%，採EOD收盤非盤中LAST；來源SHA256={raw_sha}')
            revise_candidate(row,'EODData',now,value,observed,
                'INDEX/MMFI End-of-Day OHLC 的 Close，非盤中Last；SHA256='+raw_sha)
            for candidate in row['candidate_checks']:
                if candidate['site']=='EODData':
                    candidate['url']=url
            print('MMFI_EOD_FALLBACK_PASS',value,observed,raw_sha,flush=True)
        except (requests.RequestException,ValueError) as second:
            print('MMFI_RETAIN_ORIGINAL_DATED_VALUE',str(second)[:150],flush=True)

    # Update direct, explicitly Forward (not TTM) multiples where accessible.
    for ticker in ('qqq','spy','vt'):
        item=a['items']['m03_'+ticker]
        url=f'https://stockanalysis.com/etf/{ticker}/'
        try:
            source=clean(fetch(session,url))
            val=re.search(r'Forward\s+PE\s+([0-9]+(?:\.[0-9]+)?)',source,re.I)
            date=re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2})',source)
            if not val or not date: raise ValueError('Forward PE/date missing')
            date=dt.datetime.strptime(date.group(1),'%b %d, %Y').date().isoformat()
            value=float(val.group(1))
            if not 0<value<200: raise ValueError('out of bound')
            item.update(value=value,observation_date=date,source_url=url,status='OK',
                publication_date=date,retrieval_time=now,
                method='StockAnalysis明示Forward PE，採未來預估口徑',detail=f'{ticker.upper()} Forward PE {value}，頁面資料日{date}')
            revise_candidate(item,'StockAnalysis',now,value,date,'真實網頁明示Forward PE；TTM未採用')
            print('FORWARD_PASS',ticker,value,date,flush=True)
        except (requests.RequestException,ValueError) as exc:
            print('FORWARD_RETAIN_ORIGINAL_DATED_VALUE',ticker,str(exc)[:100],flush=True)

    # Retain original observation/check dates for any source unavailable this run.
    a['generated_at']=now
    a['as_of_taipei']=now
    a['refresh_method']='Official Fed full raw HTTP reverified; other values retain dated observations unless independently refreshed'
    sys.path.insert(0,str(ROOT/'scripts'))
    from validate_macro_supplement import validate
    issues=validate(a,dt.datetime.now(dt.timezone.utc))
    if issues: raise ValueError('V703_REFRESH_QA_BLOCKED: '+'; '.join(issues))
    P8.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    P18.write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    PCAL.write_text(json.dumps(cal,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('V703_EVIDENCE_REFRESH_PASS',now,flush=True)


if __name__=='__main__':
    main()

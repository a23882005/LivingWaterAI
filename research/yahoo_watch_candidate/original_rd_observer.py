"""Original approved daily RD formula, source-observation scope only.
No valuation dependency, financial eligibility, buy recommendation or trading.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib,json,math,re,subprocess,sys,tempfile,urllib.request,urllib.parse

COMMIT='3f7ea0dcd2963ae55598ffa90b36893ed47cc9bb'

def _positive_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def daily_risk_evidence(observed):
    """Extract flat, observed daily facts from the pinned original producer.

    Source observations only: no independent technical decision and no trades.
    """
    approved = observed.get('approved_technical') or {}
    timing = approved.get('trend_timing_inputs') or {}
    bars = timing.get('bars') or []
    signals = approved.get('signals') or {}
    close = _positive_number(observed.get('observed_close'))
    previous = _positive_number(timing.get('previous_close'))
    low = _positive_number(bars[-1].get('Low')) if bars and isinstance(bars[-1], dict) else None
    evidence = {}
    if close is not None:
        evidence['daily_close'] = close
    if previous is not None:
        evidence['daily_previous_close'] = previous
    if low is not None:
        evidence['daily_low'] = low
    if close is not None and previous is not None:
        evidence['daily_change_percent'] = round((close / previous - 1) * 100, 4)

    def true_codes(group, prefix, count):
        found = []
        for slot in signals.get(group, []):
            if not isinstance(slot, dict) or slot.get('truth') != 'TRUE':
                continue
            ref = str(slot.get('rule_ref') or '')
            code = ref.rsplit(' ', 1)[-1]
            if re.fullmatch(prefix + '[1-' + str(count) + ']', code):
                found.append(code)
        return '|'.join(found)

    breaks = true_codes('down_break', 'D', 3)
    evidence['rd_break_true_codes'] = breaks
    evidence['rd_accel_true_codes'] = true_codes('down_accel', 'A', 8)

    # If D2 was confirmed by the original producer, show its exact pivot only
    # when the completed-session crossing independently matches that value.
    if 'D2' in breaks.split('|') and close is not None and previous is not None:
        t = observed.get('rows')
        lows = (observed.get('swings') or {}).get('lows') or []
        if isinstance(t, int) and t >= 3:
            index = t - 1
            eligible = []
            for pivot in lows:
                if not isinstance(pivot, dict) or not isinstance(pivot.get('index'), int):
                    continue
                p = pivot['index']
                level = _positive_number(pivot.get('value'))
                if level is not None and p + 2 <= index - 1 and index - 21 <= p <= index - 1:
                    eligible.append((p, level, pivot.get('pivot_session')))
            if eligible:
                _, level, day = max(eligible, key=lambda item: item[0])
                if previous >= level > close and isinstance(day, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                    evidence['daily_confirmed_swing_low'] = level
                    evidence['daily_confirmed_swing_session'] = day
    return evidence


def observed_rd(symbol,root,now=None):
    now=now or datetime.now(timezone.utc);root=Path(root).resolve()
    result=dict(symbol=symbol,status='UNKNOWN',runaway_down='UNKNOWN',scope='OBSERVED_APPROVED_DAILY_FORMULA_NOT_BUY',formal_v82_executed=False)
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        return {**result,'reason':'ORIGINAL_COMMIT_MISMATCH'}
    if subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD']).returncode:
        return {**result,'reason':'ORIGINAL_SOURCE_MODIFIED'}
    sys.path[:0]=[str(root/'系統工程/Family/W8'),str(root/'系統工程/Family/W5')]
    from member_market_source import read_market
    if Path(read_market.__code__.co_filename).resolve()!=root/'系統工程/Family/W8/member_market_source.py':
        return {**result,'reason':'ORIGINAL_MODULE_SHADOWED'}
    from approved_v04_technical import load_profile
    import exchange_calendars as xc
    query=urllib.parse.urlencode(dict(range='1y',interval='1d',events='div,splits'))
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?'+query
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as response:raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:return {**result,'reason':'RESPONSE_TOO_LARGE'}
    acquired=datetime.now(timezone.utc);data=json.loads(raw)['chart']['result'][0];meta=data['meta']
    if meta.get('symbol')!=symbol:return {**result,'reason':'SOURCE_IDENTITY_MISMATCH'}
    if data.get('events',{}).get('splits'):return {**result,'reason':'SPLIT_IN_WINDOW_REQUIRES_SOURCE_QUALIFICATION'}
    if meta.get('instrumentType') not in ('ETF','EQUITY'):return {**result,'reason':'UNSUPPORTED_PRODUCT_TYPE'}
    tz=meta.get('exchangeTimezoneName')
    if tz=='America/New_York' and meta.get('currency')=='USD':cal_id='XNYS';exchange=meta['exchangeName']
    elif tz=='Asia/Taipei' and meta.get('currency')=='TWD' and symbol.endswith('.TW'):cal_id='XTAI';exchange='TWSE'
    else:return {**result,'reason':'UNSUPPORTED_MARKET_CALENDAR'}
    # Known fixed-income products retain their separate original V75 route.
    if symbol in {'SGOV','SPSB'}:return {**result,'reason':'FIXED_INCOME_NOT_V82_EQUITY_ROUTE'}
    start=datetime.fromtimestamp(data['timestamp'][0],ZoneInfo(tz)).date().isoformat()
    evaluation=max(now,acquired);cal=xc.get_calendar(cal_id,start=start,end=evaluation.date()+timedelta(days=7))
    sessions=[dict(session_id=str(d.date()),open_at=cal.session_open(d).isoformat(),close_at=cal.session_close(d).isoformat())
              for d in cal.sessions_in_range(start,str(evaluation.astimezone(ZoneInfo(tz)).date()))]
    calendar=dict(exchange=exchange,timezone=tz,provider='exchange_calendars',version=xc.__version__,
                  coverage_cutoff=evaluation.isoformat(),sessions=sessions,scope='IDENTIFIED_CALENDAR_OBSERVATION_NOT_OFFICIAL_PIT')
    def desc(p):return dict(local_path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'raw.json';p.write_bytes(raw);c=Path(tmp)/'calendar.json';c.write_text(json.dumps(calendar))
        source={**desc(p),'provider':'YAHOO_CHART','symbol':symbol,'provider_symbol':symbol,'currency':meta['currency'],
                'timezone':tz,'exchange':exchange,'provider_exchange':meta['exchangeName'],'source_reference':url,
                'retrieved_at':acquired.isoformat(),'calendar_source':desc(c)}
        observed=read_market(source,symbol=symbol,evaluation_at=evaluation.isoformat(),repo_root=root,
            profile=load_profile(root/'系統工程/Family/W8/owner_approved_v10.json'),is_etf=meta['instrumentType']=='ETF')
    fresh=observed['observed_date']==observed['latest_expected_completed_session']
    # The original boundary explicitly flags provider OHLC as observations,
    # not canonical financial input. Preserve that distinction downstream.
    aggregate=observed['v82_original_aggregation']
    evidence=daily_risk_evidence(observed) if fresh else {}
    return {**result,**evidence,'status':'OBSERVED_DAILY_FORMULA' if fresh else 'UNKNOWN','last_session':observed['observed_date'],
            'rows':observed['rows'],'source_sha256':source['sha256'],'calendar':cal_id,
            'reason':'ORIGINAL_RD_FORMULA_ON_PROVIDER_OBSERVATIONS' if fresh else 'LATEST_COMPLETED_SESSION_MISSING',
            'runaway_down':aggregate.get('runaway_down','UNKNOWN') if fresh else 'UNKNOWN',
            'last_observed_runaway_down':aggregate.get('runaway_down','UNKNOWN'),
            'expected_session':observed['latest_expected_completed_session']}

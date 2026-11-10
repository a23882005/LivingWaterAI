"""Yahoo reference observation + honest pipeline-status mail, NOT V82 execution.
This entry point never invents formal predicates from intraday bars.
"""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from github_json_outbox import GithubContentsBackend
from gmail_smoke import MailOutbox
from monitor_core import observe
from safe_notify import send_notice


def fetch(symbol):
    q=urllib.parse.urlencode(dict(range='5d',interval='5m',includePrePost='true'))
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?'+q
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (read-only market observation)'})
    with urllib.request.urlopen(req,timeout=20) as response:
        raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('RESPONSE_TOO_LARGE')
    return json.loads(raw)


def build_notice(symbol,payload,now,run,repo):
    delay=1200 if symbol.endswith(('.TW','.TWO')) else 0
    row=observe(payload,symbol,now.timestamp(),publication_delay_seconds=delay)
    # Quality / expiry policy only, not an investment threshold. Old observations
    # include scheduled market closures; this does not label them a source outage.
    status=row['data_status']
    if row.get('age_seconds',0)>delay+900:status='OLD_OBSERVATION_NOT_CURRENT'
    reason='FORMAL_PRODUCER_NOT_CONNECTED__NO_V82_BUY_CONCLUSION'
    event='reference-health-v1:'+now.date().isoformat()+':'+symbol+':'+status+':'+reason
    return dict(schema='LW_MARKET_NOTICE_V1',event_id=event,symbol=symbol,
        source='Yahoo Finance chart',observed_at=now.isoformat(),generated_at=now.isoformat(),
        data_status=status,reason=reason,notice_kind='REFERENCE_ONLY',run_id=run,
        run_url='https://github.com/'+repo+'/actions/runs/'+run,
        quote_time=row.get('bar_end_utc'),session=row.get('session','UNKNOWN'),
        delay_seconds=delay if delay else None,market_price=row.get('ohlcv',{}).get('close'),
        valid_until=(now+timedelta(minutes=20)).isoformat(),formal_v82_executed=False,
        monitor_status='FORMAL_AUTOSTART_BLOCKED_UNKNOWN')


def main():
    repo=os.environ['GITHUB_REPOSITORY']
    if repo!='a23882005/LivingWaterAI' or os.environ.get('GITHUB_REF_NAME')!='main':
        raise ValueError('PRODUCTION_ENTRY_MAIN_ONLY')
    symbols=os.environ.get('WATCH_SYMBOLS','0050.TW,VT,SOXX,TSM').split(',')
    symbols=list(dict.fromkeys(s.strip() for s in symbols if s.strip()))
    if not symbols or len(symbols)>60 or any(not re.fullmatch(r'[A-Z0-9.^=-]{1,20}',s) for s in symbols):
        raise ValueError('WATCH_UNIVERSE_INVALID')
    backend=GithubContentsBackend(token=os.environ['GITHUB_TOKEN'],repository=repo,branch='main',
        path='research/yahoo_watch_candidate/state/notice.json')
    outbox=MailOutbox(backend);counts={}
    now=datetime.now(timezone.utc)
    for symbol in symbols:
        try:payload=fetch(symbol)
        except Exception:payload={}
        report=build_notice(symbol,payload,now,os.environ['GITHUB_RUN_ID'],repo)
        # Stable daily health+quality key prevents per-poll email spam. Recurrence
        # of an already reported quality state on the same UTC day is suppressed.
        state=send_notice(report,outbox=outbox,sender=os.environ['GMAIL_ADDRESS'],
            recipient=os.environ['GMAIL_ADDRESS'],app_password=os.environ['GMAIL_APP_PASSWORD'])
        counts[state]=counts.get(state,0)+1
        time.sleep(.2)
    print(json.dumps({'status_counts':counts,'formal_v82_executed':False},sort_keys=True))
    if any(k not in ('ALREADY_SENT','SENT_SMTP_ACCEPTED') for k in counts):raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception:
        print('MARKET_REFERENCE_POLL_FAILED_NO_PRIVATE_DIAGNOSTICS');raise SystemExit(1)

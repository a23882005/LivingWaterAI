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
from github_json_outbox import GithubContentsBackend,event_key
from gmail_smoke import MailOutbox
from monitor_core import observe
from safe_notify import send_notice
from original_rd_observer import observed_rd


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


def activity(observation,previously_active=False,manual_stop=False):
    if manual_stop:return False
    return previously_active or (observation.get('status')=='OBSERVED_DAILY_FORMULA' and observation.get('runaway_down')=='TRUE')


def main():
    repo=os.environ['GITHUB_REPOSITORY']
    if repo!='a23882005/LivingWaterAI' or os.environ.get('GITHUB_REF_NAME')!='main':
        raise ValueError('PRODUCTION_ENTRY_MAIN_ONLY')
    symbols=os.environ.get('WATCH_SYMBOLS','0050.TW,VT,SOXX,TSM').split(',')
    symbols=list(dict.fromkeys(s.strip() for s in symbols if s.strip()))
    if not symbols or len(symbols)>60 or any(not re.fullmatch(r'[A-Z0-9.^=-]{1,20}',s) for s in symbols):
        raise ValueError('WATCH_UNIVERSE_INVALID')
    stopped=set(os.environ.get('STOP_SYMBOLS','').split(','))
    backend=GithubContentsBackend(token=os.environ['GITHUB_TOKEN'],repository=repo,branch='main',
        path='research/yahoo_watch_candidate/state/notice.json')
    outbox=MailOutbox(backend);counts={}
    started=time.monotonic()
    for index,symbol in enumerate(symbols):
        if time.monotonic()-started>300:
            counts['NOT_EVALUATED_TIME_BUDGET']=len(symbols)-index;break
        if symbol in stopped:
            counts['MANUALLY_STOPPED']=counts.get('MANUALLY_STOPPED',0)+1;continue
        now=datetime.now(timezone.utc)
        try:observation=observed_rd(symbol,os.environ['V82_ORIGINAL_ROOT'])
        except Exception:observation=dict(status='UNKNOWN',runaway_down='UNKNOWN',reason='ORIGINAL_SOURCE_OBSERVATION_FAILED')
        _,doc=backend.read()
        activation_id='rd-observation-activation-v1:'+symbol
        prior=doc['events'].get(event_key(activation_id)) in ('PENDING','SENT')
        active=activity(observation,prior)
        if not active and observation.get('runaway_down')=='FALSE':
            counts['INACTIVE_NO_RD_OBSERVATION']=counts.get('INACTIVE_NO_RD_OBSERVATION',0)+1;continue
        payload={}
        if active:
            try:payload=fetch(symbol)
            except Exception:pass
        report=build_notice(symbol,payload,now,os.environ['GITHUB_RUN_ID'],repo)
        rd=observation.get('runaway_down','UNKNOWN')
        reason=observation.get('reason','UNKNOWN')
        report.update(rd_observation=rd,daily_session=observation.get('last_session'),
            activation_basis='ORIGINAL_APPROVED_RD_DAILY_PRICE_FORMULA_OBSERVATION_ONLY',
            monitor_status='ACTIVE_OBSERVATION_NOT_BUY' if active else 'ACTIVATION_UNKNOWN',
            reason=reason)
        report['event_id']=(activation_id if active and not prior else
            'rd-observation-health-v1:'+now.date().isoformat()+':'+symbol+':'+rd+':'+report['data_status']+':'+reason)
        state=send_notice(report,outbox=outbox,sender=os.environ['GMAIL_ADDRESS'],
            recipient=os.environ['GMAIL_ADDRESS'],app_password=os.environ['GMAIL_APP_PASSWORD'])
        counts[state]=counts.get(state,0)+1
    print(json.dumps({'status_counts':counts,'formal_v82_executed':False},sort_keys=True))
    allowed={'ALREADY_SENT','SENT_SMTP_ACCEPTED','MANUALLY_STOPPED','INACTIVE_NO_RD_OBSERVATION'}
    if any(k not in allowed for k in counts):raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception:
        print('MARKET_REFERENCE_POLL_FAILED_NO_PRIVATE_DIAGNOSTICS');raise SystemExit(1)

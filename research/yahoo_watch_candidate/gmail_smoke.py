"""One synthetic Gmail delivery via durable public-ID-only outbox. No market call."""
import os
from datetime import datetime,timezone,timedelta
from github_json_outbox import GithubContentsBackend,GithubJsonOutbox,event_key
from safe_notify import send_notice

class MailOutbox:
    def __init__(self,backend):self.box=GithubJsonOutbox(backend)
    def reserve(self,event_id,body):return self.box.reserve(event_key(event_id))
    def mark_sent(self,event_id):return self.box.mark_sent(event_key(event_id))

def main():
    repo=os.environ['GITHUB_REPOSITORY'];branch=os.environ['GITHUB_REF_NAME']
    if repo!='a23882005/LivingWaterAI' or branch!='candidate/yahoo-watch-router-20261110':
        raise ValueError('SMOKE_SCOPE_FORBIDDEN')
    run=os.environ['GITHUB_RUN_ID'];now=datetime.now(timezone.utc)
    report=dict(schema='LW_MARKET_NOTICE_V1',event_id='gmail-smoke-'+run,
        symbol='TEST',source='SYNTHETIC_NO_MARKET_DATA',observed_at=now.isoformat(),
        generated_at=now.isoformat(),data_status='TEST_ONLY',reason='SMTP_AND_OUTBOX_TEST_NOT_A_MARKET_SIGNAL',
        notice_kind='TEST',run_id=run,run_url='https://github.com/'+repo+'/actions/runs/'+run,
        valid_until=(now+timedelta(hours=1)).isoformat(),formal_v82_executed=False,
        session='NOT_APPLICABLE',delay_seconds=None)
    backend=GithubContentsBackend(token=os.environ['GITHUB_TOKEN'],repository=repo,branch=branch,
        path='research/yahoo_watch_candidate/state/gmail-smoke.json')
    state=send_notice(report,outbox=MailOutbox(backend),sender=os.environ['GMAIL_ADDRESS'],
        recipient=os.environ['GMAIL_ADDRESS'],app_password=os.environ['GMAIL_APP_PASSWORD'])
    print('GMAIL_SMOKE_STATUS='+state)
    if state not in ('SENT_SMTP_ACCEPTED','ALREADY_SENT'):raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except Exception:
        print('GMAIL_SMOKE_FAILED_NO_PRIVATE_DIAGNOSTICS');raise SystemExit(1)

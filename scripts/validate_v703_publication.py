"""Recheck the W7 time/policy contract immediately before publication or archival."""
import datetime as dt
import json
from pathlib import Path
try:
    import build_daily_v703_site as builder
except ModuleNotFoundError:
    from scripts import build_daily_v703_site as builder

def validate_current_contract(feed, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError('verification clock must be timezone-aware')
    try:made=builder._aware_time(feed.get('asOf'))
    except (AttributeError,TypeError,ValueError) as exc:raise ValueError('invalid aware snapshot time') from exc
    if made is None or made>now+dt.timedelta(minutes=5) or now-made>=dt.timedelta(hours=26):
        raise ValueError('snapshot outside 26-hour window')
    today=now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    rows=feed.get('indicators',{})
    raw={}
    mapping={'dataDate':'observation_date','source':'source_url','policySchema':'policy_schema','effectiveDate':'effective_date','publicationDate':'publication_date','retrievalTime':'retrieval_time','lastVerifiedAt':'last_verified_at','sourceEvidence':'source_evidence','lowerBound':'lower_bound','upperBound':'upper_bound','candidateChecks':'candidate_checks'}
    for key in builder.M06_COMPONENTS:
        row=rows.get(key)
        if not isinstance(row,dict):raise ValueError('missing policy component: '+key)
        raw[key]={mapping.get(k,k):v for k,v in row.items()}
    errors=builder._m06_component_issues(raw,today,feed.get('monthlyReleaseCalendar',{}).get('items',{}),now)
    if errors:raise ValueError('; '.join(errors))
    rate,inf,rstar,gap=[raw[k]['value'] for k in builder.M06_COMPONENTS]
    expected=(rate-inf-rstar)-(.5*(inf-2)+.5*gap)
    derived=rows.get('m06',{}).get('value')
    if isinstance(derived,bool) or not isinstance(derived,(int,float)) or not __import__('math').isfinite(derived) or abs(derived-expected)>.001:
        raise ValueError('m06 derived value disagrees with validated components')
    return True

def verify_live_payload(expected,live,expected_html,live_html):
    if live!=expected:raise ValueError('live JSON differs from validated build')
    if live_html!=expected_html:raise ValueError('live HTML differs from validated build')
    validate_current_contract(live)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('feed');a=p.parse_args()
    validate_current_contract(json.loads(Path(a.feed).read_text()))
    print('W7 publication time/policy contract PASS')

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
    validate_publication_gate(live)


def validate_publication_gate(feed, now=None):
    """Allow a verified CPI-only data update; formal scoring stays strict."""
    now = now or dt.datetime.now(dt.timezone.utc)
    validate_current_contract(feed, now)
    v = feed.get('verification', {})
    rows = feed.get('indicators', {})
    publication = feed.get('publication', {})
    if (feed.get('schema') != 'V70.3/family-macro-feed-v3'
            or set(rows) != set(builder.MACRO_CONFIG_IDS)|{'s03','s04'}
            or v.get('transportIndicators') != 28 or v.get('independentIndicators') != 25
            or v.get('totalRequired') != 26 or v.get('requiredScoringIndicators') != 22):
        raise ValueError('publication schema/counts invalid')
    formal = v.get('ready') is True
    if formal:
        if v.get('valid') != 26 or v.get('requiredScoringIndicatorsValidated') != 22 or v.get('problems') or v.get('missing'):
            raise ValueError('formal publication requires complete 22/22')
        if publication and (publication.get('mode') != 'FORMAL' or publication.get('scoringAllowed') is not True):
            raise ValueError('formal publication state disagrees')
    else:
        evidence = rows.get('m05', {}).get('officialUnavailable')
        if (v.get('publicationReady') is not True or v.get('valid') != 25
                or v.get('requiredScoringIndicatorsValidated') != 21
                or publication.get('schema') != 'V70.3/publication-state-v1'
                or publication.get('mode') != 'DATA_ONLY' or publication.get('scoringAllowed') is not False
                or publication.get('reason') != builder.CPI_REASON
                or rows.get('m05', {}).get('value') is not None
                or rows.get('m05', {}).get('status') != 'OFFICIAL_UNAVAILABLE'
                or rows.get('m05', {}).get('dataDate') != '2026-10-01'
                or v.get('missing') or not v.get('problems')
                or any(not p.startswith('m05:') for p in v['problems'])
                or not builder.valid_official_gap(evidence, now)):
            raise ValueError('data-only publication requires exact verified CPI-only exception')
    # Recheck the actual non-CPI fields, not merely the producer's ready/count flags.
    mapping={'dataDate':'observation_date','source':'source_url','policySchema':'policy_schema','effectiveDate':'effective_date','publicationDate':'publication_date','retrievalTime':'retrieval_time','lastVerifiedAt':'last_verified_at','sourceEvidence':'source_evidence','lowerBound':'lower_bound','upperBound':'upper_bound','candidateChecks':'candidate_checks'}
    today = now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    for key in rows:
        if not formal and key == 'm05':
            continue
        row = rows.get(key)
        if not isinstance(row, dict):
            raise ValueError('missing publication field: '+key)
        raw = {mapping.get(k,k):value for k,value in row.items()}
        errors = builder._validate(key,raw,today,feed.get('monthlyReleaseCalendar',{}).get('items',{}),now)
        if key in builder.SUPPLEMENT_IDS:
            errors += builder._validate_candidate_checks(key,raw)
        if errors:
            raise ValueError('; '.join(errors))
    return 'FORMAL' if formal else 'DATA_ONLY'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('feed');a=p.parse_args()
    mode=validate_publication_gate(json.loads(Path(a.feed).read_text()))
    print('W7 publication time/policy contract PASS', mode)

"""Synthetic browser-only fixture; never written to formal feed or archive."""
import json,re,copy
from pathlib import Path
from test_v703_policy_evidence import policy,b,NOW
HTML=Path(__file__).resolve().parents[1]/'系統工程/總經V70/V70-3-27.html'
def feed():
    text=HTML.read_text();d=json.loads(re.search(r'<script[^>]+id="v70-embedded-feed"[^>]*>(.*?)</script>',text,re.S).group(1))
    d['testFixture']='W7-A10 SYNTHETIC ONLY';d['asOf']='2026-10-22T03:00:00Z';d['batchDateTaipei']='2026-10-22'
    for key,row in d['indicators'].items():
        row.update(status='OK',dataDate='2026-10-21',method='synthetic fixture',detail='Synthetic browser acceptance fixture only')
        if row.get('value') is None:row['value']=2.0
        if key in b.MONTHLY:row['dataDate']='2026-09-30'
        if key in b.QUARTERLY:row['dataDate']='2026-09-30'
        if key in b.VALUATION_REFERENCE:
            row.update(lastVerifiedAt='2026-10-22T02:00:00Z',sourceEvidence={'label':'Forward P/E','value':row['value'],'url':row['source']})
    rows=d['indicators'];rows['m06_rate']=b._normalize(policy(),'m06_rate')
    for key in b.M06_COMPONENTS:rows[key]['candidateChecks']=copy.deepcopy(policy()['candidate_checks'])
    rows['m06']['value']=(rows['m06_rate']['value']-rows['m06_inf']['value']-rows['m06_rstar']['value'])-(.5*(rows['m06_inf']['value']-2)+.5*rows['m06_output_gap']['value'])
    rows['s03']=copy.deepcopy(rows['m07'])
    rows['m16']['dataDate']=d['leiHistory'][-1]['observation_date']
    rows['m16']['value']=d['leiHistory'][-1]['value']
    return d

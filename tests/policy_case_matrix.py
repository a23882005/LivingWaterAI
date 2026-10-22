"""Synthetic shared policy contract cases for Python, Node and Chromium."""
import copy
from test_v703_policy_evidence import policy, NOW

def cases():
    result=[('valid_old_effective',policy(),NOW,True)]
    changes=[('effective_date','2026-10-23'),('value',4.2),('source_url','https://example.com'),('unit','bp'),('last_verified_at','2026-10-22T02:05:00'),('retrieval_time','2026-10-20T02:00:00Z'),('publication_date','2026-07-31')]
    for key,value in changes:
        r=policy();r[key]=value;result.append((key,r,NOW,False))
    for key,value in [('result','CACHE_READ'),('response_sha256','bad'),('excerpt','')]:
        r=policy();r['source_evidence'][key]=value;result.append(('evidence_'+key,r,NOW,False))
    r=policy();del r['source_evidence'];result.append(('missing_evidence',r,NOW,False))
    r=policy();r['upper_bound']['effective_date']='2026-07-31';result.append(('bound_date',r,NOW,False))
    import datetime as dt
    deadline=dt.datetime(2026,10,23,4,tzinfo=dt.timezone.utc)
    result.extend([('before_expiry',policy(),deadline-dt.timedelta(milliseconds=1),True),('exact_expiry',policy(),deadline,False)])
    return result

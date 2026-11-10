"""Read-only real-source probe. No SMTP, state writes, accounts or trading."""
import json,os
from original_rd_observer import observed_rd
results=[]
for symbol in ('0050.TW','VT','SOXX','TSM'):
    try:r=observed_rd(symbol,os.environ['V82_ORIGINAL_ROOT'])
    except Exception:r={'symbol':symbol,'status':'UNKNOWN','reason':'SOURCE_PROBE_ERROR','runaway_down':'UNKNOWN','formal_v82_executed':False}
    assert r['formal_v82_executed'] is False
    assert r['runaway_down'] in ('TRUE','FALSE','UNKNOWN')
    results.append(r)
# At least one source must exercise the original numeric route. UNKNOWNs are
# visible evidence limits, not a claim of 4/4 source qualification.
assert any(r['status']=='OBSERVED_DAILY_FORMULA' for r in results),'NO_ORIGINAL_DAILY_PRODUCER_REACHED'
print(json.dumps({'scope':'OBSERVATION_ONLY_NO_BUY','actual_email_count':0,'results':results},sort_keys=True))

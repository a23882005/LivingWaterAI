"""Synthetic diagnostic of the accepted W5 projection, not a remediation test."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--w5', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
home = Path(args.w5).resolve()
sys.path.insert(0, str(home))
from permission_bridge import project_permissions
from family_boundary import position_view, timestamp
from family_input import digest

rows = [
    {'account_key':'TEST_ACCOUNT','instrument_key':'TEST_ASSET','as_of_utc':'2026-10-20T00:00:00Z','quantity_decimal':'10'},
    {'account_key':'TEST_ACCOUNT','instrument_key':'TEST_ASSET','as_of_utc':'2026-10-21T00:00:00Z','quantity_decimal':'0'},
]
tables = {'portfolio_position':rows,'portfolio_instrument':[{'instrument_key':'TEST_ASSET'}]}
for key in ('universe_membership','universe_confirmation','permission_policy','permission_confirmation','holding_policy_proposal','holding_policy_confirmation'):
    tables[key] = []
snapshot = {'client_id':'TEST_CLIENT','tables':tables,'payload_digest':digest(tables)}
result = project_permissions(snapshot, account='TEST_ACCOUNT', evaluation_at='2026-10-22T00:00:00Z')[0]
assert result['existing_holding'] is True and result['retain_in_holdings_and_drift'] is True
output = {
    'scope':'SYNTHETIC_ONLY_DIAGNOSTIC_NOT_REMEDIATION_PASS',
    'source_commit':'2d569cc9d61bc70538f5dd6e3087d4af5d014e08',
    'source_sha256':{name:hashlib.sha256((home/name).read_bytes()).hexdigest() for name in ('permission_bridge.py','family_boundary.py')},
    'cleared_position':{'latest_quantity':'0','observed_existing_holding':result['existing_holding'],'observed_retain':result['retain_in_holdings_and_drift'],'required_work':'W7-B09','status':'REPRODUCED_PENDING_FIX'},
}
rows[0]['as_of_utc'] = rows[1]['as_of_utc']
snapshot['payload_digest'] = digest(tables)
complete = {'state':'COMPLETE','source_reference':'SYNTHETIC_ONLY','snapshot_digest':snapshot['payload_digest'],'account_key':'TEST_ACCOUNT','as_of':'2026-10-21T00:00:00Z'}
at = timestamp('2026-10-22T00:00:00Z','test')
forward = position_view(snapshot,'TEST_ACCOUNT',at,complete)[0]['quantity']
rows.reverse()
snapshot['payload_digest'] = digest(tables)
complete['snapshot_digest'] = snapshot['payload_digest']
reverse = position_view(snapshot,'TEST_ACCOUNT',at,complete)[0]['quantity']
assert forward == '10' and reverse == '0'
output['same_timestamp'] = {'forward':forward,'reversed':reverse,'status':'ORDER_DEPENDENCE_REPRODUCED','downstream':'stock/bond source bridges reject ambiguity; B09 centralizes projection'}
Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Two synthetic diagnostics reproduced; B09 remediation remains pending.')

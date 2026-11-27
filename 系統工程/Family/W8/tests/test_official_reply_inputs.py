from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_official_reply_inputs as M

AT='2026-10-29T22:00:00Z'


def case(tmp_path, *, body=None, attachments=None):
    message={'headers':[{'name':'From','value':'Fund Inquiry <Fund_Inquiry@ssga.com>'},
        {'name':'Date','value':'Thu, 29 Oct 2026 20:45:16 +0000'},
        {'name':'Subject','value':'RE: SPSB historical yields'},
        {'name':'Authentication-Results','value':'dkim=pass spf=pass dmarc=pass'}],
        'body_plain':body or 'Unfortunately, we are unable to provide the requested information.\r\nPublic information is on our website.\r\nFrom: SYNTHETIC\r\nCould you provide fees and paid access?',
        'attachments':attachments or []}
    files={'SSGA_reply.json':json.dumps(message).encode(),'START_HERE.txt':b'SYNTHETIC handoff; owner submitted IB inquiry, no ticket or reply attached.'}
    manifest=[]
    for name,raw in files.items():
        (tmp_path/name).write_bytes(raw);manifest.append({'path':name,'bytes':len(raw),'sha256':sha256(raw).hexdigest()})
    raw=json.dumps(manifest).encode();(tmp_path/'manifest.json').write_bytes(raw)
    return {'schema_version':'Family.W8.V75OfficialReplySource.v1','root':str(tmp_path),
        'manifest_sha256':sha256(raw).hexdigest(),'ingested_at':AT,'source_reference':'SYNTHETIC_OWNER_HANDOFF'}


def test_closed_inquiry_is_not_pending_delivery_or_a_fee_offer_from_quoted_request(tmp_path):
    source=case(tmp_path);out=M.read(source,AT)
    assert out['state_street']['status']=='CLOSED_UNAVAILABLE'
    assert not out['state_street']['awaiting_data_delivery'] and not out['state_street']['paid_offer_in_reply']
    assert out['interactive_brokers']['status']=='USER_REPORTED_SUBMITTED_AWAITING_REPLY'
    assert out['interactive_brokers']['ticket_id'] is None and not out['interactive_brokers']['reply_received']
    assert not out['outreach_authorized'] and not out['new_yield_ROC_or_NBBO_data_supplied']


def test_reply_preserves_financial_metrics_and_availability(tmp_path):
    source=case(tmp_path);pool={'available_at':'2026-10-28T00:00:00Z','asset_metrics':{'SYNTHETIC':1},'source_proofs':{'original':'bound'}}
    before=deepcopy(pool);M.extend(pool,source,AT)
    assert all(pool[k]==v for k,v in before.items())
    assert M.read(None,AT) is None


def test_reply_time_hash_and_disposition_are_bound(tmp_path):
    source=case(tmp_path)
    with pytest.raises(PermissionError,match='AVAILABILITY'):M.read(source,'2026-10-29T21:59:59Z')
    (tmp_path/'SSGA_reply.json').write_bytes(b'{}')
    with pytest.raises(PermissionError,match='SOURCE_HASH'):M.read(source,AT)
    source=case(tmp_path,body='Data files will be delivered tomorrow.')
    with pytest.raises(PermissionError,match='DISPOSITION'):M.read(source,AT)

"""Run an existing W5 golden through two new original FamilyRunner instances.

Usage: python run_w5_replay.py W5_HANDOFF_DIRECTORY OUTPUT_JSON
Uses only the authorized W5 source and baseline dependency trees.
"""
from pathlib import Path
import json
import os
import sys
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from replay import digest, replay, verify_files


def main(handoff,output):
    handoff=Path(handoff).resolve()
    home=Path(__file__).resolve().parent
    lock=json.loads((home/'source_lock.json').read_text())
    verify_files(handoff,lock)
    w5=handoff/'repo/系統工程/Family/W5'
    root=handoff/'baseline/sources'
    os.environ['W5_SOURCE_ROOT']=str(root)
    sys.path[:0]=[str(w5),str(w5/'tests')]
    from verify_dependencies import verify
    dependency_count=verify(root)
    from test_family_end_to_end import full_family_case
    from family_runner import FamilyRunner
    from family_input import digest as w5digest
    req,ctx=full_family_case()
    old=json.loads((w5/'evidence/family_e2e_positive.json').read_text())
    original=json.loads((handoff/'synthetic_evidence/family_e2e_full_result.json').read_text())
    assert w5digest(original)==old['actual']['full_result_sha256']
    assert w5digest(req)==old['request_sha256'],'W5 golden input changed'
    assert w5digest(ctx)==old['context_sha256'],'W5 golden context changed'
    payload={'request':req,'context':ctx}
    owner=req['owner']
    event=dict(schema_version='Family.BR.Event.v1',event_id='BR-W5-GOLDEN-001',
        client_id=owner['client_id'],account_id=owner['account'],
        funding_domain_id=owner['funding_domain'],event_time=req['evaluation_at'],
        snapshot_id=req['run_id'],data_kind='SYNTHETIC',versions={'source_lock':digest(lock)},
        input=payload,input_sha256=digest(payload),portfolio_before=[],portfolio_after=[],
        value_state='KNOWN',issue_codes=[],sources=[dict(source_id='W5-ORIGINAL-GOLDEN',
        payload=old,sha256=digest(old),basis='NOT_APPLICABLE',
        evidence_ref='W5/evidence/family_e2e_positive.json')])
    def compute(data):
        # A fresh runner forces actual compute; no previous cache is shared.
        context=deepcopy(data['context'])
        result=FamilyRunner(root,context_provider=lambda:context).analyze(data['request'])
        assert result['status']=='OK',result
        return result
    # W5's later technical-source bridge added one field. Its declared behavior
    # for this pre-existing synthetic fixture (no technical_source) is null.
    # Preserve every original field; additions beyond this explicit null fail.
    assert ctx.get('technical_source') is None
    assert 'technical_intake' not in original
    golden={**original,'technical_intake':None}
    result=replay(event,engine=compute,expected_client=owner['client_id'],
        expected_versions=event['versions'],source_root=handoff,source_lock=lock,golden=golden)
    result['golden_compatibility']={'original_sha256':w5digest(original),
        'explicit_addition':{'technical_intake':None},'all_original_fields':'EXACT_COMPARE'}
    result['verified_w5_dependencies']=dependency_count
    result['historical_readiness']='OPEN_PUBLICATION_VINTAGE_EVIDENCE'
    result['note']='Original synthetic golden; historical availability is not inferred.'
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='result'},ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main(*sys.argv[1:])

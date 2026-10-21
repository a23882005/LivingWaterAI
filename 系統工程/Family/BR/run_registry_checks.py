"""Build and verify all existing snapshot registrations at their time boundary."""
import json
import sys
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from replay import digest, instant, ReplayError
from source_registry import build_registry, read_snapshot


def main(root,audit_path,output_dir):
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    audit=json.loads(Path(audit_path).read_text())
    registry=build_registry(root,audit,trusted_audit_sha256=digest(audit))
    # This pin is emitted to the release evidence and consumed separately from requests.
    pin=digest(registry)
    (out/'source_registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    results=[]
    for entry in registry['entries']:
        args=dict(trusted_registry_sha256=pin,symbol=entry['symbol'])
        selected=read_snapshot(root,registry,**args,cutoff=entry['available_at'],purpose='ARCHIVE_READ_ONLY')
        checks={'at_capture':len(selected['rows'])==entry['row_count'],'decision_eligible':selected['decision_eligible']}
        cases=[('before_capture',(instant(entry['available_at'])-timedelta(microseconds=1)).isoformat(),'ARCHIVE_READ_ONLY','NO_SOURCE_AVAILABLE_AT_CUTOFF'),
               ('historical',entry['available_at'],'HISTORICAL_REPLAY','PER_BAR_PUBLICATION_UNPROVEN'),
               ('decision',entry['available_at'],'DECISION_INPUT','DECISION_BASIS_REVIEW_REQUIRED')]
        for name,cutoff,purpose,code in cases:
            try:read_snapshot(root,registry,**args,cutoff=cutoff,purpose=purpose)
            except ReplayError as exc:checks[name]=str(exc)==code
            else:checks[name]=False
        if not all(checks[k] for k in ('at_capture','before_capture','historical','decision')) or checks['decision_eligible']:
            raise RuntimeError('REGISTRY_CHECK_FAILED:'+entry['symbol'])
        results.append({'symbol':entry['symbol'],**checks})
    result={'schema_version':'Family.BR.RegistryChecks.v1','status':'PASS','sources':len(results),
        'boundary_checks':4*len(results),'registry_sha256':pin,'results':results,
        'historical_readiness':'OPEN_SOURCE_EVIDENCE','production':'HOLD','trade_authorization':'NONE'}
    (out/'registry_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'}))


if __name__=='__main__':main(*sys.argv[1:])

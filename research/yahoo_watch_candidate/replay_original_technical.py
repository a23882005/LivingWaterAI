"""Replay original approved technical producer against source-qualified evidence.
No download, fabricated source receipt, strategy replacement, account or mail action.
The qualification artifact and underlying captured sources must exist locally.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

APPROVED_SOURCE_COMMIT='3f7ea0dcd2963ae55598ffa90b36893ed47cc9bb'

def replay(root,qualification,expected_sha,symbol,evaluation_at):
    root=root.resolve(strict=True);qualification=qualification.resolve(strict=True)
    commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if commit!=APPROVED_SOURCE_COMMIT:raise ValueError('ORIGINAL_SOURCE_COMMIT_MISMATCH')
    if subprocess.run(['git','-C',str(root),'diff','--quiet','HEAD'],check=False).returncode:
        raise ValueError('ORIGINAL_TRACKED_SOURCE_MODIFIED')
    raw=qualification.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('QUALIFICATION_HASH_MISMATCH')
    w8=root/'系統工程/Family/W8';w5=w8.parent/'W5'
    sys.path[:0]=[str(w8),str(w5)]
    modules={name:importlib.import_module(name) for name in
             ('qualified_equity_inputs','approved_v04_technical','technical_source_bridge')}
    for name,module in modules.items():
        expected=(w5 if name=='technical_source_bridge' else w8)/(name+'.py')
        if Path(module.__file__).resolve()!=expected.resolve():raise ValueError('ORIGINAL_MODULE_SHADOWED')
    source=modules['qualified_equity_inputs'].item(symbol,{'local_path':str(qualification),'sha256':expected_sha},evaluation_at,root)
    approved=modules['approved_v04_technical'].produce(source['rows'],
        profile=modules['approved_v04_technical'].load_profile(w8/'owner_approved_v10.json'),is_etf=True)
    technical=modules['technical_source_bridge']._aggregate(root,approved['signals'],approved['ma20_ok'])
    return dict(schema='ORIGINAL_TECHNICAL_REPLAY_V1',symbol=symbol,source_commit=commit,
        qualification_sha256=expected_sha,evaluation_at=evaluation_at,
        source_status=source['status'],last_session=source['observed_date'],rows=len(source['rows']),
        technical=technical,left_price_condition='UNKNOWN',
        status='TECHNICAL_ONLY_NOT_FULL_V82',buy_permission='UNKNOWN',trade_action='NONE',
        historical_publication_pit_attested=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--symbol',choices=['VT','QQQ'],required=True)
    p.add_argument('--evaluation-at',default=None);args=p.parse_args()
    try:
        r=replay(args.root,args.qualification,args.sha256,args.symbol,args.evaluation_at or datetime.now(timezone.utc).isoformat())
        print(json.dumps(r,sort_keys=True))
    except Exception as e:
        # Approved source codes are useful, but do not print arbitrary raw messages/paths.
        code=str(e)
        if not code.replace('_','').isalnum() or len(code)>120:code='SOURCE_REPLAY_FAILED'
        print(json.dumps({'status':'BLOCKED','reason':code,'error_type':type(e).__name__,'trade_action':'NONE'}))
        raise SystemExit(1)
if __name__=='__main__':main()

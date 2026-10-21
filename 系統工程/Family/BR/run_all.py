"""One command verifies BR code, original engines, history and registry.

Usage: python run_all.py W5_HANDOFF_DIRECTORY OUTPUT_DIRECTORY
Requires the pinned requirements.lock in an isolated Python environment.
"""
import json
from pathlib import Path
import subprocess
import sys


def run(handoff, output):
    home=Path(__file__).resolve().parent
    source=Path(handoff).resolve();out=Path(output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    tasks=[('tests',[sys.executable,'-m','pytest','-q',str(home/'tests')]),
        ('w5',[sys.executable,str(home/'run_w5_replay.py'),str(source),str(out/'w5_replay.json')]),
        ('history',[sys.executable,str(home/'audit_existing_history.py'),str(source/'market_intake'),str(out/'history_audit.json')]),
        ('registry',[sys.executable,str(home/'run_registry_checks.py'),str(source/'market_intake'),str(out/'history_audit.json'),str(out)])]
    for name,command in tasks:
        task=subprocess.run(command,cwd=home,text=True,capture_output=True)
        (out/(name+'.log')).write_text(task.stdout+task.stderr)
        if task.returncode:
            (out/'RUN_STATUS.json').write_text(json.dumps({'status':'FAIL','step':name,'returncode':task.returncode},indent=2)+'\n')
            raise SystemExit(task.returncode)
    replay=json.loads((out/'w5_replay.json').read_text())
    history=json.loads((out/'history_audit.json').read_text())
    registry=json.loads((out/'registry_checks.json').read_text())
    status={'status':'PASS','scope':'BR engineering regression with declared source evidence gaps',
        'w5_status':replay['status'],'capture_status':replay['capture_proof']['status'],
        'history_files':history['files'],'snapshot_integrity_passed':history['snapshot_integrity_passed'],
        'registry_boundary_checks':registry['boundary_checks'],
        'historical_ready':False,'br_major_gate':'OPEN_SOURCE_EVIDENCE',
        'w7_release':'NOT_RELEASED','production':'HOLD','trade_authorization':'NONE'}
    (out/'RUN_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(status,ensure_ascii=False))


if __name__=='__main__':run(*sys.argv[1:])

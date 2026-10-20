"""Operator CLI: request is untrusted; authority file is supplied separately."""
import argparse
import json
import os
from pathlib import Path
from family_runner import FamilyRunner
from family_boundary import BoundaryError


def strict_json(path):
    def reject(value):raise ValueError('NONFINITE_JSON')
    return json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=reject)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--repo-root',default=os.environ.get('W5_SOURCE_ROOT',str(Path(__file__).resolve().parents[3])))
    parser.add_argument('--trusted-context',default=os.environ.get('W5_TRUSTED_CONTEXT'))
    args=parser.parse_args()
    if Path(args.request).resolve()==Path(args.output).resolve():parser.error('output must differ from request')
    if args.trusted_context and Path(args.trusted_context).resolve()==Path(args.output).resolve():parser.error('output must differ from trusted context')
    def provider():
        if not args.trusted_context:raise BoundaryError('TRUSTED_CONTEXT_REQUIRED','trusted_context')
        return strict_json(args.trusted_context)
    try:
        req=strict_json(args.request)
        if not isinstance(req,dict):raise ValueError('REQUEST_OBJECT_REQUIRED')
        result=FamilyRunner(args.repo_root,context_provider=provider).analyze(req)
    except (OSError,ValueError,TypeError):
        result={'schema_version':'Family.W5.result.v1','status':'ERROR','issue_codes':[{'code':'CLI_INPUT_OR_DEPENDENCY_ERROR'}],
            'canonical_result':None,'mentor':None,'production':'HOLD','trade_action':'NO_TRADE'}
    destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return 0 if result['status']=='OK' else 2


if __name__=='__main__':raise SystemExit(main())

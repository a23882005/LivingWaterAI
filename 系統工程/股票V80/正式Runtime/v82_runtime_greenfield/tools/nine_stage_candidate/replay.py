"""Read a bound research input and save one isolated replay; disabled by default."""
from pathlib import Path
import argparse
import json
from .engine import replay,PROFILES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-research',action='store_true')
    parser.add_argument('--input',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--profile',choices=PROFILES,default=PROFILES[0])
    parser.add_argument('--compact-daily',action='store_true')
    args=parser.parse_args()
    if not args.enable_research:
        print(json.dumps(replay([],[])));return
    if args.input is None or args.output is None:parser.error('enabled research requires --input and --output')
    data=json.loads(args.input.read_text())
    result=replay(data['rows'],data['inputs'],source=data['source'],profile=args.profile,
        enabled=True,compact_daily=args.compact_daily)
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,default=str,indent=2)
    print(json.dumps({'profile':args.profile,'sessions':len(result),'formal_strategy_enabled':False,'trade_action':'NO_TRADE'}))


if __name__=='__main__':main()

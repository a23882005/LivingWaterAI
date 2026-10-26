"""PM read-only validation of actual IB observations using approved routines.

No native deployment readiness, target confirmation, funding or trade authority
is inferred from these numeric observations. Raw receipts remain private.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
import hashlib
import json
import math
import subprocess
import sys
import argparse
import pandas as pd

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--receipts-dir',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--symbols',nargs='+',required=True)
parser.add_argument('--evaluated-at',help='Timezone-aware observation evaluation boundary')
args=parser.parse_args()
ROOT=args.repo.resolve(strict=True)
BASE=args.receipts_dir.resolve(strict=True)
if not args.symbols or any(not x or '/' in x or '\\' in x or x in ('.','..') for x in args.symbols):
    parser.error('Exact provider symbols required; file paths are not symbols')
sys.path.insert(0,str(ROOT/'系統工程/Family/W5'))
from technical_source_bridge import _originals, _aggregate, NAMES
from market_bridge import read_macro_snapshot


def run():
    now=datetime.fromisoformat(args.evaluated_at.replace('Z','+00:00')) if args.evaluated_at else datetime.now(timezone.utc)
    if now.utcoffset() is None:raise ValueError('EVALUATION_TIMEZONE_REQUIRED')
    if args.output.resolve().exists():raise FileExistsError('NEW_EVIDENCE_OUTPUT_REQUIRED')
    legacy,numeric=_originals()
    results=[];receipts=[]
    for symbol in dict.fromkeys(args.symbols):
        p=BASE/f'IB_{symbol}_source.json'
        r=json.loads(p.read_text());h=r['history'];req=r['request'];issues=[]
        keys=['time','open','high','low','close','volume']
        lengths={k:len(h[k]) for k in keys}
        if len(set(lengths.values()))!=1:
            raise ValueError('BAR_ARRAY_LENGTH_MISMATCH')
        matches=[x for x in r['contracts']['results']
                 if x.get('underlying_contract_id')==req['contract_id']
                 and x.get('symbol')==symbol and x.get('exchange')==req['exchange']]
        if len(matches)!=1 or h['chart_step']!=86400:
            raise ValueError('INSTRUMENT_OR_TIMEFRAME_MISMATCH')
        times=[datetime.fromisoformat(t.replace('Z','+00:00')) for t in h['time']]
        if times!=sorted(set(times)) or any(t.utcoffset() is None for t in times):
            raise ValueError('BAR_TIME_INVALID')
        if h.get('chart_end'):
            end=datetime.fromisoformat(h['chart_end'].replace('Z','+00:00'))
            if times[-1]>end:issues.append('CHART_END_PRECEDES_LAST_BAR')
            if end>now:issues.append('CHART_END_IN_FUTURE')
        rows=[];excluded=[];bad=[]
        for i,t in enumerate(times):
            vals={k:float(h[k][i]) for k in keys[1:]}
            if (not all(math.isfinite(v) for v in vals.values())
                or not vals['low']<=min(vals['open'],vals['close'])
                    <=max(vals['open'],vals['close'])<=vals['high']
                or vals['low']<=0 or vals['volume']<0):
                bad.append(h['time'][i])
            # Conservative exclusion only. Do not invent formal exchange close
            # times, verified sessions, adjustment basis or historical receipt.
            if t+timedelta(days=1)>now:
                excluded.append(h['time'][i]);continue
            rows.append({'Date':h['time'][i],**{k.title():v for k,v in vals.items()}})
        selected={'provider':'IBKR','reference':f"IBKR:{req['contract_id']}",
                  'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        if bad or any(x.startswith('CHART_END_') for x in issues):
            issues.append('IB_SOURCE_REJECTED')
            cache=ROOT/'data/market_history/global'/f'{symbol}.csv'
            if not cache.is_file():raise ValueError('NO_VERIFIED_FALLBACK')
            manifest=json.loads((cache.parent/'manifest.json').read_text())
            item=manifest['items'][symbol]
            frame=pd.read_csv(cache)
            if (item['status']!='OK' or len(frame)!=item['rows']
                or frame.iloc[-1]['Date']!=item['latest_observation']):
                raise ValueError('FALLBACK_MANIFEST_MISMATCH')
            rows=[];excluded=[]
            for _,r0 in frame.iterrows():
                t=datetime.fromisoformat(str(r0['Date'])).replace(tzinfo=timezone.utc)
                vals={k:float(r0[k.title()]) for k in keys[1:]}
                if (not all(math.isfinite(v) for v in vals.values())
                    or not vals['low']<=min(vals['open'],vals['close'])
                        <=max(vals['open'],vals['close'])<=vals['high']
                    or vals['low']<=0 or vals['volume']<0):
                    raise ValueError('FALLBACK_OHLCV_INVALID')
                if t+timedelta(days=1)>now:
                    excluded.append(str(r0['Date']));continue
                rows.append({'Date':str(r0['Date']),
                             **{k.title():v for k,v in vals.items()}})
            selected={'provider':'EXISTING_GITHUB_YFINANCE_CACHE',
                      'reference':str(cache.relative_to(ROOT)),
                      'raw_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),
                      'last_verified_utc':item['last_verified_utc'],
                      'latest_observation':item['latest_observation']}
            issues.append('CACHED_OBSERVATION_DATE_MUST_BE_SHOWN')
        if len(rows)<13:raise ValueError('NATIVE_NUMERIC_SAMPLE_INSUFFICIENT')
        frame=pd.DataFrame(rows)
        td9=legacy['calculate_td9'](frame['Close'].tolist())
        values=numeric.technical(frame)
        issues+=['PROVIDER_ADJUSTMENT_BASIS_NOT_ATTESTED',
                 'OFFICIAL_SESSION_CONTINUITY_NOT_ATTESTED',
                 'CANONICAL_PREDICATES_INCOMPLETE']
        aggregation=_aggregate(ROOT,{g:[{'truth':'UNKNOWN'} for _ in names]
                                    for g,names in NAMES.items()})
        results.append({'symbol':symbol,'contract_id':req['contract_id'],
            'exchange':req['exchange'],'received_bars':len(times),'used_bars':len(rows),
            'first_bar':rows[0]['Date'],'last_bar':rows[-1]['Date'],
            'excluded_potentially_forming_bars':excluded,
            'raw_source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'ib_invalid_ohlcv_count':len(bad),'ib_invalid_bar_times':bad,
            'selected_source':selected,'selected_history':rows,
            'data_provenance':'SOURCE_BACKED',
            'numeric_scope':'OBSERVED_PROVIDER_PRICES__METADATA_GAPS_DECLARED',
            'td9':asdict(td9),'original_numeric':values,
            'native_v82_unknown_aggregation':aggregation,'issue_codes':issues,
            'formal_deployment_eligible':False,'trade_authorization':'NONE',
            'call_trace':['IBKR.get_price_history',
                'W5.technical_source_bridge._originals/hash_lock',
                'ORIGINAL.calculate_td9','ORIGINAL.analytics.technical',
                'V82.evaluate_technical']})
        receipts.append(r)
    macro=read_macro_snapshot(ROOT,source_commit=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    result={'schema':'Family.W8.LiveSourceComputation.v1',
        'recorded_at_utc':now.isoformat(),
        'scope':'PM_SOURCE_OBSERVATIONS_NOT_PROJECT_LOGIN_OR_COMPLETE_FAMILY_RUN',
        'macro':macro,'results':results,'source_receipts':receipts,
        'remaining':['Same-run W2/C7/funding/V70 tactical request producer',
                     'Provider adjustment/session metadata and canonical predicates',
                     'Four-member 04 and W6 complete run'],
        'official_family_db_modified':False,'production':'HOLD',
        'trade_authorization':'NONE'}
    dest=args.output.resolve()
    if dest.exists():raise FileExistsError('NEW_EVIDENCE_OUTPUT_REQUIRED')
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    for x in results:
        print({k:x[k] for k in ['symbol','received_bars','used_bars','last_bar',
                               'excluded_potentially_forming_bars','issue_codes']})
    print('EVIDENCE',dest.stat().st_size,hashlib.sha256(dest.read_bytes()).hexdigest())


if __name__=='__main__':run()

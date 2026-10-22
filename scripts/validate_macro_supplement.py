"""Validate a staged eight-item Task payload without changing data or publishing."""
import argparse
import datetime as dt
import json
from pathlib import Path
from build_daily_v703_site import SUPPLEMENT_IDS, VALUATION_REFERENCE, _normalize, _validate, _validate_candidate_checks


def validate(payload, now):
    errors=[]
    if not isinstance(payload,dict) or not isinstance(payload.get('items'),dict):
        return ['items object required']
    if payload.get('schema') != 'V70.3/10h-eight-supplement-v3':
        errors.append('eight-supplement-v3 schema required')
    if set(payload['items']) != SUPPLEMENT_IDS:
        errors.append('exactly eight supplement keys required')
    if now.tzinfo is None:
        return ['aware validation clock required']
    stamps={}
    for field in ('generated_at','as_of_taipei'):
        try:
            stamp=dt.datetime.fromisoformat(payload[field].replace('Z','+00:00'))
            stamps[field]=stamp
            if field=='as_of_taipei' and stamp.utcoffset()!=dt.timedelta(hours=8):
                raise ValueError()
            if stamp.tzinfo is None or stamp>now or (now-stamp).total_seconds()>=26*3600:
                raise ValueError()
        except (KeyError,TypeError,ValueError,AttributeError):
            errors.append(field+': missing, invalid, future or expired timestamp')
    if len(stamps)==2 and stamps['generated_at']!=stamps['as_of_taipei']:
        errors.append('generation timestamps must identify the same instant')
    today=now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()
    for key in SUPPLEMENT_IDS:
        row=payload['items'].get(key)
        errors.extend(_validate(key,row,today,{},now))
        errors.extend(_validate_candidate_checks(key,row))
        if key in VALUATION_REFERENCE and isinstance(row,dict):
            try:
                evidence=_normalize(row,key).get('sourceEvidence')
            except (TypeError,ValueError,KeyError,AttributeError):
                evidence=None
            if not evidence:
                errors.append(key+': Forward/FY1 value/source evidence required')
        if key=='s05' and isinstance(row,dict):
            try:
                if not 0<=float(row['value'])<=100: raise ValueError()
            except (KeyError,TypeError,ValueError):errors.append('s05: percentage outside 0-100')
    return errors


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload');parser.add_argument('--now',help='fixed aware timestamp for reproducible tests')
    args=parser.parse_args()
    now=dt.datetime.fromisoformat(args.now.replace('Z','+00:00')) if args.now else dt.datetime.now(dt.timezone.utc)
    errors=validate(json.loads(Path(args.payload).read_text()),now)
    print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False,indent=2))
    raise SystemExit(bool(errors))

"""Read existing W5-authorized historical artifacts; no downloads or edits.

CSV history_digest is checked against the original W5 intake record. Evidence
reports snapshot reproducibility separately from historical point-in-time.
"""
import csv
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'runtime'))
from replay import instant, digest


def audit(directory,output):
    directory=Path(directory)
    entries=[]
    for path in sorted(directory.glob('*.csv')):
        evidence=path.with_name(path.name+'.result.json')
        if not evidence.is_file():
            entries.append({'file':path.name,'status':'BLOCKED','issues':['INTAKE_RECEIPT_MISSING']})
            continue
        old=json.loads(evidence.read_text())
        meta=old['source_metadata']
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        issues=[]
        rows=list(csv.DictReader(path.read_text(encoding='utf-8-sig').splitlines()))
        # W5 history_digest hashes canonical parsed rows, not CSV file bytes.
        # The independent Family context stores the raw CSV SHA-256.
        row_sha=digest(rows)
        context_path=path.with_name(path.stem+'.family_context.json')
        if context_path.is_file():
            context=json.loads(context_path.read_text())
            expected_raw=context.get('technical_source',{}).get('sha256')
        else:expected_raw=None
        if sha!=expected_raw:issues.append('RAW_FILE_HASH_MISMATCH')
        if row_sha!=old['history_digest'] or row_sha!=meta['history_digest'] or rows!=old['source_history']:
            issues.append('CANONICAL_HISTORY_MISMATCH')
        dates=[];splits=[];dividends=[]
        for row in rows:
            try:
                day=date.fromisoformat(row['Date']); dates.append(day)
                price=Decimal(row['Close'])
                if not price.is_finite() or price<=0:issues.append('INVALID_PRICE')
                for key,events in [('Stock Splits',splits),('Dividends',dividends)]:
                    if key not in row:issues.append('MISSING_'+key);continue
                    n=Decimal(row[key])
                    if not n.is_finite() or n<0:issues.append('INVALID_'+key)
                    elif n!=0:events.append({'date':row['Date'],'value':row[key]})
            except (ValueError,KeyError,InvalidOperation):issues.append('INVALID_ROW')
        if not dates:issues.append('EMPTY_HISTORY')
        if dates!=sorted(set(dates)):issues.append('UNSORTED_OR_DUPLICATE_DATE')
        capture=meta.get('artifact_written_at')
        if not capture:issues.append('CAPTURE_TIME_MISSING')
        elif dates and max(dates)>instant(capture).date():issues.append('BAR_AFTER_CAPTURE')
        if meta.get('fetch_completed_at') and capture and instant(meta['fetch_completed_at'])>instant(capture):
            issues.append('CAPTURE_TIME_ORDER')
        gaps=[]
        if meta.get('split_basis_verified') is not True:gaps.append('SPLIT_BASIS_UNVERIFIED')
        if not meta.get('historical_publication_evidence'):gaps.append('PER_BAR_PUBLICATION_UNPROVEN')
        if not meta.get('dividend_return_convention'):gaps.append('DIVIDEND_RETURN_CONVENTION_UNCONFIRMED')
        entries.append({'file':path.name,'symbol':meta.get('symbol'),'status':'PASS' if not issues else 'BLOCKED',
            'sha256':sha,'canonical_history_sha256':row_sha,
            'receipt_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),
            'rows':len(rows),'first_date':str(min(dates)) if dates else None,'last_date':str(max(dates)) if dates else None,
            'snapshot_available_at':capture,'snapshot_time_semantics':meta.get('receipt_semantics'),
            'price_field':meta.get('price_field'),'auto_adjust':meta.get('auto_adjust'),
            'split_events':splits,'dividend_events':dividends,'issues':sorted(set(issues)),
            'historical_readiness':'OPEN' if gaps or issues else 'EVIDENCE_REVIEW_REQUIRED',
            'historical_gaps':gaps,'source_reference':meta.get('source_reference')})
    result={'schema_version':'Family.BR.HistoryAudit.v1','files':len(entries),
        'snapshot_integrity_passed':sum(x['status']=='PASS' for x in entries),
        'entries':entries,'scope':'Existing W5 snapshots only; not source publication verification',
        'production':'HOLD','trade_authorization':'NONE'}
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='entries'}))
    if not entries or any(x['status']!='PASS' for x in entries):raise SystemExit(1)


if __name__=='__main__':audit(*sys.argv[1:])

import json
import hashlib
import csv
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_existing_history import audit
from replay import digest


def fixture(tmp):
    p=tmp/'TEST.csv';p.write_text('Date,Close,Dividends,Stock Splits\n2020-01-01,10,0,0\n2020-01-02,5,0.2,2\n')
    rows=list(csv.DictReader(p.read_text().splitlines()));h=digest(rows)
    meta={'history_digest':h,'symbol':'TEST','artifact_written_at':'2020-01-03T00:00:00Z',
          'fetch_completed_at':'2020-01-02T23:00:00Z','split_basis_verified':None}
    (tmp/'TEST.csv.result.json').write_text(json.dumps({'history_digest':h,'source_metadata':meta,'source_history':rows}))
    (tmp/'TEST.family_context.json').write_text(json.dumps({'technical_source':{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}))
    return p


def test_distinct_file_and_row_hashes_and_historical_gaps(tmp_path):
    fixture(tmp_path);out=tmp_path/'audit.json';audit(tmp_path,out)
    row=json.loads(out.read_text())['entries'][0]
    assert row['status']=='PASS' and row['sha256']!=row['canonical_history_sha256']
    assert row['historical_readiness']=='OPEN'
    assert len(row['split_events'])==len(row['dividend_events'])==1


def test_corrupted_csv_fails_with_explicit_evidence(tmp_path):
    p=fixture(tmp_path);p.write_text(p.read_text().replace('2020-01-02,5','2020-01-02,6'))
    out=tmp_path/'audit.json'
    with pytest.raises(SystemExit):audit(tmp_path,out)
    issues=json.loads(out.read_text())['entries'][0]['issues']
    assert 'RAW_FILE_HASH_MISMATCH' in issues and 'CANONICAL_HISTORY_MISMATCH' in issues


def test_empty_input_does_not_pass(tmp_path):
    with pytest.raises(SystemExit):audit(tmp_path,tmp_path/'audit.json')

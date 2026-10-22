"""Check collector JSON, heterogeneous CSV rows and Markdown as one output set."""
import csv,json,argparse
from pathlib import Path

def validate_outputs(folder):
    root=Path(folder)
    report=json.loads((root/'18_macro_verification.json').read_text())
    with (root/'18_macro_verification.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);rows=list(reader);fields=reader.fieldnames
    items=report['items']
    if len(rows)!=len(items) or {r['id'] for r in rows}!=set(items):raise ValueError('CSV row set mismatch')
    expected_fields=set().union(*(set(r) for r in items.values()))
    if set(fields)!=expected_fields:raise ValueError('CSV fields mismatch')
    markdown=(root/'18_macro_report.md').read_text()
    for r in rows:
        item=items[r['id']]
        for key in fields:
            value=item.get(key)
            if isinstance(value,(dict,list)):
                if json.loads(r[key])!=value:raise ValueError('CSV diagnostic mismatch: '+key)
            elif r[key]!=('' if value is None else str(value)):
                raise ValueError('CSV scalar mismatch: '+key)
        if '| '+r['id']+' |' not in markdown:raise ValueError('report row missing')
        error=str(item.get('error') or '').replace('|',';').replace('\n',' ')
        if error and error not in markdown:raise ValueError('report error missing')
    return len(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args()
    print('JSON/CSV/report PASS:',validate_outputs(a.folder),'rows')

"""Verify actual checkout bytes for all 40 managed source resources."""
import json
from pathlib import Path
from source_resources import validate_source_catalog, verified_source_bytes, VerifiedPrincipal

if __name__ == '__main__':
    base=Path(__file__).resolve().parent
    root=base.parents[2]
    catalog=json.loads((base/'B05_SOURCE_CATALOG.json').read_text())
    inventory=json.loads((base/'B03_ACCESS_INVENTORY.json').read_text())
    policies=json.loads((base/'source_policies.json').read_text())
    rows=validate_source_catalog(catalog,inventory,policies)
    count=0
    for row in rows.values():
        if row['category']=='readonly_resource':
            verified_source_bytes(row,policies,VerifiedPrincipal('service:family-runtime',1),'read',0,(root/row['path']).read_bytes())
            count+=1
    print(f'{len(rows)} inventory entries; {count} source byte hashes PASS')

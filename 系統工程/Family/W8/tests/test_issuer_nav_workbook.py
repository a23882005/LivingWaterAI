from hashlib import sha256
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5')]
from holdings_analysis import read_issuer_facts
import issuer_nav_workbook as workbook


def test_original_issuer_workbook_is_read_only_with_its_own_listing_and_cutoff(tmp_path, monkeypatch):
    path = tmp_path/'fund.xlsx'
    path.write_bytes(b'workbook fixture')
    monkeypatch.setattr(workbook, 'xlsx_rows', lambda *_: {
        4: {'A':'Vanguard FTSE All-World UCITS ETF (USD) Accumulating'},
        9: {'A':'Date','B':'NAV (USD)','C':'Market price (GBP)'},
        10: {'A':'20 Nov 2026','B':'US$172.9725','C':'£133.5200'},
        11: {'A':'30 Sept 2026','B':'US$169.00','C':'£130.00'},
    })
    source = {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
              'available_at':'2026-11-21T17:00:00Z',
              'source_url':'https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating'}
    assert read_issuer_facts({'nav_workbook':source},'VWRA','2026-11-21T16:59:59Z') is None
    facts = read_issuer_facts({'nav_workbook':source},'VWRA','2026-11-21T17:00:00Z')
    assert facts['metrics']=={} and 'nav_redemption_status' not in facts
    observed = facts['issuer_nav_table']
    assert observed['latest_observations'][0]=={'source_row':10,'observed_date':'2026-11-20',
        'fund_nav_usd':'172.9725','market_price_reference_gbp':'133.5200'}
    assert observed['first_observed_date']=='2026-09-30'
    assert not observed['creation_redemption_flows_verified']
    with pytest.raises(PermissionError,match='IDENTITY_OR_BYTES'):
        workbook.read(source,'NATO','2026-11-21T17:00:00Z')
    path.write_bytes(b'tampered')
    with pytest.raises(PermissionError,match='IDENTITY_OR_BYTES'):
        workbook.read(source,'VWRA','2026-11-21T17:00:00Z')

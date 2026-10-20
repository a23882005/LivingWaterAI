import hashlib
import sqlite3
import pytest
from family_input import TABLES, read_snapshot, InputError

def make_db(path):
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE family_member_identity(client_id TEXT)')
        c.execute("INSERT INTO family_member_identity VALUES ('TEST')")
        for table in TABLES:
            c.execute('CREATE TABLE '+table+'(client_id TEXT, value TEXT)')
        c.execute("INSERT INTO cash_balance_snapshot VALUES ('TEST',NULL)")

def test_read_preserves_null_and_source(tmp_path):
    p=tmp_path/'a.db';make_db(p);before=p.read_bytes()
    r=read_snapshot(p,expected_client_id='TEST')
    assert r['tables']['cash_balance_snapshot'][0]['value'] is None
    assert p.read_bytes()==before
    assert r['source_sha256']==hashlib.sha256(before).hexdigest()

def test_identity_checked_before_return(tmp_path):
    p=tmp_path/'a.db';make_db(p)
    with pytest.raises(InputError,match='CLIENT_MISMATCH'):read_snapshot(p,expected_client_id='OTHER')

def test_contaminated_table_rejected(tmp_path):
    p=tmp_path/'a.db';make_db(p)
    with sqlite3.connect(p) as c:c.execute("INSERT INTO portfolio_account VALUES ('OTHER','1')")
    with pytest.raises(InputError,match='CROSS_CLIENT'):read_snapshot(p,expected_client_id='TEST')

def test_schema_error_not_empty_holdings(tmp_path):
    p=tmp_path/'a.db';make_db(p)
    with sqlite3.connect(p) as c:c.execute('DROP TABLE portfolio_position')
    with pytest.raises(InputError,match='SCHEMA_MISSING'):read_snapshot(p,expected_client_id='TEST')

def test_missing_db_not_created(tmp_path):
    p=tmp_path/'missing.db'
    with pytest.raises(FileNotFoundError):read_snapshot(p,expected_client_id='TEST')
    assert not p.exists()

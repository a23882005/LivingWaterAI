"""Data-free unit tests; production-schema tests are kept private."""
import copy
import sqlite3
import unittest
from confirmed_asset_facts import append_confirmed_asset_facts, read_latest_confirmed_asset_facts

COLUMNS = {'family_member_identity': [('client_id', 'TEXT'), ('member_slot', 'INTEGER'), ('family_alias', 'TEXT'), ('family_alias_key', 'TEXT'), ('display_name', 'TEXT'), ('display_name_state', 'TEXT'), ('member_status', 'TEXT'), ('identity_evidence_state', 'TEXT'), ('identity_source', 'TEXT'), ('identity_source_file_id', 'TEXT'), ('origin_db_sha256', 'TEXT'), ('created_at_utc', 'TEXT'), ('updated_at_utc', 'TEXT')], 'portfolio_account': [('client_id', 'TEXT'), ('account_key', 'TEXT'), ('account_label', 'TEXT'), ('account_currency', 'TEXT'), ('account_state', 'TEXT'), ('source_kind', 'TEXT'), ('source_reference', 'TEXT'), ('as_of_utc', 'TEXT'), ('created_at_utc', 'TEXT')], 'portfolio_instrument': [('client_id', 'TEXT'), ('instrument_key', 'TEXT'), ('instrument_type', 'TEXT'), ('ticker', 'TEXT'), ('exchange_code', 'TEXT'), ('isin', 'TEXT'), ('instrument_label', 'TEXT'), ('quote_currency', 'TEXT'), ('identity_state', 'TEXT'), ('source_kind', 'TEXT'), ('source_reference', 'TEXT'), ('as_of_utc', 'TEXT'), ('created_at_utc', 'TEXT')], 'cash_account_scope': [('client_id', 'TEXT'), ('account_key', 'TEXT'), ('currency_code', 'TEXT'), ('account_currency_state', 'TEXT'), ('source_kind', 'TEXT'), ('source_reference', 'TEXT'), ('created_at_utc', 'TEXT')], 'currency_registry': [('currency_code', 'TEXT'), ('minor_digits', 'INTEGER'), ('source_reference', 'TEXT'), ('verified_at_utc', 'TEXT'), ('data_state', 'TEXT')], 'portfolio_snapshot_run': [('client_id', 'TEXT'), ('run_id', 'TEXT'), ('as_of_utc', 'TEXT'), ('version_no', 'INTEGER'), ('run_state', 'TEXT'), ('data_state', 'TEXT'), ('source_kind', 'TEXT'), ('source_reference', 'TEXT'), ('created_at_utc', 'TEXT'), ('sealed_at_utc', 'TEXT'), ('content_hash', 'TEXT')], 'portfolio_snapshot_item': [('client_id', 'TEXT'), ('run_id', 'TEXT'), ('item_no', 'INTEGER'), ('domain_code', 'TEXT'), ('entity_key', 'TEXT'), ('field_key', 'TEXT'), ('value_state', 'TEXT'), ('value_type', 'TEXT'), ('value_text', 'TEXT'), ('value_integer_minor', 'INTEGER'), ('unit', 'TEXT'), ('currency_code', 'TEXT'), ('source_row_key', 'TEXT'), ('source_observed_at_utc', 'TEXT'), ('source_kind', 'TEXT'), ('source_reference', 'TEXT'), ('recorded_at_utc', 'TEXT')], 'portfolio_snapshot_lineage': [('client_id', 'TEXT'), ('run_id', 'TEXT'), ('item_no', 'INTEGER'), ('origin_domain', 'TEXT'), ('origin_record_key', 'TEXT'), ('origin_effective_at_utc', 'TEXT'), ('origin_received_at_utc', 'TEXT'), ('origin_record_version', 'TEXT'), ('origin_source_reference', 'TEXT'), ('origin_evidence_state', 'TEXT')], 'portfolio_position': [('client_id', 'TEXT'), ('account_key', 'TEXT'), ('instrument_key', 'TEXT'), ('as_of_utc', 'TEXT'), ('quantity_decimal', 'TEXT'), ('cost_state', 'TEXT'), ('cost_basis_total_decimal', 'TEXT'), ('cost_per_unit_decimal', 'TEXT'), ('cost_currency', 'TEXT'), ('cost_source_kind', 'TEXT'), ('cost_source_reference', 'TEXT'), ('position_source_kind', 'TEXT'), ('position_source_reference', 'TEXT'), ('recorded_at_utc', 'TEXT')]}

def fixture(client='synthetic_member'):
    db=sqlite3.connect(':memory:')
    for table,columns in COLUMNS.items():
        db.execute('CREATE TABLE '+table+' ('+','.join('"'+key+'" '+kind for key,kind in columns)+')')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('INSERT INTO family_member_identity (client_id) VALUES (?)',(client,))
    db.execute("INSERT INTO portfolio_account (client_id,account_key) VALUES (?,'TEST_ACCOUNT')",(client,))
    db.execute("INSERT INTO portfolio_instrument (client_id,instrument_key,quote_currency) VALUES (?,'TEST_STOCK','TWD')",(client,))
    db.execute("INSERT INTO cash_account_scope (client_id,account_key,currency_code) VALUES (?,'TEST_ACCOUNT','TWD')",(client,))
    db.execute("INSERT INTO currency_registry (currency_code,minor_digits) VALUES ('TWD',2)")
    db.execute("INSERT INTO portfolio_snapshot_run (client_id,run_id,as_of_utc,version_no,run_state,source_kind) VALUES (?,'TEST_BASE','2020-01-01T00:00:00Z',1,'SEALED','OWNER_VERIFIED')",(client,))
    db.execute("INSERT INTO portfolio_position (client_id,account_key,instrument_key,as_of_utc,quantity_decimal) VALUES (?,'TEST_ACCOUNT','TEST_STOCK','2020-01-01T00:00:00Z','2')",(client,))
    return db

def payload():
    return dict(confirmed=True,request_id='synthetic-request-1',source_reference='Synthetic unit test only',as_of_utc='2020-01-03T00:00:00Z',account_key='TEST_ACCOUNT',instrument_key='TEST_STOCK',quantity='2',cost_per_unit='5',currency='TWD',investable_cash='10',long_term_stock_weight='0.6',long_term_bond_weight='0.4',quote=dict(price='6',currency='TWD',observed_date='2020-01-02',observation_precision='TRADING_DATE_ONLY',retrieved_at_utc='2020-01-02T12:00:00Z',kind='CLOSE',url='https://example.com/synthetic-quote'))

class SyntheticTests(unittest.TestCase):
    def test_four_independent_tenants(self):
        for member in ('synthetic_a','synthetic_b','synthetic_c','synthetic_d'):
            with self.subTest(member=member):
                db=fixture(member)
                try:
                    r=append_confirmed_asset_facts(db,member,payload())
                    self.assertEqual(r['position_cost_total'],'10');self.assertEqual(r['market_value'],'12')
                    self.assertFalse(r['persisted']);self.assertEqual(r['trade_authorization'],'NONE')
                    self.assertEqual(db.execute('SELECT DISTINCT client_id FROM portfolio_snapshot_item').fetchall(),[(member,)])
                finally:db.close()
    def test_date_only_never_invents_timestamp(self):
        db=fixture()
        try:
            r=append_confirmed_asset_facts(db,'synthetic_member',payload())
            self.assertEqual(db.execute("SELECT source_observed_at_utc FROM portfolio_snapshot_item WHERE run_id=? AND field_key='reference_market_value_twd'",(r['run_id'],)).fetchone(),(None,))
        finally:db.close()
    def test_repeated_request_and_conflict(self):
        db=fixture()
        try:
            append_confirmed_asset_facts(db,'synthetic_member',payload())
            self.assertEqual(append_confirmed_asset_facts(db,'synthetic_member',payload())['status'],'LOCAL_ALREADY_PREPARED')
            changed=payload();changed['quantity']='3'
            with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):append_confirmed_asset_facts(db,'synthetic_member',changed)
        finally:db.close()
    def test_latest_reader(self):
        db=fixture()
        try:
            result=append_confirmed_asset_facts(db,'synthetic_member',payload())
            current=read_latest_confirmed_asset_facts(db,'synthetic_member')
            self.assertEqual(current['run_id'],result['run_id'])
            self.assertEqual(dict((x['field_key'],x['value_text']) for x in current['fields'])['reference_market_value_twd'],'12')
            self.assertFalse(current['cash_ledger_verified'])
        finally:db.close()
    def test_wrong_identity(self):
        db=fixture()
        try:
            with self.assertRaisesRegex(ValueError,'IDENTITY'):append_confirmed_asset_facts(db,'wrong_member',payload())
        finally:db.close()
    def test_cash_not_settlement(self):
        db=fixture()
        try:
            r=append_confirmed_asset_facts(db,'synthetic_member',payload());self.assertEqual(r['cash_ledger_state'],'UNCHANGED')
            self.assertEqual(db.execute("SELECT value_text FROM portfolio_snapshot_item WHERE run_id=? AND field_key='investable_confirmation_basis'",(r['run_id'],)).fetchone()[0],'OWNER_CONFIRMED_NOT_BROKER_RECONCILIATION')
        finally:db.close()
if __name__=='__main__':unittest.main()

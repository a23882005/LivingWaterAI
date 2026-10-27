"""Accepted source selection, source boundaries and immutable private snapshots."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from datetime import datetime, timezone
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('holdings_projection_test', HERE.parent/'W5/official_holdings_source.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
sys.path.insert(0,str(HERE.parent/'W5'))


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.client = 'fam_' + 'a'*32
        self.tables = {'portfolio_instrument': [
            {'client_id': self.client, 'instrument_key': 'VT_KEY', 'ticker': 'VT', 'quote_currency': 'USD'}],
            'portfolio_position': [
                {'client_id': self.client, 'instrument_key': 'VT_KEY', 'account_key': 'IB',
                 'quantity_decimal': '1.00', 'as_of_utc': '2026-09-01T00:00:00Z'}],
            'portfolio_snapshot_run': [], 'portfolio_snapshot_item': []}

    def run_source(self, run='SOURCE', kind='W6', at='2026-10-20T00:00:00Z'):
        self.tables['portfolio_snapshot_run'].append({'client_id': self.client,
            'run_id': run, 'run_state': 'SEALED', 'source_kind': 'AUTHORIZED_IMPORT',
            'as_of_utc': at, 'version_no': 1})
        item = {'client_id': self.client, 'run_id': run, 'item_no': 1,
            'domain_code': 'W6_ACCEPTED_SOURCE' if kind == 'W6' else 'OWNER_SCREENSHOT_SOURCE',
            'field_key': 'accepted_W6_broker_holdings_json' if kind == 'W6' else 'quantity',
            'entity_key': 'ADBE', 'value_state': 'KNOWN', 'value_text':
                json.dumps([{'symbol': 'VT', 'quantity': '2.3000', 'broker_label': 'IB', 'currency': 'USD'},
                    {'symbol': 'USD_CASH', 'quantity': '5.10', 'broker_label': 'IB', 'currency': 'USD'}])
                if kind == 'W6' else '3.2500', 'source_observed_at_utc': None}
        self.tables['portfolio_snapshot_item'].append(item)
        return item

    def snapshot(self):
        return {'client_id': self.client, 'source_sha256': 'a'*64,
                'tables': self.tables, 'payload_digest': M._digest(self.tables)}

    def build(self):
        return M.project_official_holdings(self.snapshot(), evaluation_at='2026-10-27T00:00:00Z')

    def test_source_supersedes_ledger_without_addition_and_cash_is_separate(self):
        self.run_source();before = deepcopy(self.tables);out = self.build()
        self.assertEqual(len(out['analysis_security_positions']), 1)
        self.assertEqual(out['analysis_security_positions'][0]['quantity'], '2.3000')
        self.assertEqual(out['ledger_positions'][0]['quantity'], '1.00')
        self.assertEqual(out['ledger_only_positions'], [])
        self.assertEqual(out['cash_sources'][0]['symbol'], 'USD_CASH')
        self.assertEqual(out['cash_sources'][0]['settlement_state'], 'UNKNOWN')
        self.assertIsNone(out['analysis_security_positions'][0]['observed_at'])
        self.assertEqual(self.tables, before)

    def test_missing_registry_does_not_discard_screenshot_position(self):
        self.run_source(kind='SCREENSHOT');out = self.build()
        self.assertEqual(out['source_symbols_missing_from_instrument_registry'], ['ADBE'])
        self.assertEqual(out['analysis_security_positions'][0]['quantity'], '3.2500')
        self.assertIsNone(out['analysis_security_positions'][0]['instrument_key'])
        self.assertEqual(out['ledger_only_positions'][0]['symbol'], 'VT')

    def test_newer_unrelated_sealed_run_cannot_erase_holdings(self):
        self.run_source()
        self.tables['portfolio_snapshot_run'].append({'client_id': self.client,
            'run_id': 'NEW_PROFILE', 'run_state': 'SEALED', 'source_kind': 'OWNER_VERIFIED',
            'as_of_utc': '2026-10-26T00:00:00Z', 'version_no': 2})
        self.assertEqual(self.build()['analysis_security_positions'][0]['quantity'], '2.3000')

    def test_ambiguous_runs_and_cross_family_rows_are_rejected(self):
        self.run_source();self.run_source(run='TIE')
        with self.assertRaisesRegex(ValueError, 'RUN_AMBIGUOUS'):self.build()
        self.tables['portfolio_snapshot_run'].pop()
        self.tables['portfolio_snapshot_item'].pop()
        self.tables['portfolio_snapshot_item'][0]['client_id'] = 'OTHER'
        with self.assertRaisesRegex(PermissionError, 'CLIENT_MISMATCH'):self.build()

    def test_duplicate_source_position_and_invalid_quantity_are_rejected(self):
        item = self.run_source();rows = json.loads(item['value_text']);rows.append(rows[0])
        item['value_text'] = json.dumps(rows)
        with self.assertRaisesRegex(ValueError, 'POSITION_AMBIGUOUS'):self.build()
        for value in ('NaN', '-1', True):
            rows[0]['quantity'] = value;item['value_text'] = json.dumps(rows[:2])
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'QUANTITY_INVALID'):self.build()

    def test_future_and_hypothetical_intakes_are_excluded(self):
        self.run_source(at='2027-01-01T00:00:00Z')
        self.assertEqual(self.build()['analysis_security_positions'], [])
        self.tables['portfolio_snapshot_run'][0].update(
            as_of_utc='2026-10-20T00:00:00Z', source_kind='USER_HYPOTHETICAL')
        self.assertEqual(self.build()['analysis_security_positions'], [])

    def test_different_source_layers_are_not_added(self):
        self.run_source();item = self.run_source(run='SCREEN', kind='SCREENSHOT')
        item['entity_key'] = 'VT';out = self.build()
        self.assertEqual(out['source_layer_conflicts'], ['VT'])
        self.assertEqual(len(out['analysis_security_positions']), 2)

    def test_unknown_cash_is_not_zero_or_settled(self):
        self.run_source(kind='SCREENSHOT')
        for field in ('cash_balance', 'settled_cash', 'reserved_cash'):
            self.tables['portfolio_snapshot_item'].append({'client_id': self.client,
                'run_id': 'SOURCE', 'field_key': field, 'domain_code': 'OWNER_SCREENSHOT_SOURCE',
                'value_state': 'KNOWN' if field == 'cash_balance' else 'UNKNOWN',
                'value_text': '55.10' if field == 'cash_balance' else None})
        out = self.build();cash = {r['field']: r for r in out['cash_sources']}
        self.assertEqual(cash['cash_balance']['value'], '55.10')
        self.assertIsNone(cash['settled_cash']['value'])
        self.assertIsNone(cash['reserved_cash']['value'])
        self.assertFalse(out['cash_settlement_asserted'])

    def bound_positions(self):
        snapshot=self.snapshot();decision={'source_reference':'SYNTHETIC_OWNER_ACCEPTANCE'}
        acceptance={'client_id':self.client,'source_db_sha256':'a'*64,
            'snapshot_digest':snapshot['payload_digest'],'owner_decision':decision,
            'owner_decision_digest':M._digest(decision)}
        scope={'owner':{'client_id':self.client,'account':'IB','broker':'IBKR'},
            'source_snapshot_digest':snapshot['payload_digest']}
        return M.build_official_position_view(snapshot,'IB',
            datetime(2026,10,27,tzinfo=timezone.utc),acceptance,scope)

    def test_native_position_view_uses_source_quantity_and_keeps_unknown_date(self):
        self.run_source();positions=self.bound_positions()
        self.assertEqual(len(positions),1)
        self.assertEqual(positions[0]['quantity'],'2.3000')
        self.assertIsNone(positions[0]['source_position']['as_of_utc'])
        self.assertEqual(positions[0]['source_position']['received_at_utc'],'2026-10-20T00:00:00Z')
        from stock_source_bridge import bind_stock_source
        self.tables.update({k:[] for k in ('universe_membership','universe_confirmation',
            'permission_policy','permission_confirmation','holding_policy_proposal','holding_policy_confirmation')})
        mapping={'instrument_key':'VT_KEY','asset_id':'VT','account_key':'IB',
            'native_owner':{'account':'NATIVE_IB'},'source_reference':'SYNTHETIC_BOUND_SOURCE'}
        req={'client_id':self.client,'client_snapshot':{'payload':self.snapshot()},
            'owner':{'account':'IB','currency':'USD'},'evaluation_at':'2026-10-27T00:00:00Z',
            'native_bundle':{'stock_request':{'asset_context':{'asset':{'asset_id':'VT'},
                'confirmed_position_snapshot':{'quantity':'2.3000'}}},
                'stock_evidence':{'asset_id':'VT','exchange':None,'currency':'USD'}}}
        bound=bind_stock_source(req,SimpleNamespace(payload={'positions':positions}),
            {'stock_instrument':mapping,'native_owner':mapping['native_owner']})
        self.assertEqual(bound['confirmed_quantity'],'2.3000')
        self.assertEqual(bound['policy']['holding_policy'],'UNKNOWN')
        self.assertFalse(bound['policy']['new_buy_candidate'])

    def test_source_broker_category_cannot_pull_in_taiwan_positions(self):
        item=self.run_source();rows=json.loads(item['value_text'])
        rows.append({'symbol':'0050','quantity':'1000','broker_label':'截圖台灣券商','currency':'TWD'})
        item['value_text']=json.dumps(rows)
        self.assertEqual([r['source_instrument']['ticker'] for r in self.bound_positions()],['VT'])

    def test_screenshot_identity_comes_from_source_without_registry_or_exchange_guess(self):
        self.run_source(kind='SCREENSHOT')
        self.tables['portfolio_snapshot_item'].extend([
            {'client_id':self.client,'run_id':'SOURCE','domain_code':'OWNER_SCREENSHOT_SOURCE',
             'entity_key':'IB_SCREEN','field_key':'broker_account_number','value_state':'UNKNOWN'},
            {'client_id':self.client,'run_id':'SOURCE','domain_code':'OWNER_SCREENSHOT_SOURCE',
             'entity_key':'ADBE','field_key':'last_price_displayed','value_state':'KNOWN',
             'value_text':'100.12','currency_code':'USD','unit':'USD_PER_SHARE'}])
        positions=self.bound_positions();instrument=positions[0]['source_instrument']
        self.assertEqual(instrument['ticker'],'ADBE')
        self.assertEqual(instrument['quote_currency'],'USD')
        self.assertIsNone(instrument['exchange_code'])
        self.assertEqual(instrument['identity_state'],'SOURCE_SYMBOL_ONLY')


if __name__ == '__main__':unittest.main()

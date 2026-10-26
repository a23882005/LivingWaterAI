"""W8 transaction projection regression: all synthetic, no customer data."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "post_trade_state.py"
SPEC = importlib.util.spec_from_file_location("family_post_trade_state", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class CurrentPositions(unittest.TestCase):
    def sources(self, quantity="0", when="2026-10-26T00:00:00Z", state="SEALED"):
        return {
            "portfolio_position": [{
                "client_id": "fam_test", "account_key": "MAIN", "instrument_key": "VT",
                "as_of_utc": "2026-10-25T00:00:00Z", "quantity_decimal": "8",
                "cost_state": "UNKNOWN", "position_source_reference": "fixture"}],
            "portfolio_snapshot_run": [{"run_id": "test-run", "run_state": state}],
            "portfolio_snapshot_item": [{
                "run_id": "test-run", "domain_code": MOD.DOMAIN,
                "entity_key": "MAIN|VT", "field_key": "quantity_decimal",
                "value_state": "KNOWN", "value_text": quantity,
                "source_observed_at_utc": when, "source_reference": "fixture"}],
        }

    def test_all_sold_removes_current_but_history_remains(self):
        tables = self.sources()
        self.assertEqual(MOD.effective_positions(tables), [])
        self.assertEqual(len(tables["portfolio_position"]), 1)

    def test_partial_post_trade_quantity(self):
        rows = MOD.effective_positions(self.sources(quantity="3.5"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity_decimal"], "3.5")

    def test_old_close_does_not_override_newer_real_position(self):
        rows = MOD.effective_positions(self.sources(when="2026-10-24T00:00:00Z"))
        self.assertEqual(rows[0]["quantity_decimal"], "8")

    def test_unsealed_pending_rows_are_not_current(self):
        rows = MOD.effective_positions(self.sources(state="DRAFT"))
        self.assertEqual(rows[0]["quantity_decimal"], "8")

    def test_wrong_entity_key_rejected(self):
        tables = self.sources()
        tables["portfolio_snapshot_item"][0]["entity_key"] = "invalid"
        with self.assertRaises(ValueError):
            MOD.effective_positions(tables)

    def test_unconfirmed_input_rejected(self):
        with self.assertRaises(ValueError):
            MOD.append_post_trade(None, "fam_test", "e", {"owner_confirmed": False}, "2026-10-26T00:00:00Z")

if __name__ == "__main__":
    unittest.main()

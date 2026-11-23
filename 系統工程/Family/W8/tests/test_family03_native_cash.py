"""Protect the full-account denominator when a menu 03 target retains native cash."""
import sys
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[3] / "C-配置決策引擎＋Mentor整合" / "正式Runtime"
sys.path.insert(0, str(RUNTIME))
from work3.cash_position import is_native_cash
from work3.engine import _validate_allocation
from work4.engine import _aggregate_positions


class NativeCashTests(unittest.TestCase):
    def setUp(self):
        self.weight = dict(value_state="KNOWN", unit="portfolio_weight", data_quality="OK",
                           freshness="FRESH", source_reference_ids=["ACCOUNT"], value=1.0)
        self.cash = dict(instrument_id="CASH_TWD", ticker=None, base_currency="TWD", asset_type="現金",
                         source_reference_ids=["ACCOUNT"], weight=dict(self.weight, value=0.05), value_state="KNOWN")
        security = dict(self.cash, ticker="EXAMPLE", instrument_id="ETF_EXAMPLE", asset_type="ETF",
                        weight=dict(self.weight, value=0.95))
        self.allocation = dict(allocation_id="test", stage="PROPOSED", declared_total_weight=self.weight,
                               source_reference_ids=["ACCOUNT"], positions=[security,self.cash],
                               denominator=dict(self.weight, currency="TWD", amount=1000))
        self.assets = {"EXAMPLE":dict(ticker="EXAMPLE",base_currency="TWD")}

    def test_income_is_not_inferred_and_cash_is_not_redistributed(self):
        issues = []
        ok, positions, total = _validate_allocation(self.allocation, {"assets":list(self.assets.values())}, issues)
        self.assertTrue(ok, issues)
        self.assertEqual(([p["weight"]["value"] for p in positions],total),([0.95,0.05],1))
        ok, securities, total, denominator, _ = _aggregate_positions(self.allocation,self.assets,issues)
        self.assertTrue(ok, issues)
        self.assertEqual(([p["weight"] for p in securities],total,denominator),([0.95],1,1000))

    def test_unidentified_security_currency_and_source_still_block(self):
        for change in [dict(asset_type="ETF"),dict(instrument_id="unknown"),dict(base_currency="USD"),
                       dict(source_reference_ids=[]),dict(ticker="UNKNOWN"),
                       dict(weight=dict(self.cash["weight"], freshness="STALE"))]:
            with self.subTest(change=change):
                row = dict(self.cash,**change)
                self.assertFalse(is_native_cash(row,"TWD"))
                allocation = dict(self.allocation, positions=[self.allocation["positions"][0],row])
                self.assertFalse(_aggregate_positions(allocation,self.assets,[])[0])
                self.assertFalse(_validate_allocation(allocation,{"assets":list(self.assets.values())},[])[0])

    def test_cash_amount_must_agree_with_account(self):
        self.cash["portfolio_amount"] = dict(value_state="KNOWN",currency="TWD",amount=500)
        issues = []
        self.assertFalse(_aggregate_positions(self.allocation,self.assets,issues)[0])
        self.assertIn("C_POSITION_AMOUNT_WEIGHT_CONFLICT", [i["code"] for i in issues])

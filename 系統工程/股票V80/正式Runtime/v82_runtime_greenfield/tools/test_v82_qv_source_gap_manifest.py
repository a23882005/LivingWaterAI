import json
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
P=HERE/'v82_qv_source_gap_manifest_20261031.json'

class QVGapManifestTests(unittest.TestCase):
    def setUp(self):
        self.m=json.loads(P.read_text(encoding='utf-8'))
        self.items=self.m['items']

    def test_exact_fifteen_assets(self):
        expected={'0050','NATO','VALU','VWRA','VT','PPH','QQQ','SOXX','IUCS','VDC','GOOGL','MSFT','NVDA','AVGO','ZTS'}
        self.assertEqual(set(self.items),expected)

    def test_no_numeric_qv_is_invented(self):
        for symbol,item in self.items.items():
            self.assertEqual(item['qv_status'],'UNKNOWN',symbol)
            self.assertNotIn('qV',item,symbol)
            self.assertTrue(item['reason'],symbol)

    def test_named_v10_routes_keep_primary_metric(self):
        expected={
            '0050':('TAIWAN_LARGE_CAP_ETF','FORWARD_PE'),
            'NATO':('DEFENSE_MILITARY_ETF','FORWARD_PE'),
            'VWRA':('GLOBAL_EQUITY_ETF','FORWARD_PE'),
            'VT':('GLOBAL_EQUITY_ETF','FORWARD_PE'),
            'PPH':('PHARMA_HEALTHCARE_ETF','FORWARD_PE'),
            'QQQ':('TECH_AI_HIGH_GROWTH_ETF','FORWARD_PE'),
            'SOXX':('SEMICONDUCTOR_ETF','FORWARD_PE'),
        }
        for symbol,(cls,metric) in expected.items():
            self.assertEqual(self.items[symbol]['formal_class'],cls)
            self.assertEqual(self.items[symbol]['primary_metric'],metric)

    def test_sector_etfs_require_subtype_registry(self):
        for symbol in ('IUCS','VDC'):
            x=self.items[symbol]
            self.assertEqual(x['formal_class'],'SECTOR_THEME_ETF')
            self.assertEqual(x['sector_or_theme'],'CONSUMER_STAPLES')
            self.assertEqual(x['primary_metric'],'UNKNOWN_PENDING_SUBTYPE_REGISTRY')
            self.assertEqual(x['reason'],'VALUATION_SUBTYPE_REGISTRY_REQUIRED')

    def test_individual_stocks_do_not_guess_profile(self):
        for symbol in ('GOOGL','MSFT','NVDA','AVGO','ZTS'):
            x=self.items[symbol]
            self.assertEqual(x['class_status'],'ROUTE_EVIDENCE_REQUIRED')
            self.assertEqual(x['formal_class'],'UNKNOWN_PENDING_PROFILE_OWNER')
            self.assertEqual(x['reason'],'FORMAL_PROFILE_ROUTE_REQUIRED')

    def test_valu_identity_is_global_equity_but_history_under_two_years(self):
        x=self.items['VALU']
        self.assertEqual(x['formal_class'],'GLOBAL_EQUITY_ETF')
        self.assertEqual(x['primary_metric'],'FORWARD_PE')
        self.assertEqual(x['reason'],'HISTORY_SPAN_UNDER_TWO_YEARS')

if __name__=='__main__':
    unittest.main(verbosity=2)

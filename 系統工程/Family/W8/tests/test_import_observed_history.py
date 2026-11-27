"""Public table import keeps exact prices, source identity and completed dates."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from import_observed_history import parse_displayed_history


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.document={'symbol':'SYN','source_url':'https://stockanalysis.com/stocks/syn/history/',
            'extracted_text':'L1: NASDAQ: SYN · Real-Time Price · USD\n'
            'L2: Oct 27, 2026 | 10 | 12 | 9 | 11 | 10.5 | 0% | 1,000\n'
            'L3: Oct 26, 2026 | 9 | 11 | 8 | 10 | 9.5 | 0% | 2,000\n'}
        self.when='2026-10-27T17:00:00Z'

    def test_forming_day_excluded_and_unadjusted_and_adjusted_values_separate(self):
        before=deepcopy(self.document)
        rows,metadata=parse_displayed_history(self.document,self.when)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['Date'],'2026-10-26')
        self.assertEqual(rows[0]['Close'],'10');self.assertEqual(rows[0]['Adj Close'],'9.5')
        self.assertEqual(rows[0]['Volume'],'2000')
        self.assertEqual(metadata['excluded_rows'][0]['reason'],'FORMING_OR_FUTURE_BAR')
        self.assertEqual(self.document,before)

    def test_url_symbol_and_market_currency_mismatch_rejected(self):
        for key,value in [('symbol','OTHER'),('source_url','https://stockanalysis.com/stocks/other/history/')]:
            doc={**self.document,key:value}
            with self.assertRaises(ValueError):parse_displayed_history(doc,self.when)
        doc=deepcopy(self.document);doc['extracted_text']=doc['extracted_text'].replace('USD','EUR')
        with self.assertRaises(ValueError):parse_displayed_history(doc,self.when)

    def test_duplicate_date_is_not_silently_overwritten(self):
        self.document['extracted_text']+='L4: Oct 26, 2026 | 8 | 11 | 7 | 9 | 8 | 0% | 500\n'
        with self.assertRaisesRegex(ValueError,'DUPLICATE_DATE'):
            parse_displayed_history(self.document,self.when)

    def test_london_conflicting_currency_label_is_preserved(self):
        self.document['source_url']='https://stockanalysis.com/quote/lon/SYN/history/'
        self.document['extracted_text']=self.document['extracted_text'].replace(
            'NASDAQ: SYN · Real-Time Price · USD','LON:SYN Currency is GBP · Price in USD')
        _,meta=parse_displayed_history(self.document,self.when)
        self.assertTrue(meta['provider_currency_label_conflict']);self.assertEqual(meta['currency'],'USD')
        self.assertFalse(meta['formal_deployment_eligible'])


if __name__=='__main__':unittest.main()

"""Exact, dated INDEX/MMFI fallback regression tests."""
import datetime as dt
import importlib.util
import pathlib
import unittest
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("refresh_v703_predeploy",ROOT/"scripts/refresh_v703_predeploy.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NY=ZoneInfo('America/New_York')
CLOSED=dt.datetime(2026,11,2,18,0,tzinfo=NY)
ACTIVE=dt.datetime(2026,11,2,13,30,tzinfo=NY)

def page(symbol="INDEX, MMFI: Percent of Stocks Above 50-Day Average",
         recent="02 Nov 26 47.22 48.08 45.97 48.04 0"):
    return f"""<h3>{symbol}</h3>
      <div>LAST: 40.90</div>
      <h3>RECENT END OF DAY PRICES</h3>
      <table><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th></tr>
      <tr><td>{recent}</td></tr>
      <tr><td>30 Oct 26</td><td>44.11</td><td>44.24</td><td>40.05</td><td>41.56</td><td>0</td></tr>
      </table><h3>SYMBOL HISTORY</h3>""".encode('utf8')


class MMFIFallbackTests(unittest.TestCase):
    def test_uses_dated_close_not_intraday_last(self):
        value,date=mod.parse_mmfi_eod(page(),dt.date(2026,11,3),CLOSED)
        self.assertEqual((value,date),(48.04,"2026-11-02"))
    def test_symbol_is_exact_index_mmfi(self):
        with self.assertRaisesRegex(ValueError,"INDEX/MMFI"):
            mod.parse_mmfi_eod(page(symbol="S&P500 Above 50 Day MA"),dt.date(2026,11,3),CLOSED)
    def test_future_date_rejected(self):
        with self.assertRaisesRegex(ValueError,"future date"):
            mod.parse_mmfi_eod(page(),dt.date(2026,11,1),CLOSED)
    def test_outside_high_low_rejected(self):
        with self.assertRaisesRegex(ValueError,"high/low"):
            mod.parse_mmfi_eod(page(recent="02 Nov 26 47.22 48.08 45.97 39.00 0"),dt.date(2026,11,3),CLOSED)
    def test_incomplete_date_rejected(self):
        with self.assertRaisesRegex(ValueError,"complete OHLC"):
            mod.parse_mmfi_eod(page(recent="02 Nov 26 47.22 48.08"),dt.date(2026,11,3),CLOSED)


    def test_intraday_nyse_row_uses_prior_completed_close(self):
        value,date=mod.parse_mmfi_eod(page(),dt.date(2026,11,3),ACTIVE)
        self.assertEqual((value,date),(41.56,"2026-10-30"))
    def test_same_day_after_nyse_close_uses_latest(self):
        value,date=mod.parse_mmfi_eod(page(),dt.date(2026,11,3),CLOSED)
        self.assertEqual((value,date),(48.04,"2026-11-02"))


if __name__=="__main__":
    unittest.main()

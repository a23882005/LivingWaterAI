"""Offline regression checks for the production 16-item macro collector."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch
import pandas as pd

BASE=pathlib.Path(__file__).resolve().parents[1]
FILE=BASE/"系統工程"/"總經V70"/"總經爬蟲程式16項.py"
spec=importlib.util.spec_from_file_location("macro16",FILE)
macro=importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)

class MacroRegression(unittest.TestCase):
    def test_sahm_stable(self):
        class Source:
            fredsources={"UNRATE":("BLS","https://api.bls.gov/publicAPI/v2/timeseries/data/")}
            def fred(self, key):
                self.assert_key=key
                return pd.Series([4.0]*18,index=pd.date_range("2025-01-01",periods=18,freq="MS"))
        result=macro.sahm_from_unrate(Source())
        self.assertEqual(result["value"],0.0)
        self.assertEqual(result["status"],"OK")
        self.assertIn("api.bls.gov",result["source_url"])

    def test_cpi_same_calendar_month(self):
        class Source:
            fredsources={"CPILFESL":("BLS","https://api.bls.gov")}
            def fred(self,key):
                return pd.Series([300,315],index=pd.to_datetime(["2025-09-01","2026-09-15"]))
        r=macro.core_cpi(Source())
        self.assertEqual(r["value"],5.0)
        self.assertEqual(r["observation_date"],"2026-09-15")

    def test_breakeven_calculation(self):
        with patch.object(macro,"treasury_breakeven") as mocked:
            mocked.return_value=macro.row("m13",2.4,"2026-10-13","https://home.treasury.gov","matched rates")
            r=macro.breakeven_5y(object())
            self.assertEqual(r["value"],2.4)
            mocked.assert_called_once()

    def test_cpi_provider_without_provenance(self):
        class BareProvider:
            def fred(self,key):
                return pd.Series([300,315],index=pd.to_datetime(["2025-09-01","2026-09-01"]))
        r=macro.core_cpi(BareProvider())
        self.assertEqual(r["value"],5.0)

    def test_future_date_rejected(self):
        import datetime as dt
        future=(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()+dt.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            macro.row("m07",20,future,"https://cdn.cboe.com","test")
if __name__=="__main__":
    unittest.main()

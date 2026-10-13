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

    def test_sahm_gapped_months(self):
        class GappedSource:
            fredsources={"UNRATE":("BLS","https://api.bls.gov/publicAPI/v2/timeseries/data/")}
            def fred(self,key):
                if key=="UNRATE":
                    dates=pd.date_range("2025-01-01",periods=18,freq="MS")
                    return pd.Series([4.0]*17,index=dates.delete(7))
                raise ValueError("Sahm source missing")
        with self.assertRaises(RuntimeError) as ctx:
            macro.sahm_from_unrate(GappedSource())
        self.assertIn("2025-08",str(ctx.exception))

    def test_sahm_shutdown_gap_official(self):
        class Gap:
            fredsources={"UNRATE":("BLS","https://api.bls.gov/")}
            def fred(self,key):
                if key!="UNRATE": raise RuntimeError("unavailable")
                dates=pd.date_range("2025-07-01",periods=15,freq="MS")
                dates=dates[dates.to_period("M")!=pd.Period("2025-10")]
                return pd.Series([4.0]*len(dates),index=dates)
        with self.assertRaises(ValueError) as ctx:
            macro.sahm_from_unrate(Gap())
        self.assertIn("2025-10 CPS not collected per BLS",str(ctx.exception))

    def test_recent_unemployment_survives_history_gap(self):
        """Latest U3 must remain usable even if Sahm lacks historical months."""
        class Response:
            def raise_for_status(self): pass
            def json(self):
                dates=pd.date_range("2026-07-01",periods=3,freq="MS")
                return {"status":"REQUEST_SUCCEEDED","Results":{"series":[{
                    "seriesID":"LNS14000000",
                    "data":[{"year":str(d.year),"period":"M%02d"%d.month,
                             "value":"4.0"} for d in dates]}]}}
        class FakeSession:
            def post(self,url,**kwargs): return Response()
        source=macro.Fetcher()
        source.s=FakeSession()
        series=source.fred("UNRATE")
        self.assertEqual(len(series),3)
        self.assertEqual(source.fredsources["UNRATE"][0],"BLS_HISTORY_V2")

    def test_official_fred_api_parses_hy_oas_and_hides_key(self):
        class FakeResponse:
            def raise_for_status(self): pass
            def json(self):
                return {"observations":[{"date":"2026-10-13","value":"3.25"}]}
        class FakeSession:
            def get(self,url,**kwargs):
                self.url=url
                return FakeResponse()
        source=macro.Fetcher()
        source.s=FakeSession()
        with patch.dict("os.environ",{"FRED_API_KEY":"test_secret_key"}):
            series=source.fred("BAMLH0A0HYM2")
        self.assertAlmostEqual(float(series.iloc[-1]),3.25)
        self.assertEqual(source.fredsources["BAMLH0A0HYM2"][0],"FRED_OFFICIAL_API")
        self.assertNotIn("test_secret_key",source.fredsources["BAMLH0A0HYM2"][1])
        self.assertIn("observation_start=",source.s.url)
        self.assertIn("BAMLH0A0HYM2",source.s.url)


    def test_invalid_mirror_removed(self):
        class Session:
            def __init__(self): self.urls=[]
            def get(self,url,**kwargs):
                self.urls.append(url)
                raise RuntimeError("unavailable")
        f=macro.Fetcher()
        f.s=Session()
        with patch.dict("os.environ",{"FRED_API_KEY":""}):
            with self.assertRaises(RuntimeError): f.fred("BAMLH0A0HYM2")
        self.assertEqual(len(f.s.urls),1)

    def test_future_date_rejected(self):
        import datetime as dt
        future=(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()+dt.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            macro.row("m07",20,future,"https://cdn.cboe.com","test")
if __name__=="__main__":
    unittest.main()

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

    def test_mmfi_live_adapter_accepts_verified_dated_quote(self):
        import datetime as dt
        from unittest.mock import Mock
        stamp=int(dt.datetime.now(dt.timezone.utc).timestamp())-86400
        payload={"chart":{"error":None,"result":[{
            "meta":{"symbol":"$MMFI","longName":"NYSE Percent of Stocks Above 50-Day Moving Average"},
            "timestamp":[stamp],
            "indicators":{"quote":[{"close":[56.4]}]}
        }]}}
        response=Mock()
        response.raise_for_status.return_value=None
        response.json.return_value=payload
        session=Mock()
        session.get.return_value=response
        source=Mock(s=session,timeout=12)
        observed=macro.fetch_mmfi_market_breadth(source)
        self.assertEqual(observed["status"],"OK")
        self.assertEqual(observed["value"],56.4)
        self.assertIsNotNone(observed["observation_date"])

    def test_mmfi_rejects_unverified_instrument(self):
        import datetime as dt
        from unittest.mock import Mock
        stamp=int(dt.datetime.now(dt.timezone.utc).timestamp())-86400
        response=Mock()
        response.raise_for_status.return_value=None
        response.json.return_value={"chart":{"result":[{
            "meta":{"symbol":"MMFI","longName":"Generic Momentum Fund"},
            "timestamp":[stamp],"indicators":{"quote":[{"close":[56.4]}]}
        }]}}
        source=Mock(s=Mock(get=Mock(return_value=response)),timeout=12)
        with self.assertRaisesRegex(ValueError,"identity"):
            macro.fetch_mmfi_market_breadth(source)


    def test_mmfi_barchart_official_index(self):
        from unittest.mock import Mock
        import datetime as dt
        date=(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1)).isoformat()
        response=Mock()
        response.raise_for_status.return_value=None
        response.json.return_value={"status":{"code":200},"results":[
            {"symbol":"$MMFI","tradingDay":date,"close":62.5},
            {"symbol":"$MOFI","tradingDay":date,"close":99.0}
        ]}
        source=Mock(s=Mock(get=Mock(return_value=response)),timeout=12)
        with patch.dict("os.environ",{"BARCHART_ONDEMAND_API_KEY":"test-only"}):
            result=macro.fetch_mmfi_barchart_history(source)
        self.assertEqual(result["value"],62.5)
        self.assertEqual(result["observation_date"],date)

    def test_mmfi_barchart_requires_api_key(self):
        from unittest.mock import Mock
        with patch.dict("os.environ",{"BARCHART_ONDEMAND_API_KEY":""}):
            with self.assertRaisesRegex(ValueError,"absent"):
                macro.fetch_mmfi_barchart_history(Mock())


    def test_etf_candidate_numeric_kept_separate_from_verified_data(self):
        from unittest.mock import Mock
        source=Mock()
        ticker=Mock()
        ticker.get_info.return_value={"trailingPE":23.7}
        with patch("yfinance.Ticker",return_value=ticker):
            with self.assertRaisesRegex(ValueError,"methodology unverified"):
                macro.fetch_etf_valuation_candidate(source,"SPY","m03_spy")
        self.assertEqual(source.etf_candidates["SPY"]["candidate_trailing_pe"],23.7)
        self.assertEqual(source.etf_candidates["SPY"]["validation"],
                         "UNVERIFIED: retrieval time is not valuation date")


    def test_23_independent_macro_fields_accounting(self):
        self.assertEqual(len(macro.LABELS),24)
        self.assertIn("m07",macro.LABELS)
        self.assertIn("s03",macro.LABELS)
        ids=[key for key in macro.LABELS if key!="s03"]
        self.assertEqual(len(ids),23)
        # Neither output schema nor source VIX values are silently deleted.
        self.assertIn("s03",macro.LABELS)


    def test_spy_issuer_index_pe_is_dated_but_not_promoted_to_fund_pe(self):
        from unittest.mock import Mock
        import datetime as dt
        today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
        date=today.strftime("%b %d %Y")
        response=Mock()
        response.raise_for_status.return_value=None
        response.text=("<h2>Index Characteristics as of "+date+"</h2>"
                       "<div>Price/Earnings 25.21 Price/Earnings Ratio FY1 21.39</div>")
        source=Mock(s=Mock(get=Mock(return_value=response)),timeout=12)
        result=macro.probe_spy_issuer_index_pe(source)
        self.assertEqual(result["candidate_index_pe"],25.21)
        self.assertIn("INDEX_PROXY_ONLY",result["validation"])

if __name__=="__main__":
    unittest.main()

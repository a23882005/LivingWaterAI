"""Regression cases for role budgets, the six common periods, and sparse history."""
import sys
from datetime import date,timedelta
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import equity_sleeve as calc
import family03_plans as plans


class ThreePlans(unittest.TestCase):
    def test_dates_are_intersected_across_all_six(self):
        portfolios=[plans.blank() for _ in range(3)]
        for p,k in zip(portfolios,("A","B","C")):
            p["layers"]["主軸"]={k:100}
        data={s:("USD",{(date(2024,1,1)+timedelta(days=i)).isoformat():100+i/100
                        for i in range(n,500)}) for n,s in enumerate(("VT","VOO","QQQ","A","B","C"))}
        rows=plans.six(portfolios,data,[],calc)
        self.assertEqual(len(rows),6)
        self.assertEqual({r["歷史試算"]["共同觀察筆數"] for r in rows},{495})
        del data["B"]
        self.assertTrue(all("B" in r["歷史試算"]["缺行情"] for r in plans.six(portfolios,data,[],calc)))
    def test_short_history_and_direct_exposure(self):
        prices={"短期":("USD",{"2026-01-05":100,"2026-01-06":90})}
        h=calc.simulate({"短期":100},prices)
        self.assertAlmostEqual(h["期間報酬率"],-.1)
        self.assertNotIn("年化報酬率",h)
        rows=calc.direct_exposures({"ZTS","PAWZ"},{"ZTS"},[])
        self.assertAlmostEqual(calc.exposure({"ZTS":5,"PAWZ":10},rows)["共同曝險"][0]["已知合計百分點"],5.999)
    def test_fx_uses_same_date_and_correct_direction(self):
        data={"TW":("TWD",{"a":300,"b":310}),"US":("USD",{"a":10,"b":11})}
        fx=lambda _:{"USDTWD":("TWD_PER_USD",{"a":30})}
        self.assertEqual(calc.common_currency(data,fx)["TW"],("USD",{"a":10}))
    def test_each_range_covers_each_allowed_percentage_once(self):
        for limit in range(101):
            self.assertEqual([v for a,b in plans.available_bands(limit).values() for v in range(a,b+1)],list(range(limit+1)))

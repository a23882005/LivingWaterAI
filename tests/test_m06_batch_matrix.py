"""Deterministic m06 scenario matrix; no network, CME scraping or credentials."""
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('m06_batch',ROOT/'scripts'/'probe_m06_fedwatch_free.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def feed(day,meeting,levels):
    return {'target_source':'fred','trade_date':day,'current_target':'3.75%-4.00%',
            'meetings':[{'date':meeting,'probabilities':levels}]}

class BatchQA(unittest.TestCase):
    def test_51_weighted_distributions(self):
        today=dt.date(2026,10,14)
        for pct in range(101):
            with self.subTest(pct=pct):
                p={'3.75%-4.00%':pct,'4.00%-4.25%':100-pct}
                r=m.calculate(feed('2026-10-13','2027-10-27',p),today)
                self.assertAlmostEqual(r['m06_expected_rate_change_quarters'],(100-pct)/100,places=4)
                self.assertEqual(r['as_of_settlement'],'2026-10-13')
    def test_9_trade_date_freshness_cases(self):
        today=dt.date(2026,10,14)
        for age in (0,1,2,3,4,5,6,7,-1):
            day=today-dt.timedelta(days=age)
            horizon=day+dt.timedelta(days=365)
            p=feed(day.isoformat(),horizon.isoformat(),{'3.75%-4.00%':100})
            with self.subTest(age=age):
                if 0<=age<=5:
                    self.assertEqual(m.calculate(p,today)['status'],'CANDIDATE_NEEDS_REVIEW')
                else:
                    with self.assertRaises(ValueError):
                        m.calculate(p,today)
    def test_14_probability_mass_cases(self):
        day=dt.date(2026,10,14)
        for total in (0,1,90,95,99,99.49,99.5,99.9,100,100.1,100.5,100.51,101,110):
            with self.subTest(total=total):
                p=feed('2026-10-13','2027-10-27',
                       {'3.75%-4.00%':total/2,'4.00%-4.25%':total/2})
                if 99.5<=total<=100.5:
                    self.assertEqual(m.calculate(p,day)['status'],'CANDIDATE_NEEDS_REVIEW')
                else:
                    with self.assertRaises(ValueError):
                        m.calculate(p,day)
    def test_frozen_now_example_math_only(self):
        ps=[.5,6.1,21.2,32.5,25.6,11.1,2.6,.3]
        levels=[f'{3.75+0.25*i:.2f}%-{4.0+0.25*i:.2f}%' for i in range(8)]
        result=m.calculate(feed('2026-10-14','2027-10-27',dict(zip(levels,ps))),
                           dt.date(2026,10,14))
        self.assertAlmostEqual(result['m06_expected_rate_change_quarters'],3.2192,places=4)
        self.assertEqual(result['days_from_12m_target_to_meeting'],13)

if __name__=='__main__': unittest.main()

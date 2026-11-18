import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from scripts import macro_official_direct as direct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('official_macro18', ROOT/'系統工程/總經V70/總經爬蟲18項.py')
macro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)
DAY = dt.date(2026, 11, 11)


def h41(unit='1000000', duplicate=False, omit=False):
    content = '<Data>'
    for key, name in direct.NAMES.items():
        if omit and key == 'WDTGAL':
            continue
        attrs = dict(SERIES_NAME=name, FREQ='19', SERIESTYPE='L', UNIT='Currency',
                     UNIT_MULT=unit, CURRENCY='USD', DISTRIBUTION='TOTC' if key=='WALCL' else 'TOT')
        body = '<Series '+ ' '.join(f'{k}="{v}"' for k,v in attrs.items())+'>'
        for date, value in [('2026-08-12', '6759955' if key=='WALCL' else '959405'),
                            ('2026-11-11', '6758867' if key=='WALCL' else '912134')]:
            body += f'<Obs TIME_PERIOD="{date}" OBS_VALUE="{value}" OBS_STATUS="A"/>'
        body += '</Series>'
        content += body + (body if duplicate else '')
    content += '</Data>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('H41_data.xml', content)
    return out.getvalue()


def operation(amount=725000000):
    return dict(operationId='RP TEST', operationDate='2026-08-12', settlementDate='2026-08-12',
                maturityDate='2026-08-13', operationType='Reverse Repo', term='Overnight',
                auctionStatus='Results', totalAmtAccepted=amount,
                details=[dict(securityType='Treasury', amtAccepted=amount)])


def rawops(op):
    return json.dumps({'repo': {'operations': op}}).encode()


class OfficialDirectTests(unittest.TestCase):
    def test_h41_exact_series_and_original_units(self):
        r=direct.parsed_h41(h41(),DAY)
        self.assertEqual(float(r['WALCL']['values'][DAY]),6758867)
        self.assertEqual(float(r['WDTGAL']['values'][DAY]),912134)

    def test_h41_rejects_weekly_average_or_unit_drift(self):
        with self.assertRaises(ValueError):direct.parsed_h41(h41(unit='1000000000'),DAY)

    def test_h41_rejects_duplicate_series(self):
        with self.assertRaises(ValueError):direct.parsed_h41(h41(duplicate=True),DAY)

    def test_h41_rejects_missing_tga(self):
        with self.assertRaises(ValueError):direct.parsed_h41(h41(omit=True),DAY)

    def rrp(self,ops):
        with patch.object(direct.holiday,'open_day',return_value=True),patch.object(direct.holiday,'next_open',return_value=dt.date(2026,8,13)):
            return direct.normal_rrp(dt.date(2026,8,12),rawops(ops),b'test calendar')

    def test_normal_rrp_preserves_billions(self):
        self.assertEqual(float(self.rrp([operation()])),.725)

    def test_explicit_zero_result_valid_but_empty_is_unknown(self):
        self.assertEqual(self.rrp([operation(0)]),0)
        with self.assertRaises(ValueError):self.rrp([])

    def test_rrp_wrong_amount_and_tenor_rejected(self):
        o=operation();o['totalAmtAccepted']=1
        with self.assertRaises(ValueError):self.rrp([o])
        o=operation();o['term']='Term'
        with self.assertRaises(ValueError):self.rrp([o])

    def test_netliq_91_days_and_approved_holiday_helper(self):
        def get(url,**kwargs):
            raw=h41() if url==direct.H41 else b'calendar' if url==direct.holiday.HOLIDAYS else rawops([operation()])
            return SimpleNamespace(content=raw,url=url,raise_for_status=lambda:None)
        f=SimpleNamespace(s=SimpleNamespace(get=get),timeout=5)
        with patch.object(direct.holiday,'open_day',side_effect=lambda d,c:d!=DAY),patch.object(direct.holiday,'next_open',return_value=dt.date(2026,8,13)),patch.object(direct.holiday,'fetch_holiday',return_value={'value_usd_bn':.152,'kind':'HOLIDAY_OUTSTANDING_DERIVED'}) as holiday:
            value,date,ev=direct.netliq(f,today=dt.date(2026,11,18))
        self.assertAlmostEqual(value,46.756);self.assertEqual(date,'2026-11-11')
        self.assertEqual(ev['begin'],'2026-08-12');holiday.assert_called_once_with(f,DAY)

    def test_netliq_official_failure_keeps_original_legacy(self):
        with patch.object(direct,'netliq',side_effect=ValueError('official down')),patch.object(macro,'netliq_legacy',return_value={'value':46.756}) as backup:
            r=macro.netliq(object());self.assertEqual(r['value'],46.756);backup.assert_called_once()

    def test_treasury_matches_dates_and_month_baseline(self):
        def get(url,**kwargs):
            text='Date,5-Year\n10/16/2026,4.37\n11/17/2026,4.26\n' if 'type=daily_treasury_yield_curve' in url else 'Date,5-Year\n10/16/2026,2.00\n11/17/2026,2.00\n'
            return SimpleNamespace(text=text,content=text.encode(),url=url,raise_for_status=lambda:None)
        f=SimpleNamespace(s=SimpleNamespace(get=get),timeout=5)
        self.assertAlmostEqual(macro.treasury_breakeven(f,'m13')['value'],2.26)
        r=macro.treasury_breakeven(f,'m17');self.assertAlmostEqual(r['value'],-.11)
        self.assertEqual(r['source_evidence']['legs']['begin']['date'],'2026-10-16')

    def test_treasury_cross_year_loads_prior_year_baseline(self):
        class Fixed(dt.datetime):
            @classmethod
            def now(cls,tz=None):return cls(2027,1,8,tzinfo=dt.timezone.utc)
        def get(url,**kwargs):
            date='12/07/2026' if '/2026/' in url else '01/07/2027'
            val='4.37' if '/2026/' in url else '4.26'
            text=f'Date,5-Year\n{date},{val if "type=daily_treasury_yield_curve" in url else "2.00"}\n'
            return SimpleNamespace(text=text,content=text.encode(),url=url,raise_for_status=lambda:None)
        f=SimpleNamespace(s=SimpleNamespace(get=get),timeout=5)
        with patch.object(macro.dt,'datetime',Fixed):r=macro.treasury_breakeven(f,'m17')
        self.assertAlmostEqual(r['value'],-.11);self.assertEqual(len(r['source_evidence']['sources']),4)

    def test_treasury_mismatched_dates_rejected(self):
        def get(url,**kwargs):
            date='11/17/2026' if 'type=daily_treasury_yield_curve' in url else '11/16/2026'
            text=f'Date,5-Year\n{date},2.00\n'
            return SimpleNamespace(text=text,content=text.encode(),url=url,raise_for_status=lambda:None)
        with self.assertRaises(ValueError):macro.treasury_breakeven(SimpleNamespace(s=SimpleNamespace(get=get),timeout=5),'m13')

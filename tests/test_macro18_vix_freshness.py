"""Regression: VIX close must belong to the latest completed XNYS session.

This is a source-quality check only: no changes to V70 scoring, CAP or trading.
"""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / '系統工程/總經V70/總經爬蟲18項.py'
spec = importlib.util.spec_from_file_location('macro18_vix_freshness', SOURCE)
macro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(macro)


class Response:
    status_code = 200
    headers = {'Content-Type': 'text/csv'}

    def __init__(self, body='', payload=None):
        self.text = body
        self.content = body.encode('utf-8')
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def vix_chart(observation_date='2026-11-05', value=28.18, symbol='^VIX'):
    # Use 16:00 New York time (21:00 UTC in November), not UTC midnight.
    date = dt.date.fromisoformat(observation_date)
    timestamp = int(dt.datetime(
        date.year, date.month, date.day, 21, 0, tzinfo=dt.timezone.utc).timestamp())
    return {'chart': {'result': [{
        'meta': {'symbol': symbol}, 'timestamp': [timestamp],
        'indicators': {'quote': [{'close': [value]}]},
    }]}}


class VixFreshnessTests(unittest.TestCase):
    def test_expected_us_close_after_ny_close_not_taipei_date(self):
        clock = lambda y,m,d,h,minute=0: dt.datetime(
            y,m,d,h,minute,tzinfo=dt.timezone.utc)
        self.assertEqual(macro.last_completed_vix_session(clock(2026,11,5,21,29)),
                         dt.date(2026,11,4))
        self.assertEqual(macro.last_completed_vix_session(clock(2026,11,5,21,30)),
                         dt.date(2026,11,5))
        self.assertEqual(macro.last_completed_vix_session(clock(2026,11,6,3)),
                         dt.date(2026,11,5))
        self.assertEqual(macro.last_completed_vix_session(clock(2026,11,8,15)),
                         dt.date(2026,11,6))

    def test_holiday_and_early_close(self):
        clock = lambda h,minute: dt.datetime(
            2026,11,27,h,minute,tzinfo=dt.timezone.utc)
        # Thanksgiving Nov 26 is closed; Black Friday Nov 27 closes 13:00 NY.
        self.assertEqual(macro.last_completed_vix_session(clock(18,29)),
                         dt.date(2026,11,25))
        self.assertEqual(macro.last_completed_vix_session(clock(18,30)),
                         dt.date(2026,11,27))

    def test_cboe_fresh_wins_even_with_fred_key(self):
        f = macro.Fetcher()
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            if 'cdn.cboe.com' in url:
                return Response('DATE,CLOSE\n11/04/2026,16.61\n11/05/2026,28.18\n')
            raise AssertionError('Cboe fresh: fallback should not be fetched')

        f.s.get = get
        with patch.object(macro, 'last_completed_vix_session',
                          return_value=dt.date(2026,11,5)), \
             patch.dict(macro.os.environ, {'FRED_API_KEY': 'test-only'}):
            observed = f.fred('VIXCLS')
        self.assertAlmostEqual(float(observed.iloc[-1]), 28.18)
        self.assertEqual(str(observed.index[-1].date()), '2026-11-05')
        self.assertEqual(f.fredsources['VIXCLS'][0], 'CBOE_OFFICIAL_VIX')
        self.assertEqual(len(calls), 1)

    def test_stale_cboe_falls_back_to_fresh_yahoo_before_fred(self):
        f = macro.Fetcher()
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            if 'cdn.cboe.com' in url:
                return Response('DATE,CLOSE\n11/04/2026,16.61\n')
            if 'query1.finance.yahoo.com' in url:
                return Response(payload=vix_chart())
            raise AssertionError('Fresh Yahoo should be selected before FRED')

        f.s.get = get
        with patch.object(macro, 'last_completed_vix_session',
                          return_value=dt.date(2026,11,5)), \
             patch.dict(macro.os.environ, {'FRED_API_KEY': 'test-only'}):
            observed = f.fred('VIXCLS')
        self.assertAlmostEqual(float(observed.iloc[-1]), 28.18)
        self.assertEqual(str(observed.index[-1].date()), '2026-11-05')
        self.assertEqual(f.fredsources['VIXCLS'][0], 'YAHOO_VIX_CHART')
        self.assertEqual([x['result'] for x in f.fredattempts['VIXCLS']],
                         ['FAILED', 'OK'])
        self.assertIn('VIX_LAGGED_SESSION', f.fredattempts['VIXCLS'][0]['error'])
        self.assertEqual(len(calls), 2)

    def test_all_sources_lag_fail_closed_instead_of_old_ok(self):
        f = macro.Fetcher()

        def get(url, **kwargs):
            if 'cdn.cboe.com' in url:
                return Response('DATE,CLOSE\n11/04/2026,16.61\n')
            if 'query1.finance.yahoo.com' in url:
                return Response(payload=vix_chart('2026-11-04', 16.61))
            if 'api.stlouisfed.org' in url:
                return Response(payload={'observations': [
                    {'date': '2026-11-04', 'value': '16.61'}]})
            return Response('DATE,VIXCLS\n2026-11-04,16.61\n')

        f.s.get = get
        with patch.object(macro, 'last_completed_vix_session',
                          return_value=dt.date(2026,11,5)), \
             patch.dict(macro.os.environ, {'FRED_API_KEY': 'test-only'}):
            with self.assertRaisesRegex(RuntimeError, 'All FRED sources failed'):
                f.fred('VIXCLS')
        self.assertNotIn('VIXCLS', f.fredcache)
        # An old but valid quote advances to the next source without retry.
        self.assertEqual(len(f.fredattempts['VIXCLS']), 4)
        self.assertEqual([a['provider'] for a in f.fredattempts['VIXCLS'][:2]],
                         ['CBOE_OFFICIAL_VIX', 'YAHOO_VIX_CHART'])
        self.assertTrue(all(x['result'] == 'FAILED'
                            for x in f.fredattempts['VIXCLS']))

    def test_yahoo_ignores_unfinished_current_session_candle(self):
        f = macro.Fetcher()
        # Cboe is unavailable; Yahoo includes the last completed session and
        # an intraday next-session candle. Do not mistake it for a later close.
        d5 = dt.datetime(2026,11,5,21,tzinfo=dt.timezone.utc)
        d6 = dt.datetime(2026,11,6,18,tzinfo=dt.timezone.utc)
        chart = {'chart': {'result': [{
            'meta': {'symbol': '^VIX'},
            'timestamp': [int(d5.timestamp()), int(d6.timestamp())],
            'indicators': {'quote': [{'close': [28.18, 25.1]}]},
        }]}}
        def get(url, **kwargs):
            if 'cdn.cboe.com' in url:
                return Response('DATE,CLOSE\n11/04/2026,16.61\n')
            if 'query1.finance.yahoo.com' in url:
                return Response(payload=chart)
            raise AssertionError('Unexpected fallback')
        f.s.get = get
        with patch.object(macro, 'last_completed_vix_session',
                          return_value=dt.date(2026,11,5)), \
             patch.dict(macro.os.environ, {'FRED_API_KEY': ''}):
            observed = f.fred('VIXCLS')
        self.assertEqual(str(observed.index[-1].date()), '2026-11-05')
        self.assertAlmostEqual(float(observed.iloc[-1]), 28.18)

    def test_yahoo_identity_mismatch_is_rejected(self):
        f = macro.Fetcher()

        def get(url, **kwargs):
            if 'cdn.cboe.com' in url:
                return Response('DATE,CLOSE\n11/04/2026,16.61\n')
            if 'query1.finance.yahoo.com' in url:
                return Response(payload=vix_chart(symbol='^SPX'))
            return Response('DATE,VIXCLS\n2026-11-04,16.61\n')

        f.s.get = get
        with patch.object(macro, 'last_completed_vix_session',
                          return_value=dt.date(2026,11,5)), \
             patch.dict(macro.os.environ, {'FRED_API_KEY': ''}):
            with self.assertRaises(RuntimeError):
                f.fred('VIXCLS')
        self.assertTrue(any('identity mismatch' in x.get('error','')
                            for x in f.fredattempts['VIXCLS']))


if __name__ == '__main__':
    unittest.main()

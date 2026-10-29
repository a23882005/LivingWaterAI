"""Observation periods never stand in for official publication time."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_official_release_inputs as R
import v75_macro_inputs as M


def test_pce_latest_release_remains_current_only_before_its_announced_next_release():
    text=('Personal Income and Outlays, August 2026 '
        'EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026 '
        'Next release: October 29, 2026, at 8:30 a.m. EDT')
    release=R.monthly_release(text,'BEA_PCE');release['source_sha256']='SYNTHETIC'
    assert release['observation_period']=='2026-08-01'
    assert release['release_at']=='2026-09-30T08:30:00-04:00'
    records={'BEA_PCE':release,'BEA_CURRENT':{'current_period':'2026-08-01','current_release_date':'September 30, 2026'}}
    assert R.monthly_freshness(records,'BEA_PCE','2026-08-01','2026-10-29T12:29:59Z')['state']=='FRESH'
    assert R.monthly_freshness(records,'BEA_PCE','2026-08-01','2026-10-29T12:30:00Z')['state']=='STALE'
    assert R.monthly_freshness(records,'BEA_PCE','2026-09-01','2026-10-29T07:00:00Z')['state']=='UNKNOWN'
    records.pop('BEA_CURRENT')
    assert R.monthly_freshness(records,'BEA_PCE','2026-08-01','2026-10-29T07:00:00Z')['state']=='UNKNOWN'


def test_bls_release_metadata_preserves_et_dst_transition():
    text=('8:30 a.m. (ET) Wednesday, October 14, 2026 '
        'CONSUMER PRICE INDEX - SEPTEMBER 2026 '
        'The Consumer Price Index news release for October 2026 is scheduled to be published on Tuesday, '
        'November 10, 2026, at 8:30 a.m. (ET).')
    release=R.monthly_release(text,'BLS_CPI')
    assert release['observation_period']=='2026-09-01'
    assert release['release_at'].endswith('-04:00') and release['next_release_at'].endswith('-05:00')


def test_us_business_window_excludes_declared_holiday_but_not_a_missing_workday():
    days=M.weekdays(date(2026,10,28),20)
    assert date(2026,10,12) not in days and days[-1]==date(2026,9,29)
    values={d:M.number('2.5') for d in days};assert M.window(values,20)==days
    values.pop(date(2026,10,22))
    with pytest.raises(ValueError,match='SESSION_GAP'):M.window(values,20)


def test_policy_strategy_link_is_not_misread_as_an_fomc_rate_statement():
    parser=R.Text();parser.feed('<a href="/newsevents/pressreleases/monetary20250822a.htm">'
        'Statement on Longer-Run Goals and Monetary Policy Strategy</a>'
        '<a href="/newsevents/pressreleases/monetary20261028a.htm">HTML</a>')
    assert parser.html_links==['/newsevents/pressreleases/monetary20261028a.htm']

from datetime import datetime,timezone
import unittest
from market_poll import build_notice
class Tests(unittest.TestCase):
    def test_missing_source_never_formal(self):
        r=build_notice('VT',{},datetime(2026,11,10,tzinfo=timezone.utc),'1','owner/repo')
        self.assertEqual(r['data_status'],'UNKNOWN');self.assertFalse(r['formal_v82_executed'])
        self.assertEqual(r['monitor_status'],'FORMAL_AUTOSTART_BLOCKED_UNKNOWN')
    def test_health_id_stable_within_day(self):
        a=build_notice('VT',{},datetime(2026,11,10,1,tzinfo=timezone.utc),'1','owner/repo')
        b=build_notice('VT',{},datetime(2026,11,10,2,tzinfo=timezone.utc),'2','owner/repo')
        self.assertEqual(a['event_id'],b['event_id'])
    def test_tw_delay_explicit(self):
        r=build_notice('0050.TW',{},datetime(2026,11,10,tzinfo=timezone.utc),'1','owner/repo')
        self.assertEqual(r['delay_seconds'],1200);self.assertEqual(r['notice_kind'],'REFERENCE_ONLY')

class ActivityTests(unittest.TestCase):
    def test_only_original_true_starts(self):
        from market_poll import activity
        self.assertTrue(activity({'status':'OBSERVED_DAILY_FORMULA','runaway_down':'TRUE'}))
        self.assertFalse(activity({'status':'UNKNOWN','runaway_down':'TRUE'}))
        self.assertFalse(activity({'status':'OBSERVED_DAILY_FORMULA','runaway_down':'UNKNOWN'}))
    def test_unknown_never_stops_prior(self):
        from market_poll import activity
        self.assertTrue(activity({'status':'UNKNOWN','runaway_down':'UNKNOWN'},True))
    def test_manual_stop(self):
        from market_poll import activity
        self.assertFalse(activity({'status':'OBSERVED_DAILY_FORMULA','runaway_down':'TRUE'},True,True))

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

class BatchTests(unittest.TestCase):
    def row(self):
        r=build_notice('VT',{},datetime(2026,11,10,1,tzinfo=timezone.utc),'1','owner/repo')
        r.update(quote_time='2026-11-10T00:50:00Z',market_price=150.,data_status='OBSERVED',monitor_status='ACTIVE_OBSERVATION_NOT_BUY')
        return r
    def batch(self,rows):
        from market_poll import build_batch
        return build_batch(rows,datetime(2026,11,10,1,tzinfo=timezone.utc),'1','owner/repo')
    def test_same_data_not_resent_on_poll(self):
        a=self.row();b={**a,'observed_at':'2026-11-10T01:10:00Z','generated_at':'2026-11-10T01:10:00Z','run_id':'2'}
        self.assertEqual(self.batch([a])['event_id'],self.batch([b])['event_id'])
    def test_new_completed_bar_sends_even_same_price(self):
        a=self.row();b={**a,'quote_time':'2026-11-10T01:00:00Z'}
        self.assertNotEqual(self.batch([a])['event_id'],self.batch([b])['event_id'])
    def test_corrected_price_new_state(self):
        a=self.row();b={**a,'market_price':151.}
        self.assertNotEqual(self.batch([a])['event_id'],self.batch([b])['event_id'])
    def test_order_does_not_resend(self):
        a=self.row();b={**a,'symbol':'TSM'}
        self.assertEqual(self.batch([a,b])['event_id'],self.batch([b,a])['event_id'])
    def test_individual_expiry_preserved(self):
        a=self.row();b={**a,'symbol':'TSM','valid_until':'2026-11-10T01:05:00Z'}
        items={i['symbol']:i for i in self.batch([a,b])['items']}
        self.assertNotEqual(items['VT']['valid_until'],items['TSM']['valid_until'])
    def test_nested_private_data_rejected(self):
        from safe_notify import canonical
        with self.assertRaises(ValueError):canonical(self.batch([{**self.row(),'account':'not allowed'}]))
    def test_nested_batch_rejected(self):
        from safe_notify import canonical
        b=self.batch([self.row()]);b['items']=[self.batch([self.row()])]
        with self.assertRaises(ValueError):canonical(b)
    def test_valid_batch_allowed(self):
        from safe_notify import canonical
        self.assertIn('LW_MARKET_BATCH_V1',canonical(self.batch([self.row()])))
    def test_rotation_covers_all_first_positions(self):
        from market_poll import rotated
        symbols=['A','B','C','D'];self.assertEqual({rotated(symbols,n)[0] for n in range(4)},set(symbols))

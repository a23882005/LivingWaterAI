import unittest
from watch_router import route

def s(**kw):
    d=dict(rule_sha256='rule',qualified_formal_daily_input=True,snapshot_id='s1',producer_id='formal-engine',as_of=100,valid_until=200,L_price=False,RunawayDown=False)
    d.update(kw);return d

class Tests(unittest.TestCase):
    def test_left_price_only_observes(self):
        r=route(s(L_price=True),150,'rule');self.assertTrue(r['monitor_active']);self.assertFalse(r['new_buy_permission'])
    def test_runaway_still_observed_not_buy(self):
        r=route(s(RunawayDown=True),150,'rule');self.assertTrue(r['monitor_active']);self.assertFalse(r['new_buy_permission'])
    def test_unknown_not_false_or_start(self):
        self.assertFalse(route(s(L_price=None),150,'rule')['monitor_active'])
        self.assertTrue(route(s(L_price=None),150,'rule',True)['monitor_active'])
    def test_wrong_hash(self):
        self.assertEqual(route(s(L_price=True),150,'other')['reason'],'RULE_VERSION_MISMATCH')
    def test_expired(self):
        self.assertFalse(route(s(L_price=True),200,'rule')['monitor_active'])
    def test_intraday_cannot_impersonate_daily(self):
        self.assertFalse(route(s(L_price=True,qualified_formal_daily_input=False),150,'rule')['monitor_active'])
    def test_no_invented_exit(self):
        r=route(s(),150,'rule',True);self.assertTrue(r['monitor_active']);self.assertEqual(r['reason'],'ACTIVE_UNTIL_MANUAL_STOP')
    def test_manual_stop(self):
        self.assertFalse(route(s(),150,'rule',True,manual_stop=True)['monitor_active'])
    def test_no_provenance(self):
        self.assertFalse(route(s(L_price=True,snapshot_id=''),150,'rule')['monitor_active'])

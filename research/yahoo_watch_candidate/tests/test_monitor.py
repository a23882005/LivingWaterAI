import copy
import unittest
from monitor_core import observe, data_event_id, notification_decision

def payload():
    return {'chart':{'result':[{'meta':{'symbol':'VT','exchangeTimezoneName':'America/New_York'},'timestamp':[1794241800,1794242100], 'indicators':{'quote':[{'open':[100,101],'high':[102,103],'low':[99,100],'close':[101,102],'volume':[20,30]}]}}]}}

class Tests(unittest.TestCase):
    def test_incomplete_excluded(self):
        r=observe(payload(),'VT',1794242200)
        self.assertEqual(r['ohlcv']['close'],101)
    def test_tw_delay(self):
        p=payload();p['chart']['result'][0]['meta'].update(symbol='0050.TW',exchangeTimezoneName='Asia/Taipei')
        self.assertEqual(observe(p,'0050.TW',1794242200,publication_delay_seconds=1200)['data_status'],'UNKNOWN')
    def test_bad_price_not_used(self):
        p=payload(); p['chart']['result'][0]['indicators']['quote'][0]['close']=[500,500]
        self.assertEqual(observe(p,'VT',1794242800)['reason'],'NO_COMPLETE_VALID_BAR')
    def test_missing_not_zero(self):
        p=payload();p['chart']['result'][0]['indicators']['quote'][0]['volume']=[None,None]
        self.assertEqual(observe(p,'VT',1794242800)['data_status'],'UNKNOWN')
    def test_mismatch(self):
        self.assertEqual(observe(payload(),'TWN',1794242800)['reason'],'SYMBOL_MISMATCH')
    def test_malformed(self):
        self.assertEqual(observe({},'VT',1794242800)['data_status'],'UNKNOWN')
    def test_repeated_id_ignores_poll_time(self):
        a=observe(payload(),'VT',1794242800);b=observe(payload(),'VT',1794242900)
        self.assertEqual(data_event_id(a),data_event_id(b))
    def test_disabled(self):
        a=observe(payload(),'VT',1794242800)
        self.assertEqual(notification_decision(a,None,set()),'WATCH_DISABLED')
    def test_no_invented_buy(self):
        a=observe(payload(),'VT',1794242800)
        self.assertFalse(a['executable']);self.assertFalse(a['formal_v82_executed'])
        self.assertEqual(notification_decision(a,a['data_status'],set(),True),'NO_APPROVED_STRATEGY_EVENT')
    def test_dedupe(self):
        a=observe(payload(),'VT',1794242800)
        self.assertEqual(notification_decision(a,None,{data_event_id(a)},True),'DUPLICATE')
    def test_non_aligned_last_point(self):
        p=payload();p['chart']['result'][0]['timestamp']=[1794241801,1794242101]
        self.assertEqual(observe(p,'VT',1794242800)['reason'],'NO_COMPLETE_VALID_BAR')

if __name__=='__main__': unittest.main()

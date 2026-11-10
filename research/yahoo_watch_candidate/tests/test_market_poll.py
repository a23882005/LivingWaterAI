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

class EndToEndBatchTests(unittest.TestCase):
    def test_two_symbols_one_mail_new_data_only(self):
        import copy,contextlib,io,json,os
        from unittest.mock import patch
        import market_poll
        from safe_notify import send_notice as real_send
        class Backend:
            doc={'schema':'PUBLIC_NOTICE_STATE_V1','events':{}}
            version=0
            def __init__(self,**kw):pass
            def read(self):return str(self.version),copy.deepcopy(self.doc)
            def compare_and_swap(self,sha,doc):
                if sha!=str(self.version):raise ValueError('conflict')
                type(self).doc=copy.deepcopy(doc);type(self).version+=1
        messages=[]
        class SMTP:
            def __init__(self,*a,**k):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def login(self,*a):pass
            def send_message(self,msg):messages.append(msg);return {}
        bar=['2026-11-10T00:50:00Z']
        original_build=market_poll.build_notice
        def build(*args):
            r=original_build(*args);r.update(quote_time=bar[0],market_price=150.,data_status='OBSERVED');return r
        def send(report,**kw):return real_send(report,smtp_factory=SMTP,**kw)
        env={'GITHUB_REPOSITORY':'a23882005/LivingWaterAI','GITHUB_REF_NAME':'main','WATCH_SYMBOLS':'VT,TSM',
             'GITHUB_RUN_ID':'fixture','GITHUB_RUN_NUMBER':'1','GITHUB_TOKEN':'synthetic','GMAIL_ADDRESS':'fixture@example.invalid',
             'GMAIL_APP_PASSWORD':'synthetic','V82_ORIGINAL_ROOT':'fixture','STOP_SYMBOLS':''}
        with patch.dict(os.environ,env),patch.object(market_poll,'GithubContentsBackend',Backend),patch.object(market_poll,'observed_rd',return_value={'status':'OBSERVED_DAILY_FORMULA','runaway_down':'TRUE','reason':'SYNTHETIC'}),patch.object(market_poll,'fetch',return_value={}),patch.object(market_poll,'build_notice',side_effect=build),patch.object(market_poll,'send_notice',side_effect=send),contextlib.redirect_stdout(io.StringIO()):
            market_poll.main();market_poll.main();bar[0]='2026-11-10T01:00:00Z';market_poll.main()
        self.assertEqual(len(messages),2)
        for msg in messages:
            payload=json.loads(msg.get_content().split('\n',1)[1]);self.assertEqual(payload['schema'],'LW_MARKET_BATCH_V1');self.assertEqual(len(payload['items']),2)
            self.assertFalse(payload['formal_v82_executed'])

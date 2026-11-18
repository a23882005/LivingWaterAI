"""Formatter regression tests: no SMTP, network, accounts or trading."""
import json
import unittest
from mail_format import compose, JSON_MARKER

RUN = 'https://github.com/a23882005/LivingWaterAI/actions/runs/123'


def row(symbol='0050.TW', status='UNKNOWN', price=None, quote=None, valid=None, session='UNKNOWN', delay=1200):
    return dict(schema='LW_MARKET_NOTICE_V1', event_id='e:'+symbol, symbol=symbol,
                notice_kind='REFERENCE_ONLY', source='Yahoo Finance chart',
                data_status=status, market_price=price, quote_time=quote,
                valid_until=valid, session=session, delay_seconds=delay,
                observed_at='2026-11-18T13:05:00+00:00', formal_v82_executed=False)


def batch(items):
    return dict(schema='LW_MARKET_BATCH_V1', event_id='x', notice_kind='REFERENCE_ONLY',
                generated_at='2026-11-18T13:07:00+00:00', run_id='123', run_url=RUN,
                formal_v82_executed=False, items=items)


class MailFormatTest(unittest.TestCase):
    def compose(self, msg):
        original=json.dumps(msg,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        title, body = compose(msg,original)
        self.assertEqual(json.loads(body.split(JSON_MARKER+'\n',1)[1]),msg)
        return title,body

    def test_missing_price_explicit(self):
        title,body=self.compose(batch([row('0050.TW'),row('SOXX',delay=None)]))
        self.assertTrue(title.startswith('[V82-WATCH]'))
        self.assertIn('無可用行情0/2',title)
        self.assertIn('0050：缺價格／行情時間（UNKNOWN）',body)
        self.assertIn('此信未執行正式V82判斷或交易授權',body)

    def test_old_quote_labeled_stale(self):
        q=row(status='OLD_OBSERVATION_NOT_CURRENT',price=96.4,
              quote='2026-11-17T13:00:00+00:00',
              valid='2026-11-17T13:30:00+00:00',session='RTH')
        title,body=self.compose(batch([q]))
        self.assertIn('無可用行情0/1',title)
        self.assertIn('舊行情，已排除',body)
        self.assertIn('舊報價 96.4',body)

    def test_valid_delayed_quote_labeled_reference_only(self):
        q=row(status='OBSERVED_NOT_REALTIME_CERTIFIED',price=93.55,
              quote='2026-11-18T12:49:00+00:00',
              valid='2026-11-18T13:27:00+00:00',session='RTH')
        title,body=self.compose(batch([q]))
        self.assertIn('參考報價1/1',title)
        self.assertIn('0050：交易時段參考價 93.55元',body)
        self.assertIn('有效至 11/18 21:27',body)
        self.assertIn('未認證即時',body)

    def test_unknown_session_fails_closed(self):
        q=row('VT','OBSERVED_NOT_REALTIME_CERTIFIED',150.3,
              '2026-11-18T13:05:00Z','2026-11-18T13:27:00Z','UNKNOWN',None)
        title,body=self.compose(batch([q]))
        self.assertIn('無可用行情0/1',title)
        self.assertIn('盤別未確認',body)

    def test_expired_at_send_excluded(self):
        q=row('VT','OBSERVED_NOT_REALTIME_CERTIFIED',150.3,
              '2026-11-18T13:05:00Z','2026-11-18T13:07:00Z','POST',None)
        title,body=self.compose(batch([q]))
        self.assertIn('無可用行情0/1',title)
        self.assertIn('已過期',body)

    def test_synthetic_never_market(self):
        q=row('TEST','TEST_ONLY',100,'2026-11-18T13:05:00Z',
              '2026-11-18T13:27:00Z','RTH',None)
        q['notice_kind']='TEST'
        title,body=self.compose(batch([q]))
        self.assertIn('測試通知',title)
        self.assertIn('測試資料，已排除',body)

    def test_single_notice_works(self):
        q=row('SOXX','UNKNOWN')
        q.update(generated_at='2026-11-18T13:07:00Z',run_id='123',run_url=RUN)
        title,body=self.compose(q)
        self.assertIn('SOXX',title)
        self.assertIn(JSON_MARKER,body)

    def test_actionable_alert_uses_direct_next_step_and_preserves_evidence(self):
        q=row('VT','UNKNOWN',None,None,None,'UNKNOWN',None)
        q.update(event_id='rd-daily-action-v1:VT:2026-11-18',
                 generated_at='2026-11-18T13:07:00Z',run_id='123',run_url=RUN,
                 rd_observation='TRUE',daily_session='2026-11-18',
                 monitor_status='ACTIVE_OBSERVATION_NOT_BUY')
        title,body=self.compose(q)
        self.assertIn('日線急跌警戒已觸發',title)
        self.assertIn('請檢查買單',title)
        self.assertIn('已完成：2026-11-18 收盤日線',body)
        self.assertIn('現在請做：核對VT未成交買單的限價、股數、GTC效期及預留資金',body)
        self.assertNotIn('缺價格',body.split(JSON_MARKER,1)[0])
        self.assertNotIn('非買進訊號',title)
        self.assertIn(RUN,body)

    def test_alert_explains_actual_daily_risk_and_keeps_stale_preprice_separate(self):
        q=row('VT','OLD_OBSERVATION_NOT_CURRENT',151.19,
              '2026-11-18T13:50:00+00:00','2026-11-18T14:41:43+00:00','PRE',None)
        q.update(event_id='rd-daily-action-v1:VT:2026-11-17',
                 generated_at='2026-11-18T14:21:43+00:00',run_id='123',run_url=RUN,
                 rd_observation='TRUE',daily_session='2026-11-17',
                 monitor_status='ACTIVE_OBSERVATION_NOT_BUY',
                 daily_close=150.65,daily_previous_close=152.36,
                 daily_low=149.77,daily_change_percent=-1.1223,
                 daily_confirmed_swing_low=151.25,
                 daily_confirmed_swing_session='2026-11-05',
                 rd_break_true_codes='D2',rd_accel_true_codes='A1|A3|A4|A5|A7')
        title, body=self.compose(q)
        self.assertIn('VT｜日線急跌警戒已觸發',title)
        self.assertIn('前收152.36→收150.65美元（-1.71美元，-1.12%）',body)
        self.assertIn('盤中最低149.77美元',body)
        self.assertIn('D2收盤跌破已確認的波段低點',body)
        self.assertIn('跌勢加速已確認5項',body)
        self.assertIn('2026-11-05 151.25美元',body)
        self.assertIn('先暫緩新增VT買單',body)
        self.assertIn('舊報價 151.19，時間 11/18 21:50',body)
        self.assertIn('這是舊值',body)
        self.assertNotIn('前收151.19',body)

    def test_missing_risk_evidence_is_explicit_and_no_intraday_substitute(self):
        q=row('VT','UNKNOWN',151.19,'2026-11-18T13:50:00Z',
              '2026-11-18T14:41:43Z','PRE',None)
        q.update(event_id='rd-daily-action-v1:VT:2026-11-17',
                 generated_at='2026-11-18T14:21:43Z',
                 rd_observation='TRUE',daily_session='2026-11-17',
                 monitor_status='ACTIVE_OBSERVATION_NOT_BUY')
        _, body=self.compose(q)
        self.assertIn('本次警戒JSON未附日線價與跌幅',body)
        self.assertIn('尚缺D1～D3／A1～A8逐票明細',body)
        self.assertNotIn('前收151.19',body)

    def test_large_batch_stays_concise(self):
        title,body=self.compose(batch([row('X'+str(i)) for i in range(60)]))
        self.assertLess(len(title),130)
        self.assertIn('其餘52檔',body)
        self.assertIn('60檔',title)


if __name__ == '__main__':
    unittest.main()

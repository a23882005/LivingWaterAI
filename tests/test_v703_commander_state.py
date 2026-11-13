"""Commander cards must finish blocked states and never retain stale advice."""
import datetime as dt
from test_v703_data_only_frontend import data_only, feed, NOW
import test_v703_snapshot_frontend as snapshot


class CommanderStateTests(snapshot.SnapshotBrowserTests):
    def assert_paused(self, page):
        for name in ('stock', 'bond'):
            text = page.locator('#final-'+name).inner_text()
            self.assertIn('暫停發布', text)
            self.assertNotIn('計算中', text)
            self.assertNotIn('戰術額度', text)
        self.assertFalse(page.evaluate('window.v703CanPublishFormalAllocation()'))
        self.assertIsNone(page.evaluate('window.v703Latest'))

    def test_provisional_mobile_reload(self):
        page=self.open_feed(data_only(), NOW)
        page.set_viewport_size({'width':412,'height':823})
        self.assert_paused(page)
        self.assertIn('CPI 官方年增率缺資料',page.locator('#final-stock').inner_text())
        before=page.evaluate('window.v703ProvisionalSnapshot.mSafe_final')
        for _ in range(2):
            page.evaluate('window.v703ReloadFeed()')
            page.wait_for_function('window.v703DataLoaded===true')
            self.assert_paused(page)
            self.assertEqual(page.evaluate('window.v703ProvisionalSnapshot.mSafe_final'),before)
        page.locator('#final-stock').scroll_into_view_if_needed()
        page.screenshot(path='/tmp/v703_commander_mobile.png')

    def test_valid_to_expired_clears_prior_orders(self):
        page=self.open_feed(feed(), NOW)
        self.assertTrue(page.evaluate('window.v703CanPublishFormalAllocation()'))
        self.assertIn('股票戰術額度',page.locator('#final-stock').inner_text())
        page.clock.set_fixed_time(NOW+dt.timedelta(days=2))
        page.evaluate('window.v703Recompute()')
        self.assert_paused(page)

    def test_valid_to_provisional_then_recovery(self):
        page=self.open_feed(feed(), NOW)
        page.route('**/V70_macro_latest.json',lambda r:r.fulfill(json=data_only()))
        page.evaluate('window.v703ReloadFeed()')
        page.wait_for_function('window.v703DataOnly===true')
        self.assert_paused(page)
        page.route('**/V70_macro_latest.json',lambda r:r.fulfill(json=feed()))
        page.evaluate('window.v703ReloadFeed()')
        page.wait_for_function('window.v703CanPublishFormalAllocation()===true')
        self.assertIn('股票戰術額度',page.locator('#final-stock').inner_text())
        self.assertNotIn('暫停發布',page.locator('#final-bond').inner_text())

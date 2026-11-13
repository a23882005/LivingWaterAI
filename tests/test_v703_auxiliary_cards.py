"""Auxiliary cards must not resurrect old CPI or overwrite the verified macro feed."""
import test_v703_data_only_frontend as base
from test_v703_data_only_frontend import data_only, feed, NOW


class AuxiliaryCardsTests(base.DataOnlyBrowserTests):
    def assert_cards(self, page, cpi_available=False):
        self.assertEqual(page.locator('#bond-score-display').inner_text(), 'NA')
        self.assertEqual(page.locator('#bond-raw').input_value(), '')
        self.assertEqual(page.locator('#bond-real-yield').inner_text(), 'NA')
        self.assertIn('名目 10Y', page.locator('#bond-data-status').inner_text())
        self.assertEqual(page.locator('#bond-cpi-yoy').inner_text() == ': NA', not cpi_available)
        self.assertEqual(page.locator('#cap_bps_m02').inner_text(),
                         str(round(float(page.locator('#in_m02').input_value())*100))+' bps')

    def test_cards_follow_feed_and_repeated_reload(self):
        page=self.open_feed(data_only(), NOW)
        self.assert_cards(page)
        before=page.evaluate('window.v703ProvisionalSnapshot.mSafe_final')
        m14=page.locator('#in_m14').input_value()
        page.evaluate("recalcNetLiquidity(); updateBond('2.64')")
        self.assert_cards(page)
        self.assertEqual(page.locator('#in_m14').input_value(),m14)
        self.assertEqual(page.evaluate('window.v703ProvisionalSnapshot.mSafe_final'),before)
        page.evaluate('window.v703ReloadFeed()')
        self.assert_cards(page)
        page.screenshot(path='/tmp/v70_auxiliary_cards.png',full_page=True)

    def test_cpi_recovery_does_not_substitute_tips_or_change_macro(self):
        page=self.open_feed(feed(), NOW)
        self.assertTrue(page.evaluate('window.v703CanPublishFormalAllocation()'))
        self.assert_cards(page,cpi_available=True)
        self.assertNotEqual(page.locator('#in_m08').input_value(),'')
        self.assertTrue(page.evaluate('Number.isNaN(parseFloat(document.querySelector("#bond-score-display").innerText))'))
        self.assertIn('歷史教學範例：2026 年 1–2 月',page.locator('body').inner_text())
        page.route('**/V70_macro_latest.json',lambda r:r.fulfill(json=data_only()))
        page.evaluate('window.v703ReloadFeed()')
        self.assert_cards(page)

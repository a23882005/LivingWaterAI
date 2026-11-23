"""Marked synthetic publisher prose tests the original fallback after HTTP errors."""
import unittest
from unittest.mock import patch
import requests
from scripts import refresh_v703_predeploy as m
GOOD=b'News provided by Institute for Supply Management October 2026 Manufacturing PMI at 55.5 percent SOURCE Institute for Supply Management'
class ISMHTTPFallbackTests(unittest.TestCase):
    def test_primary_valid_no_extra_request(self):
        with patch.object(m,'fetch',return_value=GOOD) as fetch:
            self.assertEqual(m.refresh_manufacturing_headline(object()),(55.5,m.ISM));self.assertEqual(fetch.call_count,1)
    def test_primary_404_reaches_existing_distributed_source(self):
        with patch.object(m,'fetch',side_effect=[requests.HTTPError('synthetic404'),GOOD]) as fetch:
            value,url=m.refresh_manufacturing_headline(object());self.assertEqual(value,55.5);self.assertIn('prnewswire.com',url);self.assertEqual(fetch.call_count,2)
    def test_primary_login_page_reaches_existing_fallback(self):
        with patch.object(m,'fetch',side_effect=[b'login',GOOD]):self.assertEqual(m.refresh_manufacturing_headline(object())[0],55.5)
    def test_wrong_month_or_value_remains_blocked(self):
        for data in (GOOD.replace(b'October 2026',b'September 2026'),GOOD.replace(b'55.5',b'54.5')):
            with self.subTest(data=data),patch.object(m,'fetch',side_effect=[requests.HTTPError(),data]):
                with self.assertRaises(ValueError):m.refresh_manufacturing_headline(object())
    def test_unverified_publisher_remains_blocked(self):
        with patch.object(m,'fetch',side_effect=[requests.HTTPError(),b'October 2026 Manufacturing PMI at 55.5 percent']):
            with self.assertRaisesRegex(ValueError,'publisher identity'):m.refresh_manufacturing_headline(object())
    def test_all_three_http_failures_propagate_without_success(self):
        with patch.object(m,'fetch',side_effect=[requests.HTTPError(),requests.HTTPError(),requests.Timeout()]):
            with self.assertRaises(requests.Timeout):m.refresh_manufacturing_headline(object())
    def test_distributor_403_reaches_same_publisher_official_pdf(self):
        with patch.object(m,'fetch',side_effect=[requests.HTTPError(),requests.HTTPError(),b'%PDF-synthetic']) as fetch,patch.object(m,'manufacturing_headline_from_official_pdf',return_value=55.5):
            self.assertEqual(m.refresh_manufacturing_headline(object()),(55.5,m.ISM_MANUFACTURING_PDF));self.assertEqual(fetch.call_args.args[1],m.ISM_MANUFACTURING_PDF);self.assertEqual(fetch.call_count,3)
    def pdf(self,text):
        from types import SimpleNamespace
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)])
    def test_pdf_headline_requires_period_publisher_and_headline_not_component(self):
        good='Institute for Supply Management October 2026 Manufacturing PMI® 55.5 54.5 +1.0 New Orders 55.5'
        with patch('pypdf.PdfReader',return_value=self.pdf(good)):self.assertEqual(m.manufacturing_headline_from_official_pdf(b'%PDF-synthetic'),55.5)
        for wrong in (good.replace('October 2026','September 2026'),good.replace('Institute for Supply Management','unverified'),good.replace('PMI® 55.5','PMI® 54.5'),good.replace('Manufacturing PMI®','New Orders')):
            with self.subTest(wrong=wrong),patch('pypdf.PdfReader',return_value=self.pdf(wrong)):
                with self.assertRaises(ValueError):m.manufacturing_headline_from_official_pdf(b'%PDF-synthetic')
    def test_html_login_and_oversized_document_are_not_pdf_evidence(self):
        for raw in (b'<html>login</html>',b'%PDF-'+b'x'*(2*1024*1024)):
            with self.assertRaises(ValueError):m.manufacturing_headline_from_official_pdf(raw)
if __name__=='__main__':unittest.main()

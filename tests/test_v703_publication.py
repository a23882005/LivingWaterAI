import copy,datetime as dt,unittest
from unittest.mock import patch
from v703_browser_fixture import feed,NOW
from scripts.validate_v703_publication import validate_current_contract,verify_live_payload
class PublicationContractTests(unittest.TestCase):
    def test_valid_and_expiry_boundary(self):
        self.assertTrue(validate_current_contract(feed(),NOW))
        with self.assertRaises(ValueError):validate_current_contract(feed(),NOW+dt.timedelta(hours=26))
    def test_bad_child_and_derived_rejected(self):
        for key in ['m06_rate','m06_inf','m06_rstar','m06_output_gap']:
            f=feed();f['indicators'][key]['candidateChecks']=[]
            with self.subTest(key=key),self.assertRaises(ValueError):validate_current_contract(f,NOW)
        f=feed();f['indicators']['m06']['value']+=1
        with self.assertRaises(ValueError):validate_current_contract(f,NOW)
    def test_live_payload_exact_match(self):
        f=feed()
        with patch('scripts.validate_v703_publication.validate_current_contract',return_value=True):
            verify_live_payload(f,copy.deepcopy(f),'HTML','HTML')
            wrong=copy.deepcopy(f);wrong['indicators']['m02']['value']+=1
            with self.assertRaises(ValueError):verify_live_payload(f,wrong,'HTML','HTML')
            with self.assertRaises(ValueError):verify_live_payload(f,f,'HTML','OLD')
if __name__=='__main__':unittest.main()

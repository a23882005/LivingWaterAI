"""Owner-approved previous CPI: provenance, expiry, and unchanged other gates."""
import copy
import datetime as dt
import gzip
import json
import unittest
from pathlib import Path
from scripts import v703_cpi_availability as c
from scripts import build_daily_v703_site as b
from scripts.validate_v703_publication import validate_publication_gate

class CpiCarryTests(unittest.TestCase):
    def setUp(self):
        from test_v703_cpi_data_only import BLS, NOW
        self.now=NOW
        self.raw=b'observation_date,CPILFESL\n2025-09-01,330.418\n2025-10-01,\n2026-09-01,338.896\n2026-10-01,339.900\n'
        self.ev=c.verify_official_gap(self.raw,BLS,self.now)
        self.row=c.previous_valid_cpi(self.raw,self.ev,self.now)
    def test_value_date_weight_input(self):
        self.assertEqual(self.row['value'],2.565841)
        self.assertEqual(self.row['observation_date'],'2026-09-01')
        self.assertEqual(b._validate('m05',self.row,self.now.date(),{},self.now),[])
        self.assertEqual(b._normalize(self.row)['carryForward'],self.row['carryForward'])
    def test_tamper_is_rejected(self):
        for key,value in [('value',0),('observation_date','2026-10-01'),('status','OK'),('source_url','https://example.com')]:
            bad=copy.deepcopy(self.row);bad[key]=value
            self.assertFalse(c.valid_cpi_carry(bad,self.now),key)
        bad=copy.deepcopy(self.row);bad['carryForward']['baseIndex']+=1
        self.assertFalse(c.valid_cpi_carry(bad,self.now))
        with self.assertRaises(ValueError):c.previous_valid_cpi(self.raw+b' ',self.ev,self.now)
    def test_expiry_and_other_series(self):
        self.assertFalse(c.valid_cpi_carry(self.row,self.now+dt.timedelta(hours=26)))
        self.assertFalse(c.valid_cpi_carry(self.row,dt.datetime(2026,12,10,13,30,tzinfo=dt.timezone.utc)))
        self.assertTrue(b._validate('m15',self.row,self.now.date(),{},self.now))
    def test_real_build_and_publication(self):
        from test_v703_cpi_data_only import data_only
        feed=data_only()
        feed['indicators']['m05']=b._normalize(self.row)
        feed['verification'].update(ready=True,valid=26,requiredScoringIndicatorsValidated=22,problems=[])
        feed['publication'].update(mode='FORMAL',scoringAllowed=True,provisionalScoringAllowed=False,
            calculationPolicy=c.CARRY_POLICY,carriedIndicators=['m05'],excludedIndicators=[])
        self.assertEqual(validate_publication_gate(feed,self.now),'FORMAL')
        self.assertEqual(feed['publication']['calculationPolicy'],c.CARRY_POLICY)
        self.assertEqual(feed['publication']['excludedIndicators'],[])
        bad=copy.deepcopy(feed);bad['indicators']['m07']['status']='STALE'
        with self.assertRaises(ValueError):validate_publication_gate(bad,self.now)
        bad=copy.deepcopy(feed);bad['indicators']['m05']['value']=0
        with self.assertRaises(ValueError):validate_publication_gate(bad,self.now)

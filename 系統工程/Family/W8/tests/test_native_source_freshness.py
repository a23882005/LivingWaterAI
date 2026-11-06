from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import json,sys,unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import native_source_freshness as F


class SourceFreshnessTest(unittest.TestCase):
    def case(self,hours):
        raw=json.loads((ROOT/'系統工程/總經V70/V70_macro_latest.json').read_text())
        at=datetime.fromisoformat(raw['asOf'].replace('Z','+00:00'))+timedelta(hours=hours)
        request={'evaluation_at':at.isoformat(),'macro_snapshot':{'payload':raw}}
        report={'analysis_result':{'positions':[{'native_product_identity':{'engine_route':'V75_PREDICATES'},
            'market':{'symbol':'SGOV','observed_date':'2026-10-26','formal_deployment_eligible':False,
                'source_sha256':'a'*64}}]}}
        return request,report

    def test_original_contract_distinguishes_current_feed_and_expired_feed(self):
        request,report=self.case(1);fresh=F.build(ROOT,request,report)
        self.assertEqual(fresh['v70']['state'],'FRESH',fresh['v70'])
        self.assertEqual(fresh['market']['state'],'UNKNOWN')
        request,report=self.case(27);old=F.build(ROOT,request,report)
        self.assertEqual(old['v70']['state'],'STALE')
        self.assertIn('26-hour',old['v70']['reason'])

    def test_future_feed_cannot_be_declared_fresh(self):
        request,report=self.case(-1)
        self.assertEqual(F.build(ROOT,request,report)['v70']['state'],'UNKNOWN')

    def test_resigned_freshness_cannot_replace_unattested_prices(self):
        request,report=self.case(1);report['native_source_freshness']=F.build(ROOT,request,report)
        F.validate(ROOT,request,report)
        report['native_source_freshness']['market']['state']='FRESH'
        with self.assertRaisesRegex(PermissionError,'REPLAY_MISMATCH'):F.validate(ROOT,request,report)


if __name__=='__main__':unittest.main()

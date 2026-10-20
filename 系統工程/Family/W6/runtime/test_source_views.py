import unittest
from copy import deepcopy
from report_receiver import ReportError,digest
from source_views import select_inventory,history_view,canonical_section,cash_history_view


class ViewsTests(unittest.TestCase):
    def test_current_inventory_and_hash_conflicts(self):
        good=[{'source_id':'current','role':'CURRENT','sha256':'a','observed_sha256':'a'},
              {'source_id':'old','role':'HISTORICAL','sha256':'b','observed_sha256':'b'}]
        self.assertEqual(select_inventory(good,'current'),good[0])
        for case in ['wrong_hash','duplicate','two_current','old_selected']:
            r=deepcopy(good);key='current'
            if case=='wrong_hash':r[0]['observed_sha256']='wrong'
            if case=='duplicate':r.append(deepcopy(r[0]))
            if case=='two_current':r[1]['role']='CURRENT'
            if case=='old_selected':key='old'
            with self.assertRaises(ReportError):select_inventory(r,key)
    def test_history_timezone_sequence_rollback(self):
        base={'client_id':'a','event_id':'1','occurred_at':'2026-01-01T08:00:00+08:00',
              'sequence':1,'source_id':'s','confirmed_by':'owner','confirmed':True,'before':1,'after':2,'impact':'correction'}
        rollback={**base,'event_id':'2','occurred_at':'2026-01-01T00:00:00Z','sequence':2,'before':2,'after':1,'impact':'rollback'}
        self.assertEqual(history_view([rollback,base],'a'),[base,rollback])
        for field,value in [('client_id','b'),('confirmed',False),('source_id',None),('occurred_at','2026-01-01T00:00:00')]:
            bad={**base,field:value}
            with self.assertRaises(ReportError):history_view([bad],'a')
    def test_canonical_sections_preserve_all_values(self):
        for section in ['target','drift','performance','risk','look_through','valuation','funding']:
            payload={'zero':0,'missing':None,'negative':-12,'ratio':'0.123456789','source_period':'historical'}
            e={'client_id':'a','run_id':'r','section':section,'value_state':'PARTIAL','payload':payload,
               'payload_sha256':digest(payload),'source_id':'s','rules_sha':'rules','as_of':'2026-01-01T00:00:00Z'}
            out=canonical_section(e,client_id='a',run_id='r',section=section)
            self.assertEqual(out,e);out['payload']['zero']=99;self.assertEqual(e['payload']['zero'],0)
            self.assertIsNone(canonical_section(None,client_id='a',run_id='r',section=section)['payload'])
            for field,value in [('client_id','b'),('run_id','other'),('payload_sha256','bad'),('rules_sha',None)]:
                with self.assertRaises(ReportError):canonical_section({**e,field:value},client_id='a',run_id='r',section=section)
    def test_cash_dates_not_summed_and_protection_preserved(self):
        rows=[{'client_id':'a','as_of':'2026-01-01','reported_cash_minor':100,'available':None},
              {'client_id':'a','as_of':'2026-01-02','reported_cash_minor':120,'available':None}]
        s={'client_id':'a','tables':{'cash_balance_snapshot':rows,'protected_funding_claim':[{'client_id':'a','amount':50}]}}
        out=cash_history_view(s);self.assertEqual(out['tables']['cash_balance_snapshot'],rows)
        self.assertEqual(out['tables']['protected_funding_claim'][0]['amount'],50)
        self.assertEqual(out['snapshot_aggregation'],'NONE')
        s['tables']['cash_balance_snapshot'][0]['client_id']='b'
        with self.assertRaises(ReportError):cash_history_view(s)

if __name__=='__main__':unittest.main()

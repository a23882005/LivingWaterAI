import unittest
from execution_health import collect,unknown,validate
from market_poll import build_batch,build_notice
from safe_notify import canonical
from datetime import datetime,timezone

class Tests(unittest.TestCase):
    def get(self,path):
        if path=='/actions/runs/20':return dict(path='.github/workflows/yahoo-reference-monitor.yml',head_branch='main',event='schedule',run_started_at='2026-11-10T06:45:00Z')
        if 'workflows/' in path:return {'workflow_runs':[dict(id=19,status='completed',conclusion='failure',head_branch='main'),dict(id=18,status='completed',conclusion='success',head_branch='main')]}
        if path=='/actions/runs/18/jobs':return {'jobs':[dict(name='reference',conclusion='success',completed_at='2026-11-10T05:49:10Z')]}
        raise AssertionError(path)
    def test_real_fields_no_guessed_slot(self):
        r=collect('a23882005/LivingWaterAI','20','fixture',get=self.get)
        self.assertIsNone(r['scheduled_slot']);self.assertEqual(r['actual_started_at'],'2026-11-10T06:45:00Z')
        self.assertEqual(r['last_success_at'],'2026-11-10T05:49:10Z');self.assertEqual(r['last_success_run_id'],'18')
    def test_failure_becomes_unknown(self):
        def fail(path):raise TimeoutError()
        self.assertEqual(collect('a23882005/LivingWaterAI','20','fixture',get=fail)['status'],'UNKNOWN')
    def test_no_prior_success_not_invented(self):
        def get(path):
            if 'workflows/' in path:return {'workflow_runs':[]}
            return self.get(path)
        self.assertIsNone(collect('a23882005/LivingWaterAI','20','fixture',get=get)['last_success_at'])
    def test_wrong_workflow_rejected(self):
        r=collect('a23882005/LivingWaterAI','20','fixture',get=lambda path:{'path':'other','head_branch':'main'})
        self.assertEqual(r['status'],'UNKNOWN')
    def test_extra_private_field_rejected(self):
        with self.assertRaises(ValueError):validate({**unknown(),'holdings':'PRIVATE'})
    def test_guessed_slot_rejected(self):
        with self.assertRaises(ValueError):validate({**unknown(),'scheduled_slot':'2026-11-10T06:43:00Z'})
    def test_metadata_does_not_defeat_quote_dedup(self):
        now=datetime(2026,11,10,tzinfo=timezone.utc);r=build_notice('VT',{},now,'20','owner/repo')
        a=build_batch([r],now,'20','owner/repo',unknown());b=build_batch([r],now,'21','owner/repo',collect('a23882005/LivingWaterAI','20','fixture',get=self.get))
        self.assertEqual(a['event_id'],b['event_id']);self.assertIn('execution',canonical(b))

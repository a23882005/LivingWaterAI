import copy
import json
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'/'c_configuration_core'))
from work17.target_draft import build_final_target_draft
from work18.target_confirmation import create_pending_version, apply_confirmation

F=json.loads((ROOT/'fixtures/W2_17_TARGET_DRAFT_GOLDEN.json').read_text())
G=json.loads((ROOT/'fixtures/W2_18_CONFIRMATION_GOLDEN.json').read_text())
NOW=G['confirmation']['confirmed_at']
PROPOSED=G['proposal']['proposed_at']
EXPIRES=G['proposal']['expires_at']

def make_draft(plans=None):
    return build_final_target_draft(c_work6_response=copy.deepcopy(F['c_work6_response']),
        funding_budgets=copy.deepcopy(F['funding_budgets']),planned_investments=copy.deepcopy(plans if plans is not None else F['planned_investments']),
        risk_by_instrument=copy.deepcopy(F['risk_by_instrument']),expected_client_id=F['expected_client_id'],
        expected_run_id=F['expected_run_id']).draft

def stage(draft=None,ledger=None,expected=None):
    d=draft or make_draft()
    return create_pending_version(ledger=ledger,draft=d,proposed_at=PROPOSED,expires_at=EXPIRES,
        policy_version=G['proposal']['policy_version'],data_version=G['proposal']['data_version'],
        source_reference_ids=G['proposal']['source_reference_ids'],expected_latest_version=expected)

def confirm(record,**changes):
    c=G['confirmation']
    args={'ledger':record.ledger,'client_id':G['client_id'],'version':record.ledger['latest_version'],
        'target_hash':record.ledger['versions'][-1]['target_hash'],'action':c['action'],
        'client_explicit_decision':c['client_explicit_decision'],'confirmed_at':c['confirmed_at'],'confirmed_by':c['confirmed_by'],
        'source_reference_ids':record.ledger['versions'][-1]['source_reference_ids'],'now':NOW}
    args.update(changes)
    return apply_confirmation(**args)

class W2_18Tests(unittest.TestCase):
    def test_p01_explicit_exact_hash_confirms_only_one_staging_version(self):
        pending=stage(); row=pending.ledger['versions'][0]
        self.assertEqual((pending.status,row['status']),("PENDING","PENDING"))
        approved=confirm(pending)
        self.assertEqual(approved.status,'CONFIRMED')
        self.assertEqual(approved.ledger['versions'][0]['status'],'CONFIRMED')
        self.assertEqual(approved.event['write_scope'],'ISOLATED_TEST_STAGING')
        self.assertTrue(approved.no_commit)

    def test_n01_reject_wrong_hash_client_expired_and_early_time_no_commit(self):
        pending=stage()
        cases=[
            ({'action':'REJECT'},'REJECTED'),
            ({'action':'REJECT','client_explicit_decision':'FALSE'},'EXPLICIT_CLIENT_CONFIRMATION_REQUIRED'),
            ({'target_hash':'0'*64},'TARGET_HASH_MISMATCH'),
            ({'client_id':'CLIENT_TEST_B'},'CROSS_CLIENT_CONFIRMATION'),
            ({'now':'2026-10-20T08:01:00+08:00','confirmed_at':'2026-10-20T08:01:00+08:00'},'TARGET_EXPIRED'),
            ({'confirmed_at':'2026-10-20T06:59:00+08:00'},'CONFIRMATION_BEFORE_PROPOSAL'),
        ]
        for changes,expected in cases:
            out=confirm(pending,**changes)
            self.assertTrue(out.no_commit)
            if expected=='REJECTED': self.assertEqual(out.status,'REJECTED')
            else: self.assertIn(expected,out.issue_codes)

    def test_b01_duplicate_signature_idempotent_changed_signature_conflict(self):
        pending=stage(); first=confirm(pending)
        replay=confirm(first)
        self.assertEqual(replay.status,'IDEMPOTENT')
        conflict=confirm(first,source_reference_ids=['SRC_DIFFERENT'])
        self.assertIn('DUPLICATE_CONFIRMATION_CONFLICT',conflict.issue_codes)

    def test_b01_revised_draft_supersedes_pending_old_signature_and_detects_race(self):
        first=stage(); old_hash=first.ledger['versions'][0]['target_hash']
        plans=copy.deepcopy(F['planned_investments']); plans[0]['amount']=5500
        changed=make_draft(plans)
        race_plans=copy.deepcopy(F['planned_investments']); race_plans[0]['amount']=5400
        second=stage(changed,first.ledger,expected=1)
        self.assertEqual(second.ledger['versions'][0]['status'],'SUPERSEDED')
        self.assertEqual(second.ledger['latest_version'],2)
        old=apply_confirmation(ledger=second.ledger,client_id='CLIENT_TEST_A',version=1,target_hash=old_hash,
            action='CONFIRM',client_explicit_decision='TRUE',confirmed_at=NOW,confirmed_by='CLIENT_TEST_A',
            source_reference_ids=second.ledger['versions'][0]['source_reference_ids'],now=NOW)
        self.assertIn('TARGET_VERSION_CONFLICT',old.issue_codes)
        race=stage(make_draft(race_plans),first.ledger,expected=0)
        self.assertIn('VERSION_CONFLICT',race.issue_codes)

if __name__=='__main__': unittest.main()

"""Synthetic producer-to-consumer seam; no family DB or external writes."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
import unittest

W7 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W7 / 'vendor/w2/tests'))
sys.path.insert(0, str(W7.parent / 'W5'))
from test_w2_18_target_confirmation import stage, confirm
from family_boundary import validate_target, BoundaryError


def envelope():
    confirmed = confirm(stage())
    record = confirmed.ledger['versions'][0]
    return {'payload': deepcopy(record), 'target_version': record['version'],
            'target_hash': record['target_hash'],
            'confirmation_run_id': record['draft']['identity']['run_id']}


class TargetCompatibility(unittest.TestCase):
    def test_full_record_json_roundtrip_preserves_consumer_contract(self):
        target = envelope()
        restored = json.loads(json.dumps(target, ensure_ascii=False, allow_nan=False))
        result = validate_target(restored, 'CLIENT_TEST_A', datetime.fromisoformat('2026-10-22T20:00:00+08:00'))
        self.assertEqual(result, target)
        self.assertEqual(result['payload']['status'], 'CONFIRMED')

    def test_wrong_client_rejected(self):
        with self.assertRaises(BoundaryError):
            validate_target(envelope(), 'CLIENT_TEST_B', datetime.fromisoformat('2026-10-22T20:00:00+08:00'))

    def test_changed_confirmation_evidence_rejected(self):
        target = envelope()
        target['payload']['confirmation_evidence']['source_reference_ids'].append('UNTRUSTED')
        with self.assertRaises(BoundaryError):
            validate_target(target, 'CLIENT_TEST_A', datetime.fromisoformat('2026-10-22T20:00:00+08:00'))

    def test_changed_target_rejected(self):
        target = envelope()
        target['payload']['draft']['target_lines'][0]['weight']['value'] = 0.99
        with self.assertRaises(BoundaryError):
            validate_target(target, 'CLIENT_TEST_A', datetime.fromisoformat('2026-10-22T20:00:00+08:00'))


if __name__ == '__main__':
    unittest.main()

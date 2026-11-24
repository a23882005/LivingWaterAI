import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_phone_receipt import finish_phone_receipt


class PhoneReceiptTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.groups = ["00000000", "00010002", "01234567", "12345678",
                       "89abcdef", "00112233", "abcdef01", "ff000000"]
        self.receipt = {"request_id": "fixture", "status": "verified", "verified_at": 42,
                        "proof_groups": self.groups}

    def test_native_json_and_text_preserve_each_group_and_original_fields(self):
        r = self.receipt
        for result in [r, json.dumps(r), {"structuredContent": r},
                       {"content": [{"type": "text", "text": json.dumps(r)}]}]:
            with self.subTest(result=type(result)):
                self.assertEqual(finish_phone_receipt(self.session, result),
                                 self.session.mobile_finish.return_value)
                self.session.mobile_finish.assert_called_with({**r, "proof": "".join(self.groups)})

    def test_complete_issuer_groups_work_independently_of_a_short_transcription(self):
        finish_phone_receipt(self.session, {**self.receipt, "proof": "0" * 61})
        received = self.session.mobile_finish.call_args.args[0]
        self.assertEqual(received["proof"], "".join(self.groups))
        self.assertEqual(len(received["proof"]), 64)

    def test_incomplete_groups_and_pending_results_never_reach_session(self):
        for change in [{"proof_groups": self.groups[:-1]},
                       {"proof_groups": self.groups[:-1] + ["12345"]},
                       {"proof_groups": self.groups[:-1] + ["zzzzzzzz"]}, {"status": "pending"},
                       {"status": "locked"}, {"status": "expired"}, {"isError": True}]:
            with self.assertRaises(ValueError):
                finish_phone_receipt(self.session, {**self.receipt, **change})
        self.session.mobile_finish.assert_not_called()

    def test_legacy_and_final_signature_decision_belong_to_original_session(self):
        legacy = {"request_id": "fixture", "status": "verified", "proof": "0" * 61}
        self.session.mobile_finish.side_effect = PermissionError("original signature check")
        for r in [legacy, self.receipt]:
            with self.assertRaises(PermissionError):
                finish_phone_receipt(self.session, r)
        self.assertEqual(self.session.mobile_finish.call_args_list[0].args, (legacy,))

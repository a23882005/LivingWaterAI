import unittest
from copy import deepcopy
from report_receiver import receive_action, ReportError
from test_report_receiver import fixture


class DirectReceiptTests(unittest.TestCase):
    def test_failure_without_optional_client_preserved(self):
        _, request, result = fixture()
        view = receive_action(result, request)
        self.assertEqual(view['issue_codes'], result['issue_codes'])
        self.assertEqual(view['source_run_id'], request['run_id'])

    def test_direct_failure_binding(self):
        _, request, result = fixture()
        for field in ('schema_version', 'run_id', 'request_id', 'client_id'):
            with self.subTest(field=field):
                changed = deepcopy(result)
                changed[field] = 'foreign'
                with self.assertRaises(ReportError):
                    receive_action(changed, request)

    def test_nested_failure_identity(self):
        _, request, result = fixture()
        result['issue_codes'] = [{'code': 'MISSING', 'detail': {'client_id': 'other'}}]
        with self.assertRaises(ReportError):
            receive_action(result, request)


if __name__ == '__main__':
    unittest.main()

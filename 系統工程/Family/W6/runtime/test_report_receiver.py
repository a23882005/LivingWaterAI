import unittest
from copy import deepcopy
from report_receiver import assemble, render_review, ReportError, digest, input_digest, receive_action


def fixture(member='a'):
    s={'schema_version':'Family.W5.W1Snapshot.v1','client_id':member,
       'identity':{'client_id':member,'family_alias':'Test '+member},
       'tables':{'portfolio_account':[{'client_id':member,'account_key':'broker1','account_label':'First'},
                                    {'client_id':member,'account_key':'broker2','account_label':'Second'}],
        'portfolio_instrument':[{'client_id':member,'instrument_key':'BOND','ticker':'BOND'}],
        'portfolio_position':[{'client_id':member,'account_key':a,'instrument_key':'BOND',
                               'quantity_decimal':q,'cost_state':'UNKNOWN','as_of_utc':'2026-01-01T00:00:00Z'}
                              for a,q in [('broker1','13'),('broker2','6')]],
        'cash_balance_snapshot':[]}}
    q={'schema_version':'Family.W5.request.v1','client_id':member,'run_id':'run-'+member,
       'request_id':'request-'+member,'evaluation_at':'2026-01-02T00:00:00Z',
       'trade_authorization':'NONE','client_snapshot':{'payload':deepcopy(s)}}
    r={'schema_version':'Family.W5.result.v1','run_id':q['run_id'],'request_id':q['request_id'],
       'status':'DATA_UNAVAILABLE','canonical_result':None,'mentor':None,
       'issue_codes':[{'code':'TARGET_REQUIRED'}],'production':'HOLD','trade_action':'NO_TRADE'}
    return s,q,r


class ReceiverTests(unittest.TestCase):
    def setUp(self):self.members={k:'Test '+k for k in 'abcd'}
    def build(self,s,q,r,client='a'):return assemble(s,q,r,client_id=client,members=self.members)
    def test_four_members_and_deterministic_immutable(self):
        for k in self.members:
            s,q,r=fixture(k);before=digest([s,q,r]);v=self.build(s,q,r,k)
            self.assertEqual(v,self.build(s,q,r,k));self.assertEqual(before,digest([s,q,r]))
    def test_cross_broker_symbol_not_collapsed(self):
        v=self.build(*fixture());self.assertEqual(len(v['holdings']),2)
        self.assertEqual([x['position']['quantity_decimal'] for x in v['holdings']],['13','6'])
    def test_unknown_not_zero(self):
        v=self.build(*fixture());self.assertEqual(v['holdings'][0]['position']['cost_state'],'UNKNOWN')
        self.assertFalse(v['formal_output_eligible']);self.assertEqual(v['engine']['items'],[])
    def test_all_cross_member_substitutions(self):
        for a in self.members:
            for b in self.members:
                if a==b:continue
                s,q,r=fixture(a);s2,_,_=fixture(b)
                with self.assertRaises(ReportError):self.build(s2,q,r,a)
    def test_unknown_fifth_member(self):
        with self.assertRaises(ReportError):self.build(*fixture('e'),client='e')
    def test_wrong_run_request_schema(self):
        for key in ['run_id','request_id','schema_version']:
            s,q,r=fixture();r[key]='wrong'
            with self.assertRaises(ReportError):self.build(s,q,r)
    def test_nested_client_and_alias(self):
        for field in ['client_id','family_alias']:
            s,q,r=fixture();s['identity'][field]='wrong';q['client_snapshot']['payload']=s
            with self.assertRaises(ReportError):self.build(s,q,r)
    def test_duplicate_positions_accounts_cash(self):
        for table in ['portfolio_position','portfolio_account','portfolio_instrument']:
            s,q,r=fixture();s['tables'][table].append(deepcopy(s['tables'][table][0]));q['client_snapshot']['payload']=s
            with self.assertRaises(ReportError):self.build(s,q,r)
    def test_failed_output_advice_rejected(self):
        s,q,r=fixture();r['mentor']={'action':'BUY'}
        with self.assertRaises(ReportError):self.build(s,q,r)
    def test_order_execution_scope(self):
        s,q,r=fixture();r['trade_action']='BUY'
        with self.assertRaises(ReportError):self.build(s,q,r)
    def test_html_script_escape(self):
        v=self.build(*fixture());v['member_alias']='<script>x</script>'
        self.assertNotIn('<script>',render_review(v))
    def test_empty_member(self):
        s,q,r=fixture();s['tables']['portfolio_position']=[];q['client_snapshot']['payload']=s
        self.assertEqual(self.build(s,q,r)['holdings'],[])


def action_fixture(advice=False):
    _, q, r = fixture()
    owner = {'broker': 'SYNTH_BROKER', 'account': 'broker1', 'funding_domain': 'SYNTH_POOL'}
    q['native_bundle'] = {'stock_request': {'work3_handoff': {'owner': deepcopy(owner)}}}
    canonical = {'items': [{'item_id': 'SYNTH_ITEM', 'account_owner': owner,
                            'data_lineage': ['SYNTHETIC'], 'rule_lineage': ['SYNTHETIC'],
                            'canonical_action': 'WAIT', 'deployment_amount': '0'}]}
    mentor = {'client_id': q['client_id'], 'run_id': q['run_id'], 'owner': owner,
              'execution_advice_allowed': advice, 'canonical_deployment_result': canonical,
              'canonical_deployment_result_sha256': digest(canonical)}
    if advice is True:
        mentor.update(contract_name='Family.W5.mentor.v1', recommendations_allowed=True,
                      broker_execution_allowed=False, production='HOLD', trade_action='NO_TRADE')
    r.update(status='OK', client_id=q['client_id'], input_digest=input_digest(q),
             data_provenance='SYNTHETIC', mentor=mentor)
    return q, r


class MentorScopeTests(unittest.TestCase):
    def test_legacy_false_needs_no_new_fields_and_source_stays_immutable(self):
        q, r = action_fixture()
        before = deepcopy((q, r))
        out = receive_action(r, q)
        self.assertIs(out['source_execution_advice_allowed'], False)
        self.assertIs(out['broker_execution_allowed'], False)
        self.assertEqual(out['items'], r['mentor']['canonical_deployment_result']['items'])
        self.assertEqual((q, r), before)

    def test_both_routes_reject_explicit_broker_permission_and_wrong_flag_types(self):
        for advice in (False, True):
            for key, bad in [('broker_execution_allowed', True), ('broker_execution_allowed', 'False'),
                             ('broker_execution_allowed', 0), ('broker_execution_allowed', None),
                             ('recommendations_allowed', 'True'), ('recommendations_allowed', 1),
                             ('recommendations_allowed', None)]:
                with self.subTest(advice=advice, flag=key, value=bad):
                    q, r = action_fixture(advice)
                    r['mentor'][key] = bad
                    with self.assertRaises(ReportError): receive_action(r, q)

    def test_unknown_advice_values_rejected_instead_of_truthiness_coercion(self):
        for value in (None, 0, 1, 'False', 'True', '', [], {}):
            with self.subTest(value=value):
                q, r = action_fixture()
                r['mentor']['execution_advice_allowed'] = value
                with self.assertRaisesRegex(ReportError, 'MENTOR_EXECUTION_SCOPE'): receive_action(r, q)

    def test_failure_receipts_never_supply_advice_or_canonical_items(self):
        for status in ('DATA_UNAVAILABLE', 'REJECTED', 'BLOCKED', 'INVALID_INPUT', 'ERROR'):
            with self.subTest(status=status):
                _, q, r = fixture()
                r['status'] = status
                out = receive_action(r, q)
                self.assertEqual(out['items'], [])
                self.assertIs(out['execution_advice_allowed'], False)
                self.assertIs(out['broker_execution_allowed'], False)
                for key, value in (('mentor', action_fixture(True)[1]['mentor']), ('canonical_result', {})):
                    bad = deepcopy(r); bad[key] = value
                    with self.assertRaisesRegex(ReportError, 'FAILED_RESULT_HAS_ADVICE'): receive_action(bad, q)

if __name__=='__main__':unittest.main()

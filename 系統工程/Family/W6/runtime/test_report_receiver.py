import unittest
from copy import deepcopy
from report_receiver import assemble, render_review, ReportError, digest


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

if __name__=='__main__':unittest.main()

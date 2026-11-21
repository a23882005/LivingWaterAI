"""Invented qualified source rows: current holdings, dated history and NAV."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('current_portfolio_fixture',
    Path(__file__).parent/'fixtures/report_html/synthetic.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


def seal(case):
    portfolio=case['result']['current_portfolio_reference']
    qualification=portfolio['project_NAV_source_qualification']
    qualification['digest']=F.A.digest({k:v for k,v in qualification.items() if k!='digest'})
    contract=portfolio['contract'];contract['nav_source_qualification']=deepcopy(qualification)
    contract['digest']=F.A.digest({k:v for k,v in contract.items() if k!='digest'})
    portfolio['digest']=F.A.digest({k:v for k,v in portfolio.items() if k!='digest'})
    F.member_refresh(case)


def current_case():
    case=F.member_financial_case();source,request,result=(case[k] for k in ('source','request','result'))
    binding={k:request[k] for k in ('client_id','run_id','evaluation_at')}
    binding['source_db_sha256']=source['source_db_sha256']
    symbols=[r['symbol'] for r in result['positions']]+['SYN_BOND','SYN_BOND','SYN_SGOV']
    rows=[];approved=[]
    for index,symbol in enumerate(symbols):
        zero=index==len(symbols)-1
        row={'symbol':symbol,'quantity':'0' if zero else str(31+index),'amount':'0' if zero else '123.456789',
            'currency':None if zero else 'USD','reporting_amount_TWD':'0' if zero else '4567.890123',
            'observed_market_date':None if zero else '2026-10-29','issue':None}
        accepted={'source_representation_index':index,'symbol':symbol,'quantity':row['quantity'],
                  'security_value_TWD':row['reporting_amount_TWD']}
        if not zero:accepted.update(currency='USD',security_value_native=row['amount'],observed_market_date='2026-10-29')
        rows.append(row);approved.append(accepted)
    fx={'base_currency':'USD','quote_currency':'TWD','quote_per_base':'37.12345','source_sha256':'c'*64,
        'as_of':'2026-10-29','as_of_time':'2026-10-29T10:00:00+08:00','retrieved_at':'2026-10-29T12:00:00Z'}
    accepted={'qualification':'PM_VERIFIED_SOURCE_FOR_CURRENT_PROJECT_NAV_INPUT',
        'client_id':source['client_id'],'source_db_sha256':source['source_db_sha256'],
        'all_positive_positions_valued':True,'unreported_positions_orders_and_commitments_absent_by_explicit_Owner_policy':True,
        'cash_counted_once':True,'new_buy_permission_created':False,'approved_target_pool_rebased':False,
        'historical_PIT_or_qP_qV_qualified':False,'accepted_net_cash_by_currency':{'USD':'9.87'},
        'cash_reporting_TWD':'123.456','current_project_portfolio_NAV_TWD':'98765.432109','positions':approved}
    qualification={'schema_version':'Family.W8.ProjectNAVSourceQualification.v1',**binding,
        'member':source['member_alias'],'target_version':request['confirmed_target']['target_version'],
        'available_at':F.ASOF,'approved_member_sources':accepted,'reporting_FX':deepcopy(fx),
        'new_buy_permission_created':False,'historical_PIT_or_qP_qV_qualified':False}
    portfolio={'schema_version':'Family.W8.CurrentPortfolioReference.v1',**binding,
        'formal_NAV_source_qualified':True,'issues':[],'formal_source_qualification_dependencies':[],
        'cash_counted_once':True,'SGOV_physical_value_counted_once':True,'SGOV_roles_added_to_cash':False,
        'approved_pool_and_target_amounts_rebased':False,'new_buy_permission_created':False,
        'historical_PIT_or_qP_qV_qualified':False,'trade_action':'NO_TRADE','positions':rows,
        'accepted_net_cash_by_currency':deepcopy(accepted['accepted_net_cash_by_currency']),
        'cash_TWD':accepted['cash_reporting_TWD'],'positions_plus_accepted_cash_TWD':accepted['current_project_portfolio_NAV_TWD'],
        'security_subtotals_by_currency':{'USD':'765.4321'},'reporting_FX':fx,'project_NAV_source_qualification':qualification,
        'contract':{'schema_version':'Family.W8.CurrentMarketContract.v1',**binding,'member':source['member_alias'],
            'target_version':request['confirmed_target']['target_version'],'trade_authorization':'NONE'}}
    account=request['client_snapshot']['payload']['tables']['portfolio_account'][0]
    owner={'client_id':source['client_id'],'account':account['account_key'],'currency':'USD'}
    result['positions'][0]['holding']={'quantity':'31','quantity_state':'KNOWN','source_facts':[
        {'broker_label':'SYNTHETIC_BROKER','quantity':'7','currency':'USD','received_at':'2026-10-10T12:00:00Z'}],
        'current_broker_position':{'symbol':symbols[0],'owner':owner,'quantity':'31','currency':'USD',
            'source_sha256':'d'*64,'retrieved_at':F.ASOF}}
    result['current_portfolio_reference']=portfolio;seal(case);return case


class CurrentPortfolioTests(unittest.TestCase):
    def current(self,case):
        inputs=F.A.make_member_review_inputs(case['source'],case['request'],case['result'],
            source_id='SYNTHETIC_CURRENT_NAV',rules_sha='e'*64)
        return F.D.build_w6_current_data(case['source'],**inputs)

    def test_current_and_historical_quantities_and_all_original_rows_visible(self):
        case=current_case();before=deepcopy(case);current=self.current(case)
        self.assertEqual(case,before)
        self.assertEqual(current['report_source_lineage']['member_analysis'],case['result'])
        text='\n'.join(c['heading']+c['body'] for c in current['verified_sections']['valuation'])
        self.assertIn('當輪已核現持：31',text);self.assertIn('歷史1數量：7',text)
        self.assertIn('2026-10-10',text);self.assertIn('現持來源可得時間',text)
        projection=current['report_source_lineage']['section_projection']
        self.assertEqual(projection['current_portfolio_display']['rows_quoted'],7)
        pointers={x['pointer'] for x in projection['quoted_fields']['radar']}
        for index in range(7):
            for field in ('quantity','amount','currency','reporting_amount_TWD','observed_market_date'):
                self.assertIn(f'/result/current_portfolio_reference/positions/{index}/{field}',pointers)
        nav='\n'.join(c['body'] for c in current['verified_sections']['radar'])
        self.assertIn('98765.432109',nav);self.assertIn('USD',nav);self.assertIn('2026-10-29',nav)
        self.assertIn('SYN_BOND〔原列5〕',nav);self.assertIn('SYN_BOND〔原列6〕',nav)
        self.assertIn('新增股數：UNKNOWN',nav)
        self.assertIsNone(current['current_total_twd']);self.assertEqual(current['actual'],[])
        self.assertEqual(current['report_scope'],'SOURCE_REVIEW')

    def test_qualified_zero_position_keeps_unknown_currency_and_date(self):
        case=current_case();current=self.current(case)
        zero=case['result']['current_portfolio_reference']['positions'][-1]
        self.assertEqual(zero['amount'],'0');self.assertIsNone(zero['currency']);self.assertIsNone(zero['observed_market_date'])
        self.assertNotIn('security_value_native',case['result']['current_portfolio_reference']['project_NAV_source_qualification']['approved_member_sources']['positions'][-1])
        self.assertIn('SYN_SGOV〔原列7〕','\n'.join(c['body'] for c in current['verified_sections']['radar']))

    def test_resealed_foreign_household_run_database_time_or_target_rejected(self):
        for component in ('portfolio','qualification','contract'):
            for field in ('client_id','run_id','source_db_sha256','evaluation_at'):
                with self.subTest(component=component,field=field):
                    case=current_case();p=case['result']['current_portfolio_reference']
                    node=p if component=='portfolio' else p['project_NAV_source_qualification' if component=='qualification' else 'contract']
                    node[field]='FOREIGN';seal(case)
                    with self.assertRaises(ValueError):self.current(case)
        case=current_case();case['result']['current_portfolio_reference']['project_NAV_source_qualification']['target_version']+=1;seal(case)
        with self.assertRaises(ValueError):self.current(case)

    def test_approval_row_order_count_quantity_values_currency_and_dates_cannot_disagree(self):
        for field,value in (('source_representation_index',True),('symbol','FOREIGN'),('quantity','1'),
                ('security_value_TWD','1'),('security_value_native','1'),('currency','TWD'),('observed_market_date','2026-01-01')):
            with self.subTest(field=field):
                case=current_case();case['result']['current_portfolio_reference']['project_NAV_source_qualification']['approved_member_sources']['positions'][0][field]=value
                seal(case)
                with self.assertRaises(ValueError):self.current(case)
        case=current_case();case['result']['current_portfolio_reference']['positions'].pop();seal(case)
        with self.assertRaises(ValueError):self.current(case)

    def test_approval_total_cash_or_new_permission_cannot_be_rebound(self):
        for field,value in (('current_project_portfolio_NAV_TWD','1'),('cash_reporting_TWD','1'),
                ('accepted_net_cash_by_currency',{}),('new_buy_permission_created',True),('all_positive_positions_valued',False),
                ('approved_target_pool_rebased',True),('historical_PIT_or_qP_qV_qualified',True)):
            with self.subTest(field=field):
                case=current_case();case['result']['current_portfolio_reference']['project_NAV_source_qualification']['approved_member_sources'][field]=value
                seal(case)
                with self.assertRaises(ValueError):self.current(case)

    def test_current_broker_quantity_owner_account_currency_or_capture_cannot_disagree(self):
        for field in ('quantity','symbol','currency','source_sha256','retrieved_at','owner_client','owner_account'):
            with self.subTest(field=field):
                case=current_case();broker=case['result']['positions'][0]['holding']['current_broker_position']
                if field.startswith('owner_'):broker['owner']['client_id' if field=='owner_client' else 'account']='FOREIGN'
                else:broker[field]='2030-01-01T00:00:00Z' if field=='retrieved_at' else 'FOREIGN'
                seal(case)
                with self.assertRaises(ValueError):self.current(case)

    def test_future_price_fx_or_qualification_dates_rejected(self):
        for field in ('price','fx_quote','fx_capture','fx_date','qualification'):
            with self.subTest(field=field):
                case=current_case();p=case['result']['current_portfolio_reference'];q=p['project_NAV_source_qualification']
                if field=='price':
                    p['positions'][0]['observed_market_date']='2030-01-01';q['approved_member_sources']['positions'][0]['observed_market_date']='2030-01-01'
                elif field=='qualification':q['available_at']='2030-01-01T00:00:00Z'
                else:
                    key={'fx_quote':'as_of_time','fx_capture':'retrieved_at','fx_date':'as_of'}[field]
                    p['reporting_FX'][key]='2030-01-01' if key=='as_of' else '2030-01-01T00:00:00Z'
                    q['reporting_FX']=deepcopy(p['reporting_FX'])
                seal(case)
                with self.assertRaises(ValueError):self.current(case)

    def test_unqualified_nav_is_not_promoted_or_called_current_qualified(self):
        case=current_case();case['result']['current_portfolio_reference']['formal_NAV_source_qualified']=False;seal(case)
        current=self.current(case)
        self.assertNotIn('current_portfolio_display',current['report_source_lineage']['section_projection'])
        self.assertIsNone(current['current_total_twd'])

    def test_reference_qualification_or_contract_digest_tampering_rejected(self):
        for component in ('portfolio','qualification','contract'):
            with self.subTest(component=component):
                case=current_case();p=case['result']['current_portfolio_reference']
                node=p if component=='portfolio' else p['project_NAV_source_qualification' if component=='qualification' else 'contract']
                node['digest']='0'*64;F.member_refresh(case)
                with self.assertRaises(ValueError):self.current(case)


if __name__=='__main__':unittest.main()

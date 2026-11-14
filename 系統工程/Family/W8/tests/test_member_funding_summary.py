"""Synthetic original-claim conservation; no real-household cash assumptions."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from member_funding_summary import reconcile
from funding_guard import check_aggregate


def financial_row(symbol='SYNTHETIC_A',equity='20',bond='30',*,account='SYNTHETIC_ACCOUNT',currency='USD'):
    owner={'client_id':'SYNTHETIC_CLIENT','account':account,'broker':'SYNTHETIC_BROKER',
        'funding_domain':'SYNTHETIC_DOMAIN','currency':currency}
    cash={'available':'100','equity_executable_budget':'70','bond_executable_budget':'50'}
    decision={'asset_id':'SYNTHETIC_BOND','deploy_amount':{'amount':bond,'currency':currency},'action':'WAIT' if bond=='0' else 'BUY'}
    claims=[{'claim_id':'V82:'+symbol,'asset_id':symbol,'source_engine':'V82','asset_class':'EQUITY',
        'owner':owner,'run_id':'SYNTHETIC_RUN','amount':equity},
        {'claim_id':'V75:SYNTHETIC_BOND','asset_id':'SYNTHETIC_BOND','source_engine':'V75','asset_class':'BOND',
        'owner':owner,'run_id':'SYNTHETIC_RUN','amount':bond}]
    aggregate=check_aggregate(owner=owner,run_id='SYNTHETIC_RUN',available='100',equity_budget='70',bond_budget='50',claims=claims)
    native={'client_id':owner['client_id'],'run_id':'SYNTHETIC_RUN','stock_result':{'asset_id':symbol},
        'funding_aggregate':aggregate,'work9_request':{'work6_funding_account_isolation_result':{'cash_eligibility':cash}},
        'bond_result':{'canonical_v75_output':{'per_asset_decisions':[decision]}}}
    return {'symbol':symbol,'financial_chain':{'owner':owner,'run_id':'SYNTHETIC_RUN','full_native_pipeline_complete':True,
        'canonical_amount':{'amount':equity,'currency':currency},'native_result':{'native_result':native}}}


REQUEST={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN'}


def test_two_stocks_count_repeated_native_bond_once_and_keep_exact_cash():
    rows=[financial_row(),financial_row('SYNTHETIC_B','25')];before=deepcopy(rows)
    out=reconcile(REQUEST,rows)
    assert out['conserved'] and out['status']=='RECONCILED'
    a=out['accounts'][0]
    assert a['aggregate']['equity_used']=='45' and a['aggregate']['bond_used']=='30'
    assert a['aggregate']['available_remaining']=='25'
    assert a['duplicate_native_decisions_counted_once']==['V75:SYNTHETIC_BOND'] and rows==before


def test_individually_valid_plans_cannot_jointly_exceed_one_account():
    out=reconcile(REQUEST,[financial_row(equity='40'),financial_row('SYNTHETIC_B','40')])
    assert not out['conserved'] and out['status']=='BLOCKED'
    assert any(i['code']=='AGGREGATE_BUDGET_EXCEEDED' for i in out['issues'])


@pytest.mark.parametrize('change',['cash','bond','run','amount'])
def test_source_or_native_amount_conflicts_are_not_silently_deduplicated(change):
    rows=[financial_row(),financial_row('SYNTHETIC_B')];f=rows[1]['financial_chain'];n=f['native_result']['native_result']
    if change=='cash':n['work9_request']['work6_funding_account_isolation_result']['cash_eligibility']['available']='99'
    elif change=='bond':n['bond_result']['canonical_v75_output']['per_asset_decisions'][0]['action']='OTHER'
    elif change=='run':f['run_id']='OTHER'
    else:f['canonical_amount']['amount']='999'
    out=reconcile(REQUEST,rows)
    assert out['status']=='BLOCKED' and out['issues']


def test_two_accounts_do_not_each_receive_the_global_stock_capacity():
    rows=[financial_row(),financial_row('SYNTHETIC_B',account='SYNTHETIC_OTHER_ACCOUNT')]
    for row in rows:
        row['financial_chain']['native_result']['native_result']['stock_local_plan']={'family_ceiling_binding':{
            'scope':{'identity':{'portfolio_id':'SYNTHETIC_PORTFOLIO'}},'budget_currency':'USD',
            'budget_amount':'35','capacity':{'synthetic_capacity':'35'},'selected_account_fx_to_budget':'1'}}
    out=reconcile(REQUEST,rows)
    assert not out['conserved'] and len(out['accounts'])==2
    assert out['shared_stock_pools'][0]['new_stock_amount']=='40'
    assert any(i['code']=='MEMBER_SHARED_STOCK_CAPACITY_EXCEEDED' for i in out['issues'])


def test_unknown_inputs_remain_unknown_and_currencies_are_separate():
    partial=reconcile(REQUEST,[{'symbol':'SYNTHETIC_UNAVAILABLE'}])
    assert partial['status']=='SOURCE_INCOMPLETE' and partial['accounts']==[]
    assert not partial['unavailable_amounts_defaulted_to_zero']
    out=reconcile(REQUEST,[financial_row(bond='0'),financial_row('SYNTHETIC_B','25','0',account='SYNTHETIC_TWD',currency='TWD')])
    assert out['conserved'] and len(out['accounts'])==2 and out['cross_currency_total'] is None


def test_member_report_withholds_each_plan_when_the_shared_account_would_be_overdrawn():
    from unittest.mock import patch
    from member_financial_chain import complete_report
    from family_input import digest
    rows=[financial_row(equity='40'),financial_row('SYNTHETIC_B','40')]
    values={r['symbol']:r['financial_chain'] for r in rows}
    for f in values.values():
        f.update(formal_deployment_ready=True,mentor={'synthetic':'native mentor'},issue_codes=[],call_trace=[],
            canonical_v82_output={'synthetic':'original canonical'},drive_persistence_status='PERSISTED_REMOTE_VERIFIED')
    report={'positions':[{'symbol':r['symbol'],'missing_inputs':[],'call_trace':[],'proposed_amount':None} for r in rows],
        'summary':{},'canonical_result':None,'status':'ANALYSIS_PARTIAL'}
    report['report_digest']=digest(report)
    with patch('member_financial_chain.calculate',side_effect=lambda root,descriptor,request,symbol,**kwargs:deepcopy(values[symbol])):
        out=complete_report(report,REQUEST,{'financial_sources':{s:{} for s in values}},HERE.parents[2])
    assert out['status']=='FINANCIAL_FUNDING_RECONCILIATION_BLOCKED'
    assert not out['formal_deployment_ready'] and out['summary']['formal_financial_ready']==0
    for row in out['positions']:
        assert row['proposed_amount'] is None
        assert row['financial_chain']['per_asset_formal_deployment_ready'] is True
        assert not row['financial_chain']['formal_deployment_ready']
        assert row['financial_chain']['native_result']==values[row['symbol']]['native_result']
        assert row['result_digest']==digest({k:v for k,v in row.items() if k!='result_digest'})

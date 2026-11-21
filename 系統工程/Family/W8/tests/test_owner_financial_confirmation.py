"""Synthetic Owner source, side-specific orders and single-count cash tests."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
from family_input import digest
import owner_financial_confirmation as O


def fixture(tmp_path,member='SYN_A',request=None):
    cash={'schema':'Family.PM.OwnerAvailableCashConfirmation.v1','recorded_at':'2026-10-28T12:00:00Z',
        'owner_settlement_confirmation':{'status':'OWNER_CONFIRMED_SETTLED','confirmed_at':'2026-10-28T13:00:00Z'},
        'accounts':[],'separately_approved_additional_cash_TWD':{'SYN_A':'7','SYN_B':'11'},
        'owner_reported_bank_cash':[{'member':'SYN_C','cash_record_id':'SYN_BANK_CASH','amount':'23',
            'planning_count':1,'settlement_link_confirmed':True}]}
    values={'SYN_A':('0','0'),'SYN_B':('0','0'),'SYN_C':('23','2.5'),'SYN_D':('0','1.75')}
    for name,(twd,usd) in values.items():
        for currency,value in [('TWD',twd),('USD',usd)]:
            row={'member':name,'market':'SYNTHETIC_'+currency,'broker':'SYNTHETIC_BROKER',
                'currency':currency,'owner_confirmed_available_cash':value,'account_keys_in_previous_review':['SYN_ACCOUNT']}
            if name=='SYN_C' and currency=='TWD':row['cash_record_reference']='SYN_BANK_CASH'
            cash['accounts'].append(row)
    raw=json.dumps(cash);req=deepcopy(request) if request else {
        'client_id':'SYN_CLIENT','run_id':'SYN_RUN','evaluation_at':'2026-10-29T23:00:00Z',
        'owner':{'client_id':'SYN_CLIENT','account':None},'trade_authorization':'NONE',
        'client_snapshot':{'payload':{'client_id':'SYN_CLIENT','source_sha256':'a'*64,
            'tables':{},'payload_digest':digest({})}},'confirmed_target':{'target_version':1}}
    req['client_snapshot']['payload']['identity']={'family_alias':member.lower()}
    members={name:{'evidence_state':'OWNER_CONFIRMED','official_db_sha256':req['client_snapshot']['payload']['source_sha256'],
        'unfilled_buy_order_count':0,'unfilled_buy_orders':[],'unfilled_buy_notional_by_currency':{'TWD':'0','USD':'0'},
        'additional_deduction_from_approved_cash':'0',
        'cash_carried_forward':{'TWD':{'SYN_A':'7','SYN_B':'11'}.get(name,vals[0]),'overseas_original_currency_record':vals[1]}}
        for name,vals in values.items()}
    data={'schema_version':'Family.PM.OwnerUnfilledBuyConfirmation.v1','source_type':'DIRECT_OWNER_CONFIRMATION',
        'confirmed_by':'SYNTHETIC_OWNER','recorded_at':'2026-10-29T22:59:00Z',
        'scope':{'members':list(members),'fact':'CURRENT_UNFILLED_BUY_ORDERS',
            'confirmation_applies_from_current_turn':True,'sell_orders_covered':False,
            'other_commitments_covered':False,'historical_fills_covered':False,'historical_order_states_rewritten':False},
        'members':members,'prior_cash_source':{'drive_id':'SYN_ACCEPTED_CASH','sha256':sha256(raw.encode()).hexdigest(),'original_source_utf8':raw}}
    path=tmp_path/'SYNTHETIC_OWNER_SOURCE.json'
    def descriptor():
        path.write_text(json.dumps(data))
        return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_OWNER_CONFIRMATION','member':member}
    return req,data,descriptor


def test_current_confirmation_accepts_prior_cash_and_isolates_all_four_members(tmp_path):
    expected={'SYN_A':{'TWD':'7','USD':'0'},'SYN_B':{'TWD':'11','USD':'0'},
        'SYN_C':{'TWD':'23','USD':'2.5'},'SYN_D':{'TWD':'0','USD':'1.75'}}
    for member,values in expected.items():
        req,data,desc=fixture(tmp_path,member);before=deepcopy((req,data));out=O.read(desc(),req)
        assert out['accepted_net_available_by_currency']==values
        assert out['pending_buy_deduction_from_accepted_net_cash']=='0'
        assert out['settlement_status']=='OWNER_CONFIRMED_SETTLED'
        assert all(r['member']==member for r in out['cash_records'])
        assert (req,data)==before
        assert out['sell_orders'] is None and out['other_commitments'] is None
        assert not out['full_order_or_commitment_coverage_asserted']


def test_bank_and_broker_references_are_one_amount_not_two(tmp_path):
    req,data,desc=fixture(tmp_path,'SYN_C');out=O.read(desc(),req)
    linked=[r for r in out['cash_records'] if r['record_id']=='SYN_BANK_CASH']
    assert len(linked)==1 and linked[0]['amount']=='23' and linked[0]['amount_counted']==1
    assert linked[0]['location_reference_count']==2 and not out['bank_location_added_as_cash']


def test_historical_replay_before_owner_fact_retains_original_unknowns(tmp_path):
    req,data,desc=fixture(tmp_path);req['evaluation_at']='2026-10-29T22:58:59Z';before=deepcopy(data)
    assert O.read(desc(),req) is None and data==before


@pytest.mark.parametrize('change',['hash','member','DB','snapshot','trade'])
def test_changed_member_source_or_snapshot_cannot_reuse_confirmation(tmp_path,change):
    req,data,desc=fixture(tmp_path);source=desc()
    if change=='hash':Path(source['local_path']).write_text('{}')
    elif change=='member':source['member']='SYN_B'
    elif change=='DB':req['client_snapshot']['payload']['source_sha256']='b'*64
    elif change=='snapshot':req['client_snapshot']['payload']['tables']['injected']=[]
    else:req['trade_authorization']='ALLOWED'
    with pytest.raises(PermissionError):O.read(source,req)


@pytest.mark.parametrize('change',['count_bool','nonzero_buy','broad_sell_claim','cash_total','prior_bytes'])
def test_false_absence_scope_expansion_and_cash_change_are_rejected(tmp_path,change):
    req,data,desc=fixture(tmp_path)
    if change=='count_bool':data['members']['SYN_A']['unfilled_buy_order_count']=False
    elif change=='nonzero_buy':data['members']['SYN_A']['unfilled_buy_notional_by_currency']['TWD']='1'
    elif change=='broad_sell_claim':data['scope']['sell_orders_covered']=True
    elif change=='cash_total':data['members']['SYN_A']['cash_carried_forward']['TWD']='14'
    else:data['prior_cash_source']['original_source_utf8']+=' '
    with pytest.raises(PermissionError):O.read(desc(),req)


def test_new_zero_buy_component_does_not_clear_sell_or_historical_orders(tmp_path):
    from formal_mode_analysis import order_source,order_result_status
    req,_,desc=fixture(tmp_path);confirmation=O.read(desc(),req)['buy_order_confirmation']
    source=order_source(req,buy_confirmation=confirmation)
    assert source['buy_orders_confirmed_empty'] and source['active_buy_notional_by_currency']=={'TWD':'0','USD':'0'}
    assert source['active_orders'] is None and source['active_sell_orders'] is None
    assert not source['complete_for_open_order_exposure']
    assert source['remaining_required_fields']==['active_sell_orders_and_fill_reconciliation']
    assert order_result_status(source)=='OWNER_CONFIRMED_NO_UNFILLED_BUYS__SELL_SIDE_UNRESOLVED'
    history={'status':'UNKNOWN','orders':[{'state':'REPLACED','order_qty':'5'}]}
    out=O.bind_buy_orders(history,confirmation,req)
    assert out['orders']==history['orders'] and history=={'status':'UNKNOWN','orders':[{'state':'REPLACED','order_qty':'5'}]}


def test_concrete_current_broker_buy_conflict_names_original_field(tmp_path):
    req,_,desc=fixture(tmp_path);confirmation=O.read(desc(),req)['buy_order_confirmation']
    broker={'complete_for_open_order_exposure':True,'as_of':req['evaluation_at'],
        'active_orders':[{'side':'BUY','order_qty':'2','confirmed_filled_qty':'0'}]}
    with pytest.raises(PermissionError,match='broker_order_source.active_orders'):
        O.bind_buy_orders(broker,confirmation,req)
    broker['as_of']='2026-10-28T10:00:00Z'
    retained=O.bind_buy_orders(broker,confirmation,req)
    assert retained['prior_order_source']==broker
    assert retained['active_orders'] is None and not retained['complete_for_open_order_exposure']
    assert retained['active_buy_notional_by_currency']['TWD']=='0'


def test_funding_summary_consumes_accepted_net_cash_without_a_second_deduction(tmp_path):
    from member_funding_summary import reconcile
    req,_,desc=fixture(tmp_path,'SYN_C');out=reconcile(req,[{'symbol':'SYN_ASSET'}],owner_confirmed_facts=O.read(desc(),req))
    assert out['owner_source_acceptance']['accepted_net_available_by_currency']['TWD']=='23'
    assert out['owner_source_acceptance']['additional_pending_buy_cash_deduction']=='0'
    assert not out['owner_source_acceptance']['native_complete_reconciliation_asserted']
    assert out['status']=='SOURCE_INCOMPLETE' and out['cross_currency_total'] is None


def test_original_member_provider_and_formal_gap_consume_owner_buy_fact(tmp_path):
    from test_member_v82_analysis import MemberV82Tests,OnDemandAnalysisProvider
    from member_v82_analysis import MemberV82SourceProducer
    f=MemberV82Tests();f.setUp()
    try:
        req,data,desc=fixture(tmp_path,request={'client_id':f.client,'run_id':'SYN_RUN',
            'evaluation_at':f.at,'owner':{'client_id':f.client},'trade_authorization':'NONE',
            'client_snapshot':{'payload':f.snapshot},'confirmed_target':{'target_version':1}})
        f.snapshot['identity']=deepcopy(req['client_snapshot']['payload']['identity'])
        f.config['market_sources']={s:f.market(s) for s in ('VT','QQQ')}
        f.config['owner_financial_confirmation_source']=desc()
        provider=OnDemandAnalysisProvider(MemberV82SourceProducer(**f.config),repo_root=ROOT)
        request,runner=provider(f.snapshot,{'question':'SYNTHETIC_OWNER_FINANCIAL_SOURCE'})
        report=runner.analyze(request)
        assert report['accepted_owner_financial_facts']['accepted_net_available_by_currency']['TWD']=='7'
        for row in report['positions']:
            gap=row['formal_conclusion']['deployment_gap']
            assert gap['source_bound_inputs']['active_buy_notional_by_currency']['TWD']=='0'
            assert 'active_orders_and_fill_reconciliation' not in gap['missing_fields']
            assert 'active_sell_orders_and_fill_reconciliation' in gap['missing_fields']
        assert not report['database_written'] and report['trade_authorization']=='NONE'
    finally:f.doCleanups()


def test_c7_original_inventory_accepts_known_cash_and_buy_leafs_only(tmp_path,monkeypatch):
    from test_family_c7_source_assembly import original_case
    import member_reconciliation_source
    from family_c7_source_assembly import assemble
    _,_,req,ctx,tactical,identities,_,_=original_case(tmp_path)
    req['evaluation_at']='2026-10-29T23:00:00Z'
    req['trade_authorization']='NONE'
    req['client_snapshot']['payload']['payload_digest']=digest(req['client_snapshot']['payload']['tables'])
    _,_,desc=fixture(tmp_path,request=req);req['client_snapshot']['payload']['identity']={'family_alias':'SYN_A'}
    accepted=O.read(desc(),req)
    normalized={'digest':'b'*64,'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
        'position_values':{'positions':[]},'financial_facts':{'reported_money':{'facts':[]},
            'broker_observations':None,'accepted_owner_financial_facts':accepted}}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *args:deepcopy(normalized))
    ctx['member_reconciliation_source']={'local_path':str(tmp_path/'source.json'),'sha256':'c'*64}
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'artifacts',tactical=tactical,identities=identities)
    cash=next(r for r in out['field_inventory'] if r['field_path']=='family_scope.funding_buckets.owner_confirmed_net_cash.TWD')
    assert cash['value_state']=='KNOWN' and cash['classification']=='EXISTING_BOUND_SOURCE'
    assert out['scope_candidate']['funding_buckets'] is None and out['scope_candidate']['exposure_coverage'] is None
    assert out['original_observations']['accepted_owner_financial_facts']['pending_buy_deduction_from_accepted_net_cash']=='0'

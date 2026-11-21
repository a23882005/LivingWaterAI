"""Synthetic current Owner facts through holdings, orders, funding and C7."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
from family_input import digest
import owner_current_business as O
from test_owner_financial_confirmation import fixture as cash_fixture


def current_case(tmp_path):
    req,_,cash=cash_fixture(tmp_path,'SYN_C')
    data={'schema_version':'Family.PM.OwnerCurrentBusinessFacts.v1','confirmed_by':'SYNTHETIC_OWNER',
        'recorded_at':'2026-10-29T23:00:00Z','trade_authorization':'NONE',
        'existing_holding_preferences_preserved':True,'existing_amounts_and_targets_preserved':True,
        'current_unreported_sell_orders':[],'current_unreported_other_commitments':[],
        'current_unreported_pending_receivables_or_payables':[],
        'unreported_position_quantity':{'SYN_C':{'SYN_ZERO':'0'}},
        'members':{'SYN_C':{'client_id':req['client_id'],'source_db_sha256':'a'*64,
            'no_open_buy_orders':True,'no_open_sell_orders':True,'other_unreported_commitments_absent':True,
            'unreported_pending_receivables_or_payables_absent':True}}}
    path=tmp_path/'SYNTHETIC_CURRENT.json'
    def desc():
        path.write_text(json.dumps(data));return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
            'member':'SYN_C','source_reference':'SYNTHETIC_OWNER_CURRENT'}
    return req,data,desc,cash


def test_current_book_is_bound_but_never_rewrites_history_or_qualifies_market(tmp_path):
    req,data,desc,_=current_case(tmp_path);before=deepcopy((req,data));fact=O.read(desc(),req)
    assert fact['no_open_buy_orders'] and fact['no_open_sell_orders']
    assert not fact['historical_snapshots_rewritten'] and not fact['market_or_valuation_qualification_created']
    assert (req,data)==before
    req['evaluation_at']='2026-10-29T22:59:59Z';assert O.read(desc(),req) is None


@pytest.mark.parametrize('change',['bytes','member','client','db','snapshot','trade','sell','commitment','positive'])
def test_changed_sources_or_expanded_scope_fail_closed(tmp_path,change):
    req,data,desc,_=current_case(tmp_path)
    if change=='sell':data['members']['SYN_C']['no_open_sell_orders']=False
    elif change=='commitment':data['current_unreported_other_commitments']=[{'amount':'1'}]
    elif change=='positive':data['unreported_position_quantity']['SYN_C']['SYN_ZERO']='1'
    source=desc()
    if change=='bytes':Path(source['local_path']).write_text('{}')
    elif change=='member':source['member']='SYN_OTHER'
    elif change=='client':req['client_id']='OTHER'
    elif change=='db':req['client_snapshot']['payload']['source_sha256']='b'*64
    elif change=='snapshot':req['client_snapshot']['payload']['tables']['injected']=[]
    elif change=='trade':req['trade_authorization']='ALLOWED'
    with pytest.raises(PermissionError):O.read(source,req)


def test_only_unreported_positions_become_zero_and_positive_holdings_are_preserved(tmp_path):
    req,_,desc,_=current_case(tmp_path);current=O.read(desc(),req)
    empty={'quantity':None,'source_facts':[]};positive={'quantity':'3','source_facts':[{'quantity':'3'}]}
    assert O.holding_view(empty,'SYN_ZERO',current)['quantity']=='0'
    assert O.holding_view(empty,'SYN_UNREPORTED',current)['quantity']=='0'
    assert O.holding_view(positive,'SYN_OTHER',current)==positive
    ambiguous={'quantity':None,'source_facts':[{'quantity':'1'},{'quantity':'2'}]}
    assert O.holding_view(ambiguous,'SYN_OTHER',current)==ambiguous
    with pytest.raises(PermissionError):O.holding_view(positive,'SYN_ZERO',current)
    with pytest.raises(PermissionError):O.holding_view(ambiguous,'SYN_ZERO',current)
    assert empty=={'quantity':None,'source_facts':[]}


def test_current_order_confirmation_clears_both_sides_without_historical_fill_claim(tmp_path):
    from formal_mode_analysis import order_source
    req,_,desc,_=current_case(tmp_path);fact=O.read(desc(),req)
    out=order_source(req,O.order_confirmation(fact,req))
    assert out['status']=='VERIFIED' and out['active_orders']==[]
    assert out['active_sell_orders']==[] and out['sell_orders_confirmed_empty']
    assert not out['historical_order_or_fill_completeness_asserted']


def test_existing_logical_categories_count_linked_bank_cash_once_and_preserve_records(tmp_path):
    import owner_financial_confirmation as cash_reader
    req,_,desc,cash=current_case(tmp_path)
    req['client_snapshot']['payload']['tables']={'portfolio_account':[
        {'account_key':'SYN_ACCOUNT','account_currency':'TWD','account_label':'台股'},
        {'account_key':'SYN_ACCOUNT_US','account_currency':'USD','account_label':'美股'}],
        'holding_policy_confirmation':[{'policy':'HOLD_AS_IS','asset_id':'SYN_HELD'}]}
    req['client_snapshot']['payload']['payload_digest']=digest(req['client_snapshot']['payload']['tables'])
    accepted=cash_reader.read(cash(),req)
    # Both original source categories are explicit; neither is a real number.
    for record in accepted['cash_records']:
        if record['currency']=='USD':record['account_key_candidates']=['SYN_ACCOUNT_US']
    before=deepcopy((req,accepted));out=O.logical_portfolio(req,accepted,O.read(desc(),req))
    assert out['accepted_net_available_by_currency']=={'TWD':'23','USD':'2.5'}
    assert sum(float(b['cash_amount']) for b in out['logical_accounts'] if b['owner']['currency']=='TWD')==23
    assert out['reported_preference_records']['holding_policy_confirmation']==req['client_snapshot']['payload']['tables']['holding_policy_confirmation']
    assert all(not b['real_account_number_created'] and not b['broker_connection_verified'] for b in out['logical_accounts'])
    assert (req,accepted)==before


def test_c7_binds_current_cash_and_business_coverage_but_waits_for_market_nav(tmp_path,monkeypatch):
    from test_family_c7_source_assembly import original_case,ROOT
    import member_reconciliation_source
    from family_c7_source_assembly import assemble
    _,_,req,ctx,tactical,identities,_,_=original_case(tmp_path)
    current={'source_reference':'SYNTHETIC_CURRENT','available_at':req['evaluation_at'],
        'source_descriptor':{'local_path':'SYNTHETIC','sha256':'a'*64}}
    portfolio={'logical_accounts':[{'owner':req['owner'],'cash_amount':'23'}],
        'source':current,'reported_cap_records':{},'reported_preference_records':{}}
    normalized={'owner_current_portfolio':portfolio,'position_values':{'positions':[]},'digest':'b'*64,
        'source_db_sha256':req['client_snapshot']['payload']['source_sha256']}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
    ctx['member_reconciliation_source']={'local_path':'SYNTHETIC','sha256':'c'*64}
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities)
    scope=out['scope_candidate'];assert scope['funding_buckets'][0]['cash_amount']=='23'
    assert scope['funding_buckets'][0]['reserved_amount']=='0' and scope['exposure_coverage']['complete']
    assert scope['current_nav'] is None and scope['exposures'] is None and scope['preference_locks'] is None
    assert scope['portfolio_caps'][0]['applicability']=='NOT_APPLICABLE'
    assert [v['requirement_id'] for v in out['source_qualification']['required_original_facts']]==['current_nav']
    assert out['source_qualification']['engineering_only_fields']==[]
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and 'source_descriptor' not in out


def test_native_source_tail_does_not_reopen_owner_resolved_cash_or_order_gaps(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from test_family_c7_source_assembly import original_case,ROOT
    import member_reconciliation_source,v70_tactical_input,family_c7_source_assembly as C
    _,_,req,ctx,tactical,identities,_,_=original_case(tmp_path)
    current={'source_reference':'SYNTHETIC_CURRENT','available_at':req['evaluation_at'],
        'source_descriptor':{'local_path':'SYNTHETIC','sha256':'a'*64}}
    normalized={'owner_current_portfolio':{'logical_accounts':[{'owner':req['owner'],'cash_amount':'23'}],
        'source':current,'reported_cap_records':{},'reported_preference_records':{}},
        'position_values':{'positions':[]},'digest':'b'*64,
        'source_db_sha256':req['client_snapshot']['payload']['source_sha256']}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
    monkeypatch.setattr(v70_tactical_input,'calculate',lambda *a,**k:deepcopy(tactical))
    # The original raw account export is absent; the current accepted net cash
    # supplies that business fact without qualifying dated broker observations.
    producer=SimpleNamespace(root=ROOT,db_path=None,symbol='QQQ',class_source=None,product_sources={},
        v70_strategic_policy=None,fx_observation=None,verified_macro_feed_source=None,order_confirmation=None,
        family_c7_assembly_inputs={'schema_version':'Family.W8.C7AssemblyInputs.v1',
            'artifact_directory':str(tmp_path/'native_private'),
            'member_reconciliation_source':{'local_path':'SYNTHETIC','sha256':'c'*64}})
    import native_asset_source
    monkeypatch.setattr(native_asset_source,'classification',lambda symbol,*a:identities.get(symbol,{}))
    out=C.assemble_original_producers(producer,req,ctx,SimpleNamespace(payload={'positions':[]}),{})
    assert out['source_qualification']['engineering_only_fields']==[]
    assert not any('SETTLED_CASH' in i['code'] or 'AVAILABLE_CASH_AND' in i['code']
        or 'ORDER_ASOF_LIFECYCLE' in i['code'] for i in out['issues'])
    assert out['scope_candidate']['funding_buckets'][0]['cash_amount']=='23'


def test_cash_weight_is_preserved_when_original_v70_two_leg_method_is_missing(tmp_path,monkeypatch):
    from test_family_c7_source_assembly import original_case,ROOT
    import member_reconciliation_source
    from family_c7_source_assembly import SourceAssembler
    _,_,req,ctx,_,identities,_,_=original_case(tmp_path)
    req['confirmed_target']['payload']['draft']['target_lines'].append({
        'instrument_id':'SYN_CASH','ticker':None,'asset_type':'CASH','weight':{'value_state':'KNOWN','value':'0.05'}})
    assembler=SourceAssembler(ROOT,req,ctx,tmp_path/'private');assembler.current_normalized={}
    assert assembler.tactical(None,{}) is None
    assert assembler.issues[-1]['code']=='C7_APPROVED_CASH_WEIGHT_TO_V70_STRATEGIC_BASE_METHOD_REQUIRED'
    assert req['confirmed_target']['payload']['draft']['target_lines'][-1]['weight']['value']=='0.05'


def test_strategy_lineage_pins_raw_bootstrap_without_qualifying_unconsumed_legacy_cash(tmp_path):
    from member_reconciliation_source import source_files
    legacy=tmp_path/'SYNTHETIC_OLD_CASH.json';legacy.write_text('{}')
    producer=tmp_path/'SYNTHETIC_PRODUCER.json';producer.write_text(json.dumps({
        'configuration':{'legacy_cash':{'local_path':str(legacy),'sha256':'a'*64},
            'v70_strategic_policy':{'client_id':'SYNTHETIC_CLIENT','stock_percent':60,'bond_percent':40,
                'source_reference':'SYNTHETIC_APPROVED_STRATEGIC_POLICY'}}}))
    desc={'local_path':str(producer),'sha256':sha256(producer.read_bytes()).hexdigest()}
    pinned=source_files({'financial_producer_sources':{'SYN_ASSET':desc}},'2026-10-29T23:00:00Z')
    assert len(pinned)==1 and pinned[0]['sha256']==desc['sha256']
    producer.write_text('{}')
    with pytest.raises(PermissionError):source_files({'financial_producer_sources':{'SYN_ASSET':desc}},'2026-10-29T23:00:00Z')


@pytest.mark.parametrize('quote_currency,required',[('TWD',False),('USD',True),(None,True)])
def test_global_member_gap_uses_actual_quote_unit_without_inventing_fx(quote_currency,required):
    from formal_mode_analysis import target_fx_required
    req={'owner':{'currency':None}};market={'market_identity':{'currency':quote_currency}}
    target={'value_state':'KNOWN','amount':'100','currency':'TWD'}
    assert target_fx_required(req,market,target) is required

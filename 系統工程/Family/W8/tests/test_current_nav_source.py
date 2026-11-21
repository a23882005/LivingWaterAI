"""Synthetic NAV approval, official quotes, temporal scope and native consumers."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
from family_input import digest
from current_market_contract import read,portfolio_reference
from current_nav_source import apply_official_quote
from test_current_market_contract import contract_case


def nav_case(tmp_path):
    req,data,desc,fx=contract_case(tmp_path)
    original={'symbol':'SYN_ASSET','quantity':'2','source_kind':'SYNTHETIC_OWNER'}
    official_row={'Date':'1151029','SecuritiesCompanyCode':'SYN_ASSET','CompanyName':'SYNTHETIC_BOND','Close':'51.00'}
    official=tmp_path/'SYN_OFFICIAL.json';official.write_text(json.dumps([official_row]))
    oh=sha256(official.read_bytes()).hexdigest();url='https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'
    common={k:req[k] for k in ('client_id','run_id','evaluation_at')};common['source_db_sha256']='a'*64
    current={**common,'source_sha256':'c'*64}
    accepted={**common,'source':{'source_sha256':'d'*64},'accepted_net_available_by_currency':{'TWD':'23','USD':'2.5'}}
    expected={'symbol':'SYN_ASSET','quantity':'2','currency':'TWD','price':'51.00','observed_market_date':'2026-10-29',
        'security_value_native':'102.00','security_value_TWD':'102.00','price_source_sha256':oh,
        'source_representation_index':0,'original_position_source':deepcopy(original)}
    member={'client_id':req['client_id'],'source_db_sha256':'a'*64,
        'owner_current_confirmation_source_sha256':'c'*64,'accepted_funding_source_sha256':'d'*64,
        'positions':[expected],'accepted_net_cash_by_currency':{'TWD':'23','USD':'2.5'},
        'cash_reporting_TWD':'103','current_project_portfolio_NAV_TWD':'205',
        'qualification':'PM_VERIFIED_SOURCE_FOR_CURRENT_PROJECT_NAV_INPUT',
        'all_positive_positions_valued':True,'unreported_positions_orders_and_commitments_absent_by_explicit_Owner_policy':True,
        'cash_counted_once':True,'new_buy_permission_created':False,'approved_target_pool_rebased':False,
        'historical_PIT_or_qP_qV_qualified':False}
    nav={'schema_version':'Family.PM.CurrentProjectNAVSourceQualification.v1','verified_at':'2026-10-29T22:30:00Z',
        'source_availability_cutoff':'2026-10-29T22:30:00Z','accepted_code_baseline':'a'*40,'trade':'NONE',
        'qualification':'APPROVED_PM_NAV_SOURCE_FOR_IMPLEMENTATION__NATIVE_C7_ACCEPTANCE_PENDING',
        'members':{'SYN_C':member},'reporting_FX_original_reader_result':fx,
        'official_TPEX_selected_receipt':{'source_url':url,'retrieved_at':'2026-10-29T22:00:00Z',
            'raw_sha256':oh,'bytes':official.stat().st_size,'selected_rows':[deepcopy(official_row)]}}
    p=tmp_path/'SYN_NAV_APPROVAL.json'
    def descriptor():
        p.write_text(json.dumps(nav));source=desc()
        source['nav_qualification_source']={'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),
            'source_reference':'SYN_PM_NAV_AUTHORITY','target_version':1,
            'official_source':{'local_path':str(official),'sha256':oh,'source_reference':url}}
        return source
    values={**common,'fx_observation':fx,'positions':[{'symbol':'SYN_ASSET','quantity':'2','amount':'100','currency':'TWD',
        'observed_close':'50','observed_market_date':'2026-10-29','market_source_sha256':data['sources']['SYN_ASSET']['raw_sha256'],
        'reporting_amount_TWD':'100','quantity_source':original,'issue':None,
        'current_reference_quote':{'original_final_close_verified':False,'final_close_qualification_issues':[{'reason':'SYN_CONSERVATIVE_CLOSE'}]}}]}
    coverage={'holding_and_target_rows':[{'symbol':'SYN_ASSET','route':'V75','target_lines':[]}]}
    return req,nav,descriptor,values,coverage,accepted,current


def test_official_quote_and_recomputed_nav_qualify_only_current_project_sources(tmp_path):
    req,nav,desc,values,coverage,cash,current=nav_case(tmp_path);contract=read(desc(),req)
    before=deepcopy((req,nav,coverage,cash,current));apply_official_quote(values['positions'][0],contract)
    out=portfolio_reference(req,coverage,values,cash,current,contract)
    assert out['positions_plus_accepted_cash_TWD']=='205.00' and out['formal_NAV_source_qualified']
    assert out['positions'][0]['observed_close']=='51.00' and out['formal_source_qualification_dependencies']==[]
    assert out['positions'][0]['previous_source_dated_quote']['amount']=='100'
    assert not out['new_buy_permission_created'] and not out['historical_PIT_or_qP_qV_qualified']
    assert out['additional_cash_target_reserve_deducted']=='0' and out['cash_counted_once']
    assert (req,nav,coverage,cash,current)==before


def test_new_approval_never_backfills_accepted_earlier_reference_replay(tmp_path):
    req,_,desc,values,coverage,cash,current=nav_case(tmp_path);req['evaluation_at']='2026-10-29T22:15:00Z'
    contract=read(desc(),req);assert 'nav_source_qualification' not in contract
    old=deepcopy(values);apply_official_quote(values['positions'][0],contract);assert values==old


@pytest.mark.parametrize('change',['client','db','target','member','trade','qualification','scope','bytes','official_hash','official_url','official_row','official_future','bank'])
def test_nav_approval_cannot_cross_source_identity_or_authorized_scope(tmp_path,change):
    req,nav,desc,*_=nav_case(tmp_path)
    member=nav['members']['SYN_C']
    if change=='client':member['client_id']='OTHER'
    elif change=='db':member['source_db_sha256']='e'*64
    elif change=='member':nav['members']={'OTHER':member}
    elif change=='trade':nav['trade']='YES'
    elif change=='qualification':nav['qualification']='REFERENCE_ONLY'
    elif change=='scope':member['historical_PIT_or_qP_qV_qualified']=True
    elif change=='official_row':nav['official_TPEX_selected_receipt']['selected_rows'][0]['Close']='52'
    elif change=='official_future':nav['official_TPEX_selected_receipt']['retrieved_at']='2026-10-29T22:45:00Z'
    elif change=='bank':nav['reporting_FX_original_reader_result']={**nav['reporting_FX_original_reader_result'],'quote_per_base':'33'}
    source=desc();nested=source['nav_qualification_source']
    if change=='target':nested['target_version']=2
    elif change=='bytes':Path(nested['local_path']).write_text('{}')
    elif change=='official_hash':Path(nested['official_source']['local_path']).write_text('[]')
    elif change=='official_url':nested['official_source']['source_reference']='https://example.test/quote'
    with pytest.raises(PermissionError):read(source,req)


@pytest.mark.parametrize('change',['owner','funding','cash','holding','position_source','price_hash','total','duplicate'])
def test_nav_replays_each_original_holding_cash_and_total_without_accepting_pm_arithmetic_alone(tmp_path,change):
    req,nav,desc,values,coverage,cash,current=nav_case(tmp_path)
    if change=='total':nav['members']['SYN_C']['current_project_portfolio_NAV_TWD']='999'
    contract=read(desc(),req);apply_official_quote(values['positions'][0],contract)
    if change=='owner':current['source_sha256']='e'*64
    elif change=='funding':cash['source']['source_sha256']='e'*64
    elif change=='cash':cash['accepted_net_available_by_currency']['TWD']='46'
    elif change=='holding':values['positions'][0]['quantity']='3'
    elif change=='position_source':values['positions'][0]['quantity_source']['source_kind']='OTHER'
    elif change=='price_hash':values['positions'][0]['market_source_sha256']='e'*64
    elif change=='duplicate':values['positions'].append(deepcopy(values['positions'][0]))
    with pytest.raises(PermissionError):portfolio_reference(req,coverage,values,cash,current,contract)


@pytest.mark.parametrize('currency',['TWD','USD'])
def test_qualified_nav_feeds_original_c7_capacity_current_weights_and_reporting_fx(tmp_path,monkeypatch,currency):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import SourceAssembler
    import member_reconciliation_source
    m,ci,req,ctx,tactical,ids,_,_=original_case(tmp_path);req['owner']['currency']=currency
    at=req['evaluation_at'];owner=deepcopy(req['owner']);owner['currency']='TWD'
    current_source={'source_reference':'SYN_OWNER','available_at':at,'source_descriptor':{'sha256':'c'*64}}
    portfolio={'logical_accounts':[{'owner':owner,'cash_amount':'940'}],
        'source':current_source,'reported_cap_records':{},'reported_preference_records':{}}
    if currency=='USD':portfolio['logical_accounts'].append({'owner':deepcopy(req['owner']),'cash_amount':'0'})
    approval={'available_at':at,'source_descriptor':{'source_reference':'SYN_PM_NAV','sha256':'d'*64}}
    reference={'formal_NAV_source_qualified':True,'project_NAV_source_qualification':approval,
        'positions_plus_accepted_cash_TWD':'1000','reporting_FX':{'quote_per_base':'32'},
        'positions':[{'symbol':'QQQ','route':'V82','reference_amount_TWD':'60','amount':'60','currency':'TWD',
            'account_key':owner['account'],'quantity_source':{'source':'SYN_HOLDING'}}]}
    normalized={'owner_current_portfolio':portfolio,'position_values':{'positions':[]},'digest':'b'*64,
        'source_db_sha256':req['client_snapshot']['payload']['source_sha256']}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
    ctx['member_reconciliation_source']={'local_path':'SYNTHETIC','sha256':'c'*64}
    assembler=SourceAssembler(ROOT,req,ctx,tmp_path/'private');assembler.identities=ids;assembler.observations={}
    scope={'total_stock_ceiling':{'accounting_base':{'base_id':'SYN_APPROVED_UNCHANGED'}}}
    before=deepcopy(req);result=assembler.qualified_current(scope,reference,portfolio)
    assert scope['current_nav']['amount']==(1000 if currency=='TWD' else 31.25)
    assert result['positions'][0]['weight']['value']==0.06 and scope['preference_locks']==[]
    ci['allocations']['current_allocation']['snapshot']=result
    native_scope={'budget_currency':currency,'exposures':scope['exposures'],
        'exposure_coverage':{'confirmed_effects_already_applied':[]},
        'budget_normalizations':scope['budget_normalizations'],
        'total_stock_ceiling':scope['total_stock_ceiling']}
    if currency=='USD':assert scope['budget_normalizations'][0]['quote_per_base']=='0.03125'
    # Original C confirmed-book reconciliation consumes these values.
    if currency=='TWD':m.validate_confirmed_book(native_scope,ci,at)
    assert sum(p['weight']['value'] for p in result['positions'])==1
    assert req==before and result['confirmation_status']=='NOT_APPLICABLE'
    if currency=='TWD':
        from family_c7_source_assembly import assemble
        reference.update(contract={'available_at':at},current_stock_exposure_TWD='60',allocation_reference_gaps=[])
        normalized['current_portfolio_reference']=reference
        full=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'complete',tactical=tactical,identities=ids)
        assert full['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING'
        assert full['source_qualification']['required_original_facts']==[]
        full_scope=full['scope_candidate'];ci['identity']=deepcopy(full_scope['identity'])
        ci['source_references']+=full['source_references']
        ci['allocations']['current_allocation']['snapshot']=full['current_allocation']
        ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='TWD',value_state='KNOWN')
        native=m.capacity(full_scope,ci,at);m.validate_confirmed_book(full_scope,ci,at)
        assert native['occupied']=='60' and native['incremental_capacity']=='40'


@pytest.mark.parametrize('legacy_kind',[None,'BROAD_ETF','BOND_ETF'])
def test_current_confirmed_holding_classification_fills_legacy_omissions_and_rejects_conflicts(tmp_path,monkeypatch,legacy_kind):
    import family_c7_source_assembly as assembly
    import member_reconciliation_source
    from test_family_c7_source_assembly import original_case
    _,_,req,ctx,tactical,ids,_,_=original_case(tmp_path)
    # The current accepted holding may be absent from old target/registry IDs.
    held='SYN_HELD_OUTSIDE_LEGACY_REGISTRY';ids[held]={'asset_type':legacy_kind}
    normalized={'original_classification_sources':{'classification_source':{'sha256':'a'*64},'product_sources':{}},
        'current_portfolio_reference':{'positions':[{'symbol':held}]},
        'position_values':{'positions':[]},'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],'digest':'b'*64}
    monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
    called=[]
    def current_identities(root,request,source,products,reported_symbols=()):
        called.extend(reported_symbols);return {held:{'asset_type':'BROAD_ETF','source_sha256':'a'*64}}
    monkeypatch.setattr(assembly,'original_identities',current_identities)
    ctx['member_reconciliation_source']={'local_path':'SYNTHETIC','sha256':'c'*64}
    builder=assembly.SourceAssembler(ROOT,req,ctx,tmp_path/'private')
    if legacy_kind=='BOND_ETF':
        with pytest.raises(PermissionError,match='C7_CURRENT_AND_LEGACY_PRODUCT_BUCKET_CONFLICT'):
            builder.build(tactical=tactical,identities=ids)
    else:
        builder.build(tactical=tactical,identities=ids)
        assert assembly.asset_kind(builder.identities[held])=='equity ETF'
    assert called==[held]

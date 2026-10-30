"""Raw synthetic business records -> schema83; no household completion claim."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from family_c7_source_assembly import assemble,read_facts,DIRECT,ADAPTER,MISSING
from family_input import digest
from native_target_source import produce
from test_c7_family_ceiling import family_case


def original_case(tmp_path):
    module,ci,scope,at=family_case();owner=scope['family_owner'];approved=scope['approved_long_term_target']
    rows=[];identities={}
    for p in approved['positions']:
        stock='股票' in p['asset_type'] or 'equity' in p['asset_type'].lower()
        identities[p['ticker']]={'engine_route':'V82_TECHNICAL_OBSERVATIONS' if stock else 'V75_PREDICATES',
            'asset_type':'EQUITY_ETF' if stock else 'BOND_ETF','quote_currency':'TWD'}
        rows.append({'instrument_id':p['instrument_id'],'ticker':p['ticker'],'asset_type':identities[p['ticker']]['asset_type'],
            'weight':{'value_state':'KNOWN','value':str(p['weight']['value'])},
            'target_amount':{'value_state':'KNOWN','amount':str(p['portfolio_amount']['amount']),'currency':'TWD'}})
    request={'client_id':ci['identity']['client_id'],'run_id':ci['identity']['run_id'],'evaluation_at':at,'owner':owner,
        'client_snapshot':{'payload':{'client_id':ci['identity']['client_id'],'source_sha256':scope['source_db_sha256'],
            'tables':{'portfolio_account':[{'account_key':owner['account']}],'portfolio_position':[]}}},
        'confirmed_target':{'target_version':1,'payload':{'draft':{'allocation_id':approved['allocation_id'],
            'target_lines':rows,'denominator':{'value_state':'KNOWN','amount':str(approved['denominator']['amount']),'currency':'TWD'}},
            'confirmation_evidence':{'action':'READ_EXISTING_APPROVAL','confirmed_at':approved['confirmed_at'],'confirmed_by':approved['confirmed_by']}}},
        'macro_snapshot':{'asOf':at,'source_sha256':'b'*64,'digest':'c'*64}}
    context={'native_target_source':produce(request)}
    tactical={'allocation_base':deepcopy(request['confirmed_target']['payload']['draft']['denominator']),
        'native_execution_currency':'TWD','native_currency_amounts':{'stock':'100','bond':'0','dry_powder':'900'},
        'source_feed_sha256':'b'*64,'feed_as_of':at,
        'source_html_sha256':sha256((ROOT/'系統工程/總經V70/V70-3-27.html').read_bytes()).hexdigest()}
    facts={'schema_version':'Family.W8.PortfolioReconciliationFacts.v1','client_id':request['client_id'],
        'source_db_sha256':scope['source_db_sha256'],'target_version':1,'data_provenance':'SOURCE_BACKED',
        'source_reference':'SYNTHETIC_ORIGINAL_ACCOUNT_EXPORT','as_of':at,'available_at':at,
        'accounts':[{'owner':owner,'binding_evidence_state':'VERIFIED','binding_source_reference':'SYNTHETIC_OWNER_BINDING',
            'bucket_id':'SYNTHETIC_CASH','cash_basis':'NET_AVAILABLE','authorized_incremental_amount':'50','net_asset_value':'1000',
            'authorization_evidence_state':'VERIFIED','authorization_source_reference':'SYNTHETIC_EXPLICIT_ACCOUNT_AUTHORIZATION','authorization_confirmed_at':at,
            'cash':{'total_cash':'50','settled_cash':'50','unsettled_cash':'0','reserved_cash':'10','available_cash':'40',
                'settlement_evidence_state':'VERIFIED','source_reference':'SYNTHETIC_SETTLEMENT_RECONCILIATION'},
            'positions':[{'position_id':'SYNTHETIC_POSITION','economic_effect_ids':['SYNTHETIC_POSITION_EFFECT'],
                'asset_id':'QQQ','ticker':'QQQ','asset_class':'STOCK','quantity':'60','price':'1','currency':'TWD'},
                {'position_id':'SYNTHETIC_CORE_POSITION','economic_effect_ids':['SYNTHETIC_CORE_EFFECT'],
                'asset_id':'CORE.US','ticker':'CORE.US','asset_class':'STOCK','quantity':'0','price':'1','currency':'TWD'},
                {'position_id':'SYNTHETIC_SGOV_POSITION','economic_effect_ids':['SYNTHETIC_SGOV_EFFECT'],
                'asset_id':'SGOV','ticker':'SGOV','asset_class':'BOND','quantity':'890','price':'1','currency':'TWD'}]}],
        'coverage':{'positions_complete':True,'orders_complete':True,'other_commitments_complete':True,
            'fills_reconciled':True,'protection_complete':True,'cap_applicability_complete':True,
            'empty_portfolio_asserted':False,'confirmed_effects_already_applied':[]},
        'protection_confirmation':{'evidence_state':'VERIFIED','source_reference':'SYNTHETIC_NO_LOCKS_CONFIRMATION',
            'confirmed_by':'SYNTHETIC_OWNER','confirmed_at':at},
        'portfolio_caps':[{'cap_id':'SYNTHETIC_NO_ADDITIONAL_CAP','applicability':'NOT_APPLICABLE',
            'applicability_reason':'SYNTHETIC_EXPLICIT_OWNER_CAP_REVIEW','evidence_state':'VERIFIED','source_reference':'SYNTHETIC_CAP_SOURCE'}],
        'orders':[{'event_id':'SYNTHETIC_BUY','remaining_economic_effect_ids':['SYNTHETIC_UNFILLED_EFFECT'],
            'account':owner['account'],'asset_id':'QQQ','side':'BUY','state':'OPEN','order_quantity':'10',
            'filled_quantity':'0','remaining_quantity':'10','commitment_price':'1','price_basis':'ORIGINAL_LIMIT_PRICE','intent_id':'SYNTHETIC_INTENT'}],
        'fills':[],'other_commitments':[{'event_id':'SYNTHETIC_OTHER','economic_effect_ids':['SYNTHETIC_OTHER_EFFECT'],
            'account':owner['account'],'asset_id':'QQQ','amount':'5'}],
        'confirmed_releases':[],'holding_directives':[],'reporting_fx':[]}
    identities['CORE.US']={'engine_route':'V82_TECHNICAL_OBSERVATIONS','asset_type':'EQUITY_ETF','quote_currency':'TWD'}
    for p in facts['accounts'][0]['positions']:
        p.update(price_basis='REPORTED_MARKET_PRICE',price_as_of=at,price_source_reference='SYNTHETIC_MARKET_SNAPSHOT')
    def descriptor():
        path=tmp_path/'SYNTHETIC_RAW_PORTFOLIO_FACTS.json';path.write_text(json.dumps(facts))
        return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    return module,ci,request,context,tactical,identities,facts,descriptor


def build(tmp_path,*,facts=True):
    m,ci,req,ctx,tactical,identities,data,desc=original_case(tmp_path)
    result=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private_sources',tactical=tactical,
        identities=identities,portfolio_facts_source=desc() if facts else None)
    return m,ci,req,ctx,tactical,identities,data,desc,result


def test_raw_records_assemble_schema83_and_replay_original_capacity_without_mutating_approval(tmp_path):
    m,ci,req,ctx,t,ids,f,desc,out=build(tmp_path);before=deepcopy(req)
    assert out['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING' and not out['issues']
    scope=out['scope_candidate'];ci['identity']=deepcopy(scope['identity'])
    ci['source_references']+=out['source_references'];ci['allocations']['current_allocation']['snapshot']=out['current_allocation']
    ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='TWD',value_state='KNOWN')
    cap=m.capacity(scope,ci,req['evaluation_at']);m.validate_confirmed_book(scope,ci,req['evaluation_at'])
    assert cap['occupied']=='75' and cap['incremental_capacity']=='25'
    assert req==before and out['new_confirmation_created'] is False
    saved=json.loads(Path(out['source_descriptor']['local_path']).read_text())
    assert saved['family_scope']['approved_long_term_target']['allocation_id']==req['confirmed_target']['payload']['draft']['allocation_id']


def test_partial_sources_retain_approval_and_v70_and_name_each_missing_root(tmp_path):
    *_,out=build(tmp_path,facts=False)
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and 'source_descriptor' not in out
    assert out['scope_candidate']['total_stock_ceiling']['amount']=='100'
    assert out['scope_candidate']['approved_long_term_target']['confirmation_status']=='CONFIRMED'
    inventory={r['field_path']:r for r in out['field_inventory']}
    assert inventory['family_scope.approved_long_term_target']['classification']==DIRECT
    assert inventory['family_scope.current_nav']['classification']==ADAPTER
    assert inventory['family_scope.funding_buckets']['classification']==MISSING
    assert not out['unknown_values_defaulted_to_zero']
    assert all(r['source_locators'] and r['next_responsibility'] and r['producer'] and r['consumer'] for r in out['field_inventory'])


@pytest.mark.parametrize('change',['client','db','version','time','missing_account','native_result','unverified_binding'])
def test_original_fact_scope_cutoff_and_kind_are_enforced(tmp_path,change):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    if change=='client':f['client_id']='OTHER'
    elif change=='db':f['source_db_sha256']='e'*64
    elif change=='version':f['target_version']=2
    elif change=='time':f['available_at']='2099-01-01T00:00:00Z'
    elif change=='missing_account':f['accounts']=[]
    elif change=='native_result':f['native_result']={}
    else:f['accounts'][0]['binding_evidence_state']='UNKNOWN'
    with pytest.raises(PermissionError):read_facts(desc(),req)


@pytest.mark.parametrize('state',['PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'])
def test_pending_order_keeps_only_remaining_buy_exposure(tmp_path,state):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);order=f['orders'][0]
    order.update(state=state,order_quantity='15',filled_quantity='5',remaining_quantity='10')
    if state in ('CANCEL_PENDING','REPLACE_PENDING'):
        order['last_acknowledged_commitment']={'order_quantity':'15','commitment_price':'1',
            'source_reference':'SYNTHETIC_LAST_BROKER_ACK','as_of':req['evaluation_at']}
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    buy=next(r for r in out['scope_candidate']['exposures'] if r['kind']=='ACTIVE_BUY_RESERVATION')
    assert buy['amount']=='10' and buy['lifecycle_state']==state


@pytest.mark.parametrize('state',['CANCEL_PENDING','REPLACE_PENDING'])
def test_pending_request_cannot_replace_last_acknowledged_quantity_or_price(tmp_path,state):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);order=f['orders'][0]
    order.update(state=state,order_quantity='5',remaining_quantity='5')
    order['last_acknowledged_commitment']={'order_quantity':'10','commitment_price':'1',
        'source_reference':'SYNTHETIC_LAST_BROKER_ACK','as_of':req['evaluation_at']}
    with pytest.raises(ValueError,match='PENDING_COMMITMENT_REDUCTION_UNCONFIRMED'):
        assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())


def test_two_accounts_same_instrument_aggregate_current_once_and_keep_separate_exposures(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    second=deepcopy(f['accounts'][0]);second['owner']['account']='SECOND_ACCOUNT';second['bucket_id']='SECOND_CASH'
    second['authorized_incremental_amount']='0';second['net_asset_value']='10'
    second['cash'].update(total_cash='0',settled_cash='0',reserved_cash='0',available_cash='0')
    second['positions']=[deepcopy(second['positions'][0])]
    second['positions'][0].update(position_id='SECOND_POSITION',economic_effect_ids=['SECOND_EFFECT'],quantity='10')
    f['accounts'].append(second);req['client_snapshot']['payload']['tables']['portfolio_account'].append({'account_key':'SECOND_ACCOUNT'})
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    assert out['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING'
    qqq=[p for p in out['current_allocation']['positions'] if p['instrument_id']=='QQQ']
    assert len(qqq)==1 and qqq[0]['portfolio_amount']['amount']==70
    assert out['scope_candidate']['current_nav']['amount']==1010
    exposures=[r for r in out['scope_candidate']['exposures'] if r['asset_id']=='QQQ' and r['kind']=='CONFIRMED_POSITION']
    assert len(exposures)==2 and {r['owner']['account'] for r in exposures}=={req['owner']['account'],'SECOND_ACCOUNT'}
    ci['identity']=deepcopy(out['scope_candidate']['identity']);ci['source_references']+=out['source_references']
    ci['allocations']['current_allocation']['snapshot']=out['current_allocation']
    ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='TWD',value_state='KNOWN')
    assert m.capacity(out['scope_candidate'],ci,req['evaluation_at'])['incremental_capacity']=='15'
    m.validate_confirmed_book(out['scope_candidate'],ci,req['evaluation_at'])


def test_duplicate_position_identity_is_not_silently_overwritten(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    f['accounts'][0]['positions'][1]['position_id']=f['accounts'][0]['positions'][0]['position_id']
    with pytest.raises(ValueError,match='POSITION_IDENTITY_CONFLICT'):
        assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())


@pytest.mark.parametrize('change',['cash_net','nav','order_quantity','fill_not_applied','cap_currency'])
def test_business_reconciliation_errors_are_not_hidden_by_complete_flags(tmp_path,change):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    if change=='cash_net':f['accounts'][0]['cash']['available_cash']='51'
    elif change=='nav':f['accounts'][0]['net_asset_value']='999'
    elif change=='order_quantity':f['orders'][0]['remaining_quantity']='9'
    elif change=='fill_not_applied':f['fills']=[{'fill_id':'SYNTHETIC_FILL','account':req['owner']['account'],'asset_id':'QQQ','applied_to_position_id':'MISSING','quantity':'1'}]
    else:f['portfolio_caps']=[{'cap_id':'SYNTHETIC_CAP','applicability':'REQUIRED','value_state':'KNOWN','amount':'100',
        'currency':'USD','accounting_base_id':'WRONG','evidence_state':'VERIFIED','source_reference':'SYNTHETIC'}]
    with pytest.raises(ValueError):assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())


def test_missing_complete_lists_do_not_become_empty_books_or_empty_protection(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);f.pop('orders');f.pop('holding_directives')
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES'
    assert out['scope_candidate']['exposure_coverage'] is None and out['scope_candidate']['preference_locks'] is None


def test_assembled_original_source_reaches_real_work6_and_work7_adapters(tmp_path,monkeypatch):
    # Work5 financial contents use the existing labelled synthetic fixture;
    # raw-source assembly, Work6 reader and Work7 integration execute for real.
    from test_c7_family_ceiling import read_case
    from test_c7_engine import original_case as old_case
    from c7_engine import load_original_configuration_module,run_c7_engine
    m,ci,old_scope,at,adjustment,calls,_=read_case(monkeypatch)
    *_,out=build(tmp_path)
    scope=out['scope_candidate'];ci['identity']=deepcopy(scope['identity'])
    ci['source_references']+=out['source_references']
    ci['allocations']['current_allocation']={'value_state':'KNOWN','snapshot':deepcopy(out['current_allocation']),'reason':None}
    ci['allocations']['final_target']={'value_state':'KNOWN','snapshot':deepcopy(scope['approved_long_term_target']),'reason':None}
    base=ROOT/'系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/contracts_c7'
    work6=load_original_configuration_module(ROOT,'work6.family_long_term_read')
    result=work6.run_existing_long_term(ci,family_scope=scope,adjustment_request=adjustment,
        benchmark_path='SYNTHETIC',binding_path='SYNTHETIC',input_schema_path=base/'05_C_Canonical_Input.schema.json',
        output_schema_path=base/'06_C_Canonical_Output.schema.json',work6_request_schema_path=base/'56_C_Work6_Adjustment_Request.schema.json',
        work6_output_schema_path=base/'84_Family_Existing_LongTerm_Work6_Result.schema.json',evaluated_at=at)
    assert result['loop_status']=='EXISTING_LONG_TERM_TARGET_READ' and not result['adjustment_history']
    old,_=old_case()
    c7=run_c7_engine(ROOT,{'schema_version':'Family.W5.C7Source.v2','canonical_input':ci,'family_scope':scope,
        'work6_result':result,'funding_context':old['funding_context'],'evaluated_at':at})['result']
    assert c7['status']=='READY_FOR_PM_GATE' and c7['pm_gate']['work8_released'] is False
    assert c7['family_scope_evidence']['occupancy_and_capacity']['incremental_capacity']=='25'


def test_confirmed_and_unconfirmed_release_records_reuse_original_economic_deduplication(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);f['orders'][0]['state']='CANCEL_PENDING'
    f['orders'][0]['last_acknowledged_commitment']={'order_quantity':'10','commitment_price':'1',
        'source_reference':'SYNTHETIC_LAST_BROKER_ACK','as_of':req['evaluation_at']}
    release={'event_id':'SYNTHETIC_ACK_ONE','economic_effect_ids':['SYNTHETIC_ONE_CANCEL_EFFECT'],
        'account':req['owner']['account'],'asset_id':'QQQ','amount':'5','intent_id':'SYNTHETIC_INTENT',
        'confirmation_state':'PENDING','releases_event_id':'SYNTHETIC_BUY','release_state':'CANCELLED'}
    f['confirmed_releases']=[release]
    def capacity():
        out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
        ci['identity']=deepcopy(out['scope_candidate']['identity']);ci['source_references']=[r for r in ci['source_references'] if not r['source_id'].startswith('SRC_FAMILY_ASSEMBLY_')]+out['source_references']
        ci['allocations']['current_allocation']['snapshot']=out['current_allocation']
        return m.capacity(out['scope_candidate'],ci,req['evaluation_at'])
    assert capacity()['incremental_capacity']=='25'
    release['confirmation_state']='CONFIRMED';f['confirmed_releases'].append({**deepcopy(release),'event_id':'SYNTHETIC_ACK_TWO'})
    cap=capacity();assert cap['incremental_capacity']=='30' and cap['confirmed_release_deducted']=='5'


def test_current_nav_is_independent_of_missing_order_book_coverage(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);f['coverage']['orders_complete']=False
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    assert out['scope_candidate']['current_nav']['amount']==1000
    assert out['scope_candidate']['exposure_coverage'] is None
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and out.get('source_descriptor') is None


def test_zero_authorization_preserves_unknown_settlement_and_uses_original_provable_zero(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path);account=f['accounts'][0]
    account['authorized_incremental_amount']='0';account['cash'].update(settlement_evidence_state='UNKNOWN',
        settled_cash=None,unsettled_cash=None,reserved_cash=None,available_cash=None)
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    assert out['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING'
    scope=out['scope_candidate'];assert scope['current_nav']['amount']==1000
    assert scope['funding_buckets'][0]['cash_amount'] is None and scope['funding_buckets'][0]['settled'] is None
    ci['identity']=deepcopy(scope['identity']);ci['source_references']+=out['source_references']
    ci['allocations']['current_allocation']['snapshot']=out['current_allocation']
    cap=m.capacity(scope,ci,req['evaluation_at'])
    assert cap['incremental_capacity']=='0' and cap['cash_audit'][0]['net_available'] is None


@pytest.mark.parametrize('part',['authorization','protection','cash_reservation','price_basis','asset_class'])
def test_source_clearances_and_cash_reserved_relationship_cannot_be_inferred(tmp_path,part):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    if part=='authorization':f['accounts'][0].pop('authorization_source_reference')
    elif part=='protection':f.pop('protection_confirmation')
    elif part=='cash_reservation':f['accounts'][0]['cash'].update(reserved_cash='0',available_cash='50')
    elif part=='price_basis':f['accounts'][0]['positions'][0]['price_basis']='AVERAGE_COST'
    else:f['accounts'][0]['positions'][0]['asset_class']='BOND'
    if part in ('authorization','protection'):
        out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
        assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and 'source_descriptor' not in out
    else:
        with pytest.raises(ValueError):assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())


def test_qualified_assembled_current_does_not_depend_on_the_legacy_cash_trial_comparison(tmp_path,monkeypatch):
    import deployment_c7_sources as adapter
    m,ci,req,ctx,t,ids,f,desc,out=build(tmp_path)
    ctx.update(family_c7_profile=out['scope_candidate']['profile'],family_c7_scope_source=out['source_descriptor'],
        configuration_benchmark_source={'local_path':'SYNTHETIC_PINNED_B_PLACEHOLDER'})
    def old_trial(*a,**kw):pytest.fail('A reconciled Current must not be replaced by a cash-zero comparison')
    def benchmark(*a,**kw):raise RuntimeError('SYNTHETIC_TEST_REACHED_ORIGINAL_BENCHMARK_INTAKE')
    monkeypatch.setattr(adapter,'current_allocation',old_trial);monkeypatch.setattr(adapter,'benchmark_source',benchmark)
    with pytest.raises(RuntimeError,match='REACHED_ORIGINAL_BENCHMARK'):
        adapter.extend(ROOT,req,{},None,ctx,{'component_results':{},'source_validation_issues':[]})

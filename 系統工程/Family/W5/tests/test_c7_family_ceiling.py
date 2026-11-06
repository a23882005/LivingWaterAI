"""Synthetic PM scope-B accounting; never household sources or trade orders."""
from copy import deepcopy
from decimal import Decimal
import pytest
from test_c7_engine import original_case
from test_native_adapters import ROOT
from c7_engine import load_original_configuration_module


def family_case():
    m=load_original_configuration_module(ROOT,'work7.family_long_term')
    old,_=original_case();ci=deepcopy(old['canonical_input']);at=old['evaluated_at']
    owner={'client_id':ci['identity']['client_id'],'broker':'SYNTHETIC_BROKER','account':'SYNTHETIC_ACCOUNT',
        'currency':'TWD','funding_domain':'TW_LOCAL_BROKER'}
    proof_ref=deepcopy(ci['source_references'][0]);proof_ref.update(source_id='SYNTHETIC_FAMILY_SCOPE',source_fingerprint='a'*64,source_fingerprint_algorithm='SHA256')
    ci['source_references'].append(proof_ref)
    current=deepcopy(old['work6_result']['final_target_engine_result']['allocations']['current_allocation']['snapshot'])
    current['denominator'].update(currency='TWD',amount=1000)
    for row in current['positions']:
        amount={'QQQ':60,'CORE.US':0,'SGOV':940}[row['instrument_id']]
        row['portfolio_amount'].update(currency='TWD',amount=amount)
        row['weight']['value']=amount/1000
    ci['allocations']['current_allocation']['snapshot']=current
    proof={'source_reference_id':proof_ref['source_id'],'source_sha256':'a'*64,'as_of':at,'available_at':at,'qualification':'VERIFIED_AT_CUTOFF'}
    approved=deepcopy(old['work6_result']['final_target']['snapshot'])
    approved['denominator']['currency']='TWD'
    for row in approved['positions']:row['portfolio_amount']['currency']='TWD'
    ci['v70_asset_framework']['stock_tactical_amount'].update(value_state='KNOWN',amount=100,currency='TWD')
    base={'base_id':'SYNTHETIC_ACCOUNTING_BASE','amount':'1000','currency':'TWD','source_reference_id':proof_ref['source_id']}
    scope={'schema_version':'C.FamilyLongTermV70CeilingInput.v1','profile':m.PROFILE,'approval_contract_sha256':m.APPROVAL_SHA256,
        'identity':deepcopy(ci['identity']),'family_owner':owner,'account_owners':[owner],'budget_currency':'TWD',
        'source_db_sha256':'f'*64,'target_version':1,'approved_long_term_target':approved,'approved_target_digest':m.digest(approved),
        'approval_receipt':deepcopy(proof),'current_nav':deepcopy(ci['allocations']['current_allocation']['snapshot']['denominator']),
        'protection_coverage':{**deepcopy(proof),'complete':True,'empty_portfolio_asserted':False,'confirmed_effects_already_applied':[]},
        'preference_locks':deepcopy(old['work6_result']['preference_locks']),
        'total_stock_ceiling':{'amount':'100','currency':'TWD','cap_scope':'TOTAL_PORTFOLIO_STOCK','accounting_base':base,'receipt':deepcopy(proof)},
        'portfolio_caps':[{'cap_id':'SYNTHETIC_NONE','applicability':'NOT_APPLICABLE','value_state':'NONE'}],
        'exposure_coverage':{**deepcopy(proof),'complete':True,'empty_portfolio_asserted':False,'confirmed_effects_already_applied':[]},
        'exposures':[],
        'funding_buckets':[{'bucket_id':'SYNTHETIC_CASH','owner':owner,'currency':'TWD','value_state':'KNOWN','settled':True,
            'cash_amount':'50','reserved_amount':'10','cash_basis':'NET_AVAILABLE','authorized_incremental_amount':'50','receipt':deepcopy(proof)}]}
    for event,kind,amount in [('SYNTHETIC_POSITION','CONFIRMED_POSITION','60'),('SYNTHETIC_BUY','ACTIVE_BUY_RESERVATION','10'),('SYNTHETIC_OTHER','OTHER_COMMITMENT','5')]:
        scope['exposures'].append({'event_id':event,'economic_effect_ids':[event],'kind':kind,'owner':owner,
            'asset_id':'QQQ','amount':amount,'currency':'TWD','intent_id':'SYNTHETIC_INTENT' if kind=='ACTIVE_BUY_RESERVATION' else None,
            'side':'BUY' if kind=='ACTIVE_BUY_RESERVATION' else None,
            'amount_basis':'REMAINING_UNFILLED_NOTIONAL' if kind=='ACTIVE_BUY_RESERVATION' else 'CONFIRMED_NOTIONAL',
            'lifecycle_state':'OPEN','receipt':deepcopy(proof)})
    return m,ci,scope,at


def test_pm_capacity_example_preserves_target_and_all_callers_data():
    m,ci,scope,at=family_case();before=deepcopy((ci,scope));out=m.capacity(scope,ci,at)
    assert out['occupied']=='75' and out['incremental_room']==out['incremental_capacity']=='25'
    assert out['overage']=='0';assert (ci,scope)==before
    assert not out['new_sell_or_forced_reallocation_authorized']


def test_pm_overage_example_new_buy_zero_without_forced_sales():
    m,ci,s,at=family_case();s['exposures'][0]['amount']='110';s['exposures'][1]['amount']='5';s['exposures'].pop()
    out=m.capacity(s,ci,at);assert out['occupied']=='115' and out['overage']=='15' and out['incremental_capacity']=='0'


def test_net_cash_already_reserved_is_not_subtracted_again():
    m,ci,s,at=family_case();s['exposures']=[s['exposures'][0]];s['exposures'][0]['amount']='50'
    s['funding_buckets'][0].update(cash_amount='20',reserved_amount='10')
    out=m.capacity(s,ci,at);assert out['incremental_capacity']=='20';assert not out['cash_audit'][0]['reserved_deducted_here']


def test_local_unsubmitted_plan_is_deducted_from_broker_net_cash_once():
    m,ci,s,at=family_case();s['exposures'][0]['amount']='10'
    s['exposures'][1]['lifecycle_state']='PLANNED'
    s['funding_buckets'][0].update(cash_amount='20',reserved_amount='0')
    out=m.capacity(s,ci,at)
    assert out['incremental_capacity']=='10' and out['cash_audit'][0]['local_planning_deducted_here']=='10'


def test_gross_cash_deducts_reservation_once_and_authorization_is_separate():
    m,ci,s,at=family_case();s['exposures'][0]['amount']='10';s['funding_buckets'][0].update(cash_amount='40',reserved_amount='10',cash_basis='GROSS_SETTLED_CASH')
    out=m.capacity(s,ci,at);assert out['incremental_capacity']=='30' and out['cash_audit'][0]['reserved_deducted_here']
    s['funding_buckets'][0]['authorized_incremental_amount']='7';assert m.capacity(s,ci,at)['incremental_capacity']=='7'


def test_duplicate_economic_event_is_counted_only_once_and_conflicting_receipt_fails():
    m,ci,s,at=family_case();s['exposures'].append(deepcopy(s['exposures'][0]))
    assert m.capacity(s,ci,at)['occupied']=='75'
    s['exposures'][-1]['amount']='61'
    with pytest.raises(m.FamilyScopeError,match='CONFLICTING_ECONOMIC_EVENT'):m.capacity(s,ci,at)


def test_filled_and_remaining_portions_must_not_cover_the_same_economic_effect():
    m,ci,s,at=family_case();s['exposures'][1]['economic_effect_ids']=s['exposures'][0]['economic_effect_ids']
    with pytest.raises(m.FamilyScopeError,match='EXPOSURE_DOUBLE_COUNT'):m.capacity(s,ci,at)


@pytest.mark.parametrize('state',['OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'])
def test_live_buy_lifecycle_keeps_unfilled_notional_occupied(state):
    m,ci,s,at=family_case();s['exposures'][1]['lifecycle_state']=state
    assert m.capacity(s,ci,at)['occupied']=='75'
    s['exposures'][1]['amount_basis']='WHOLE_ORDER_AMOUNT'
    with pytest.raises(m.FamilyScopeError,match='BUY_REMAINING'):m.capacity(s,ci,at)


def release(s,confirmed=False):
    original=s['exposures'][1]
    return {'event_id':'SYNTHETIC_RELEASE','economic_effect_ids':['SYNTHETIC_RELEASE'],
        'kind':'RELEASE','owner':original['owner'],'asset_id':original['asset_id'],'intent_id':original['intent_id'],
        'amount':'5','currency':'TWD','release_confirmed':confirmed,'release_state':'CANCELLED',
        'releases_event_id':original['event_id'],'receipt':deepcopy(original['receipt'])}


def test_unconfirmed_release_keeps_capacity_then_confirmed_release_is_counted_once():
    m,ci,s,at=family_case();s['exposures'].append(release(s))
    assert m.capacity(s,ci,at)['incremental_capacity']=='25'
    s['exposures'][-1]['release_confirmed']=True;s['exposures'].append(deepcopy(s['exposures'][-1]))
    out=m.capacity(s,ci,at);assert out['occupied']=='70' and out['incremental_capacity']=='30'


def test_release_already_in_new_confirmed_snapshot_is_not_deducted_again():
    m,ci,s,at=family_case();s['exposures'].append(release(s,True));s['exposure_coverage']['confirmed_effects_already_applied']=['SYNTHETIC_RELEASE']
    out=m.capacity(s,ci,at);assert Decimal(out['occupied'])==75 and Decimal(out['incremental_capacity'])==25


def test_two_receipts_for_the_same_confirmed_release_do_not_release_twice():
    m,ci,s,at=family_case();r=release(s,True);s['exposures'].append(r)
    duplicate=deepcopy(r);duplicate['event_id']='SECOND_PROVIDER_ACK';s['exposures'].append(duplicate)
    out=m.capacity(s,ci,at);assert out['occupied']=='70' and out['incremental_capacity']=='30'
    assert out['confirmed_release_deducted']=='5'


def test_conflicting_same_economic_release_fails_instead_of_increasing_capacity():
    m,ci,s,at=family_case();r=release(s,True);s['exposures'].append(r)
    duplicate=deepcopy(r);duplicate.update(event_id='CONFLICTING_PROVIDER_ACK',amount='6');s['exposures'].append(duplicate)
    with pytest.raises(m.FamilyScopeError,match='CONFLICTING_RELEASE_ECONOMIC_EFFECT'):m.capacity(s,ci,at)


def test_sell_instruction_or_excess_release_is_not_confirmed_available_capacity():
    m,ci,s,at=family_case();s['exposures'].append(release(s,True));s['exposures'][-1]['release_state']='OPEN_SELL'
    with pytest.raises(m.FamilyScopeError,match='CONFIRMED_RELEASE_BINDING'):m.capacity(s,ci,at)
    s['exposures'][-1].update(release_state='CANCELLED',amount='11')
    with pytest.raises(m.FamilyScopeError,match='RELEASE_EXCEEDS'):m.capacity(s,ci,at)


def test_unknown_cash_is_not_zero_but_exhausted_known_ceiling_still_proves_zero():
    m,ci,s,at=family_case();s['funding_buckets'][0].update(value_state='UNKNOWN',settled=None,cash_amount=None)
    assert m.capacity(s,ci,at)['incremental_capacity'] is None
    s['exposures'][0]['amount']='110';out=m.capacity(s,ci,at)
    assert out['incremental_capacity']=='0' and out['available_authorized_incremental_funding'] is None


def test_explicit_zero_authorization_in_other_account_does_not_invent_cash_or_taint_own_funding():
    m,ci,s,at=family_case();owner={**s['family_owner'],'account':'SYNTHETIC_NO_STOCK_FUNDING_AUTHORIZATION'}
    s['account_owners'].append(owner);bucket=deepcopy(s['funding_buckets'][0])
    bucket.update(owner=owner,bucket_id='SYNTHETIC_UNKNOWN_CASH',value_state='UNKNOWN',settled=None,
        cash_amount=None,reserved_amount=None,authorized_incremental_amount='0')
    s['funding_buckets'].append(bucket);out=m.capacity(s,ci,at)
    assert out['incremental_capacity']=='25' and out['available_authorized_incremental_funding']=='50'
    assert out['cash_audit'][-1]['net_available'] is None
    assert out['cash_audit'][-1]['cash_or_settlement_unknown_retained']
    bucket['authorized_incremental_amount']=None
    assert m.capacity(s,ci,at)['incremental_capacity'] is None


def test_required_unknown_cap_is_not_na_or_a_positive_budget():
    m,ci,s,at=family_case();s['portfolio_caps']=[{'cap_id':'SYNTHETIC_REQUIRED','applicability':'REQUIRED','value_state':'UNKNOWN'}]
    out=m.capacity(s,ci,at);assert out['incremental_capacity'] is None and out['ceiling'] is None
    s['exposures'][0]['amount']='110';out=m.capacity(s,ci,at)
    assert out['incremental_capacity']=='0' and out['ceiling'] is None and Decimal(out['overage_lower_bound'])>=15


def test_known_zero_authorization_proves_no_new_buy_while_required_ceiling_cap_stays_unknown():
    m,ci,s,at=family_case();s['portfolio_caps']=[{'cap_id':'SYNTHETIC_REQUIRED','applicability':'REQUIRED','value_state':'UNKNOWN'}]
    s['funding_buckets'][0].update(value_state='UNKNOWN',settled=None,cash_amount=None,authorized_incremental_amount='0')
    out=m.capacity(s,ci,at)
    assert out['incremental_capacity']=='0' and out['ceiling'] is None
    assert out['unknown_required_caps']==['SYNTHETIC_REQUIRED']
    assert out['cash_audit'][0]['net_available'] is None


def test_same_base_client_cap_is_min_and_different_base_cannot_be_combined():
    m,ci,s,at=family_case();cap={'cap_id':'SYNTHETIC_REQUIRED','applicability':'REQUIRED','value_state':'KNOWN','amount':'80','currency':'TWD',
        'accounting_base':deepcopy(s['total_stock_ceiling']['accounting_base']),'receipt':deepcopy(s['approval_receipt'])}
    s['portfolio_caps']=[cap];assert m.capacity(s,ci,at)['incremental_capacity']=='5'
    cap['accounting_base']['base_id']='OTHER'
    with pytest.raises(m.FamilyScopeError,match='CAP_ACCOUNTING_BASE'):m.capacity(s,ci,at)


def test_multiple_accounts_do_not_duplicate_portfolio_cap_or_other_accounts_cash():
    m,ci,s,at=family_case();other={**s['family_owner'],'account':'SYNTHETIC_SECOND'};s['account_owners'].append(other)
    bucket=deepcopy(s['funding_buckets'][0]);bucket.update(bucket_id='SYNTHETIC_SECOND_CASH',owner=other,cash_amount='20')
    s['funding_buckets'].append(bucket)
    out=m.capacity(s,ci,at);assert out['available_authorized_incremental_funding']=='70' and out['incremental_capacity']=='25'
    s['funding_buckets'].pop();assert m.capacity(s,ci,at)['incremental_capacity'] is None
    s['funding_buckets'].append(deepcopy(s['funding_buckets'][0]))
    with pytest.raises(m.FamilyScopeError,match='FUNDING_ACCOUNT_SCOPE_OR_DUPLICATION'):m.capacity(s,ci,at)


@pytest.mark.parametrize('field',['profile','identity','approval','hash','base','cutoff','owner','FX'])
def test_missing_or_changed_scope_sources_cannot_auto_skip_legacy_guard(field):
    m,ci,s,at=family_case()
    if field=='profile':s['profile']='UNAPPROVED'
    elif field=='identity':s['identity']['run_id']='OTHER'
    elif field=='approval':s['approved_long_term_target']['confirmed_by']=None;s['approved_target_digest']=m.digest(s['approved_long_term_target'])
    elif field=='hash':s['approval_receipt']['source_sha256']='b'*64
    elif field=='base':s['total_stock_ceiling']['accounting_base']['amount']=None
    elif field=='cutoff':s['approval_receipt']['available_at']='2099-01-01T00:00:00Z'
    elif field=='owner':s['exposures'][0]['owner']={**s['family_owner'],'account':'OTHER'}
    else:s['exposures'][0]['currency']='USD'
    with pytest.raises(m.FamilyScopeError):m.capacity(s,ci,at)


def test_net_room_receipt_must_replay_gross_accounting_not_be_deducted_twice():
    m,ci,s,at=family_case();s['upstream_net_capacity']={'producer_contract':m.PROFILE,'gross_input_digest':m.digest(s),
        'amount':'25','receipt':deepcopy(s['approval_receipt'])}
    out=m.capacity(s,ci,at);assert out['incremental_capacity']=='25' and out['upstream_net_capacity_replayed']
    s['upstream_net_capacity']['amount']='15'
    with pytest.raises(m.FamilyScopeError,match='NET_CAPACITY_RECEIPT_REPLAY'):m.capacity(s,ci,at)


def test_empty_exposure_is_never_silently_an_empty_broker_book():
    m,ci,s,at=family_case();s['exposures']=[]
    with pytest.raises(m.FamilyScopeError,match='EMPTY_EXPOSURE'):m.capacity(s,ci,at)
    s['exposure_coverage']['empty_portfolio_asserted']=True
    assert m.capacity(s,ci,at)['incremental_capacity']=='50'


def test_work64_explicit_reporting_fx_keeps_actual_owner_currency_and_does_not_create_cash():
    m,ci,s,at=family_case();owner={**s['family_owner'],'currency':'USD'}
    s['family_owner']=owner;s['account_owners']=[owner]
    for row in s['exposures']:row.update(owner=owner,currency='USD',amount=str(Decimal(row['amount'])/2))
    for row in s['funding_buckets']:row.update(owner=owner,currency='USD',cash_amount='25',reserved_amount='5',authorized_incremental_amount='25')
    with pytest.raises(m.FamilyScopeError,match='FX_RECEIPT_REQUIRED'):m.capacity(s,ci,at)
    s['budget_normalizations']=[{'owner':owner,'from_currency':'USD','to_currency':'TWD','quote_per_base':'2',
        'accounting_base_id':s['total_stock_ceiling']['accounting_base']['base_id'],
        'purpose':'REPORTING_BUDGET_NORMALIZATION_NOT_EXECUTION','receipt':deepcopy(s['approval_receipt'])}]
    out=m.capacity(s,ci,at);assert Decimal(out['occupied'])==75 and Decimal(out['incremental_capacity'])==25
    assert out['cash_audit'][0]['native_available_authorized']=='25'
    assert out['cash_audit'][0]['available_authorized']=='50'
    s['budget_normalizations'][0]['receipt']['available_at']='2099-01-01T00:00:00Z'
    with pytest.raises(m.FamilyScopeError,match='CUTOFF'):m.capacity(s,ci,at)


def read_case(monkeypatch):
    """Public construction QA: Work5's separately tested golden output only.

    The private acceptance run additionally uses the pinned real workbook.
    This mock is never a household financial source or eligibility receipt.
    """
    m,ci,s,at=family_case()
    w6=load_original_configuration_module(ROOT,'work6.family_long_term_read')
    old,_=original_case();template=old['work6_result']['final_target_engine_result']
    calls=[]
    def original_engine(canonical,*,allocation_slot,**kwargs):
        calls.append((deepcopy(canonical),allocation_slot))
        out=deepcopy(template);out['allocations']=deepcopy(canonical['allocations'])
        out['formal_output_eligibility']['eligible']=True
        return out
    monkeypatch.setattr(w6,'run_configuration_engine',original_engine)
    request={'contract_name':'LivingWaterAI.C.Work6.AdjustmentRequest','contract_version':'C-W6-v1.0.0',
        'adjustment_id':'SYNTHETIC_READ_ONLY','requested_change_types':['REVIEW_ONLY'],
        'weight_overrides':[],'preference_decisions':[],
        'confirmation':{'action':'KEEP_PENDING','client_explicit_decision':'UNKNOWN',
            'confirmed_at':None,'confirmed_by':None,'source_reference_ids':[]},
        'radar_scores':[],'source_references':[],'source_reference_ids':['SYNTHETIC_FAMILY_SCOPE']}
    base=ROOT/'系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/contracts_c7'
    def run():
        return w6.run_existing_long_term(ci,family_scope=s,adjustment_request=request,
            benchmark_path='SYNTHETIC_NOT_A_HOUSEHOLD_SOURCE',binding_path='SYNTHETIC',
            input_schema_path=base/'05_C_Canonical_Input.schema.json',output_schema_path=base/'06_C_Canonical_Output.schema.json',
            work6_request_schema_path=base/'56_C_Work6_Adjustment_Request.schema.json',
            work6_output_schema_path=base/'84_Family_Existing_LongTerm_Work6_Result.schema.json',evaluated_at=at)
    return m,ci,s,at,request,calls,run


def test_existing_approval_reader_does_not_create_a_confirm_or_rebase_project_target(monkeypatch):
    m,ci,s,at,req,calls,run=read_case(monkeypatch)
    approved=deepcopy(s['approved_long_term_target']);out=run()
    assert [v[1] for v in calls]==['current_allocation','final_target']
    assert out['loop_status']=='EXISTING_LONG_TERM_TARGET_READ'
    assert out['adjustment_history']==[] and out['current_proposal']['value_state']=='NONE'
    proof=out['family_scope_evidence']
    assert proof['approved_long_term_target']==approved
    assert proof['project_target_money_base']==approved['denominator']
    assert proof['new_confirmation_created'] is False and proof['tactical_target_approved'] is False
    assert out['final_target']['snapshot']['confirmed_at']==approved['confirmed_at']
    assert out['final_target']['snapshot']['confirmed_by']==approved['confirmed_by']
    assert s['approved_long_term_target']==approved


def test_nav_change_affects_only_current_protection_and_drift_view(monkeypatch):
    m,ci,s,at,req,calls,run=read_case(monkeypatch)
    original=deepcopy(s['approved_long_term_target'])
    current=ci['allocations']['current_allocation']['snapshot']
    current['denominator']['amount']*=2
    for row in current['positions']:row['portfolio_amount']['amount']*=2
    s['exposures'][0]['amount']='120'
    s['current_nav']=deepcopy(current['denominator'])
    out=run();proof=out['family_scope_evidence']
    assert out['drift_snapshot']['denominator']==s['current_nav']
    assert proof['approved_long_term_target']==original and proof['project_target_money_base']==original['denominator']
    assert proof['project_target_money_rebased_to_NAV'] is False


def test_new_scope_refuses_tactical_confirmation_or_incomplete_protection(monkeypatch):
    m,ci,s,at,req,calls,run=read_case(monkeypatch)
    req['confirmation']['action']='CONFIRM'
    with pytest.raises(m.FamilyScopeError,match='NOT_TACTICAL_CONFIRM'):run()
    assert not calls
    req['confirmation']['action']='KEEP_PENDING';s['protection_coverage']['complete']=False
    with pytest.raises(m.FamilyScopeError,match='PROTECTION_SOURCE_INCOMPLETE'):run()


def family_c7(monkeypatch):
    m,ci,s,at,req,calls,run=read_case(monkeypatch)
    result=run();old,_=original_case()
    source={'schema_version':'Family.W5.C7Source.v2','canonical_input':ci,'work6_result':result,
        'funding_context':old['funding_context'],'evaluated_at':at,'family_scope':s}
    return m,source


def protected_case(monkeypatch,current_weight):
    m,ci,s,at,req,calls,run=read_case(monkeypatch)
    iid='SYNTHETIC_INDIVIDUAL_COMPANY';current=ci['allocations']['current_allocation']['snapshot']
    for row in current['positions']:
        if row['instrument_id']=='QQQ':
            row.update(instrument_id=iid,ticker=iid,asset_type='equity individual stock')
            row['weight']['value']=current_weight;row['portfolio_amount']['amount']=current_weight*1000
        elif row['instrument_id']=='SGOV':
            row['weight']['value']=1-current_weight;row['portfolio_amount']['amount']=(1-current_weight)*1000
    for row in s['approved_long_term_target']['positions']:
        if row['instrument_id']=='QQQ':row.update(instrument_id=iid,ticker=iid,asset_type='equity individual stock')
    s['approved_target_digest']=m.digest(s['approved_long_term_target'])
    for row in s['exposures']:row['asset_id']=iid
    s['exposures'][0]['amount']=str(Decimal(str(current_weight))*1000)
    s['preference_locks']=[{'instrument_id':iid,'ticker':iid,'protected_existing_holding':True,
        'client_preference_locked':True,'final_target_locked_to_current':True,'current_weight':current_weight,
        'preference_confirmed_at':at,'preference_source_ids':['SYNTHETIC_FAMILY_SCOPE'],
        'unlock_confirmed_at':None,'unlock_source_ids':[]}]
    return m,ci,s,at,run


def test_protected_position_retains_effective_current_zero_drift_and_hold_when_stock_is_over_ceiling(monkeypatch):
    from c7_engine import run_c7_engine
    m,ci,s,at,run=protected_case(monkeypatch,.1);approved=deepcopy(s['approved_long_term_target']);out=run()
    old,_=original_case()
    result=run_c7_engine(ROOT,{'schema_version':'Family.W5.C7Source.v2','canonical_input':ci,'family_scope':s,
        'work6_result':out,'funding_context':old['funding_context'],'evaluated_at':at})['result']
    assert result['status']=='READY_FOR_PM_GATE',result['issues']
    assert result['protected_locked_weights'][0]['drift']==0
    assert result['protected_locked_weights'][0]['current_weight']==result['protected_locked_weights'][0]['final_target_weight']==.1
    assert result['family_scope_evidence']['occupancy_and_capacity']['incremental_capacity']=='0'
    assert out['mentor_result_contract']['protected_holding_actions'][0]['action']=='HOLD_PROTECTED'
    assert result['family_scope_evidence']['approved_long_term_target']==approved


def test_protected_change_that_breaks_portfolio_total_requires_governance_not_residual_redistribution(monkeypatch):
    m,ci,s,at,run=protected_case(monkeypatch,.11);approved=deepcopy(s['approved_long_term_target']);out=run()
    assert out['loop_status']=='BLOCKED'
    assert 'C_W6_LT_PROTECTED_TARGET_GOVERNANCE_REQUIRED' in {i['code'] for i in out['issues']}
    assert out['family_scope_evidence']['approved_long_term_target']==approved


def test_new_scope_preserves_long_term_when_total_v70_bucket_is_different(monkeypatch):
    from c7_engine import run_c7_engine
    m,source=family_c7(monkeypatch);before=deepcopy(source)
    out=run_c7_engine(ROOT,source)['result']
    assert out['status']=='READY_FOR_PM_GATE',out['issues']
    assert all(v=='PASS' for v in out['hard_checks'].values())
    assert out['family_scope_evidence']['occupancy_and_capacity']['incremental_capacity']=='25'
    assert out['family_scope_evidence']['production_released'] is False
    assert out['residual_allocation']['method']=='PRESERVE_LONG_TERM_NO_V70_RESIDUAL_SCALING'
    approved={r['instrument_id']:r['weight']['value'] for r in source['work6_result']['final_target']['snapshot']['positions']}
    assert {r['instrument_id']:r['integrated_weight'] for r in out['integrated_asset_framework']['instrument_targets']}==approved
    assert out['pm_gate']['status']=='PENDING_ABC_PM_CONTRACT_SCHEMA_GATE'
    assert out['pm_gate']['a78_a79_released'] is False and out['pm_gate']['work8_released'] is False
    assert source==before


@pytest.mark.parametrize('kind',['protected','drift','radar','funding','isolation','lineage'])
def test_new_scope_retains_all_original_hard_checks(monkeypatch,kind):
    from c7_engine import run_c7_engine
    m,source=family_c7(monkeypatch)
    if kind=='protected':
        source['work6_result']['preference_locks'].append({'instrument_id':'QQQ','ticker':'QQQ',
            'protected_existing_holding':True,'client_preference_locked':True,'final_target_locked_to_current':True,
            'current_weight':.11,'preference_confirmed_at':source['evaluated_at'],
            'preference_source_ids':['SYNTHETIC_FAMILY_SCOPE'],'unlock_confirmed_at':None,'unlock_source_ids':[]})
    elif kind=='drift':source['work6_result']['drift_snapshot']['denominator']['amount']+=1
    elif kind=='radar':source['work6_result']['radar_snapshot']['axes'][0]['label_zh']='UNREADABLE_AXIS'
    elif kind=='funding':source['funding_context']['total_new_investment_amount']+=1
    elif kind=='isolation':source['funding_context']['contexts'][-1]['executable_budget']['equity']['source_account']='FOREIGN'
    else:source['work6_result']['identity']['run_id']='FOREIGN'
    try:out=run_c7_engine(ROOT,source)['result']
    except ValueError:return  # Original schema/source validation may reject first.
    assert out['status'] in ('BLOCKED','RETURN_TO_V70') and out['issues']

"""Synthetic confirmed role versions: one physical SGOV, separate cash book."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json
import pytest
from test_sgov_role_source import case as legacy_case
from test_family_c7_source_assembly import original_case,assemble,ROOT
from family_input import digest
from native_target_source import produce as target_projection
from sgov_role_source import produce,validate
from sgov_confirmed_units import select,units,validated_units,RoleSourceUnavailable
from deployment_c7_sources import current_sgov_roles
from v75_native_attempt import normalized_evidence


def add_rows(request,*,quantity='14',bond=6000,account=None,instrument='SGOV_SOURCE_POSITION',position_at=None):
    client=request['client_id'];account=account or request['owner']['account'];cutoff=request['evaluation_at']
    # Explicit synthetic original timestamps; no real publication/PIT claim.
    at=position_at or cutoff;tables=request['client_snapshot']['payload']['tables']
    tables.setdefault('portfolio_instrument',[]).append(dict(client_id=client,instrument_key=instrument,
        ticker='SGOV',instrument_type='ETF',identity_state='KNOWN',source_kind='OWNER_VERIFIED',source_reference='SYNTHETIC_IDENTITY',
        quote_currency=request['owner']['currency'],as_of_utc=at,created_at_utc=at))
    tables.setdefault('portfolio_position',[]).append(dict(client_id=client,account_key=account,instrument_key=instrument,
        as_of_utc=at,quantity_decimal=quantity,position_source_kind='OWNER_VERIFIED',position_source_reference='SYNTHETIC_POSITION',recorded_at_utc=at))
    key=dict(client_id=client,account_key=account,instrument_key=instrument,position_as_of_utc=at)
    proposal=dict(**key,version_no=1,previous_version_no=None,role_state='VERIFIED',evidence_state='VERIFIED',
        bond_core_bps=bond,dry_powder_bps=10000-bond,source_kind='OWNER_VERIFIED',source_reference='SYNTHETIC_ROLE',
        created_at_utc=at,effective_at_utc=at)
    confirmation=dict(**key,version_no=1,confirmer_kind='CLIENT',confirmer_reference='SYNTHETIC_OWNER',
        confirmed_at_utc=at,confirmation_source_kind='OWNER_VERIFIED',confirmation_source_reference='SYNTHETIC_CONFIRMATION')
    tables.setdefault('sgov_role_proposal',[]).append(proposal);tables.setdefault('sgov_role_confirmation',[]).append(confirmation)
    return proposal,confirmation


def case(tmp_path,**kwargs):
    request,context,report=legacy_case(tmp_path,True);proposal,confirmation=add_rows(request,**kwargs)
    return request,context,report,proposal,confirmation


def test_confirmed_current_position_splits_actual_units_and_never_adds_cash(tmp_path):
    request,context,report,*_=case(tmp_path);before=deepcopy((request,context,report));out=produce(request,context,report)
    assert out['status']=='SOURCE_DERIVED_ACCOUNTING' and out['purpose']=='MIXED'
    assert out['role_quantities']['bond_quantity']=='8.4' and out['role_quantities']['dry_quantity']=='5.6'
    assert out['roles']['sgov_bond_bucket_amount']['amount']=='840.0'
    assert out['roles']['sgov_dry_powder_bucket_amount']['amount']=='560.0'
    assert out['owner_role_confirmation']==request['client_snapshot']['payload']['tables']['sgov_role_confirmation'][0]
    assert not out['database_role_rows_created'] and not out['physical_included_in_available_cash'] and not out['equity_cash_release_authorized']
    assert (request,context,report)==before
    report['sgov_role_source']=out;validate(request,context,report)


def test_latest_unconfirmed_or_unknown_version_never_falls_back_to_old_approval(tmp_path):
    request,context,report,proposal,_=case(tmp_path);next_version={**proposal,'version_no':2,'previous_version_no':1,'bond_core_bps':2000,'dry_powder_bps':8000}
    request['client_snapshot']['payload']['tables']['sgov_role_proposal'].append(next_version)
    assert produce(request,context,report)['roles'] is None
    next_version.update(role_state='UNKNOWN',bond_core_bps=None,dry_powder_bps=None)
    assert 'LATEST_EFFECTIVE_VERSION_NOT_QUALIFIED' in produce(request,context,report)['issues'][0]


def test_future_effective_or_created_version_does_not_rewrite_past_roles(tmp_path):
    request,context,report,proposal,confirmation=case(tmp_path);tables=request['client_snapshot']['payload']['tables']
    later={**proposal,'version_no':2,'previous_version_no':1,'effective_at_utc':'2099-01-01T00:00:00Z','bond_core_bps':2000,'dry_powder_bps':8000}
    tables['sgov_role_proposal'].append(later);tables['sgov_role_confirmation'].append({**confirmation,'version_no':2})
    assert produce(request,context,report)['role_quantities']['bond_quantity']=='8.4'
    later['created_at_utc']='2099-01-01T00:00:00Z'
    assert produce(request,context,report)['role_quantities']['bond_quantity']=='8.4'


def test_new_confirmed_version_replaces_old_roles_without_new_owner_action(tmp_path):
    request,context,report,proposal,confirmation=case(tmp_path);tables=request['client_snapshot']['payload']['tables']
    tables['sgov_role_proposal'].append({**proposal,'version_no':2,'previous_version_no':1,'bond_core_bps':2500,'dry_powder_bps':7500})
    tables['sgov_role_confirmation'].append({**confirmation,'version_no':2})
    out=produce(request,context,report);assert out['role_quantities']['bond_quantity']=='3.5' and out['role_quantities']['dry_quantity']=='10.5'
    assert out['source_basis']['confirmed_position_role']['proposal']['version_no']==2
    assert not out['database_role_rows_created']


@pytest.mark.parametrize('field,value',[
    ('client_id','OTHER'),('account_key','OTHER'),('instrument_key','OTHER'),('position_as_of_utc','2026-10-28T00:00:00Z'),
    ('role_state','UNKNOWN'),('evidence_state','UNKNOWN'),('source_kind','NOT_PROVIDED'),('source_reference',''),
    ('bond_core_bps',True),('bond_core_bps',-1),('bond_core_bps',7000),
    ('version_no',3),('previous_version_no',2),('effective_at_utc','2026-10-28T00:00:00Z')])
def test_wrong_binding_or_unqualified_version_keeps_roles_unknown(tmp_path,field,value):
    request,context,report,proposal,_=case(tmp_path);proposal[field]=value
    out=produce(request,context,report);assert out['roles'] is None and out['issues']
    assert out['owner_role_confirmation'] is None and not out['equity_cash_release_authorized']


@pytest.mark.parametrize('field,value',[
    ('client_id','OTHER'),('account_key','OTHER'),('version_no',2),('confirmer_kind','UNKNOWN'),
    ('confirmer_reference',''),('confirmation_source_kind','AUTHORIZED_IMPORT'),('confirmation_source_reference',''),
    ('confirmed_at_utc','2099-01-01T00:00:00Z'),('confirmed_at_utc','2026-10-28T00:00:00Z')])
def test_latest_confirmation_must_be_exact_known_owner_source(tmp_path,field,value):
    request,context,report,_,confirmation=case(tmp_path);confirmation[field]=value
    assert produce(request,context,report)['roles'] is None


def test_role_version_for_old_quantity_is_not_applied_to_new_physical_shares(tmp_path):
    request,context,report,*_=case(tmp_path);report['analysis_result']['positions'][0]['holding']['quantity']='15'
    out=produce(request,context,report);assert out['roles'] is None
    assert 'PHYSICAL_QUANTITY_CHANGED' in out['issues'][0]


def test_new_position_without_role_confirmation_cannot_reuse_old_position_version(tmp_path):
    request,context,report,*_=case(tmp_path,position_at='2026-10-28T00:00:00Z');tables=request['client_snapshot']['payload']['tables']
    tables['portfolio_position'].append({**tables['portfolio_position'][0],'as_of_utc':request['evaluation_at'],'recorded_at_utc':request['evaluation_at']})
    assert produce(request,context,report)['roles'] is None


def test_conflicting_rows_and_duplicate_identical_rows_are_distinguished(tmp_path):
    request,context,report,proposal,confirmation=case(tmp_path);tables=request['client_snapshot']['payload']['tables']
    tables['sgov_role_proposal'].append(deepcopy(proposal));tables['sgov_role_confirmation'].append(deepcopy(confirmation))
    assert produce(request,context,report)['roles'] is not None
    tables['sgov_role_proposal'].append({**proposal,'bond_core_bps':2000,'dry_powder_bps':8000})
    assert produce(request,context,report)['roles'] is None


def test_all_account_scope_does_not_merge_role_versions_across_accounts(tmp_path):
    request,context,report,*_=case(tmp_path);request['owner']['account']=None
    out=produce(request,context,report);assert out['roles'] is None and 'SINGLE_ACCOUNT' in out['issues'][0]


@pytest.mark.parametrize('bond',[0,10000,3333])
def test_single_role_and_fractional_role_units_conserve_physical_value(tmp_path,bond):
    request,context,report,*_=case(tmp_path,bond=bond);out=produce(request,context,report)
    u=validated_units(out);assert Decimal(u['bond_quantity'])+Decimal(u['dry_quantity'])==14
    assert sum(Decimal(r['amount']) for r in out['roles'].values())==1400


def test_v75_reads_only_confirmed_bond_units_and_retains_unknown_risk_flags(tmp_path):
    request,context,report,*_=case(tmp_path);roles=produce(request,context,report)
    source=dict(native_validation={'accepted':True},adapter_request={'v75_source_context':{
        'market_snapshot':{'data_timestamp':request['evaluation_at']},'target_bond_holdings':[{'asset_id':'SGOV'}],'existing_bond_holdings':[]}},
        shared_inputs={'work3_input':{'shared_decision_context':{'payload':{}}}},predicate_observations={},
        physical_holdings={'SGOV':deepcopy(roles['physical'])},sgov_role_source=roles)
    evidence,_=normalized_evidence(request,source);facts=evidence['SGOV']
    assert facts['existing_policy']['current_position_quantity']=='8.4'
    assert facts['sgov_role_binding']['physical_quantity']=='14'
    assert facts['existing_policy']['investment_logic_invalidated'] is None
    source['physical_holdings']['SGOV']['quantity']='15'
    with pytest.raises(PermissionError,match='PHYSICAL_QUANTITY_CONFLICT'):normalized_evidence(request,source)


def test_current_reference_uses_confirmed_share_units_and_one_common_price(tmp_path):
    request,context,report,*_=case(tmp_path);roles=produce(request,context,report)
    out=current_sgov_roles(roles['roles'],'1400',Decimal('1409.80'),role_source=roles)
    assert out==[('SGOV_BOND','bond ETF',Decimal('845.88')),('SGOV_DRY','cash',Decimal('563.92'))]
    assert sum(r[2] for r in out)==Decimal('1409.80')


@pytest.mark.parametrize('field',['bond_quantity','dry_quantity','physical_quantity'])
def test_pasted_or_mutated_unit_allocations_are_rejected(tmp_path,field):
    request,context,report,*_=case(tmp_path);roles=produce(request,context,report);roles['role_quantities'][field]='999'
    with pytest.raises(RoleSourceUnavailable):current_sgov_roles(roles['roles'],'1400',Decimal('1409.80'),role_source=roles)
    report['sgov_role_source']=roles
    with pytest.raises(PermissionError,match='REPLAY_MISMATCH'):validate(request,context,report)


def family_case(tmp_path):
    data=original_case(tmp_path);module,ci,request,context,tactical,identities,facts,desc=data
    rows=request['confirmed_target']['payload']['draft']['target_lines'];old=next(r for r in rows if r['ticker']=='SGOV')
    rows.remove(old)
    for key,kind in [('SGOV_BOND','BOND_ETF'),('SGOV_DRY','CASH')]:
        r=deepcopy(old);r.update(instrument_id=key,asset_type=kind)
        r['weight']['value']=str(Decimal(old['weight']['value'])/2);r['target_amount']['amount']=str(Decimal(old['target_amount']['amount'])/2);rows.append(r)
    context['native_target_source']=target_projection(request)
    add_rows(request,quantity='890',instrument='PHYSICAL_SGOV')
    # Re-project after adding only source rows; the approved target is unchanged.
    context['native_target_source']=target_projection(request)
    sgov=next(p for p in facts['accounts'][0]['positions'] if p['ticker']=='SGOV')
    sgov['sgov_role_binding']={'instrument_key':'PHYSICAL_SGOV','position_as_of_utc':request['evaluation_at']}
    return data


def test_full_c7_current_nav_counts_one_physical_position_and_cash_stays_settled(tmp_path):
    data=family_case(tmp_path);m,ci,request,context,tactical,identities,facts,desc=data;before=deepcopy(request['confirmed_target'])
    out=assemble(ROOT,request,context,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities,portfolio_facts_source=desc())
    assert out['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING' and not out['issues']
    scope=out['scope_candidate'];current=out['current_allocation'];by={p['instrument_id']:p for p in current['positions']}
    assert Decimal(str(current['denominator']['amount']))==1000
    assert Decimal(str(by['SGOV_BOND']['portfolio_amount']['amount']))==534
    assert Decimal(str(by['SGOV_DRY']['portfolio_amount']['amount']))==356
    assert 'SGOV' not in by and scope['funding_buckets'][0]['cash_amount']=='40' and scope['funding_buckets'][0]['reserved_amount']=='10'
    ci=deepcopy(ci);ci['identity']=deepcopy(scope['identity']);ci['source_references']+=out['source_references']
    ci['allocations']['current_allocation']['snapshot']=current;ci['v70_asset_framework']['stock_tactical_amount'].update(amount=100,currency='TWD',value_state='KNOWN')
    cap=m.capacity(scope,ci,request['evaluation_at']);m.validate_confirmed_book(scope,ci,request['evaluation_at'])
    assert cap['occupied']=='75' and cap['incremental_capacity']=='25' and request['confirmed_target']==before
    assert out['original_observations']['sgov_physical_role_partitions'][0]['included_in_available_cash'] is False
    (tmp_path/'SGOV_BUSINESS_INVARIANT.json').write_text(json.dumps(dict(synthetic=True,request=request,context=context,tactical=tactical,
        identities=identities,portfolio_facts_source=desc(),native_canonical_seed=data[1],expected_scope=scope,
        expected_current=current,capacity=cap,cash=scope['funding_buckets'][0]),indent=2))


def test_same_account_cannot_supply_both_physical_and_role_position_copies(tmp_path):
    data=family_case(tmp_path);data[6]['accounts'][0]['positions'].append(deepcopy(data[6]['accounts'][0]['positions'][-1]))
    with pytest.raises(ValueError,match='CANNOT_BE_DUPLICATED'):
        assemble(ROOT,data[2],data[3],artifact_directory=tmp_path/'private',tactical=data[4],identities=data[5],portfolio_facts_source=data[7]())


def test_c7_never_invents_role_targets_when_original_approval_has_one_sgov_line(tmp_path):
    data=original_case(tmp_path);add_rows(data[2],quantity='890',instrument='PHYSICAL_SGOV')
    next(p for p in data[6]['accounts'][0]['positions'] if p['ticker']=='SGOV')['sgov_role_binding']={
        'instrument_key':'PHYSICAL_SGOV','position_as_of_utc':data[2]['evaluation_at']}
    with pytest.raises(RoleSourceUnavailable,match='APPROVED_ROLE_IDS_REQUIRED'):
        assemble(ROOT,data[2],data[3],artifact_directory=tmp_path/'private',tactical=data[4],identities=data[5],portfolio_facts_source=data[7]())


def test_another_accounts_registry_and_role_rows_do_not_change_selected_account(tmp_path):
    request,context,report,*_=case(tmp_path);add_rows(request,account='OTHER_ACCOUNT',instrument='OTHER_SGOV',quantity='99',bond=1000)
    out=produce(request,context,report);assert out['role_quantities']['bond_quantity']=='8.4'


def test_future_position_does_not_change_historical_role_selection(tmp_path):
    request,context,report,*_=case(tmp_path);tables=request['client_snapshot']['payload']['tables']
    tables['portfolio_position'].append({**tables['portfolio_position'][0],'as_of_utc':'2099-01-01T00:00:00Z',
        'recorded_at_utc':'2099-01-01T00:00:00Z','quantity_decimal':'99'})
    assert produce(request,context,report)['role_quantities']['bond_quantity']=='8.4'


def test_unknown_existing_role_does_not_fall_back_to_documentary_dry_policy(tmp_path):
    request,context,report,proposal,_=case(tmp_path);proposal.update(role_state='UNKNOWN',bond_core_bps=None,dry_powder_bps=None)
    assert context.get('approved_document_target_source')
    assert produce(request,context,report)['roles'] is None


@pytest.mark.parametrize('change',[
    lambda t:t['portfolio_instrument'][0].update(identity_state='UNKNOWN'),
    lambda t:t['portfolio_position'][0].update(position_source_reference=''),
    lambda t:t['portfolio_position'][0].update(quantity_decimal='NOT_A_NUMBER'),
    lambda t:t['portfolio_position'][0].update(recorded_at_utc='2099-01-01T00:00:00Z'),
    lambda t:t['sgov_role_proposal'].append({**t['sgov_role_proposal'][0],'version_no':3,'previous_version_no':2}),
    lambda t:t['sgov_role_confirmation'].append({**t['sgov_role_confirmation'][0],'confirmer_reference':'OTHER'})])
def test_source_identity_position_and_version_integrity_are_required(tmp_path,change):
    request,context,report,*_=case(tmp_path);change(request['client_snapshot']['payload']['tables'])
    assert produce(request,context,report)['roles'] is None


def test_zero_physical_position_retains_explicit_policy_and_never_creates_reference_value(tmp_path):
    request,context,report,*_=case(tmp_path,quantity='0',bond=10000);report['analysis_result']['positions'][0]['holding']['quantity']='0'
    out=produce(request,context,report);assert out['purpose']=='BOND' and validated_units(out)['bond_quantity']=='0'
    with pytest.raises(PermissionError,match='ROLE_VALUE_MISMATCH'):
        current_sgov_roles(out['roles'],'0',Decimal('100'),role_source=out)


def test_supplied_role_money_cannot_override_confirmed_units_even_if_one_sided(tmp_path):
    request,context,report,*_=case(tmp_path);out=produce(request,context,report)
    fake=deepcopy(out['roles']);fake['sgov_bond_bucket_amount']['amount']='1400';fake['sgov_dry_powder_bucket_amount']['amount']='0'
    with pytest.raises(PermissionError,match='ROLE_VALUE_MISMATCH'):current_sgov_roles(fake,'1400',Decimal('1400'),role_source=out)


@pytest.mark.parametrize('field',['owner','source_db_sha256','evaluation_at'])
def test_transported_role_units_keep_owner_database_and_cutoff_binding(tmp_path,field):
    request,context,report,*_=case(tmp_path);out=produce(request,context,report)
    out[field]=dict(out['owner'],client_id='OTHER') if field=='owner' else 'OTHER'
    with pytest.raises(RoleSourceUnavailable):validated_units(out)


def test_c7_fills_remain_bound_to_the_one_physical_position_after_role_partition(tmp_path):
    data=family_case(tmp_path);facts=data[6];owner=data[2]['owner']
    facts['fills']=[dict(fill_id='SYNTHETIC_SGOV_FILL',account=owner['account'],asset_id='SGOV',quantity='4',
        applied_to_position_id='SYNTHETIC_SGOV_POSITION',economic_effect_id='SYNTHETIC_SGOV_EFFECT')]
    out=assemble(ROOT,data[2],data[3],artifact_directory=tmp_path/'private',tactical=data[4],identities=data[5],portfolio_facts_source=data[7]())
    assert out['current_allocation']['denominator']['amount']==1000.0
    assert len(out['original_observations']['sgov_physical_role_partitions'])==1
    assert out['scope_candidate']['funding_buckets'][0]['cash_amount']=='40'


def test_dry_units_never_fund_c7_even_with_large_stock_room(tmp_path):
    data=family_case(tmp_path);m,ci,request,context,tactical,identities,facts,desc=data
    tactical['native_currency_amounts']['stock']='1000'
    out=assemble(ROOT,request,context,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities,portfolio_facts_source=desc())
    scope=out['scope_candidate'];ci=deepcopy(ci);ci['identity']=deepcopy(scope['identity']);ci['source_references']+=out['source_references']
    ci['allocations']['current_allocation']['snapshot']=out['current_allocation'];ci['v70_asset_framework']['stock_tactical_amount'].update(amount=1000,currency='TWD',value_state='KNOWN')
    cap=m.capacity(scope,ci,request['evaluation_at'])
    assert cap['incremental_capacity']=='40'
    assert scope['funding_buckets'][0]['cash_amount']=='40' and scope['funding_buckets'][0]['reserved_amount']=='10'
    assert Decimal(str(next(p for p in out['current_allocation']['positions'] if p['instrument_id']=='SGOV_DRY')['portfolio_amount']['amount']))==356


def test_role_names_do_not_replace_underlying_product_classification(tmp_path):
    data=family_case(tmp_path);data[5]['SGOV']={}
    out=assemble(ROOT,data[2],data[3],artifact_directory=tmp_path/'private',tactical=data[4],identities=data[5],portfolio_facts_source=data[7]())
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and 'source_descriptor' not in out
    assert any('ASSET_BUCKET_CLASSIFICATION_REQUIRED' in r['code'] for r in out['issues'])

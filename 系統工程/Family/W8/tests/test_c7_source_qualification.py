"""Named originals versus engineering work, without a new financial guard."""
from copy import deepcopy
import pytest
from test_family_c7_source_assembly import original_case,ROOT
from family_c7_source_assembly import assemble
from c7_source_qualification import AVAILABLE,MISSING,UNQUALIFIED,ENGINEERING,WAITING,annotate


def partial(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    result=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids)
    return req,ctx,t,ids,result


def test_known_approval_stays_available_and_derived_missing_fields_point_to_originals(tmp_path):
    req,ctx,t,ids,out=partial(tmp_path)
    fields={f['field_path']:f for f in out['field_inventory']}
    assert fields['family_scope.approved_target_digest']['dependency_resolution']['state']==AVAILABLE
    owners=fields['family_scope.account_owners']['dependency_resolution']
    assert owners['state']==WAITING and owners['original_requirement_ids']
    assert owners['owner_json_required'] is False
    assert out['source_qualification']['financial_pass_claimed'] is False
    assert out['status']=='PARTIAL_ORIGINAL_SOURCES' and 'source_descriptor' not in out


def test_reconciled_nav_does_not_require_complete_order_book(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    del f['orders'];f['coverage']['orders_complete']=False
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    fields={f['field_path']:f for f in out['field_inventory']}
    assert fields['family_scope.current_nav']['dependency_resolution']['state']==AVAILABLE
    assert fields['family_scope.exposures']['dependency_resolution']['state']==WAITING
    assert out['current_allocation'] is not None and 'source_descriptor' not in out


def test_complete_raw_facts_have_no_new_original_gate_and_empty_confirmed_lists_remain_valid(tmp_path):
    m,ci,req,ctx,t,ids,f,desc=original_case(tmp_path)
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private',tactical=t,identities=ids,portfolio_facts_source=desc())
    assert out['source_qualification']['required_original_facts']==[]
    assert out['status']=='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING'
    assert out['source_qualification']['financial_pass_claimed'] is False


def test_existing_cash_and_ownership_fragments_are_not_called_absent(tmp_path):
    req,ctx,t,ids,out=partial(tmp_path);account=req['owner']['account'];tables=req['client_snapshot']['payload']['tables']
    tables['cash_balance_snapshot']=[{'account_key':account,'as_of_utc':req['evaluation_at'],
        'currency_code':'TWD','reported_cash_minor':5000}]
    tables['account_ownership']=[{'account_key':account,'owner_client_id':req['client_id'],
        'ownership_state':'VERIFIED','source_reference':'SYNTHETIC_OWNER_PROOF','created_at_utc':req['evaluation_at']}]
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private2',tactical=t,identities=ids)
    facts={r['requirement_id']:r for r in out['source_qualification']['original_fact_checks']}
    assert facts['account:'+account+':owner_proof']['state']==AVAILABLE
    assert facts['account:'+account+':cash_eligibility']['state']==UNQUALIFIED
    assert facts['account:'+account+':incremental_authorization']['state']==MISSING


@pytest.mark.parametrize('future_table',[None,'account_ownership','funding_domain'])
def test_fully_bound_original_w1_owners_are_wired_independently_of_missing_nav(tmp_path,future_table):
    req,ctx,t,ids,out=partial(tmp_path);owner=req['owner'];tables=req['client_snapshot']['payload']['tables']
    base={'client_id':req['client_id'],'account_key':owner['account'],'created_at_utc':req['evaluation_at'],
        'source_reference':'SYNTHETIC_W1_IDENTITY_PROOF'}
    tables['portfolio_account']=[dict(base,account_currency=owner['currency'],account_state='KNOWN')]
    tables['account_ownership']=[dict(base,owner_client_id=owner['client_id'],ownership_state='VERIFIED')]
    tables['account_broker_link']=[dict(base,broker_key=owner['broker'],link_state='ACTIVE')]
    tables['funding_account_domain_link']=[dict(base,currency_code=owner['currency'],
        funding_domain_key=owner['funding_domain'],link_state='VERIFIED')]
    tables['funding_domain']=[{'funding_domain_key':owner['funding_domain'],'domain_state':'ACTIVE',
        'purpose_code':'INVESTMENT_CANDIDATE','created_at_utc':req['evaluation_at']}]
    if future_table:
        tables[future_table][0].update(as_of_utc=req['evaluation_at'],created_at_utc='2099-01-01T00:00:00Z')
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private2',tactical=t,identities=ids)
    if future_table:
        assert out['scope_candidate']['account_owners'] is None
        assert 'source_descriptor' not in out
        return
    assert out['scope_candidate']['account_owners']==[owner]
    assert out['scope_candidate']['current_nav'] is None and 'source_descriptor' not in out
    field=next(r for r in out['field_inventory'] if r['field_path']=='family_scope.account_owners')
    assert field['classification']=='EXISTING_BOUND_SOURCE'
    assert field['dependency_resolution']['state']==AVAILABLE


def test_a_present_locator_with_null_order_source_is_not_a_provided_book(tmp_path):
    req,ctx,t,ids,out=partial(tmp_path)
    out['field_inventory'].append({'field_path':'family_scope.exposure_coverage.original_order_snapshot',
        'classification':'ORIGINAL_FACT_NOT_PROVIDED','value_state':'UNKNOWN',
        'source_locators':[{'source':None,'source_sha256':'a'*64}]})
    annotate(out,req)
    facts={r['requirement_id']:r for r in out['source_qualification']['original_fact_checks']}
    assert facts['complete_exposure_book']['state']==MISSING


@pytest.mark.parametrize('stamp',[None,'2099-01-01T00:00:00Z','not-a-timestamp','2026-09-20'])
def test_undated_and_future_account_fragments_remain_existing_unqualified_originals(tmp_path,stamp):
    req,ctx,t,ids,out=partial(tmp_path);account=req['owner']['account'];tables=req['client_snapshot']['payload']['tables']
    tables['portfolio_account']=[{'account_key':account,'account_currency':'TWD','account_state':'KNOWN',
        'created_at_utc':stamp}]
    out=assemble(ROOT,req,ctx,artifact_directory=tmp_path/'private2',tactical=t,identities=ids)
    facts={r['requirement_id']:r for r in out['source_qualification']['original_fact_checks']}
    assert facts['account:'+account+':account_record']['state']==UNQUALIFIED

"""All-asset routing, source dates and account isolation, using safe fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import all_asset_coverage as C
from family_input import digest
from member_v82_analysis import target_source,universe
import test_member_v82_analysis as member_fixture


@pytest.fixture
def case():
    t=member_fixture.MemberV82Tests();t.setUp()
    try:yield t
    finally:t.doCleanups()


def request(t):
    target=target_source(t.snapshot,t.config,t.at)
    return dict(client_id=t.client,run_id='SYNTHETIC',evaluation_at=t.at,
        client_snapshot={'payload':t.snapshot},confirmed_target=target),universe(t.snapshot,target,t.at,t.config['repo_root'])


def test_bond_cash_and_equity_have_separate_complete_coverage(case):
    req,coverage=request(case)
    out=C.build(req,case.config,coverage,case.config['repo_root'])
    assert out['expected']==['QQQ','SGOV','VT'] and out['missing']==[]
    assert out['denominators']['equity']==2 and out['denominators']['bonds']==1
    assert out['denominators']['cash_target_lines']==1
    assert out['bonds'][0]['symbol']=='SGOV' and out['bonds'][0]['route']=='V75'
    assert not out['bonds'][0]['physical_quantity_is_role_amount']
    assert out['coverage_complete'] and not out['financial_completeness_asserted']
    assert out['denominators']['orders_and_commitments'].startswith('COMPLETENESS_UNKNOWN')


def test_bond_read_uses_original_session_validation_without_v82_votes(case):
    req,coverage=request(case);case.config['market_sources']={'SGOV':case.market('SGOV')}
    with patch('on_demand_market_observations.evaluate_observed_history',side_effect=AssertionError('V82 used for bond')):
        out=C.build(req,case.config,coverage,case.config['repo_root'])
    row=out['bonds'][0]
    assert row['market']['rows']==260 and row['market']['market_identity']['currency']=='USD'
    assert row['original_pred009'] is None  # Unbound parameters remain unknown.
    assert row['market']['observed_close'] is not None


def test_latest_value_holding_counts_without_unknown_quantity_becoming_zero(case):
    tables=case.snapshot['tables'];run='SYNTHETIC_CONFIRMED_VALUE'
    tables['portfolio_snapshot_run']=[dict(client_id=case.client,run_id=run,
        run_state='SEALED',source_kind='USER_PROVIDED',as_of_utc='2026-10-25T00:00:00Z',version_no=1)]
    tables['portfolio_snapshot_item']=[dict(client_id=case.client,run_id=run,
        domain_code='USER_CONFIRMED_REAL_HOLDING_VALUE',entity_key='VT',
        field_key='asset_label',value_state='KNOWN',value_text='VT',source_observed_at_utc=None)]
    case.seal();req,coverage=request(case);out=C.build(req,case.config,coverage,case.config['repo_root'])
    row=next(r for r in out['holding_and_target_rows'] if r['symbol']=='VT')
    assert row['coverage_basis']=='HOLDING_AND_TARGET'
    assert row['source_facts'][0]['quantity'] is None
    assert not out['database_written']


def test_missing_one_bond_history_does_not_erase_other_outputs(case):
    req,coverage=request(case);case.config['market_sources']={'SGOV':case.market('SGOV')}
    out=C.build(req,case.config,coverage,case.config['repo_root'])
    bad=deepcopy(case.config);bad['market_sources']={}
    partial=C.build(req,bad,coverage,case.config['repo_root'])
    assert partial['expected']==out['expected'] and partial['missing']==[]
    assert partial['bonds'][0]['market'] is None
    assert partial['bonds'][0]['missing_inputs'][0]['reason']=='EXACT_LISTING_HISTORY_NOT_BOUND'


def test_other_db_and_cross_account_position_are_rejected(case):
    req,coverage=request(case);bad=deepcopy(case.config);bad['source_db_sha256']='b'*64
    with pytest.raises(PermissionError,match='SOURCE_DB_MISMATCH'):C.build(req,bad,coverage,case.config['repo_root'])
    case.snapshot['tables']['portfolio_account']=[dict(client_id=case.client,account_key='OTHER',account_currency='USD')]
    case.seal();req,coverage=request(case)
    with pytest.raises(PermissionError,match='ACCOUNT_MISMATCH'):C.build(req,case.config,coverage,case.config['repo_root'])


def test_original_broker_owner_binding_is_reused_and_never_crosses_member(tmp_path):
    sys.path.insert(0,str(HERE.parent/'W5/tests'))
    from test_broker_snapshot_source import broker_case
    req,_,_,source,_,_=broker_case(tmp_path)
    views=C.read_broker_views(req,{'current_broker_sources':[source]})
    assert views[0]['positions'][0]['quantity']=='3'
    assert views[0]['cash']['available'] is None
    assert not views[0]['order_source']['lifecycle_fully_resolved']
    assert views[0]['order_source']['active_orders'][0]['state']=='REPLACE_PENDING'
    foreign=deepcopy(req);foreign['client_id']='fam_'+'b'*32
    with pytest.raises(PermissionError,match='FOREIGN_BROKER_ACCOUNT'):
        C.read_broker_views(foreign,{'current_broker_sources':[source]})
    with pytest.raises(ValueError,match='DUPLICATE_BROKER_ACCOUNT'):
        C.read_broker_views(req,{'current_broker_sources':[source,source]})

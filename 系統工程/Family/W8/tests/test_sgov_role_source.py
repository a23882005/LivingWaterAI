"""Current role accounting must not reuse target cash or cross owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from sgov_role_source import produce,validate
from native_asset_source import FORMAL_CLASSES


def case(tmp_path,documented=False):
    owner={'client_id':'SYNTHETIC','account':'A','broker':'IBKR','currency':'USD'}
    req={'client_id':'SYNTHETIC','run_id':'R','owner':owner,'evaluation_at':'2026-10-29T01:00:00Z',
        'client_snapshot':{'payload':{'source_sha256':'a'*64,'tables':{
            'sgov_role_proposal':[],'sgov_role_confirmation':[]}}},
        'confirmed_target':{'source_kind':'OFFICIAL_W1_CONFIRMED_ALLOCATION','payload':{'draft':{'target_lines':[
            {'ticker':'0050','instrument_id':'EQ','weight':{'value_state':'KNOWN','value':'0.8'}},
            {'ticker':'SGOV','instrument_id':'BD','weight':{'value_state':'KNOWN','value':'0.2'},
                'source_allocation_row':{'allocation_source_ref':'SYNTHETIC_OWNER_CONFIRMED_SOURCE'}}]}}}}
    row={'symbol':'SGOV','holding':{'quantity':'14'},
        'current_analysis':{'recommendation':{'position_currency':'USD'}},
        'market':{'observed_close':'100','observed_date':'2026-10-27','source_sha256':'b'*64}}
    report={'analysis_result':{'positions':[row]}}
    rule=tmp_path/'rule.md';rule.write_text('\n'.join(FORMAL_CLASSES))
    ctx={'sgov_role_strategic_policy':{'client_id':'SYNTHETIC','stock_percent':80,'bond_percent':20,
        'source_reference':'SYNTHETIC_CURRENT_STRATEGY'},
        'sgov_role_classification_source':{'local_path':str(rule),'sha256':sha256(rule.read_bytes()).hexdigest(),
            'source_reference':'SYNTHETIC_CLASSIFICATION'}}
    if documented:
        doc=tmp_path/'source.md';doc.write_text('## 暫時要求C｜IBKR SGOV角色\n\n'
            '- IBKR內SGOV定位：**美元股票ETF買點彈藥庫**\n'
            '- 不把IBKR SGOV固定當成生活費安全墊\n'
            '- 實際可用金額以最新IBKR截圖／帳戶現金與已掛單需求為準\n\n'
            '## 歷史目標\nSGOV目標400000；舊持倉317股\n')
        ctx['approved_document_target_source']={'client_id':'SYNTHETIC','local_source_path':str(doc),
            'source_sha256':sha256(doc.read_bytes()).hexdigest(),'source_reference':'SYNTHETIC_APPROVED_DOC',
            'source_available_at':'2026-09-19T00:00:00Z'}
    return req,ctx,report


def test_documented_use_applies_to_current_physical_value_not_old_target(tmp_path):
    req,ctx,report=case(tmp_path,True);before=deepcopy((req,ctx,report))
    out=produce(req,ctx,report)
    assert out['status']=='SOURCE_DERIVED_ACCOUNTING' and out['purpose']=='DRY_POWDER'
    assert out['roles']['sgov_bond_bucket_amount']['amount']=='0'
    assert out['roles']['sgov_dry_powder_bucket_amount']['amount']=='1400'
    assert out['owner_role_confirmation'] is None and not out['database_role_rows_created']
    assert not out['physical_included_in_available_cash'] and not out['equity_cash_release_authorized']
    assert (req,ctx,report)==before


def test_single_approved_bond_target_protects_existing_sgov_without_equity_release(tmp_path):
    req,ctx,report=case(tmp_path);out=produce(req,ctx,report)
    assert out['purpose']=='BOND'
    assert out['roles']['sgov_bond_bucket_amount']['amount']=='1400'
    assert out['roles']['sgov_dry_powder_bucket_amount']['amount']=='0'
    assert out['physical_role_sum_reconciled'] and not out['target_amount_used_as_physical_balance']
    report['sgov_role_source']=out;validate(req,ctx,report)
    report['sgov_role_source']['roles']['sgov_dry_powder_bucket_amount']['amount']='1'
    with pytest.raises(PermissionError,match='REPLAY_MISMATCH'):validate(req,ctx,report)


def test_unmapped_other_target_or_strategy_conflict_keeps_role_unknown(tmp_path):
    req,ctx,report=case(tmp_path)
    req['confirmed_target']['payload']['draft']['target_lines'][0]['ticker']='UNMAPPED'
    assert produce(req,ctx,report)['roles'] is None
    req,ctx,report=case(tmp_path);ctx['sgov_role_strategic_policy']['bond_percent']=40
    assert produce(req,ctx,report)['roles'] is None


def test_document_source_changes_or_other_owner_are_rejected(tmp_path):
    req,ctx,report=case(tmp_path,True)
    Path(ctx['approved_document_target_source']['local_source_path']).write_text('changed')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):produce(req,ctx,report)
    req,ctx,report=case(tmp_path,True);ctx['approved_document_target_source']['client_id']='OTHER'
    with pytest.raises(PermissionError,match='CLIENT_MISMATCH'):produce(req,ctx,report)


def test_broker_value_uses_same_member_current_quantity_and_capture(tmp_path):
    req,ctx,report=case(tmp_path,True)
    broker={k:deepcopy(req[k]) for k in ('client_id','run_id','owner')}
    broker.update(captured_at='2026-10-29T00:00:00Z',source_descriptor_digest='c'*64,
        positions=[{'symbol':'SGOV','quantity':'14','market_price':'101'}])
    report['broker_readonly_source']=broker;out=produce(req,ctx,report)
    assert out['roles']['sgov_dry_powder_bucket_amount']['amount']=='1414'
    assert out['physical']['valuation_as_of']==broker['captured_at']
    broker['owner']['account']='OTHER'
    with pytest.raises(PermissionError,match='OWNER_MISMATCH'):produce(req,ctx,report)


def test_existing_role_rows_and_missing_price_currency_do_not_get_defaulted(tmp_path):
    req,ctx,report=case(tmp_path,True)
    req['client_snapshot']['payload']['tables']['sgov_role_proposal']=[{'version_no':1}]
    assert produce(req,ctx,report)['roles'] is None
    req,ctx,report=case(tmp_path)
    report['analysis_result']['positions'][0]['current_analysis']['recommendation']['position_currency']=None
    assert produce(req,ctx,report)['physical'] is None

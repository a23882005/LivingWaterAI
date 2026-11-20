"""Synthetic scope checks plus original native zero-plan and shared cash math."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
import io,json,sys,zipfile
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE.parent/'W5/tests')]
from owner_qqq_scope import read,runtime_rule
from family_input import digest
from funding_guard import check_aggregate,FundingError
from formal_mode_analysis import native


def case(tmp_path):
    owner={'client_id':'fam_'+'a'*32,'broker':'IBKR','account':'SYNTHETIC_ACCOUNT',
        'currency':'USD','funding_domain':'INVESTMENT'}
    request={'client_id':owner['client_id'],'owner':owner,'run_id':'SYNTHETIC_OWNER_QQQ',
        'evaluation_at':'2026-11-20T01:00:00Z','trade_authorization':'NONE',
        'client_snapshot':{'payload':{'source_sha256':'a'*64,'client_id':owner['client_id']}}}
    def desc(p):return {'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}
    text='Joseph／QQQ 取消利率期貨依賴 利率期貨絕對不用 Joseph／QQQ 取消基金結構門檻 Joseph／QQQ 已核准現金一次對帳完成'
    directive=tmp_path/'SYNTHETIC_DIRECTIVE.docx'
    with zipfile.ZipFile(directive,'w') as z:z.writestr('word/document.xml','<document><p>'+text+'</p></document>')
    cash=tmp_path/'SYNTHETIC_CASH.json'
    cash_data={'schema':'Family.PM.OwnerAvailableCashConfirmation.v1','accounts':[
        {'member':'Joseph','broker':'Interactive Brokers','currency':'USD','owner_confirmed_available_cash':'57.83'},
        {'member':'Joseph','broker':'Cathay Securities','currency':'TWD','owner_confirmed_available_cash':'123456'}]}
    cash.write_text(json.dumps(cash_data))
    source={'schema_version':'Family.W8.V82ApprovedSource.v1','client_id':owner['client_id'],'owner':owner,
        'asset_id':'QQQ','source_db_sha256':'a'*64,'available_at':'2026-11-20T00:00:00Z',
        'source_reference':'SYNTHETIC_OWNER_SCOPE',
        'owner_qqq_scope':{'rule_id':'FAMILY_PM_JOSEPH_QQQ_20261120','member':'Joseph',
            'fund_structure':'NOT_APPLICABLE','interest_futures':'NOT_APPLICABLE',
            'directive_source':desc(directive),'cash_source':desc(cash),
            'isolated_test_ledger':str(tmp_path/'isolated.sqlite')}}
    def save():
        p=tmp_path/'SYNTHETIC_OWNER_SOURCE.json';p.write_text(json.dumps(source));return desc(p)
    return request,source,save


def test_owner_source_keeps_both_currencies_once_without_SGOV_or_TWD_conversion(tmp_path):
    req,source,save=case(tmp_path);proof=read(save(),req,'QQQ')
    assert proof['cash_by_currency']=={'USD':'57.83','TWD':'123456'}
    assert proof['fund_structure']==proof['interest_futures']=='NOT_APPLICABLE'
    assert proof['trade_authorization']=='NONE'
    assert source['owner']==req['owner']


@pytest.mark.parametrize('kind',['client','asset','broker','currency','snapshot','future','old_cutoff','rule'])
def test_owner_rule_cannot_spill_to_other_member_asset_or_cutoff(tmp_path,kind):
    req,src,save=case(tmp_path)
    if kind=='client':src['client_id']='OTHER'
    elif kind=='asset':src['asset_id']='VT'
    elif kind=='broker':req['owner']['broker']='OTHER'
    elif kind=='currency':req['owner']['currency']='TWD'
    elif kind=='snapshot':src['source_db_sha256']='b'*64
    elif kind=='future':src['available_at']='2026-11-21T00:00:00Z'
    elif kind=='old_cutoff':req['evaluation_at']='2026-11-18T00:00:00Z'
    else:src['owner_qqq_scope']['rule_id']='OTHER'
    with pytest.raises(PermissionError):read(save(),req,'QQQ')


@pytest.mark.parametrize('manifest',[None,{'local_path':'MISSING_FUTURES_PACKAGE','sha256':'f'*64},
    {'local_path':'LEGACY_OLD_FUTURES_PACKAGE','sha256':'e'*64}])
def test_stock_scope_never_opens_missing_or_old_futures_package(tmp_path,manifest):
    from v75_macro_inputs import read as read_macro
    req,_,save=case(tmp_path)
    with patch('v75_macro_inputs.Path',side_effect=AssertionError('Futures manifest opened')):
        out=read_macro(manifest,req['evaluation_at'],stock_owner_scope={'descriptor':save(),'request':req})
    assert out['future_policy_rate_prediction'] is None
    assert out['source_reference']=='https://m.stockq.org/bond/treasury.php'


def test_required_fund_structure_is_inapplicable_only_for_named_runtime_scope():
    native(ROOT)
    from test_v10_stock_integration import adopted_case
    from stock_engine import run_stock_engine,_plain
    from livingwater_v82_runtime.approved_decision import evaluate
    req,facts,contract=adopted_case();core=_plain(run_stock_engine(ROOT,req,facts,contract)['core_state'])
    context=deepcopy(facts['approved_v10_context']);context['fundamentals_viable']='UNKNOWN'
    context['left_price_conditions']={'SYNTHETIC_FALSE':'FALSE'}
    core['technical'].update(runaway_up='FALSE',right_confirmation='FALSE')
    baseline=evaluate(context,core);assert 'fundamentals_viable' in baseline['stage_audit']['required_unknown_fields']
    i=context['identity'];proof={'rule_id':'FAMILY_PM_JOSEPH_QQQ_20261120','asset_id':'QQQ',
        'client_id':i['client_id'],'owner':i['owner'],'source_db_sha256':i['snapshot_id'],
        'directive_source':{'sha256':'a'*64},'source_descriptor':{'sha256':'b'*64},
        'fund_structure':'NOT_APPLICABLE','interest_futures':'NOT_APPLICABLE'}
    context.update(owner_scoped_rule=proof,fundamentals_viable_applicability='NOT_APPLICABLE')
    scoped=evaluate(context,core)
    assert scoped['formal_stage']=='STAGE_1' and Decimal(scoped['canonical_target_rate'])==Decimal('0.10')
    assert scoped['left_inputs']['fundamentals_long_term_viable']=='NOT_APPLICABLE'
    assert context['fundamentals_viable']=='UNKNOWN'
    context['identity']['asset_id']='VT'
    with pytest.raises(ValueError,match='OWNER_SCOPED'):evaluate(context,core)


@pytest.mark.parametrize('bond,ok',[('17.83',True),('20',False)])
def test_original_guard_applies_one_shared_cash_balance(tmp_path,bond,ok):
    req,_,save=case(tmp_path);proof=read(save(),req,'QQQ');cash=proof['cash_by_currency']['USD']
    claims=[{'claim_id':kind,'owner':req['owner'],'run_id':req['run_id'],'asset_class':kind,'amount':value}
        for kind,value in [('EQUITY','40'),('BOND',bond)]]
    args=dict(owner=req['owner'],run_id=req['run_id'],available=cash,equity_budget=cash,bond_budget=cash,claims=claims)
    if ok:assert check_aggregate(**args)['available_remaining']=='0.00'
    else:
        with pytest.raises(FundingError,match='AGGREGATE_BUDGET_EXCEEDED'):check_aggregate(**args)


def test_original_zero_gap_plan_has_zero_amount_shares_and_idempotent_test_ledger(tmp_path):
    native(ROOT)
    from native_target_source import produce
    from owner_qqq_financial import calculate
    req,_,save=case(tmp_path)
    req['confirmed_target']={'payload':{'draft':{'target_lines':[{'instrument_id':'QQQ','ticker':'QQQ',
        'weight':{'value':'1'},'target_amount':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}],
        'denominator':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}}}
    target=produce(req);ctx={'native_target_source':target};req['native_target_source_digest']=digest(target)
    row={'symbol':'QQQ','holding':{'quantity_state':'KNOWN','quantity':'15'},'position_valuation_allowed':True,
        'market':{'market_identity':{'currency':'USD'},'observed_close':'100'},
        'formal_conclusion':{'canonical_target_rate':'0.10','formal_stage':'STAGE_1',
            'order_source':{'status':'VERIFIED','active_orders':[]}},
        'core_observation':{'result':{'permission':{'hard_gate':'NOT_TRIGGERED','new_buy_order_permission':True,'reason_codes':[]}}}}
    analysis={'owner':req['owner'],'analysis_result':{'positions':[row]}};proof=read(save(),req,'QQQ')
    first=calculate(ROOT,req,ctx,analysis,proof);second=calculate(ROOT,req,ctx,analysis,proof)
    assert first['final_amount']=={'amount':'0','currency':'USD'} and first['final_quantity']=='0'
    assert first['position_gap']['positive_deployment_gap']=='0'
    assert first['bound_shared_cash']['amount']=='57.83'
    assert first['test_ledger']['new_cycles']==first['test_ledger']['new_intents']==0
    assert first==second
    row['holding']['quantity']='0'
    partial=calculate(ROOT,req,ctx,analysis,proof)
    assert partial['status']=='SOURCE_INCOMPLETE' and partial['execution_plan']['execution_amount'] is None

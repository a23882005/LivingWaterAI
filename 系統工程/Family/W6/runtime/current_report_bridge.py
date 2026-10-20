"""Bind a dated report snapshot to targets and optional W5 output.

This is a W6 review input, not a W2 CONFIRMED target or a W1 verified
account record. Those records are never manufactured by the report layer.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from report_receiver import require, digest, receive_action


def number(value):
    require(value is not None and not isinstance(value,bool),'NUMBER_REQUIRED')
    try:x=Decimal(str(value))
    except (ValueError,InvalidOperation):raise ValueError('INVALID_NUMBER')
    require(x.is_finite(),'NONFINITE_NUMBER')
    return x


def bind_current_report(data, *, client_id, alias, run_id, source_reference,
                        expected_source_digest, engine_request=None, engine_result=None):
    require(bool(client_id) and bool(run_id) and bool(source_reference),'REPORT_BINDING_REQUIRED')
    require(data.get('client')==alias,'CURRENT_REPORT_MEMBER_MISMATCH')
    require(digest(data)==expected_source_digest,'CURRENT_SOURCE_DIGEST_MISMATCH')
    require(data.get('production')=='HOLD' and data.get('trade_authorization')=='NONE','REPORT_EXECUTION_SCOPE')
    actual=data['actual'];target=data['target'];broker=data['broker_holdings'];drift=data['drift']
    for name,rows,key in [('actual',actual,'代碼'),('target',target,'代碼'),('drift',drift,'標的')]:
        keys=[r[key] for r in rows];require(len(keys)==len(set(keys)),'DUPLICATE_'+name.upper())
    total=number(data['current_total']);require(total>0,'POOL_MUST_BE_POSITIVE')
    require(abs(sum(number(r['市值TWD']) for r in actual)-total)<Decimal('.001'),'CURRENT_TOTAL_MISMATCH')
    require(abs(sum(number(r['market_value_twd']) for r in broker)-total)<Decimal('.001'),'BROKER_TOTAL_MISMATCH')
    grouped={}
    for row in broker:
        require(number(row['quantity'])>=0,'NEGATIVE_HOLDING')
        grouped[row['symbol']]=grouped.get(row['symbol'],Decimal(0))+number(row['market_value_twd'])
    require(set(grouped)=={r['代碼'] for r in actual},'BROKER_COVERAGE_MISMATCH')
    for row in actual:
        require(abs(grouped[row['代碼']]-number(row['市值TWD']))<Decimal('.001'),'BROKER_ASSET_MISMATCH')
    require(abs(sum(number(r['權重']) for r in target)-1)<Decimal('1e-10'),'TARGET_WEIGHT_SUM')
    require(number(data['target_total'])==total,'TARGET_POOL_MISMATCH')
    for row in target:
        require(0<=number(row['權重'])<=1,'TARGET_WEIGHT_RANGE')
        require(abs(number(row['市值TWD'])-total*number(row['權重']))<Decimal('.001'),'TARGET_AMOUNT_MISMATCH')
    policy=data['target_pool_policy'];require(number(policy['known_subtotal_twd'])==total,'POOL_POLICY_MISMATCH')
    complete=policy.get('complete_total_twd')
    if complete is None:require(bool(policy.get('unknown')),'UNKNOWN_POOL_REASONS_REQUIRED')
    else:require(number(complete)==total and not policy.get('unknown'),'COMPLETE_POOL_CONFLICT')
    a={r['代碼']:r for r in actual};t={r['代碼']:r for r in target}
    labels={}
    for r in actual+target:
        label=r['顯示名稱'];require(label not in labels or labels[label]==r['代碼'],'AMBIGUOUS_DISPLAY_NAME');labels[label]=r['代碼']
    for row in drift:
        k=labels.get(row['標的'],row['標的']);expected=total*number(t[k]['權重']) if k in t else Decimal(0)
        require(abs(number(row['目標金額TWD'])-expected)<Decimal('.001'),'DRIFT_TARGET_MISMATCH')
        if row['實際金額TWD']!='NA':
            require(abs(number(row['差異TWD'])-(number(row['實際金額TWD'])-expected))<Decimal('.001'),'DRIFT_AMOUNT_MISMATCH')
            if k in a:require(abs(number(row['實際金額TWD'])-number(a[k]['市值TWD']))<Decimal('.001'),'DRIFT_CURRENT_MISMATCH')
    require((engine_request is None)==(engine_result is None),'ENGINE_PAIR_REQUIRED')
    if engine_result is not None:
        require(engine_request['client_id']==client_id and engine_request['run_id']==run_id,'CURRENT_ENGINE_BINDING')
        require(engine_result['run_id']==run_id,'CURRENT_ENGINE_RUN')
        engine=receive_action(engine_result,engine_request)
    else:
        engine={'status':'NOT_EVALUATED_CURRENT_SNAPSHOT','items':[],
                'issue_codes':['W2_CONFIRMED_TARGET_NOT_BOUND','W1_ACCOUNT_FUNDING_NOT_VERIFIED','CURRENT_MARKET_POLICY_INPUT_NOT_BOUND'],
                'execution_advice_allowed':False,
                'display':'本次配置已整理；完整目標、帳戶資金與行情輸入尚未交給正式引擎，未產生本次部署建議。'}
    payload={'schema_version':'Family.W6.CurrentReportInput.v1','client_id':client_id,
             'member_alias':alias,'run_id':run_id,'source_reference':source_reference,
             'source_digest':expected_source_digest,'valuation_mode':'DISCLOSED_MIXED_DATE_SNAPSHOT',
             'current':deepcopy(actual),'broker_holdings':deepcopy(broker),
             'target':{'status':'APPROVED_REPORT_WEIGHTS','w2_confirmation_record':None,
                       'rows':deepcopy(target),'pool_policy':deepcopy(policy)},
             'drift':deepcopy(drift),'funding':{'value_state':'UNKNOWN','available_for_execution':None,
                        'reported_cash_is_not_spendable_capacity':True},
             'engine':engine,'formal_output_eligible':False,'production':'HOLD','trade_authorization':'NONE'}
    payload['payload_digest']=digest(payload)
    return payload

"""Producer advice is preserved while every execution permission stays closed."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from jsonschema import Draft202012Validator

from mentor_scope import advice_scope_fields,validate_advice_scope,MentorScopeError,CONTRACT
from mentor_bridge import explain_native
from test_mentor_bridge import mentor_case,ROOT


def test_original_work9_known_amounts_and_protected_actions_keep_scope():
    request,unified,context=mentor_case();before=deepcopy((request,unified,context))
    out=explain_native(ROOT,request,unified,trusted_context=context)
    scope=validate_advice_scope(out)
    assert scope['schema_version']==CONTRACT
    schema=json.loads((Path(__file__).parents[1]/'mentor_advice_scope.schema.json').read_text())
    Draft202012Validator(schema).validate(scope)
    assert out['execution_advice_allowed'] is True and out['broker_execution_allowed'] is False
    assert out['canonical_deployment_result']==unified['canonical_deployment_result']
    for item,original in zip(out['items'],unified['canonical_deployment_result']['items']):
        assert item['recommendation']['amount']==original['deployment_amount']
        assert item['recommendation']['ratio']==original['deployment_ratio']
        assert item['recommendation']['broker_submission_allowed'] is False
    assert any(r['recommendation']['amount']['status']=='KNOWN' and
        r['recommendation']['amount']['value']['amount']=='70.00' for r in out['items'])
    assert any(r['recommendation']['amount']['status']=='KNOWN' and
        r['recommendation']['amount']['value']['amount']=='0' for r in out['items'])
    assert out['items'][0]['client_action']=='HOLD_PROTECTED'
    assert out['items'][0]['risk_signal']['raw_execution_action']=='REDUCE_RISK'
    assert (request,unified,context)==before


@pytest.mark.parametrize('key,value',[
    ('execution_advice_allowed',False),('execution_advice_allowed',1),
    ('broker_execution_allowed',True),('broker_execution_allowed',0),
    ('broker_execution_allowed','false'),('broker_execution_allowed',None),
    ('financial_mutation_allowed',True),('trade_authorization','TRADE'),
    ('production','RELEASED'),('trade_action','BUY'),('schema_version','unknown')])
def test_scope_rejects_conflation_bad_types_and_execution(key,value):
    view=advice_scope_fields();view['mentor_scope'][key]=value
    with pytest.raises(MentorScopeError):validate_advice_scope(view)


@pytest.mark.parametrize('change',['missing_contract','missing_broker','legacy_false','legacy_execution','item_execution'])
def test_missing_and_contradictory_scope_is_rejected(change):
    view=advice_scope_fields()
    if change=='missing_contract':del view['mentor_scope']
    elif change=='missing_broker':del view['broker_execution_allowed']
    elif change=='legacy_false':view['execution_advice_allowed']=False
    elif change=='legacy_execution':view['broker_execution_allowed']=True
    else:view['items']=[{'recommendation':{'broker_submission_allowed':True}}]
    with pytest.raises(MentorScopeError):validate_advice_scope(view)


def test_scope_outputs_are_independent_copies():
    first=advice_scope_fields();first['mentor_scope']['broker_execution_allowed']=True
    assert validate_advice_scope(advice_scope_fields())['broker_execution_allowed'] is False

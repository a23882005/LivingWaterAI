"""Versioned advice-only producer scope; this never authorizes broker actions."""
from copy import deepcopy

CONTRACT='Family.W5.MentorAdviceScope.v1'
_SCOPE={
    'schema_version':CONTRACT,
    'recommendations_allowed':True,
    'execution_advice_allowed':True,
    'broker_execution_allowed':False,
    'financial_mutation_allowed':False,
    'trade_authorization':'NONE',
    'production':'HOLD',
    'trade_action':'NO_TRADE',
}


class MentorScopeError(ValueError):
    pass


def advice_scope_fields():
    """Only call after the original identity, permission and Work9 replay checks."""
    return {'mentor_scope':deepcopy(_SCOPE),
        **{k:_SCOPE[k] for k in ('recommendations_allowed','execution_advice_allowed',
            'broker_execution_allowed','production','trade_action')}}


def validate_advice_scope(view):
    """Validate producer semantics; do not reinterpret legacy advice as execution."""
    scope=view.get('mentor_scope')
    if not isinstance(scope,dict) or set(scope)!=set(_SCOPE):
        raise MentorScopeError('MENTOR_SCOPE_CONTRACT_REQUIRED')
    for key,expected in _SCOPE.items():
        actual=scope[key]
        if type(actual) is not type(expected) or actual!=expected:
            raise MentorScopeError('MENTOR_SCOPE_VALUE_MISMATCH:'+key)
    for key in ('recommendations_allowed','execution_advice_allowed','broker_execution_allowed','production','trade_action'):
        if type(view.get(key)) is not type(_SCOPE[key]) or view[key]!=_SCOPE[key]:
            raise MentorScopeError('MENTOR_SCOPE_LEGACY_FIELD_MISMATCH:'+key)
    for item in view.get('items',[]):
        recommendation=item.get('recommendation') or {}
        if ('broker_submission_allowed' in recommendation
                and recommendation['broker_submission_allowed'] is not False):
            raise MentorScopeError('MENTOR_SCOPE_ITEM_BROKER_EXECUTION_FORBIDDEN')
    return deepcopy(scope)

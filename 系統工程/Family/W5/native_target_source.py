"""Project approved target identities and money units for native consumers.

Original approvals and weights stay intact. This is an ID/FX projection,
not an allocator; an unlisted holding never acquires an invented zero target.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal,InvalidOperation
from family_input import digest
from family_boundary import require


def produce(request,fx_observation=None):
    owner=request['owner'];draft=request['confirmed_target']['payload']['draft']
    currency=owner['currency'];fx=deepcopy(fx_observation)
    if fx is not None:
        require(fx.get('base_currency')=='USD' and fx.get('quote_currency')=='TWD'
            and bool(fx.get('source_url')),'TARGET_FX_SOURCE_INVALID','target_fx_source')
        try:
            observed=date.fromisoformat(fx['as_of'])
            rate=Decimal(str(fx['quote_per_base']))
        except (KeyError,ValueError,InvalidOperation):
            require(False,'TARGET_FX_SOURCE_INVALID','target_fx_source')
        require(observed<=date.fromisoformat(request['evaluation_at'][:10]),
            'TARGET_FX_FUTURE_SOURCE','target_fx_source.as_of')
        require(rate.is_finite() and rate>0,'TARGET_FX_RATE_INVALID','target_fx_source.quote_per_base')
    def money(source):
        if source.get('value_state')!='KNOWN':return deepcopy(source)
        raw=source.get('amount');require(raw is not None and not isinstance(raw,bool),
            'TARGET_NUMBER_INVALID','target.amount')
        value=Decimal(str(raw));require(value.is_finite() and value>=0,'TARGET_NUMBER_INVALID','target.amount')
        src=source.get('currency')
        if src==currency:converted=value
        elif fx is not None and (src,currency)==('TWD','USD'):converted=value/rate
        elif fx is not None and (src,currency)==('USD','TWD'):converted=value*rate
        else:return {'value_state':'UNKNOWN','amount':None,'currency':currency,
            'reason':'TARGET_FX_SOURCE_REQUIRED','original_source_money':deepcopy(source)}
        return {'value_state':'KNOWN','amount':str(converted),'currency':currency,
            'original_source_money':deepcopy(source),
            'basis':'SOURCE_CURRENCY_UNCHANGED' if src==currency else 'DATED_PUBLIC_FX_REFERENCE',
            'fx_observation':deepcopy(fx) if src!=currency else None}
    rows=draft.get('target_lines',[]);counts={}
    for row in rows:counts[row.get('ticker')]=counts.get(row.get('ticker'),0)+1
    targets={};mapping={}
    for row in rows:
        original=row['instrument_id'];ticker=row.get('ticker')
        require(isinstance(ticker,str) and bool(ticker),'TARGET_TICKER_REQUIRED','target_lines.'+original)
        native=ticker if counts[ticker]==1 else original
        require(original not in mapping and native not in targets,
            'TARGET_NATIVE_ID_COLLISION','target_lines.'+original)
        mapping[original]=native
        targets[native]={'source_instrument_id':original,'native_instrument_id':native,
            'ticker':ticker,'weight':deepcopy(row.get('weight')),'target_amount':money(row['target_amount'])}
    out={'schema_version':'Family.W5.NativeTargetSource.v1','client_id':request['client_id'],
        'run_id':request['run_id'],'owner':deepcopy(owner),
        'source_target_digest':digest(request['confirmed_target']),
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],
        'source_to_native':mapping,'targets':targets,'fx_observation':fx,
        'denominator':money(draft.get('denominator',{'value_state':'UNKNOWN'})),
        'scope':'APPROVED_TARGET_ID_AND_CURRENCY_PROJECTION__NO_REALLOCATION',
        'approval_unchanged':True,'trade_action':'NO_TRADE'}
    out['digest']=digest(out)
    return out


def bind(request,context):
    source=context.get('native_target_source')
    if source is None:
        require(request.get('native_target_source_digest') is None,
            'NATIVE_TARGET_SOURCE_REQUIRED','trusted_context.native_target_source')
        return None
    require(isinstance(source,dict) and source.get('schema_version')=='Family.W5.NativeTargetSource.v1',
        'NATIVE_TARGET_SOURCE_REQUIRED','trusted_context.native_target_source')
    require(request.get('native_target_source_digest')==digest(source),
        'NATIVE_TARGET_SOURCE_DIGEST_MISMATCH','native_target_source_digest')
    expected=produce(request,source.get('fx_observation'))
    require(source==expected,'NATIVE_TARGET_SOURCE_REPLAY_MISMATCH','native_target_source')
    return deepcopy(expected)

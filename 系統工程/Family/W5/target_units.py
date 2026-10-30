"""Bind the approved money target to C7's portfolio-weight representation.

V82 calculate_position_gap consumes money. Its canonical #36 is Money/Rate
Target; C8C9 Work8 explicitly consumes the rate representation. Keep both.
"""
from copy import deepcopy
from decimal import Decimal
from family_input import digest


def project_target_units(calculation, c7_computation):
    def fail(reason):raise ValueError('TARGET_UNIT_'+reason)
    def number(value):
        if isinstance(value,bool) or value is None:fail('NUMBER_INVALID')
        n=Decimal(str(value))
        if not n.is_finite() or n<0:fail('NUMBER_INVALID')
        return n
    def single(rows,key):
        found=[r for r in rows if r['instrument_id']==key]
        if len(found)!=1:fail('ASSET_AMBIGUOUS')
        return found[0]
    source=c7_computation['original_source'];result=c7_computation['result']
    if digest(source)!=c7_computation['source_digest']:fail('SOURCE_DIGEST_MISMATCH')
    if result['status']!='READY_FOR_PM_GATE':fail('FRAMEWORK_NOT_READY')
    binding=calculation['built_input']['integration_binding'];asset=binding['asset_id']
    if result['identity']['run_id']!=binding['run_id']:fail('RUN_MISMATCH')
    family=result.get('contract_version')=='C-W7-FAMILY-LT-v1.0.0'
    snapshot=source['work6_result']['final_target']['snapshot']
    if family:
        from work7.family_long_term import validate_result
        proof=validate_result(result)
        # Native Gap uses the approved money pool. The effective C view on
        # Current NAV is only for protection and portfolio-weight reporting.
        snapshot=proof['approved_long_term_target']
    if snapshot['allocation_id']!=binding['authorization_reference']:fail('ALLOCATION_MISMATCH')
    row=single(snapshot['positions'],asset);target=single(result['integrated_asset_framework']['instrument_targets'],asset)
    amount=row['portfolio_amount'];weight=row['weight'];denom=snapshot['denominator']
    if any(v['value_state']!='KNOWN' for v in (amount,weight,denom)):fail('SOURCE_UNKNOWN')
    if weight['unit']!='portfolio_weight':fail('WEIGHT_UNIT')
    if amount['currency']!=binding['currency'] or denom['currency']!=binding['currency']:fail('FX_REQUIRED')
    nav=number(denom['amount']);money=number(amount['amount']);rate=number(weight['value'])
    if nav<=0 or rate>1:fail('RANGE')
    # Same explicit source snapshot; tolerate only serialized float noise.
    if abs(money/nav-rate)>Decimal('1e-12'):fail('AMOUNT_WEIGHT_MISMATCH')
    if not family or not target['protected']:
        if abs(number(target['integrated_weight'])-rate)>Decimal('1e-12'):fail('C7_WEIGHT_MISMATCH')
    if number(calculation['position_gap'].project_target_position_amount)!=money:fail('NATIVE_AMOUNT_MISMATCH')
    current=source['work6_result']['final_target_engine_result']['allocations']['current_allocation']
    if current['value_state']!='KNOWN':fail('CURRENT_UNKNOWN')
    current_row=single(current['snapshot']['positions'],asset)
    current_amount=current_row['portfolio_amount']
    if current_amount['value_state']!='KNOWN':fail('CURRENT_UNKNOWN')
    if current_amount['currency']!=binding['currency']:fail('FX_REQUIRED')
    if number(current_amount['amount'])!=number(calculation['position_gap'].confirmed_amount):fail('CURRENT_AMOUNT_MISMATCH')
    return {'asset_id':asset,'allocation_id':snapshot['allocation_id'],
            'native_target_amount':str(money),'currency':binding['currency'],
            'native_confirmed_amount':str(number(current_amount['amount'])),
            'canonical_target_weight':target['integrated_weight'],'canonical_unit':'portfolio_weight',
            'denominator':deepcopy(denom),'source_target':deepcopy(row),
            **({'approved_long_term_weight':str(rate),'money_base_role':'ORIGINAL_APPROVED_INVESTMENT_POOL',
                'effective_weight_base':deepcopy(proof['current_weight_and_drift_base'])} if family else {}),
            'c7_snapshot_id':result['work7_snapshot_id'],'source_digest':c7_computation['source_digest']}

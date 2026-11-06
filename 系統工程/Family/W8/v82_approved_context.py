"""Source bindings for the single native approved-v1.0 decision contract.

Optional supplementary files supply real facts/histories, not a replacement
engine. Missing sources have named slots and never become fabricated history,
an empty order ledger, a legal range, or permission to mobilize SGOV.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
from family_input import digest
from family_boundary import timestamp


def read_source(descriptor,request,symbol):
    if descriptor is None:return {}
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:raise PermissionError('V82_APPROVED_SOURCE_HASH_MISMATCH')
    data=json.loads(raw.decode('utf-8-sig'))
    expected={'client_id':request['client_id'],'owner':request['owner'],'asset_id':symbol,
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256']}
    if data.get('schema_version')!='Family.W8.V82ApprovedSource.v1' or any(data.get(k)!=v for k,v in expected.items()):
        raise PermissionError('V82_APPROVED_SOURCE_IDENTITY_MISMATCH')
    if not data.get('source_reference') or timestamp(data['available_at'],'available_at')>timestamp(request['evaluation_at'],'evaluation_at'):
        raise PermissionError('V82_APPROVED_SOURCE_NOT_AVAILABLE_AT_CUTOFF')
    # A caller cannot paste the projection produced below into a source file.
    if 'verified_market_identity' in data or 'native_history_source_readback' in data:
        raise PermissionError('V82_MARKET_IDENTITY_DERIVED_PROJECTION_NOT_AN_INPUT')
    evidence=data.get('market_identity_source')
    if evidence is not None:
        import csv,io,re
        from datetime import datetime
        from zoneinfo import ZoneInfo
        bound={k:request[k] for k in ('client_id','run_id','evaluation_at')}
        bound.update(asset_id=symbol,source_db_sha256=expected['source_db_sha256'])
        if (any(data.get(k)!=v or evidence.get(k)!=v for k,v in bound.items())
            or evidence.get('schema_version')!='Family.W8.PV2MarketIdentitySource.v1'
            or evidence.get('provider')!='MASSIVE'):
            raise PermissionError('V82_MARKET_IDENTITY_MEMBER_RUN_DB_OR_CUTOFF_MISMATCH')
        at=timestamp(request['evaluation_at'],'evaluation_at')
        started=timestamp(evidence['started_at'],'started_at')
        retrieved=timestamp(evidence['retrieved_at'],'retrieved_at')
        # This route is an observed US reference snapshot for this query date,
        # not historical dissemination proof for prices or financial fields.
        day=datetime.fromisoformat(request['evaluation_at'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        endpoint='/v3/reference/tickers/'+symbol
        if (evidence.get('endpoint')!=endpoint or evidence.get('query')!={'date':day}
            or evidence.get('source_reference')!='https://api.massive.com'+endpoint+'?date='+day
            or not started<=retrieved<=timestamp(data['available_at'],'available_at')<=at):
            raise PermissionError('V82_MARKET_IDENTITY_SOURCE_SCOPE_OR_TIME_MISMATCH')
        source=evidence['source'];original=Path(source['local_path']).read_bytes()
        if sha256(original).hexdigest()!=source['sha256']:
            raise PermissionError('V82_MARKET_IDENTITY_ORIGINAL_BYTES_CHANGED')
        table=csv.DictReader(io.StringIO(original.decode('utf-8-sig')))
        if len(table.fieldnames or [])!=len(set(table.fieldnames or [])):
            raise PermissionError('V82_MARKET_IDENTITY_ORIGINAL_COLUMNS_AMBIGUOUS')
        records=list(table)
        if len(records)!=1:
            raise PermissionError('V82_MARKET_IDENTITY_SINGLE_ORIGINAL_RECORD_REQUIRED')
        record=records[0]
        if (None in record or any(v is None for v in record.values())
            or record.get('ticker')!=symbol or record.get('market')!='stocks'
            or record.get('locale')!='us' or record.get('active')!='true'
            or not record.get('type')
            or not re.fullmatch(r'[A-Z0-9]{4}',record.get('primary_exchange',''))
            or not re.fullmatch(r'BBG[A-Z0-9]{9}',record.get('share_class_figi',''))
            or not re.fullmatch(r'[a-z]{3}',record.get('currency_name',''))):
            raise PermissionError('V82_MARKET_IDENTITY_ORIGINAL_SECURITY_NOT_QUALIFIED')
        observed={'listing':record['primary_exchange'],'share_class':record['share_class_figi'],
            'currency':record['currency_name'].upper()}
        supplied=data.get('market_identity') or {}
        if (any(supplied.get(k)!=observed[k] for k in ('listing','share_class'))
            or supplied.get('currency',observed['currency'])!=observed['currency']):
            raise PermissionError('V82_MARKET_IDENTITY_ORIGINAL_PROJECTION_MISMATCH')
        proof={'schema_version':'Family.W8.VerifiedPV2MarketIdentity.v1',**bound,
            'market_identity':deepcopy(observed),'provider':'MASSIVE','endpoint':endpoint,
            'query':deepcopy(evidence['query']),'source_reference':evidence['source_reference'],
            'started_at':evidence['started_at'],'retrieved_at':evidence['retrieved_at'],
            'source':deepcopy(source),'availability_basis':'OBSERVED_REFERENCE_CAPTURE_ONLY',
            'historical_financial_PIT_attested':False}
        proof['digest']=digest(proof)
        data['verified_market_identity']={**observed,'currency_source':proof}
    if data.get('native_history_source') is not None:
        if any(data.get(k) is not None for k in ('price_history','valuation_history')):
            raise PermissionError('V82_HISTORY_INLINE_AND_PINNED_ROUTES_CONFLICT')
        from native_history_source import read
        histories,receipt=read(data['native_history_source'],request,symbol)
        data.update(histories)
        data['native_history_source_readback']=receipt
    return data


def build(root,row,request,*,fundamental,price_conditions,left_safety,source_descriptor=None):
    from formal_mode_analysis import native
    native(root)
    from livingwater_v82_runtime.approved_profiles import CUTS,SPEC_SHA256,truth
    from livingwater_v82_runtime.approved_decision import evaluate
    from livingwater_v82_runtime.daily_slice import _or
    from livingwater_v82_runtime.core_rules import tri_and
    from native_asset_source import FORMAL_CLASSES
    classes=dict(zip(FORMAL_CLASSES,CUTS))
    identity=row['native_product_identity'];core=row['core_observation']['result'];market=row['market']
    approved=market.get('approved_technical') or {};extra=read_source(source_descriptor,request,row['symbol'])
    metric=core['valuation'].get('primary_metric')
    selected=[r for r in row['core_observation']['actual_inputs']['valuation_metrics'] if r.get('metric_name')==metric]
    credit=(row.get('macro_observations') or {}).get('credit',{}).get('risk_level')
    profile=classes.get(identity.get('primary_class'),'UNKNOWN')
    observed=(extra.get('market_identity') or {})
    # Listing/share-class are indispensable to own-history identity. A ticker
    # or an account's currency alone does not prove either field.
    market_identity={'listing':observed.get('listing'),'share_class':observed.get('share_class')}
    if extra.get('verified_market_identity') is not None:
        market_identity=deepcopy(extra['verified_market_identity'])
    supplied_fundamental=extra.get('fundamentals_viable')
    if identity.get('asset_type')=='INDIVIDUAL_STOCK':fundamental=supplied_fundamental
    macro=extra.get('macro_pressure_inputs') or {}
    inflation=truth(macro.get('inflation_chain_accelerating'))
    real=truth(macro.get('real_yield_rising_fast'));bias=macro.get('policy_bias')
    hawkish=truth(bias=='HAWKISH') if bias in ('HAWKISH','DOVISH','NEUTRAL') else truth(None)
    pressure=_or(inflation,tri_and(real,hawkish))
    context={'schema_version':'V82.ApprovedDecisionContext.v1','spec_sha256':SPEC_SHA256,
        'identity':{'client_id':request['client_id'],'asset_id':row['symbol'],'run_id':request['run_id'],
            'owner':deepcopy(request['owner']),'snapshot_id':request['client_snapshot']['payload']['source_sha256'],
            'evaluation_at':request['evaluation_at']},'market_identity':market_identity,
        'profile_id':profile,'current_metric_value':selected[0].get('current') if len(selected)==1 else None,
        'fundamentals_viable':truth(fundamental).value,
        'left_price_conditions':{k:truth(v).value for k,v in price_conditions.items()},
        'left_safety':truth(extra.get('left_safety',left_safety)).value,
        'off_low':approved.get('off_low','UNKNOWN'),
        'credit_level':credit if type(credit) is int else extra.get('credit_level'),
        'credit_allows_right':truth(credit<=1 if type(credit) is int else
            extra['credit_level']<=1 if type(extra.get('credit_level')) is int else None).value,
        'core_etf':'TRUE' if identity.get('asset_type')=='BROAD_ETF' else 'FALSE' if identity.get('asset_type') else 'UNKNOWN',
        'high_beta':extra.get('high_beta','UNKNOWN'),
        'macro_pressure':pressure.value,
        'right_valuation_condition':truth(core['valuation']['level']!='EXTREME_CANDIDATE'
            if core['valuation'].get('formal_output_eligible') else None).value,
        'right_event_dependencies':deepcopy(extra.get('right_event_dependencies',[])),
        'right_event_dependency_scope_verified':extra.get('right_event_dependency_scope_verified',False),
        'stage_required_facts':{'asset_identity':truth(identity.get('asset_type') is not None).value,
            'primary_framework':truth(bool(row.get('primary_framework')) and profile in CUTS).value,
            **deepcopy(extra.get('additional_stage_facts',{}))},
        'stage_restrictions':deepcopy(extra.get('stage_restrictions',[])),
        'stage_constraint_facts':deepcopy(extra.get('stage_constraint_facts',{})),
        'absolute_range_proof':deepcopy(extra.get('absolute_range_proof')),
        'valuation_history':deepcopy(extra.get('valuation_history')),'price_history':deepcopy(extra.get('price_history')),
        'maturity_signals':deepcopy(approved.get('left_maturity_signals',[])),
        'trend_timing_inputs':deepcopy(approved.get('trend_timing_inputs',{
            'bars':[],'ma5':None,'ma10':None,'ma20':None,'previous_atr14':None,'previous_close':None,
            'breakout_retest_success':'UNKNOWN'})),
        'session':deepcopy(extra.get('session',{})),'cycle_snapshot':deepcopy(extra.get('cycle_snapshot')),
        'planning_ledger_source':deepcopy(extra.get('planning_ledger_source')),
        'execution_costs':deepcopy(extra.get('execution_costs')),
        'execution_constraints':deepcopy(extra.get('execution_constraints')),
        'additional_position_caps':deepcopy(extra.get('additional_position_caps')),
        'additional_caps_scope_verified':extra.get('additional_caps_scope_verified',False),
        'shared_allocation_request':deepcopy(extra.get('shared_allocation_request')),
        'funding_layers':deepcopy(extra.get('funding_layers')),
        'supplemental_source_descriptor':deepcopy(source_descriptor),
        'source_binding':{'analysis_core_digest':digest(row['core_observation']),
            'technical_digest':digest(approved),'source_reference':extra.get('source_reference'),
            'supplementary_facts_supplied':bool(extra)}}
    if row.get('history_source_qualification') is not None:
        context['source_binding']['history_source_qualification_digest']=row['history_source_qualification']['digest']
        # Source observations cannot fill valuation_history/price_history or
        # safety predicates. Those remain the original qualified input routes.
    if extra.get('native_history_source_readback') is not None:
        context['source_binding']['native_history_source_readback']=deepcopy(extra['native_history_source_readback'])
    return context,evaluate(context,core)


def validate(root,row,request,trusted_context,*,target_projection=None):
    """Re-read supplementary bytes and replay the same native rule producer."""
    from formal_mode_analysis import build_formal_conclusion
    from current_analysis_delivery import current_judgment
    actual=row.get('formal_conclusion')
    if not row.get('core_observation'):
        if actual is not None:raise PermissionError('V82_APPROVED_UNEXPECTED_CONCLUSION')
        return
    expected=build_formal_conclusion(root,row,request,target_projection=target_projection,
        approved_source_descriptor=(trusted_context.get('v82_approved_sources') or {}).get(row['symbol']))
    for key in ('approved_v10_context','approved_v10_analysis','market_predicates',
                'selected_mode','formal_stage','canonical_target_rate','four_modes'):
        if not actual or actual.get(key)!=expected[key]:
            raise PermissionError('V82_APPROVED_NATIVE_REPLAY_MISMATCH:'+key)
    if row['current_analysis']['current_judgment']!=current_judgment(row,root,
            approved_target=expected['approved_project_target']):
        raise PermissionError('V82_APPROVED_REPORT_JUDGMENT_REPLAY_MISMATCH')

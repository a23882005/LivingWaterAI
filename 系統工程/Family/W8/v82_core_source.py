"""Checked operator evidence for the unchanged V82 Core input contract.

Each supplied leaf retains its own source bytes, availability and validity.
Fetching a current page cannot attest historical PIT or negative event coverage.
Absent leaves remain absent; this adapter does not create safety decisions.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json

SCHEMA='Family.W8.V82CoreSource.v1'
SAFETY=('safety.macro','safety.credit_liquidity','safety.material_events','safety.etf_structure')
LEFT_PRICE=('price_map_zone','near_confirmed_low','near_important_ma_or_support','meaningful_drawdown')
LEFT_EVENT='uncontrollable_event_gap_clear'
LEFT_LEAVES=tuple('left.'+name for name in (*LEFT_PRICE,LEFT_EVENT))


def time(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None:raise ValueError('V82_CORE_SOURCE_TIMEZONE_REQUIRED')
    return result


def _bytes(descriptor):
    raw=Path(descriptor['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=descriptor['sha256']:
        raise PermissionError('V82_CORE_SOURCE_HASH_MISMATCH')
    return raw


def read(descriptor,request,symbol):
    if descriptor is None:return None
    raw=_bytes(descriptor);data=json.loads(raw)
    expected={'client_id':request['client_id'],'owner':request['owner'],'asset_id':symbol,
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256']}
    at=time(request['evaluation_at'])
    if data.get('schema_version')!=SCHEMA or any(data.get(k)!=v for k,v in expected.items()):
        raise PermissionError('V82_CORE_SOURCE_SCOPE_MISMATCH')
    if time(data['available_at'])>at or not data.get('source_reference'):
        raise PermissionError('V82_CORE_SOURCE_NOT_AVAILABLE')
    leaves={}
    for name,record in data.get('leaves',{}).items():
        if name not in (*SAFETY,*LEFT_LEAVES,'hard_gate_predicates','structural_confirmation','theses','valuation_metrics','fundamental_fields'):
            raise ValueError('V82_CORE_SOURCE_UNKNOWN_LEAF:'+name)
        proof=record.get('proof',{})
        original=_bytes(proof)
        # A producer's source contract must explicitly bound freshness. No
        # blanket "N/A" converts a current capture into formal safety evidence.
        if (not proof.get('source_reference') or not proof.get('methodology_reference')
            or not time(proof['as_of'])<=time(proof['available_at'])<=time(data['available_at'])<=at
            or time(proof['valid_until'])<at or proof.get('pit_status')!='VERIFIED'
            or not proof.get('pit_receipt_reference')):
            raise PermissionError('V82_CORE_LEAF_VALIDITY_OR_PIT_REQUIRED:'+name)
        value=deepcopy(record.get('value'))
        if name in LEFT_LEAVES:
            # Replay the source owner's assertion, not a pasted price vote or
            # an invented near-support/drawdown formula. Asset-local methods
            # must already have an explicit approved definition and reference.
            assertion=json.loads(original)
            bound={**expected,'run_id':request['run_id'],'evaluation_at':request['evaluation_at']}
            definition=assertion.get('rule_definition') or {}
            if (value not in ('TRUE','FALSE','UNKNOWN')
                or assertion.get('schema_version')!='Family.W8.VerifiedLeftAssertion.v1'
                or any(assertion.get(k)!=v for k,v in bound.items())
                or assertion.get('field_path')!=name or assertion.get('value')!=value
                or assertion.get('validation_status')!='VERIFIED'
                or definition.get('approval_state')!='APPROVED_EXISTING_RULE'
                or not definition.get('authority_reference')
                or definition.get('methodology_reference')!=proof['methodology_reference']
                or definition.get('rule_reference')!=('V82 Work41-D / Work34' if name=='left.'+LEFT_EVENT else 'V82 Work41-A')
                or any(assertion.get(k)!=proof[k] for k in ('as_of','available_at','valid_until'))):
                raise PermissionError('V82_LEFT_ORIGINAL_ASSERTION_OR_DEFINITION_REQUIRED:'+name)
            if (not proof.get('retrieved_at') or assertion.get('retrieved_at')!=proof['retrieved_at']
                or not time(proof['available_at'])<=time(proof['retrieved_at'])<=time(data['available_at'])):
                raise PermissionError('V82_LEFT_ORIGINAL_ACQUISITION_TIME_REQUIRED:'+name)
            if name!='left.'+LEFT_EVENT:
                if (assertion.get('observation_scope')!='COMPLETED_SESSION'
                    or not assertion.get('session_close_at')
                    or time(assertion['session_close_at'])>time(proof['as_of'])
                    or not assertion.get('price_basis')):
                    raise PermissionError('V82_LEFT_COMPLETED_SESSION_AND_BASIS_REQUIRED:'+name)
            else:
                coverage=assertion.get('coverage') or {};required=coverage.get('required_domains')
                if (not isinstance(required,list) or not required or len(required)!=len(set(required))
                    or set(coverage.get('checked_domains',[]))!=set(required)
                    or not coverage.get('required_domain_scope_reference')
                    or not coverage.get('event_registry_checkpoint')
                    or coverage.get('active_event_registry_reviewed') is not True
                    or not coverage.get('coverage_cutoff')
                    or time(coverage['coverage_cutoff'])!=time(proof['as_of'])
                    or assertion.get('event_dependency_scope_verified') is not True
                    or not isinstance(assertion.get('event_dependencies'),list)):
                    raise PermissionError('V82_LEFT_EVENT_COVERAGE_AND_DEPENDENCIES_REQUIRED')
            leaves[name]={'value':value,'proof':deepcopy(proof),'original_assertion':assertion}
            continue
        if name in SAFETY:
            if value not in ('TRUE','FALSE'):
                raise ValueError('V82_CORE_SAFETY_TRUTH_REQUIRED:'+name)
            if name=='safety.material_events':
                coverage=record.get('coverage',{})
                required=coverage.get('required_domains')
                if (not isinstance(required,list) or not required or len(set(required))!=len(required)
                    or set(coverage.get('checked_domains',[]))!=set(required)
                    or not coverage.get('event_registry_checkpoint')
                    or time(coverage['coverage_cutoff'])!=time(proof['as_of'])):
                    raise PermissionError('V82_CORE_EVENT_COVERAGE_REQUIRED')
        elif name=='hard_gate_predicates':
            if (not isinstance(value,list) or not value
                or any(v not in ('TRUE','FALSE','UNKNOWN') for v in value)
                or record.get('complete_predicate_scope_verified') is not True):
                raise PermissionError('V82_CORE_HARD_GATE_SCOPE_REQUIRED')
        elif name=='structural_confirmation':
            if value not in ('TRUE','FALSE','UNKNOWN'):raise ValueError('V82_CORE_STRUCTURAL_TRUTH_REQUIRED')
        elif not isinstance(value,list):
            raise ValueError('V82_CORE_FIELD_LIST_REQUIRED:'+name)
        if name in ('valuation_metrics','fundamental_fields'):
            key='metric_name' if name=='valuation_metrics' else 'field_name'
            names=[r.get(key) for r in value]
            if None in names or len(set(names))!=len(names):raise ValueError('V82_CORE_DUPLICATE_OR_MISSING_FIELD:'+name)
            for r in value:
                if (r.get('source_reference')!=proof['source_reference']
                    or r.get('source_sha256')!=proof['sha256']
                    or r.get('as_of')!=proof['as_of'] or not r.get('unit')
                    or r.get('freshness')!='FRESH' or r.get('pit_status')!='VERIFIED'
                    or r.get('data_quality') not in ('OK','FALLBACK_USED')):
                    raise PermissionError('V82_CORE_FIELD_PROOF_MISMATCH:'+name)
        leaves[name]={'value':value,'proof':deepcopy(proof)}
    return {'schema_version':SCHEMA,'source_sha256':descriptor['sha256'],
        'source_reference':data['source_reference'],'leaves':leaves,
        **({'source_descriptor':deepcopy(descriptor)} if set(leaves)&set(LEFT_LEAVES) else {})}


def left_inputs(qualified_source,request,symbol):
    """Re-read the existing Core-source seam before exposing original Left leaves."""
    source=qualified_source or {}
    if not set(source.get('leaves',{}))&set(LEFT_LEAVES):return {}
    if read(source['source_descriptor'],request,symbol)!=source:
        raise PermissionError('V82_LEFT_ORIGINAL_SOURCE_REPLAY_MISMATCH')
    return {name[5:]:deepcopy(record) for name,record in source['leaves'].items() if name in LEFT_LEAVES}


def arguments(source,*,broad_etf):
    """Translate qualified leaves only; the native Core owns all arbitration."""
    if not source:return {},set()
    from livingwater_v82_runtime.core_rules import EvidenceFact
    from livingwater_v82_runtime.enums import PredicateTruth,RequirementLevel,DataQuality,Freshness,PitStatus
    result={};resolved=set();safety=[]
    for name,leaf in source['leaves'].items():
        # Left source assertions are consumed by Work41, not as extra kwargs
        # or safety/valuation facts in the unchanged Core.
        if name in LEFT_LEAVES:continue
        if name=='safety.etf_structure' and not broad_etf:
            raise PermissionError('V82_CORE_ETF_STRUCTURE_ON_INDIVIDUAL_STOCK')
        if name in ('theses','structural_confirmation') and broad_etf:
            raise PermissionError('V82_CORE_COMPANY_THESIS_ON_ETF')
        value=leaf['value'];proof=leaf['proof']
        if name in SAFETY:
            safety.append(EvidenceFact(name=name,value=value,requirement=RequirementLevel.SAFETY_REQUIRED,
                data_quality=DataQuality.OK,freshness=Freshness.FRESH,pit_status=PitStatus.VERIFIED,
                source_reference=proof['source_reference']))
            resolved.add(name)
        elif name=='hard_gate_predicates':
            result[name]=[PredicateTruth(v) for v in value];resolved.add(name)
        elif name=='structural_confirmation':
            result[name]=PredicateTruth(value);resolved.add(name)
        else:result[name]=deepcopy(value)
    result['safety_facts']=safety
    return result,resolved

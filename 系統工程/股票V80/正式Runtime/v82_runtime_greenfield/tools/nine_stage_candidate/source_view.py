"""Dated reference display; qualification/expiry belongs to the source owner.

This view never manufactures a TTL, a valuation percentile, a PIT vintage or
financial permission. A reference without an owner-defined expiry stays dated
information and cannot become FRESH through repeated cache reads.
"""
from copy import deepcopy
from .engine import _stamp


def reference_view(source, *, decision_cutoff, expected_identity):
    row=deepcopy(source)
    fields=('instrument','listing','currency','metric','price_basis')
    if any(not expected_identity.get(k) or row.get(k)!=expected_identity[k] for k in fields):
        raise ValueError('REFERENCE_IDENTITY_OR_METRIC_CONFLICT')
    if not row.get('source_reference') or not row.get('source_digest'):
        raise ValueError('REFERENCE_SOURCE_BINDING_REQUIRED')
    cutoff=_stamp(decision_cutoff)
    availability=row.get('available_at')
    if not availability:
        state='AVAILABILITY_UNKNOWN'
    elif _stamp(availability)>cutoff:
        state='NOT_AVAILABLE_AT_DECISION'
    elif row.get('valid_until') is None:
        state='DATED_REFERENCE__VALIDITY_UNDEFINED'
    elif not row.get('validity_contract_reference'):
        raise ValueError('OWNER_DEFINED_VALIDITY_CONTRACT_REQUIRED')
    elif cutoff>_stamp(row['valid_until']):
        state='EXPIRED'
    else:
        state='WITHIN_ORIGINAL_SOURCE_VALIDITY'
    row.update(reference_state=state,refresh_changes_observed_date=False,
        historical_qV_inferred=False,financial_permission_granted=False)
    return row


def reference_chain(sources, *, decision_cutoff, expected_identity):
    views=[reference_view(s,decision_cutoff=decision_cutoff,expected_identity=expected_identity) for s in sources]
    qualified=[v for v in views if v['reference_state']=='WITHIN_ORIGINAL_SOURCE_VALIDITY'
        and (v.get('source_role')=='ORIGINAL_PRODUCER' or
            v.get('fallback_approval_reference') and v.get('source_role') in ('APPROVED_FALLBACK','LAST_KNOWN_VALID'))]
    return {'dated_views':views,'selected_qualified_source':qualified[0] if qualified else None,
        'historical_qV':None,'current_PE_is_forward_PE':False,'new_global_TTL_created':False,
        'source_owner_order_preserved':True}

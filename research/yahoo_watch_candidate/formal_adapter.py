"""Project existing approved producer outputs; no duplicated V82 calculations.
The caller must obtain these outputs from verified original runtime execution,
not arbitrary user/uploaded JSON. Hash binding does not authenticate a producer.
"""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def tri(value):
    return {'TRUE':True,'FALSE':False,'UNKNOWN':None}.get(value) if isinstance(value,str) else None

def project(analysis, technical, *, receipt):
    if receipt.get('source_qualification')!='VERIFIED_FORMAL_DAILY':
        raise ValueError('FORMAL_DAILY_QUALIFICATION_REQUIRED')
    if receipt.get('analysis_sha256')!=digest(analysis) or receipt.get('technical_sha256')!=digest(technical):
        raise ValueError('PRODUCER_OUTPUT_BINDING_MISMATCH')
    for key in ('rule_sha256','snapshot_id','producer_id','as_of','valid_until'):
        if receipt.get(key) is None:raise ValueError('PROVENANCE_REQUIRED')
    # Only these formal outputs leave this boundary. Client/account identities,
    # holdings, cash, selected stage and quantity are never copied to monitoring.
    price=analysis.get('left_inputs',{}).get('price_condition_at_least_one')
    down=technical.get('native_technical_aggregation',{}).get('runaway_down')
    return {k:receipt[k] for k in ('rule_sha256','snapshot_id','producer_id','as_of','valid_until')} | {
        'qualified_formal_daily_input':True,'L_price':tri(price),'RunawayDown':tri(down)}

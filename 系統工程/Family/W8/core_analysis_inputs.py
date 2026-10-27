"""Source-to-Core arguments and diagnostics, with no investment algorithm.

The unchanged Core owns the waterfall and tri-state aggregation. Missing
contracts remain explicit; prices cannot stand in for news or safety evidence.
"""
from copy import deepcopy

GLOBAL_ETF_WATERFALL=('FORWARD_PE','TRAILING_PE','CAPE','PB','FCF_YIELD')


def issuer_inputs(facts, dated_metrics=()):
    metrics=[];fundamentals=[]
    if facts:
        for name,record in facts['metrics'].items():
            common={'source_reference':facts['source_url'],'source_sha256':facts['source_sha256'],
                'as_of':facts['as_of'],'observed_date_text':facts['as_of']}
            if name in GLOBAL_ETF_WATERFALL:
                metrics.append({**common,'metric_name':name,'current':record['value'],
                    'unit':record.get('unit'),'historical_median':None,
                    'data_quality':'OK','freshness':'UNKNOWN','pit_status':'UNVERIFIABLE',
                    'scope':'DATED_ISSUER_FACT__VALIDITY_AND_HISTORICAL_BASIS_UNVERIFIED'})
            if name in ('ROE','EARNINGS_GROWTH'):
                fundamentals.append({**common,'field_name':name,'value':record['value'],
                    'unit':record.get('unit'),'requirement_level':'MODULE_REQUIRED',
                    'field_value_state':'KNOWN','data_quality':'OK','direction':'UNKNOWN'})
    # A historical observation is not allowed to replace the latest fact with
    # the same metric name in the native resolver's map.
    names={r['metric_name'] for r in metrics}
    metrics.extend(deepcopy(r) for r in dated_metrics if r['metric_name'] not in names)
    present={r['field_name'] for r in fundamentals}
    for name in ('ROE','EARNINGS_GROWTH'):
        if name not in present:
            fundamentals.append({'field_name':name,'value':None,'requirement_level':'MODULE_REQUIRED',
                'field_value_state':'UNKNOWN','data_quality':'UNKNOWN','direction':'UNKNOWN'})
    return metrics,fundamentals


def valuation_path_audit(metrics):
    by={r['metric_name']:r for r in metrics};audit=[]
    for name in GLOBAL_ETF_WATERFALL:
        metric=by.get(name);missing=[]
        if metric is None:missing=['current','source_reference','as_of','unit','methodology']
        else:
            missing=[k for k in ('current','source_reference','as_of','unit') if metric.get(k) is None]
            if metric.get('freshness') not in ('FRESH','NOT_APPLICABLE'):missing.append('freshness_contract')
            if metric.get('pit_status') not in ('VERIFIED','NOT_APPLICABLE'):missing.append('pit_receipt')
            # Raw multiples must have their own legal scale; never borrow the
            # operational Forward PE scale for trailing PE or PB.
            if metric.get('historical_median') is None and metric.get('valuation_level') is None:
                missing.append('own_historical_reference_or_authorized_range')
        audit.append({'metric':name,'status':'UNAVAILABLE' if missing else 'INPUT_READY',
            'missing_fields':missing,'source_reference':(metric or {}).get('source_reference'),
            'sot_section':'V82 §32.6 / §32.6A / §32.3 / §32.21A',
            'blocks_other_candidates':False})
    return audit


def unresolved_core_contracts(observed,broad_etf):
    gaps=[
        ('safety.macro','SOURCE_CONTRACT_MISSING','V70 raw feed is not a verified V82 macro safety fact set','V82 §38–40 / §62'),
        ('safety.credit_liquidity','SOURCE_CONTRACT_MISSING','Verified credit/liquidity level, direction and speed are absent','V82 §38–40 / §62'),
        ('safety.material_events','SOURCE_CONTRACT_MISSING','Required-domain event coverage/checkpoint evidence is absent','V82 Work5 / §62'),
        ('hard_gate_predicates','SOURCE_CONTRACT_MISSING','No complete same-run original V82 safety predicate producer result is bound','V82 §39 / §62'),
        ('ma20_ok','DEFINITION_OR_PRODUCER_UNRESOLVED','MA20 comparison is available; the significant-break predicate has no verified executable mapping. Close > MA20 is not a substitute','V82 §43-A / §24-C')]
    if broad_etf:
        gaps.append(('safety.etf_structure','SOURCE_CONTRACT_MISSING',
            'Product diversification establishes type/grade, not current ETF structural safety or event coverage','V82 Work4 ETF applicability'))
    else:
        gaps.append(('structural_confirmation','SOURCE_CONTRACT_MISSING',
            'No verified company thesis/event confirmation is bound','V82 Work4'))
    return [{'field_path':path,'kind':kind,'reason':reason,'sot_section':section}
        for path,kind,reason,section in gaps]

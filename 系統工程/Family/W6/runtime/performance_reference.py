"""W6 historical weighted reference; never portfolio CAGR or scenario score."""
from math import isfinite, fsum

def weighted_reference(weights, metrics):
    if len({r['instrument_id'] for r in weights}) != len(weights):
        raise ValueError('DUPLICATE_INSTRUMENT')
    if any(not isfinite(r['weight']) or r['weight'] < 0 for r in weights):
        raise ValueError('INVALID_WEIGHT')
    if abs(fsum(r['weight'] for r in weights)-1) > 1e-9:
        raise ValueError('WEIGHT_SUM_NOT_ONE')
    rows=[];basis=set();covered=[];contributions=[]
    for row in weights:
        metric=metrics.get(row['instrument_id'],{})
        value=metric.get('annualized_return')
        numeric=isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value)
        complete=all(metric.get(k) not in (None,'','UNKNOWN','NA') for k in ('currency','period_start','period_end','as_of','return_basis'))
        use=numeric and complete
        if row['weight']>0 and use:
            basis.add(tuple(metric[k] for k in ('currency','period_start','period_end','as_of','return_basis')))
            covered.append(row['weight']);contributions.append(row['weight']*value)
        rows.append({**row,'annualized_return':value if numeric else None,'contribution':row['weight']*value if use else None,'state':'KNOWN' if use else 'DATA_UNAVAILABLE'})
    coverage=fsum(covered);comparable=len(basis)==1
    full=abs(coverage-1)<1e-9 and comparable
    return {'coverage':coverage,'known_contribution':fsum(contributions) if contributions else None,'a_ref':fsum(contributions) if full else None,'state':'KNOWN' if full else 'DATA_UNAVAILABLE','comparable_basis':comparable,'rows':rows,'score_0_100':None,'defense_score':None,'model':'W6_WEIGHTED_REFERENCE_V1'}

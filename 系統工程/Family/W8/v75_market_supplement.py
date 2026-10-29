"""Bind a captured public daily MOVE series to original V75 PRED-005.

Provider observations supplement, rather than rewrite, the V70 macro snapshot.
No exchange-close, canonical freshness or other predicate facts are invented.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json


def _time(value):
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.utcoffset() is None:raise ValueError('V75_SUPPLEMENT_TIMEZONE_REQUIRED')
    return at


def read(source,evaluation_at):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    receipt_raw=Path(source['receipt_path']).read_bytes()
    if (sha256(raw).hexdigest()!=source['sha256']
        or sha256(receipt_raw).hexdigest()!=source['receipt_sha256']):
        raise PermissionError('V75_SUPPLEMENT_SOURCE_CHANGED')
    receipt=json.loads(receipt_raw)
    at=_time(evaluation_at);available=_time(receipt['available_at'])
    if (receipt.get('http_status')!=200 or receipt.get('sha256')!=source['sha256']
        or available>at or _time(receipt['requested_at'])>available
        or not receipt.get('url','').startswith('https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE?')):
        raise PermissionError('V75_SUPPLEMENT_RECEIPT_BINDING_MISMATCH')
    data=json.loads(raw,parse_float=Decimal)['chart']
    if data.get('error') or len(data.get('result') or [])!=1:
        raise ValueError('V75_SUPPLEMENT_PROVIDER_RESULT_REQUIRED')
    result=data['result'][0];meta=result['meta']
    if meta.get('symbol')!='^MOVE' or meta.get('exchangeTimezoneName')!='America/New_York':
        raise PermissionError('V75_SUPPLEMENT_SYMBOL_OR_TIMEZONE_MISMATCH')
    stamps=result['timestamp'];values=result['indicators']['quote'][0]['close']
    if len(stamps)!=len(values) or stamps!=sorted(set(stamps)):
        raise ValueError('V75_SUPPLEMENT_DATE_ORDER_OR_COVERAGE')
    zone=ZoneInfo(meta['exchangeTimezoneName']);points={}
    for stamp,value in zip(stamps,values):
        observed=datetime.fromtimestamp(stamp,zone).date()
        available_day=available.astimezone(zone).date()
        if observed>available_day:
            raise ValueError('V75_SUPPLEMENT_NONCLOSED_OR_FUTURE_SESSION')
        if observed==available_day:
            regular=meta.get('currentTradingPeriod',{}).get('regular',{})
            end=datetime.fromtimestamp(regular['end'],zone) if regular.get('end') else None
            if end is None or end.date()!=observed or end>available or meta.get('dataGranularity')!='1d':
                raise ValueError('V75_SUPPLEMENT_NONCLOSED_OR_FUTURE_SESSION')
        if observed in points:raise ValueError('V75_SUPPLEMENT_DUPLICATE_SESSION')
        if value is not None:
            if isinstance(value,bool):raise ValueError('V75_SUPPLEMENT_INVALID_INDEX_VALUE')
            value=Decimal(value)
            if not value.is_finite() or value<=0:raise ValueError('V75_SUPPLEMENT_INVALID_INDEX_VALUE')
        points[observed]=value
    if not points:raise ValueError('V75_SUPPLEMENT_EMPTY_SERIES')
    last=max(points)
    if points[last] is None:raise ValueError('V75_SUPPLEMENT_LATEST_VALUE_MISSING')
    expected=[last]
    while len(expected)<6:
        prior=expected[-1]-timedelta(days=1)
        while prior.weekday()>=5:prior-=timedelta(days=1)
        expected.append(prior)
    # Require all six actual observations; never skip a holiday/missing row
    # and relabel a longer comparison as exactly five business days.
    if any(points.get(day) is None for day in expected):
        raise ValueError('V75_SUPPLEMENT_FIVE_BUSINESS_DAY_COVERAGE_REQUIRED')
    current,previous=points[last],points[expected[-1]]
    with localcontext() as ctx:
        ctx.prec=40
        change=(current/previous-1)*100
    return {'schema_version':'Family.W8.V75MarketSupplement.v1','predicate_id':'PRED-005',
        'metrics':{'move':str(current),'move_pct_change_5bd':str(change)},
        'observed_date':last.isoformat(),'comparison_date':expected[-1].isoformat(),
        'comparison_close':str(previous),'observed_sessions':[d.isoformat() for d in reversed(expected)],
        'source_reference':receipt['url'],'source_sha256':source['sha256'],
        'receipt_sha256':source['receipt_sha256'],'available_at':receipt['available_at'],
        'provider':'YAHOO_FINANCE_DAILY_INDEX_CHART','exchange_close_attested':False,
        'scope':'DATED_PROVIDER_OBSERVATIONS__NOT_CANONICAL_FRESHNESS_ATTESTATION'}


def apply(observations,supplement,*,evaluation_at,repo_root):
    if supplement is None:return observations
    from bond_advisory import candidates
    supported=set(candidates(repo_root))
    from v75_runtime.predicates import EVALUATORS
    out=deepcopy(observations)
    out['bond_market_supplement']=deepcopy(supplement)
    for row in out['assets']:
        if row['symbol'] not in supported:continue
        predicates=row.get('v75_original_predicates',{})
        if 'PRED-005' not in predicates:continue
        previous=deepcopy(predicates['PRED-005'])
        result=EVALUATORS['PRED-005'](supplement['metrics'],_time(evaluation_at),
            [supplement['source_reference'],supplement['source_sha256']])
        predicates['PRED-005']={'metrics':deepcopy(supplement['metrics']),
            'original_result':result.model_dump(mode='json'),'input_coverage':'COMPLETE_RAW_METRICS',
            'input_freshness_verified':False,'deployment_input_eligible':False,
            'original_default_freshness_is_not_attestation':True,
            'original_result_as_of_basis':'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE',
            'supplement_source':deepcopy(supplement),'previous_macro_observation':previous}
        row['call_trace'].append('V75.PRED-005:DATED_PUBLIC_DAILY_SUPPLEMENT')
    return out


def validate(request,context,report,root):
    supplement=read(context.get('bond_market_supplement_source'),request['evaluation_at'])
    if report.get('bond_market_supplement')!=supplement:
        raise PermissionError('V75_SUPPLEMENT_REPLAY_MISMATCH')
    if supplement is None:return
    from on_demand_market_observations import _macro_metrics
    from bond_advisory import candidates
    candidates(root)  # Load and verify the frozen source before a cold replay.
    from v75_runtime.predicates import EVALUATORS
    metrics,_=_macro_metrics(request['macro_snapshot'],request['evaluation_at'])
    old_metrics=metrics.get('PRED-005',{})
    old_result=EVALUATORS['PRED-005'](old_metrics,_time(request['evaluation_at']),
        ['OBSERVED_CACHE_ONLY','ORIGINAL_NUMERIC_FORMULAS','FULL_SOURCE_COVERAGE_PENDING'])
    old={'metrics':old_metrics,'original_result':old_result.model_dump(mode='json'),
        'input_coverage':'PARTIAL' if old_metrics else 'MISSING',
        'original_result_as_of_basis':'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE',
        'input_freshness_verified':False,'original_default_freshness_is_not_attestation':True,
        'deployment_input_eligible':False}
    rows=[r.get('market') for r in report['analysis_result']['positions'] if r.get('market')]
    rows+=list(report.get('bond_target_market_observations',{}).values())
    for row in rows:
        slot=row.get('v75_original_predicates',{}).get('PRED-005')
        if slot is None:continue
        seed={'symbol':row['symbol'],'v75_original_predicates':{'PRED-005':old},'call_trace':[]}
        expected=apply({'assets':[seed]},supplement,evaluation_at=request['evaluation_at'],repo_root=root)
        if slot!=expected['assets'][0]['v75_original_predicates']['PRED-005']:
            raise PermissionError('V75_SUPPLEMENT_PREDICATE_REPLAY_MISMATCH')

"""Same-expiry, six-month SOFR implied rates for PRED-002's meeting roll.

This source is never an SOFR-OIS spread or a PRED-007 tenor definition.
Contract identity comes from the broker ladder; price quotation comes from
CME. No contract code, maturity or rate level is inferred from an ETF.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
from v75_remaining_inputs import time,number

CME_GUIDE='https://www.cmegroup.com/education/articles-and-reports/understanding-sofr-futures'


def _value(response):
    if response.get('isError') or not isinstance(response.get('structuredContent'),dict):
        raise ValueError('V75_SOFR_BROKER_RESPONSE_REQUIRED')
    return response['structuredContent']


def _called_at(value):return time(value.replace(' UTC','+00:00').replace(' ','T'))


def read(source,evaluation_at):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if source.get('schema_version')!='Family.W8.SOFROneMonthSource.v1' or sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('V75_SOFR_SOURCE_BYTES_OR_SCHEMA')
    packet=json.loads(raw,parse_float=Decimal);at=time(evaluation_at);available=time(source['available_at'])
    root,ladder,history=(packet[k] for k in ('root_search','ladder','history'))
    if not _called_at(root['requested_at'])<=_called_at(ladder['requested_at'])<=time(history['requested_at'])<=time(history['available_at'])<=available<=at:
        raise PermissionError('V75_SOFR_SOURCE_TIME_ORDER')
    roots=[r for r in _value(root['result'])['results'] if r.get('symbol')=='SOFR1'
        and r.get('exchange')=='CME' and r.get('country_code')=='US'
        and '1-month' in r.get('description','').lower()
        and any(s.get('security_type')=='FUT' for s in r.get('sections',[]))]
    if len(roots)!=1:raise PermissionError('V75_SOFR_ROOT_IDENTITY')
    if (root.get('tool_name')!='search_contracts' or root.get('arguments') not in ({'query':'SOFR'},{'query':'SOFR1'})
        or ladder.get('tool_name')!='search_futures'
        or ladder.get('arguments')!={'underlying_contract_id':roots[0]['underlying_contract_id']}):
        raise PermissionError('V75_SOFR_ROOT_TO_LADDER_BINDING')
    index=at.year*12+at.month-1+6;month=f'{index//12:04d}{index%12+1:02d}'
    contracts=[c for c in _value(ladder['result'])['contracts'] if c.get('contract_month')==month and c.get('exchange')=='CME']
    if len(contracts)!=1:raise PermissionError('V75_SOFR_SIX_MONTH_EXPIRY_REQUIRED')
    contract=contracts[0];cid=contract['contract_id']
    if type(cid) is not int or cid<=0 or contract['last_trading_date'][:6]!=month:
        raise PermissionError('V75_SOFR_CONTRACT_IDENTITY')
    args={'contract_id':cid,'exchange':'CME','outside_rth':False,'period':'THREE_MONTHS',
        'step':'ONE_DAY','security_type':'FUT','include_corporate_actions':False}
    if history.get('tool_name')!='get_price_history' or history.get('arguments')!=args:
        raise PermissionError('V75_SOFR_HISTORY_METHOD_BINDING')
    series=_value(history['response']);stamps=series['time']
    if (series.get('chart_step')!=86400 or series.get('source')!='Last' or not stamps or stamps!=sorted(set(stamps))
        or any(len(series[k])!=len(stamps) for k in ('open','high','low','close','volume'))
        or time(series['chart_end'])>time(history['available_at'])):
        raise ValueError('V75_SOFR_HISTORY_BASIS_OR_ORDER')
    zone=ZoneInfo('America/New_York');known_day=time(history['available_at']).astimezone(zone).date();points={};excluded=[]
    for i,stamp in enumerate(stamps):
        moment=time(stamp)
        if moment>time(history['available_at']) or not time(series['chart_start'])<=moment<=time(series['chart_end']):
            raise PermissionError('V75_SOFR_FUTURE_BAR')
        day=moment.astimezone(zone).date()
        if day>=known_day:excluded.append(stamp);continue
        o,h,l,c,v=(number(series[k][i]) for k in ('open','high','low','close','volume'))
        if h<max(o,l,c) or l>min(o,h,c) or min(o,h,l,c)<=0 or v<0 or v!=v.to_integral_value() or day in points:
            raise ValueError('V75_SOFR_INVALID_OHLCV_OR_DUPLICATE')
        points[day]=c
    from v75_macro_inputs import window
    days=window(points,5);current=points[days[0]];previous=points[days[5]]
    guide=source['cme_quote_source'];guide_raw=Path(guide['local_path']).read_bytes();receipt_raw=Path(guide['receipt_path']).read_bytes()
    if sha256(guide_raw).hexdigest()!=guide['sha256'] or sha256(receipt_raw).hexdigest()!=guide['receipt_sha256']:
        raise PermissionError('V75_SOFR_CME_SOURCE_CHANGED')
    receipt=json.loads(receipt_raw)
    if (receipt.get('url')!=CME_GUIDE or receipt.get('final_url',CME_GUIDE)!=CME_GUIDE
        or receipt.get('sha256')!=guide['sha256'] or receipt.get('http_status')!=200
        or not time(receipt['requested_at'])<=time(receipt['available_at'])<=at):
        raise PermissionError('V75_SOFR_CME_RECEIPT')
    from v75_official_release_inputs import Text
    parser=Text();parser.feed(guide_raw.decode('utf-8-sig'));text=' '.join(parser.parts)
    if not all(p in text for p in ('100 contract price points minus','arithmetic average of daily SOFR','One-Month SOFR')):
        raise PermissionError('V75_SOFR_CME_QUOTATION_REQUIRED')
    return {'schema_version':'Family.W8.SOFROneMonthInputs.v1',
        'metrics':{'expected_policy_rate_6m_delta_5bd_bps':str((previous-current)*100)},
        'calculation':{'contract_id':cid,'exchange':'CME','contract_month':month,
            'last_trading_date':contract['last_trading_date'],'observed_date':str(days[0]),'comparison_date':str(days[5]),
            'current_price':str(current),'comparison_price':str(previous),
            'formula':'((100-current_price)-(100-comparison_price))*100 bps',
            'scope':'SIX_MONTH_AHEAD_DELIVERY_MONTH_AVERAGE_SOFR__NOT_SOFR_OIS_SPREAD',
            'price_source':'IBKR_LAST_DAILY__NOT_OFFICIAL_CME_SETTLEMENT','excluded_current_day_bars':excluded,
            'historical_publication_times_asserted':False},
        'source_proofs':{
            'SOFR_BROKER':{'source_reference':'IBKR:get_price_history:'+str(cid),
                'source_sha256':source['sha256'],'available_at':source['available_at']},
            'SOFR_CME':{'source_reference':CME_GUIDE,'source_sha256':guide['sha256'],
                'receipt_sha256':guide['receipt_sha256'],'available_at':receipt['available_at']}}}


def extend(pool,source,evaluation_at):
    if source is None:return pool
    if not pool.get('formal_parameters'):raise PermissionError('V75_SOFR_FORMAL_PARAMETERS_REQUIRED')
    observed=read(source,evaluation_at);pool['sofr_horizon_observation']=observed
    for key,proof in observed['source_proofs'].items():
        pool['source_proofs'][key]=proof
        pool['available_at']=max(pool['available_at'],proof['available_at'],key=time)
    qualified=pool['qualified_shared_predicate_inputs']['PRED-002'];old=pool['calculations']['PRED-002'];new=observed['calculation']
    aligned=all(old[k]==new[k] for k in ('observed_date','comparison_date'))
    previous=pool['shared_metrics']['PRED-002']['expected_policy_rate_6m_delta_5bd_bps']
    difference=abs(number(previous)-number(observed['metrics']['expected_policy_rate_6m_delta_5bd_bps']))
    conflict=difference>25
    pool['auxiliary_policy_rate_observations']={'fed_funds':{'metrics':deepcopy(pool['shared_metrics']['PRED-002']),
        'calculation':deepcopy(old)},'source_difference_bps':str(difference),'source_conflict_unresolved':conflict,
        'scope':'BOTH_SOURCE_LINEAGES_PRESERVED__NO_MEETING_PROBABILITIES_ADDED'}
    legal=bool(qualified['meeting_roll_dates']) and aligned and not conflict
    qualified.update(input_freshness_verified=legal and all(c['state']=='FRESH' for c in qualified['checks']),
        fallback='SAME_SIX_MONTH_SOFR_CONTRACT' if legal else 'UNRESOLVED_SOURCE_ALIGNMENT_OR_CONFLICT',
        sources_date_aligned=aligned,source_conflict_unresolved=conflict)
    if legal:
        pool['shared_metrics']['PRED-002']=deepcopy(observed['metrics']);pool['calculations']['PRED-002']=deepcopy(new)
        pool['unprovided_inputs']['PRED-002']=[]
    return pool

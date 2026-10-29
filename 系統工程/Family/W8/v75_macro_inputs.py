"""Normalize captured official series for unchanged V75 predicates.

No policy-rate target is substituted for EFFR, no inflation expectation is
substituted for realized inflation, and no Treasury history is presented as
an ETF yield history. All formulas below produce inputs, not decisions.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta
from decimal import Decimal,localcontext
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse,parse_qs
import csv,io,json

from family_input import digest
from v75_market_supplement import _time


class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.tables=[];self.depth=0;self.table=[];self.row=[];self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.table=[]
        if self.depth==1:
            if tag=='tr':self.row=[]
            if tag in ('td','th'):self.cell=[]
    def handle_endtag(self,tag):
        if self.depth==1:
            if tag in ('td','th') and self.cell is not None:
                self.row.append(' '.join(self.cell));self.cell=None
            if tag=='tr' and self.row:self.table.append(self.row)
            if tag=='table':self.tables.append(self.table)
        if tag=='table':self.depth-=1
    def handle_data(self,value):
        if self.depth==1 and self.cell is not None and value.strip():
            self.cell.append(' '.join(value.split()))


def number(value):
    if isinstance(value,(bool,float)):raise ValueError('V75_MACRO_EXACT_NUMBER_REQUIRED')
    value=Decimal(value)
    if not value.is_finite():raise ValueError('V75_MACRO_NONFINITE')
    return value


def weekdays(end,count):
    # The parameter table says US business days. A missing ordinary
    # business-day quote remains an error; federal holidays are excluded
    # by the declared calendar, never by skipping missing observations.
    import pandas as pd
    from pandas.tseries.holiday import USFederalHolidayCalendar
    offset=pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
    days=[end]
    while len(days)<=count:
        days.append((pd.Timestamp(days[-1])-offset).date())
    return days


def window(points,count):
    last=max(points);days=weekdays(last,count)
    if any(points.get(day) is None for day in days):
        raise ValueError('V75_MACRO_COMPARISON_SESSION_GAP')
    return days


def fred(raw,key,at):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or set(rows[0])!={'observation_date',key}:
        raise ValueError('V75_MACRO_FRED_IDENTITY:'+key)
    points={};order=[]
    for row in rows:
        day=date.fromisoformat(row['observation_date'])
        if day>at.date() or day in points:raise ValueError('V75_MACRO_FRED_DATE:'+key)
        value=None if row[key] in ('','.') else number(row[key])
        points[day]=value;order.append(day)
    if order!=sorted(order):raise ValueError('V75_MACRO_FRED_ORDER:'+key)
    return points


def monthly(points,months):
    current=max(day for day,value in points.items() if value is not None)
    index=current.year*12+current.month-1-months
    prior=date(index//12,index%12+1,1)
    if current.day!=1 or points.get(prior) is None:
        raise ValueError('V75_MACRO_MONTHLY_COMPARISON_GAP')
    if points[current]<=0 or points[prior]<=0:raise ValueError('V75_MACRO_INDEX_NOT_POSITIVE')
    with localcontext() as ctx:
        ctx.prec=40
        value=((points[current]/points[prior])**(Decimal(12)/months)-1)*100
    return str(value),{'observed_date':current.isoformat(),'comparison_date':prior.isoformat(),
        'current_index':str(points[current]),'comparison_index':str(points[prior]),
        'formula':'((current_index / comparison_index) ** (12 / months) - 1) * 100'}


def sep(raw):
    parser=Tables();parser.feed(raw.decode('utf-8-sig'));matches=[]
    for table in parser.tables:
        for i,row in enumerate(table):
            if row and row[0]=='Federal funds rate' and len(row)==16:
                headers=table[1][:5]
                if headers[-1]!='Longer run':continue
                if headers[:4]!=[str(int(headers[0])+n) for n in range(4)]:continue
                matches.append((number(row[5]),row,headers))
    if len(matches)!=1:raise ValueError('V75_MACRO_SEP_MEDIAN_COLUMN_REQUIRED')
    value,row,headers=matches[0]
    return str(value),{'table':'Summary of Economic Projections, Table 1',
        'row':row,'median_columns':headers,'selected_column':'Median / Longer run'}


def futures(raw,at,known_by=None):
    chart=json.loads(raw,parse_float=Decimal)['chart']
    if chart.get('error') or len(chart.get('result') or [])!=1:raise ValueError('V75_MACRO_FUTURES_RESULT')
    result=chart['result'][0];meta=result['meta'];symbol=meta.get('symbol','')
    codes='FGHJKMNQUVXZ'
    if (len(symbol)!=9 or not symbol.startswith('ZQ') or not symbol.endswith('.CBT')
        or symbol[2] not in codes or meta.get('instrumentType')!='FUTURE'
        or meta.get('currency')!='USD' or meta.get('dataGranularity')!='1d'):
        raise ValueError('V75_MACRO_FUTURES_IDENTITY')
    month=codes.index(symbol[2])+1;year=2000+int(symbol[3:5])
    if (year-at.year)*12+month-at.month!=6:raise ValueError('V75_MACRO_FUTURES_HORIZON')
    zone=ZoneInfo(meta['exchangeTimezoneName']);points={};excluded=[]
    stamps=result['timestamp'];closes=result['indicators']['quote'][0]['close']
    if len(stamps)!=len(closes) or stamps!=sorted(set(stamps)):
        raise ValueError('V75_MACRO_FUTURES_ORDER')
    for stamp,close in zip(stamps,closes):
        moment=datetime.fromtimestamp(stamp,zone)
        if moment>(known_by or at):raise ValueError('V75_MACRO_FUTURES_FUTURE_QUOTE')
        if (moment.hour,moment.minute,moment.second)!=(0,0,0):
            excluded.append(moment.isoformat());continue # forming quote bar is not a daily close
        if moment.date() in points:raise ValueError('V75_MACRO_FUTURES_DUPLICATE')
        points[moment.date()]=number(close) if close is not None else None
    days=window(points,5);current=points[days[0]];prior=points[days[-1]]
    if not excluded and days[0]>=at.astimezone(zone).date():
        raise ValueError('V75_MACRO_FUTURES_FORMING_SESSION')
    return str((prior-current)*100),{'symbol':symbol,'contract_month':f'{year}-{month:02d}',
        'observed_date':days[0].isoformat(),'comparison_date':days[-1].isoformat(),
        'current_price':str(current),'comparison_price':str(prior),'excluded_forming_quote_bars':excluded,
        'formula':'(comparison_futures_price - current_futures_price) * 100 bps',
        'scope':'SAME_SIX_MONTH_CONTRACT_MONTHLY_AVERAGE_RATE__NOT_FOMC_PROBABILITY'}


def read(source,evaluation_at):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('V75_MACRO_MANIFEST_CHANGED')
    manifest=json.loads(raw)
    if manifest.get('schema_version')!='Family.W8.V75MacroSourceManifest.v1':
        raise ValueError('V75_MACRO_MANIFEST_SCHEMA')
    from formal_v75_parameters import read as read_parameters
    parameters=read_parameters(manifest.get('formal_parameter_source'),evaluation_at)
    at=_time(evaluation_at);data={};proofs={}
    for key,item in manifest['sources'].items():
        content=Path(item['local_path']).read_bytes();receipt_raw=Path(item['receipt_path']).read_bytes()
        if sha256(content).hexdigest()!=item['sha256'] or sha256(receipt_raw).hexdigest()!=item['receipt_sha256']:
            raise PermissionError('V75_MACRO_SOURCE_CHANGED:'+key)
        receipt=json.loads(receipt_raw);url=receipt['url']
        if (receipt.get('http_status')!=200 or receipt.get('sha256')!=item['sha256']
            or _time(receipt['available_at'])>at or _time(receipt['requested_at'])>_time(receipt['available_at'])):
            raise PermissionError('V75_MACRO_RECEIPT_MISMATCH:'+key)
        expected=('https://www.federalreserve.gov/monetarypolicy/fomcprojtabl' if key=='SEP' else
            'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/' if key=='TREASURY' else
            'https://query1.finance.yahoo.com/v8/finance/chart/ZQ' if key=='FUTURES' else
            'https://markets.newyorkfed.org/api/rp/repo/all/results/' if key=='NYFED_REPO' else
            'https://query1.finance.yahoo.com/v8/finance/chart/'+key[6:]+'?' if key in ('YAHOO_SGOV','YAHOO_SPSB') else
            'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+key)
        if not url.startswith(expected):raise PermissionError('V75_MACRO_PROVIDER_IDENTITY:'+key)
        if key in ('YAHOO_SGOV','YAHOO_SPSB'):
            query=parse_qs(urlparse(url).query)
            if (query.get('interval')!=['1d'] or query.get('range') not in (['5y'],['10y'],['max'])
                or not {'div','splits'}<=set(','.join(query.get('events',[])).split(','))):
                raise PermissionError('V75_MACRO_YIELD_EVENT_QUERY_REQUIRED:'+key)
        data[key]=content;proofs[key]={'source_reference':url,'source_sha256':item['sha256'],
            'receipt_sha256':item['receipt_sha256'],'available_at':receipt['available_at']}
    out={'schema_version':'Family.W8.V75MacroInputs.v1','manifest_sha256':source['sha256'],
        'available_at':max((v['available_at'] for v in proofs.values()),key=_time),
        'source_proofs':proofs,'shared_metrics':{},'asset_metrics':{},'calculations':{},
        'unprovided_inputs':{},'canonical_freshness_attested':False}
    if parameters is not None:
        out['formal_parameters']=parameters
        out['available_at']=max(out['available_at'],parameters['available_at'],key=_time)
    from v75_issuer_facts import read as read_issuers
    issuers=read_issuers(manifest.get('etf_issuer_sources'),evaluation_at)
    if issuers and parameters is None:raise PermissionError('V75_ISSUER_FORMAL_PARAMETER_BINDING_REQUIRED')
    for symbol,issuer in issuers.items():
        out['source_proofs']['ISSUER_'+symbol]={k:issuer[k] for k in
            ('source_reference','source_sha256','receipt_sha256','available_at')}
        out['available_at']=max(out['available_at'],issuer['available_at'],key=_time)
    from v75_official_release_inputs import read as read_releases
    releases=read_releases(manifest.get('official_release_sources'),evaluation_at)
    if releases and parameters is None:raise PermissionError('V75_RELEASE_FORMAL_PARAMETER_BINDING_REQUIRED')
    if releases:
        out['official_release_observations']=releases
        for key,record in releases.items():
            out['source_proofs']['RELEASE_'+key]={k:record[k] for k in
                ('source_reference','source_sha256','receipt_sha256','available_at')}
            out['available_at']=max(out['available_at'],record['available_at'],key=_time)
    series={key:fred(value,key,_time(proofs[key]['available_at'])) for key,value in data.items()
        if key not in ('SEP','TREASURY','FUTURES','NYFED_REPO','YAHOO_SGOV','YAHOO_SPSB')}
    effr=series['EFFR'];last=max(day for day,value in effr.items() if value is not None)
    start=last.replace(year=last.year-10)
    sample=[value for day,value in effr.items() if start<=day<=last and value is not None]
    if min(effr)>start or len(sample)<2000:raise ValueError('V75_MACRO_EFFR_TEN_YEAR_COVERAGE')
    import pandas as pd
    from pandas.tseries.holiday import USFederalHolidayCalendar
    expected={d.date() for d in pd.date_range(start,last,freq=pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar()))}
    covered=sum(effr.get(d) is not None for d in expected)
    if covered*100<len(expected)*80:raise ValueError('V75_MACRO_EFFR_EIGHTY_PERCENT_COVERAGE')
    median,basis=sep(data['SEP']);pce_yoy,yoy_basis=monthly(series['PCEPILFE'],12)
    out['shared_metrics']['PRED-001']={'effr_pct':str(effr[last]),
        'effr_10y_percentile_pct':str(Decimal(sum(value<=effr[last] for value in sample))*100/len(sample)),
        'sep_long_run_median_pct':median,'core_pce_yoy_pct':pce_yoy}
    out['calculations']['PRED-001']={'effr_observed_date':last.isoformat(),
        'percentile_window_start':start.isoformat(),'sample_count':len(sample),
        'required_us_business_observations':len(expected),'valid_required_observations':covered,
        'coverage_minimum_percent':80,'comparison_calendar':'US_FEDERAL_BUSINESS_DAYS',
        'percentile_method':'EMPIRICAL_CDF_WEAK_RANK__COUNT_LE_CURRENT_DIV_VALID_OBSERVATIONS',
        'SEP':basis,'core_pce_yoy':yoy_basis}
    delta,basis=futures(data['FUTURES'],at,_time(proofs['FUTURES']['available_at']))
    out['shared_metrics']['PRED-002']={'expected_policy_rate_6m_delta_5bd_bps':delta}
    out['calculations']['PRED-002']=basis
    credit={};credit_basis={}
    for label,key in [('hy','BAMLH0A0HYM2'),('ig','BAMLC0A0CM'),('a','BAMLC0A3CA'),('bbb','BAMLC0A4CBBB')]:
        points=series[key];days=window(points,20);current=points[days[0]]
        if label=='hy':credit['hy_oas_bps']=str(current*100)
        for n in (5,20):credit[f'{label}_oas_delta_{n}bd_bps']=str((current-points[days[n]])*100)
        credit_basis[label]={'series':key,'observed_date':days[0].isoformat(),
            'comparison_5bd':days[5].isoformat(),'comparison_20bd':days[20].isoformat(),'unit_conversion':'PERCENT_TO_BPS_X100'}
    out['shared_metrics']['PRED-004']=credit;out['calculations']['PRED-004']=credit_basis
    inflation={};inflation_basis={}
    for label,key in [('core_pce','PCEPILFE'),('core_cpi','CPILFESL'),('core_ppi','WPSFD49116')]:
        if key not in series:continue
        for n in (3,6):
            value,basis=monthly(series[key],n);inflation[f'{label}_ann{n}_pct']=value
            inflation_basis[f'{label}_ann{n}_pct']=basis
    if 'T5YIE' in series:
        values=series['T5YIE'];days=window(values,20)
        inflation['breakeven_5y_pct']=str(values[days[0]])
        inflation['breakeven_5y_delta_20bd_bps']=str((values[days[0]]-values[days[20]])*100)
        inflation_basis['breakeven']={'series':'T5YIE','observed_date':str(days[0]),'comparison_date':str(days[20]),
            'formula':'(current_percent - prior_percent) *100 bps','comparison_calendar':'US_FEDERAL_BUSINESS_DAYS'}
    if 'DCOILWTICO' in series:
        values=series['DCOILWTICO'];days=window(values,20)
        if min(values[d] for d in days)<=0:raise ValueError('V75_MACRO_POSITIVE_OIL_PRICE_REQUIRED')
        inflation['oil_price_change_20bd_pct']=str((values[days[0]]/values[days[20]]-1)*100)
        inflation_basis['oil']={'series':'DCOILWTICO','observed_date':str(days[0]),'comparison_date':str(days[20]),
            'formula':'(current_price / prior_price -1) *100 percent','comparison_calendar':'US_FEDERAL_BUSINESS_DAYS'}
    out['shared_metrics']['PRED-006']=inflation;out['calculations']['PRED-006']=inflation_basis
    out['unprovided_inputs']['PRED-006']=[k for k in ('core_ppi_ann3_pct','core_ppi_ann6_pct',
        'breakeven_5y_delta_20bd_bps','breakeven_5y_pct','oil_price_change_20bd_pct') if k not in inflation]
    rows=list(csv.DictReader(io.StringIO(data['TREASURY'].decode('utf-8-sig'))))
    # PRED-003's duration <=1y branch uses 1Y, including SGOV. 3M may
    # describe its holdings but is never the canonical branch reference.
    for asset,tenor in [('SGOV','1 Yr'),('SPSB','2 Yr')]:
        profile=issuers.get(asset,{}).get('facts',{}).get('effective_duration')
        if profile and profile.get('value') is not None:
            from formal_v75_parameters import treasury_reference
            if profile['unit']!='YEARS':raise ValueError('V75_MACRO_DURATION_UNIT')
            tenor=treasury_reference(profile['value'])
        if not rows or tenor not in rows[0]:
            out.setdefault('asset_unprovided_inputs',{}).setdefault(asset,{})['PRED-003']=[
                'official Treasury '+tenor+' reference history']
            out['asset_metrics'].setdefault(asset,{})['PRED-003']={}
            continue
        points={}
        for row in rows:
            day=datetime.strptime(row['Date'],'%m/%d/%Y').date()
            if day>at.date() or day in points:raise ValueError('V75_MACRO_TREASURY_DATE')
            points[day]=number(row[tenor]) if row[tenor] else None
        days=window(points,10);current=points[days[0]]
        metrics={'yield_delta_5bd_bps':str((current-points[days[5]])*100),
            'yield_delta_10bd_bps':str((current-points[days[10]])*100),
            'yield_up_days_last5':sum(points[days[n]]>points[days[n+1]] for n in range(5))}
        out['asset_metrics'][asset]={'PRED-003':metrics}
        out['calculations'][asset+'.PRED-003']={'tenor':tenor,'observed_date':days[0].isoformat(),
            'comparison_5bd':days[5].isoformat(),'comparison_10bd':days[10].isoformat(),
            'scope':'TREASURY_RATE_PATH_REFERENCE__NOT_ETF_YIELD_ATTRACTIVENESS_HISTORY',
            'basis':'V75_PREDICATE_PARAMS_v1.0.3 / PRED-003 duration reference maturity',
            'effective_duration_source':deepcopy(profile),'auxiliary_3m_is_branch_reference':False}
        if parameters and profile and profile.get('value') is not None:
            from v75_etf_quality_inputs import daily_freshness
            checks=[daily_freshness(d,evaluation_at) for d in (days[0].isoformat(),profile['observed_date'])]
            out.setdefault('qualified_predicate_inputs',{}).setdefault(asset,{})['PRED-003']={
                'input_freshness_verified':all(r['state']=='FRESH' for r in checks),
                'checks':checks,'basis':'FORMAL_DURATION_REFERENCE_AND_ORIGINAL_DAILY_FRESHNESS'}
    if parameters:
        from v75_etf_quality_inputs import daily_freshness
        checks=[daily_freshness(v['observed_date'],evaluation_at) for v in credit_basis.values()]
        out.setdefault('qualified_shared_predicate_inputs',{})['PRED-004']={
            'input_freshness_verified':all(r['state']=='FRESH' for r in checks),
            'checks':checks,'basis':'ALL_HY_IG_A_BBB_LEVELS_AND_5_20_BUSINESS_DAY_DELTAS'}
    from v75_remaining_inputs import extend
    out=extend(out,data,proofs)
    from v75_market_contract import qualify
    out=qualify(out,data,proofs,manifest,evaluation_at)
    from v75_etf_quality_inputs import extend as extend_quality
    out=extend_quality(out,data,issuers,evaluation_at)
    from v75_official_release_inputs import qualify as qualify_releases
    out=qualify_releases(out,evaluation_at)
    from v75_sofr_horizon_inputs import extend as extend_sofr
    out=extend_sofr(out,manifest.get('sofr_horizon_source'),evaluation_at)
    from v75_handoff_inputs import extend as extend_handoff
    out=extend_handoff(out,manifest.get('source_handoff'),data,evaluation_at)
    from v75_ready_data_inputs import extend as extend_ready_data
    out=extend_ready_data(out,manifest.get('ready_data_source'),data,evaluation_at)
    from v75_pred007_inputs import extend as extend_pred007
    return extend_pred007(out,manifest.get('pred007_amendment_source'),evaluation_at)


def slot(pool,pid,asset,previous,evaluation_at):
    if pid=='PRED-007':
        from v75_pred007_inputs import slot as amended_slot
        amended=amended_slot(pool,asset,evaluation_at,previous)
        if amended is not None:return amended
    metrics=pool['asset_metrics'].get(asset,{}).get(pid,pool['shared_metrics'].get(pid))
    if metrics is None:return None
    from v75_runtime.predicates import EVALUATORS
    result=EVALUATORS[pid](metrics,_time(evaluation_at),
        [proof['source_reference'] for proof in pool['source_proofs'].values()])
    contract=pool.get('qualified_bond_markets',{}).get(asset,{})
    fresh=(contract.get('eligible') is True and
        pid=='PRED-007' and pool['calculations']['PRED-007']['observed_date']==contract['observed_date'])
    qualified=pool.get('qualified_predicate_inputs',{}).get(asset,{}).get(pid,
        pool.get('qualified_shared_predicate_inputs',{}).get(pid,{}))
    if qualified:fresh=qualified.get('input_freshness_verified') is True
    if pid=='PRED-010' and asset in pool.get('etf_quality_assessments',{}):
        fresh=pool['etf_quality_assessments'][asset]['input_freshness_verified']
    missing=deepcopy(pool.get('asset_unprovided_inputs',{}).get(asset,{}).get(pid,
        pool['unprovided_inputs'].get(pid,[])))
    entry={'metrics':deepcopy(metrics),'original_result':result.model_dump(mode='json'),
        'input_coverage':'PARTIAL_RAW_METRICS' if missing else 'COMPLETE_RAW_METRICS',
        'unprovided_inputs':missing,
        'source_pool_digest':digest(pool),'source_available_at':pool['available_at'],
        'input_freshness_verified':fresh,'deployment_input_eligible':fresh and result.assessment_status.value=='VALID',
        'original_default_freshness_is_not_attestation':True,
        'original_result_as_of_basis':'EVALUATION_TIME__OBSERVATION_DATES_SEPARATE',
        'previous_observation':deepcopy(previous)}
    if pid=='PRED-008' and asset+'.PRED-008' in pool['calculations']:
        entry['yield_reference']=deepcopy(pool['calculations'][asset+'.PRED-008'])
    return entry


def apply(observations,pool,*,evaluation_at,repo_root,macro=None):
    if pool is None:return observations
    from bond_advisory import candidates
    from v75_market_contract import apply as apply_qualified_market
    observations=apply_qualified_market(observations,pool,repo_root=repo_root,evaluation_at=evaluation_at,macro=macro)
    supported=set(candidates(repo_root));out=deepcopy(observations);out['v75_macro_inputs']=deepcopy(pool)
    for row in out['assets']:
        if row['symbol'] not in supported:continue
        predicates=row.setdefault('v75_original_predicates',{})
        for pid in set(pool['shared_metrics'])|set(pool['asset_metrics'].get(row['symbol'],{})):
            predicates[pid]=slot(pool,pid,row['symbol'],predicates.get(pid),evaluation_at)
        row['call_trace'].append('V75.PRED-001/002/003/004/006/007/008/010:SOURCE_NORMALIZATION')
    return out


def validate(request,context,report,root):
    pool=read(context.get('v75_macro_source_manifest'),request['evaluation_at'])
    if report.get('v75_macro_inputs')!=pool:raise PermissionError('V75_MACRO_SOURCE_REPLAY_MISMATCH')
    if pool is None:return
    from bond_advisory import candidates
    supported=set(candidates(root))
    rows=[r['market'] for r in report['analysis_result']['positions'] if r.get('market')]
    rows+=list(report.get('bond_target_market_observations',{}).values())
    for row in rows:
        if row['symbol'] not in supported:continue
        for pid in set(pool['shared_metrics'])|set(pool['asset_metrics'].get(row['symbol'],{})):
            recorded=row.get('v75_original_predicates',{}).get(pid)
            if recorded is None or recorded!=slot(pool,pid,row['symbol'],recorded.get('previous_observation'),request['evaluation_at']):
                raise PermissionError('V75_MACRO_PREDICATE_REPLAY_MISMATCH')

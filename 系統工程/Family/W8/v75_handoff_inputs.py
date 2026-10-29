"""Read DOT's delivered raw sources with byte and row reconciliation.

The Treasury series is a labelled government-bond fallback. Distribution
amounts preserve issuer precision, provisional character and missing ROC.
This module does not supply undefined tenors, licensed data or investment rules.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path,PurePosixPath
from zipfile import ZipFile
import csv,io,json,re,xml.etree.ElementTree as ET
from v75_remaining_inputs import number,time,_year_ago

PARAMETERS_SHA='9aea7bca82fa0f9b3835136a87afcdb08682b226ed4162213e083186beb5f54e'
DATA_CONTRACT_SHA='a9665f758b97637abafd6428c5bbff2918ff1209ae04afcdc5b8238f9928c3bd'
SS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_PARSED={}


def xml(raw,repair_ampersands=False):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('HANDOFF_XML_DTD_FORBIDDEN')
    text=raw.decode('utf-8-sig')
    if repair_ampersands:text=re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)','&amp;',text)
    return ET.fromstring(text)


def xlsx_rows(raw):
    with ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:raise ValueError('HANDOFF_XLSX_CRC')
        strings=[''.join(e.itertext()) for e in xml(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
        book=xml(z.read('xl/workbook.xml'));first=book.find('{*}sheets/{*}sheet')
        rid=first.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels=xml(z.read('xl/_rels/workbook.xml.rels'))
        target=next(e.attrib['Target'] for e in rels if e.attrib['Id']==rid)
        target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        if '..' in PurePosixPath(target).parts:raise ValueError('HANDOFF_XLSX_RELATION_PATH')
        out={}
        for row in xml(z.read(target)).findall('{*}sheetData/{*}row'):
            cells={}
            for cell in row:
                value=cell.find('{*}v');value=value.text if value is not None else None
                if cell.attrib.get('t')=='s':value=strings[int(value)] if value is not None else None
                elif cell.attrib.get('t')=='inlineStr':value=''.join(e.text or '' for e in cell.findall('.//{*}t'))
                cells[re.sub(r'\d','',cell.attrib['r'])]=value
            out[int(row.attrib['r'])]=cells
        return out


def csv_rows(raw):return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
def iso(value,fmt):return datetime.strptime(value,fmt).date().isoformat()
def excel_day(value):return (date(1899,12,30)+timedelta(days=int(value))).isoformat()
def amount(value):return None if value in (None,'') else str(number(value))


def distributions(files,observed_date):
    end=date.fromisoformat(observed_date);start=_year_ago(end)
    root=xml(files['etf_quality/sgov_data.xls'],True)
    sheet=next(s for s in root.findall('{*}Worksheet') if s.attrib.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')=='Distributions')
    rows=[[c.find('{*}Data').text if c.find('{*}Data') is not None else '' for c in r] for r in sheet.findall('{*}Table/{*}Row')]
    header=rows[0];original={r[1]:dict(zip(header,r)) for r in rows[1:] if len(r)==len(header)}
    out={'SGOV':[],'SPSB':[]}
    for row in csv_rows(files['etf_quality/sgov_12_distributions.csv']):
        source=original.get(row['Ex-Date'])
        if source is None or any(amount(row[k])!=amount(source[k]) for k in header[3:]):raise PermissionError('HANDOFF_SGOV_DISTRIBUTION_ROW_MISMATCH')
        ex=iso(row['Ex-Date'],'%b %d, %Y')
        out['SGOV'].append({'ex_date':ex,'total':amount(source['Total Distribution']),
            'income':amount(source['Income']),'roc':amount(source['Return of Capital']),
            'characterization':'PROVISIONAL_ISSUER_DISPLAY' if ex[:4]=='2026' else 'ISSUER_PRIOR_YEAR_DISPLAY',
            'final_tax_characterization':False,'source_row':rows.index([source[k] for k in header])+1})
    expected={iso(d,'%b %d, %Y') for d in original if start<date.fromisoformat(iso(d,'%b %d, %Y'))<=end}
    if {r['ex_date'] for r in out['SGOV']}!=expected:raise PermissionError('HANDOFF_SGOV_DISTRIBUTION_COVERAGE')
    original=xlsx_rows(files['etf_quality/spsb_distributions.xlsx'])
    for row in csv_rows(files['etf_quality/spsb_12_distributions.csv']):
        source=original[int(row['source_row'])]
        if (source.get('B')!='SPSB' or source.get('C')!='78464A474' or source['D']!=row['EX-DATE']
            or amount(source['G'])!=amount(row['DIVIDEND ($)'])
            or amount(source.get('H'))!=amount(row['SHORT TERM CAPITAL GAIN ($)'])
            or amount(source.get('I'))!=amount(row['LONG TERM CAPITAL GAIN ($)'])):
            raise PermissionError('HANDOFF_SPSB_DISTRIBUTION_ROW_MISMATCH')
        out['SPSB'].append({'ex_date':iso(source['D'],'%m/%d/%Y'),'dividend':amount(source['G']),
            'st_cap_gain':amount(source.get('H')),'lt_cap_gain':amount(source.get('I')),
            'total':None,'roc':None,'characterization':'ROC_NOT_PRESENT_IN_DISTRIBUTION_FILE',
            'final_tax_characterization':False,'source_row':int(row['source_row'])})
    expected={iso(r['D'],'%m/%d/%Y') for r in original.values() if r.get('B')=='SPSB' and r.get('C')=='78464A474'
        and start<date.fromisoformat(iso(r['D'],'%m/%d/%Y'))<=end}
    if {r['ex_date'] for r in out['SPSB']}!=expected:raise PermissionError('HANDOFF_SPSB_DISTRIBUTION_COVERAGE')
    tax=xlsx_rows(files['etf_quality/spsb_tax.xlsx']);tax_rows={}
    for row in csv_rows(files['etf_quality/spsb_2025_tax_rows.csv']):
        source=tax[int(row['source_row'])];ex=excel_day(source['H'])
        if (source.get('B')!='78464A474' or source.get('C')!='SPSB' or ex!=row['Ex-Dividend Date']
            or amount(source.get('J'))!=amount(row['Total Distribution Per Share (11+12+13)'])
            or amount(source.get('Z'))!=amount(row['Nondividend Distributions'])):
            raise PermissionError('HANDOFF_SPSB_TAX_ROW_MISMATCH')
        tax_rows[ex]={'total':amount(source.get('J')),'roc':amount(source.get('Z')),'tax_source_row':int(row['source_row'])}
    for row in out['SPSB']:
        if row['ex_date'] in tax_rows:
            row.update(tax_rows[row['ex_date']],characterization='OFFICIAL_2025_TAX_BREAKDOWN',final_tax_characterization=True)
    return out


def treasury(files):
    data=json.loads(files['rates/treasury_short_tenor_daily_20211029_20261028.json'],parse_float=Decimal)
    metadata=data['metadata'];manifest=json.loads(files['rates/source_manifest.json']);original={}
    with ZipFile(io.BytesIO(files['rates/treasury_source_bundle_20261029.zip'])) as z:
        if z.testzip() is not None:raise PermissionError('HANDOFF_TREASURY_ZIP_CRC')
        for source in manifest['sources']:
            if not source['key'].isdigit():continue
            expected='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value='+source['key']
            if source.get('url')!=expected or source.get('status')!=200:raise PermissionError('HANDOFF_TREASURY_PROVIDER_IDENTITY')
            raw=z.read('raw/'+source['key']+'.xml')
            if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('HANDOFF_TREASURY_XML_HASH')
            for row in xml(raw).findall('.//{*}properties'):
                day=row.find('{*}NEW_DATE').text[:10]
                if day[:4]!=source['key']:raise PermissionError('HANDOFF_TREASURY_YEAR_IDENTITY')
                if metadata['first']<=day<=metadata['last']:
                    if day in original:raise ValueError('HANDOFF_TREASURY_DUPLICATE_DATE')
                    original[day]={key:str(number(row.find('{*}'+key).text)) for key in ('BC_1MONTH','BC_2MONTH','BC_3MONTH')}
    observations=data['observations'];dates=[r['date'] for r in observations]
    if dates!=sorted(set(dates)) or len(dates)!=metadata['row_count'] or set(dates)!=set(original):raise PermissionError('HANDOFF_TREASURY_COVERAGE')
    for row in observations:
        if any(number(row[k])!=number(original[row['date']][k]) for k in original[row['date']]):raise PermissionError('HANDOFF_TREASURY_EXTRACT_XML_MISMATCH')
    return {'metadata':metadata,'observations':[{'date':d,**original[d]} for d in dates],
        'xml_observations_reconciled':len(dates),'source_manifest':manifest}


def read(source,evaluation_at):
    if source is None:return None
    if source.get('schema_version')!='Family.W8.V75SourceHandoff.v1' or time(source['ingested_at'])>time(evaluation_at):
        raise PermissionError('HANDOFF_SOURCE_SCHEMA_OR_AVAILABILITY')
    root=Path(source['root']).resolve();raw=(root/'PACKAGE_MANIFEST.json').read_bytes()
    if sha256(raw).hexdigest()!=source['manifest_sha256']:raise PermissionError('HANDOFF_MANIFEST_HASH')
    files={}
    for item in json.loads(raw):
        path=PurePosixPath(item['path']);local=(root/str(path)).resolve()
        if path.is_absolute() or '..' in path.parts or not local.is_relative_to(root) or str(path) in files:raise PermissionError('HANDOFF_MANIFEST_PATH')
        content=local.read_bytes()
        if len(content)!=item['bytes'] or sha256(content).hexdigest()!=item['sha256']:raise PermissionError('HANDOFF_SOURCE_HASH:'+str(path))
        files[str(path)]=content
    if (sha256(files['contracts/V75_PREDICATE_PARAMS_v1.0.3.md']).hexdigest()!=PARAMETERS_SHA
        or sha256(files['contracts/market_data_contract_v1.1.0_20260928.md']).hexdigest()!=DATA_CONTRACT_SHA):
        raise PermissionError('HANDOFF_FORMAL_CONTRACT_IDENTITY')
    key=source['manifest_sha256']
    if key not in _PARSED:
        rates=treasury(files)
        _PARSED[key]={'treasury':rates,'distributions':distributions(files,rates['metadata']['last'])}
    if time(_PARSED[key]['treasury']['metadata']['retrieved_at_utc'])>time(source['ingested_at']):
        raise PermissionError('HANDOFF_RETRIEVAL_AFTER_INGESTION')
    return {'schema_version':'Family.W8.VerifiedV75SourceHandoff.v1','manifest_sha256':source['manifest_sha256'],
        'source_available_at':source['ingested_at'],'source_reference':'OWNER_ATTACHED_DOT_V75_SOURCE_HANDOFF_20261029',
        **deepcopy(_PARSED[key]),
        'contracts':{'market_data_version':'1.1.0','market_data_sha256':DATA_CONTRACT_SHA,
            'predicate_sha256':PARAMETERS_SHA,'term_status':'SPECIFICATION_UNDEFINED',
            'source_metadata':json.loads(files['contracts/source_metadata.json'])},
        'distribution_retrieval_time_exact':None,
        'distribution_retrieval_window_utc':['2026-10-29T06:57:51Z','2026-10-29T06:58:41Z'],
        'raw_files_verified':len(files),'trade_action':'NO_TRADE'}


def weekly_benchmark(observations,duration_years):
    """Fixed nearest current-duration tenor; last published value each week."""
    tenor_months=number(duration_years)*12
    ranked=sorted((abs(tenor_months-month),month) for month in (1,2,3))
    if ranked[0][0]==ranked[1][0]:raise ValueError('HANDOFF_TENOR_MATCH_AMBIGUOUS')
    month=ranked[0][1];key=f'BC_{month}MONTH';end=date.fromisoformat(observations[-1]['date'])
    start=end.replace(year=end.year-5);sample={}
    for row in observations:
        day=date.fromisoformat(row['date'])
        if not start<=day<=end:continue
        friday=day+timedelta(days=(4-day.weekday())%7)
        sample[friday]=(day,number(row[key]))
    first_friday=start+timedelta(days=(4-start.weekday())%7);last_friday=end+timedelta(days=(4-end.weekday())%7)
    expected=[];cursor=first_friday
    while cursor<=last_friday:expected.append(cursor);cursor+=timedelta(days=7)
    if set(sample)!=set(expected):raise ValueError('HANDOFF_WEEKLY_YIELD_COVERAGE')
    values=[sample[d][1] for d in expected];current=values[-1]
    metrics={'yield_percentile_pct':str(Decimal(sum(v<=current for v in values))*100/len(values)),
        'history_years':'5','formal_proxy':False}
    return metrics,{'identity':'PROXY','yield_basis':'DURATION_MATCHED_TREASURY_PAR_YIELD_FALLBACK',
        'selected_tenor_months':month,'selected_field':key,'selection':'FIXED_NEAREST_CURRENT_EFFECTIVE_DURATION',
        'current_effective_duration_years':str(number(duration_years)),
        'historical_fund_duration_inferred':False,'weekly_sampling':'LAST_PUBLISHED_OBSERVATION_IN_EACH_FRIDAY_ENDING_WEEK',
        'window_start':str(start),'window_end':str(end),'observed_date':str(sample[expected[-1]][0]),
        'first_week_observed_date':str(sample[expected[0]][0]),'weekly_observations':len(values),
        'latest_week_complete':expected[-1]<=end,'latest_yield_pct':str(current),
        'latest_week_nominal_end':str(expected[-1]),'percentile_method':'EMPIRICAL_CDF_WEAK_RANK',
        'methodology_break_date':'2021-12-06','is_fund_ytm':False,'is_sec_yield':False,
        'interpolated_or_forward_filled':False,'historical_publication_times_asserted':False}


def distribution_window(rows,observed_date):
    end=date.fromisoformat(observed_date);start=_year_ago(end)
    selected=[deepcopy(r) for r in rows if start<date.fromisoformat(r['ex_date'])<=end]
    dates=[r['ex_date'] for r in selected]
    if len(selected)!=12 or len(set(dates))!=12:raise ValueError('HANDOFF_DISTRIBUTION_WINDOW_COVERAGE')
    provisional=any(r['characterization']=='PROVISIONAL_ISSUER_DISPLAY' for r in selected)
    complete=all(r['total'] is not None and r['roc'] is not None and r['final_tax_characterization'] for r in selected)
    total=sum((number(r['total']) for r in selected if r['total'] is not None),Decimal(0))
    reported=sum((number(r['roc']) for r in selected if r['roc'] is not None),Decimal(0))
    visible_complete=all(r['total'] is not None and r['roc'] is not None for r in selected)
    return {'period_start_exclusive':str(start),'period_end_inclusive':str(end),'periods':len(selected),'rows':selected,
        'as_reported_total_distribution':str(total) if visible_complete else None,
        'as_reported_dividend_sum':str(sum((number(r['dividend']) for r in selected),Decimal(0))) if 'dividend' in selected[0] else None,
        'as_reported_roc_pct':format(reported/total*100,'f') if visible_complete and total>0 else None,
        'provisional_issuer_components':provisional,'complete_final_breakdown':complete,
        'complete_source_breakdown':visible_complete,
        'distribution_rule_basis':'V75_PREDICATE_PARAMS_v1.0.3 / PRED-010.C: issuer distribution source; final annual tax status is separate',
        'missing_roc_dates':[r['ex_date'] for r in selected if r['roc'] is None],
        'native_distribution_quality_state':'UNKNOWN' if not visible_complete else None,
        'missing_components_not_filled_zero':True}


def extend(pool,source,data,evaluation_at):
    if source is None:return pool
    if not pool.get('formal_parameters'):raise PermissionError('HANDOFF_FORMAL_PARAMETERS_REQUIRED')
    delivered=read(source,evaluation_at);rates=delivered['treasury']
    from v75_etf_quality_inputs import assess,daily_freshness
    pool['source_handoff']={k:deepcopy(delivered[k]) for k in
        ('schema_version','manifest_sha256','source_reference','source_available_at','contracts','raw_files_verified',
         'distribution_retrieval_time_exact','distribution_retrieval_window_utc')}
    pool['source_proofs']['DOT_HANDOFF']={'source_reference':delivered['source_reference'],
        'source_sha256':source['manifest_sha256'],'available_at':delivered['source_available_at']}
    pool['available_at']=max(pool['available_at'],delivered['source_available_at'],key=time)
    for symbol,issuer in pool.get('issuer_observations',{}).items():
        if symbol not in delivered['distributions']:continue
        contract=pool.get('qualified_bond_markets',{}).get(symbol)
        observed=contract['observed_date'] if contract else rates['metadata']['last']
        window=distribution_window(delivered['distributions'][symbol],observed)
        window['source_manifest_sha256']=source['manifest_sha256']
        issuer['facts']['distribution_source_observation']=window
        assessment=assess(issuer,contract,data.get('YAHOO_'+symbol),pool['formal_parameters'],evaluation_at,
            authorized_universe=pool['etf_quality_assessments'][symbol]['normalized_facts']['authorized_universe'])
        pool['etf_quality_assessments'][symbol]=assessment
        pool['asset_metrics'][symbol]['PRED-010']=assessment['metrics']
        pool['calculations'][symbol+'.PRED-010']=assessment
        pool['asset_unprovided_inputs'][symbol]['PRED-010']=assessment['unprovided_inputs']
    issuer=pool.get('issuer_observations',{}).get('SGOV');duration=(issuer or {}).get('facts',{}).get('effective_duration')
    if issuer and duration and duration.get('value') is not None:
        metrics,proof=weekly_benchmark(rates['observations'],duration['value'])
        proof.update(source_manifest_sha256=source['manifest_sha256'],xml_rows_reconciled=rates['xml_observations_reconciled'],
            official_fund_yield_history_available=False,
            fallback_authority='ORIGINAL_PRED_008_GOVERNMENT_TREASURY_FALLBACK__OWNER_REQUESTED_SOURCE_HANDOFF')
        checks=[daily_freshness(proof['observed_date'],evaluation_at),daily_freshness(duration['observed_date'],evaluation_at)]
        pool['asset_metrics'].setdefault('SGOV',{})['PRED-008']=metrics
        pool['calculations']['SGOV.PRED-008']=proof
        pool.setdefault('qualified_predicate_inputs',{}).setdefault('SGOV',{})['PRED-008']={
            'input_freshness_verified':all(c['state']=='FRESH' for c in checks),'checks':checks,
            'basis':'VERIFIED_TREASURY_BACKUP__COMPLETE_FIVE_YEAR_WEEKLY_GRID','identity':'PROXY'}
        pool['asset_unprovided_inputs']['SGOV']['PRED-008']=[]
        pool['canonical_yield_observations']['SGOV']['predicate_reference']=proof
    return pool

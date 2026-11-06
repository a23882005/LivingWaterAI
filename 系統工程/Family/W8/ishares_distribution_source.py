"""Current issuer distribution observations, never a historical publication clock.

HTML and the download are independent representations of one current issuer
snapshot. Agreement is evidence about observed values, not event completeness,
old-share cash basis, broker settlement or an earlier publication/revision.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json,re,xml.etree.ElementTree as ET

from family_input import digest
from member_market_source import time

SCHEMA='Family.W8.IsharesDistributionSources.v1'
SS='urn:schemas-microsoft-com:office:spreadsheet'
COLUMNS=('recordDate','exDate','payableDate','totalDistribution','incomeAmount',
    'shortTermCapitalGain','longTermCapitalGain','returnOnCapital')
LABELS=('Record Date','Ex-Date','Payable Date','Total Distribution','Income',
    'ST Cap Gains','LT Cap Gains','Return of Capital')
SCHEDULE_URL='https://www.ishares.com/us/literature/shareholder-letters/isharesandblackrocketfsdistributionschedule.pdf'


def pinned(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('ISHARES_ORIGINAL_BYTES_CHANGED')
    return raw


def acquired(source,known_by):
    raw=pinned(source);receipt=json.loads(pinned(source['acquisition_source']))
    if (type(receipt.get('status')) is not int or receipt['status']!=200 or receipt.get('url')!=source['url']
        or receipt.get('final_url')!=source['url'] or receipt.get('sha256')!=source['sha256']
        or type(receipt.get('bytes')) is not int or receipt['bytes']!=len(raw)
        or not time(receipt['started_at'])<=time(receipt['retrieved_at'])<=time(known_by)):
        raise PermissionError('ISHARES_URL_CAPTURE_OR_TIME_MISMATCH')
    return raw,receipt


def amount(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?',value):
        raise ValueError('ISHARES_ORIGINAL_DECIMAL_REQUIRED')
    return Decimal(value)


def day(value):
    months={m:i+1 for i,m in enumerate(('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'))}
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z][a-z]{2} \d\d, \d{4}',value) or value[:3] not in months:
        raise ValueError('ISHARES_ORIGINAL_DATE_REQUIRED')
    return date(int(value[-4:]),months[value[:3]],int(value[4:6]))


class Components(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.values=[]
    def handle_starttag(self,tag,attrs):
        if tag=='walrus-render-on-client':
            values=[v for k,v in attrs if k=='componentprops']
            if len(values)>1:raise ValueError('ISHARES_DUPLICATE_COMPONENT_ATTRIBUTE')
            if values:self.values.append(json.loads(values[0]))


def html_table(raw,manifest):
    parser=Components();parser.feed(raw.decode('utf-8-sig'));parts=parser.values
    headers=[p for p in parts if p.get('componentId')=='fundHeader']
    facts=[p for p in parts if p.get('componentId')=='keyFundFacts']
    if not headers or len(facts)!=1:raise ValueError('ISHARES_ORIGINAL_IDENTITY_COMPONENT_REQUIRED')
    for p in headers:
        ctx=p['context']
        if (ctx.get('ticker')!=manifest['symbol'] or ctx.get('productId')!=manifest['portfolio_id']
            or ctx.get('currencyCode')!='USD' or p.get('fundName')!=manifest['fund_name']):
            raise PermissionError('ISHARES_ORIGINAL_FUND_IDENTITY_CONFLICT')
    if facts[0]['dataPoints']['cusip']['formattedValue']!=manifest['cusip']:
        raise PermissionError('ISHARES_ORIGINAL_CUSIP_CONFLICT')
    tables=[p['distributionTableData'] for p in parts if 'distributionTableData' in p]
    if len(tables)!=1:raise ValueError('ISHARES_UNIQUE_ORIGINAL_DISTRIBUTION_TABLE_REQUIRED')
    table=tables[0];columns={c['name']:c for c in table}
    if len(columns)!=len(table) or set(columns)!=set(COLUMNS):
        raise ValueError('ISHARES_ORIGINAL_COLUMN_COVERAGE')
    if any(not isinstance(columns[k].get(field),list) for k in COLUMNS for field in ('value','formattedValue')):
        raise ValueError('ISHARES_ORIGINAL_PARALLEL_ROW_COVERAGE')
    lengths=[len(columns[k][field]) for k in COLUMNS for field in ('value','formattedValue')]
    if not lengths or not lengths[0] or len(set(lengths))!=1:
        raise ValueError('ISHARES_ORIGINAL_PARALLEL_ROW_COVERAGE')
    rows=[]
    for i in range(lengths[0]):
        original={k:dict(value=columns[k]['value'][i],formatted=columns[k]['formattedValue'][i]) for k in COLUMNS}
        for k in COLUMNS[:3]:
            parsed=day(original[k]['formatted']);v=original[k]['value']
            if type(v) is not int or str(v)!=parsed.strftime('%Y%m%d'):
                raise ValueError('ISHARES_ORIGINAL_DATE_REPRESENTATION_CONFLICT')
        for k in COLUMNS[3:]:
            prefix=columns[k].get('prefix')
            if not isinstance(prefix,list) or len(prefix)!=lengths[0] or prefix[i]!='$':
                raise PermissionError('ISHARES_ORIGINAL_CURRENCY_PREFIX_CONFLICT')
            if amount(original[k]['value'])!=amount(original[k]['formatted']):
                raise ValueError('ISHARES_DISPLAY_AND_ORIGINAL_AMOUNT_CONFLICT')
        dates=[day(original[k]['formatted']) for k in COLUMNS[:3]]
        if not dates[1]<=dates[0]<=dates[2]:raise ValueError('ISHARES_ORIGINAL_EVENT_DATE_ORDER')
        with localcontext() as ctx:
            ctx.prec=max(50,sum(len(original[k]['value']) for k in COLUMNS[3:])+10)
            if amount(original['totalDistribution']['value'])!=sum(amount(original[k]['value']) for k in COLUMNS[4:]):
                raise ValueError('ISHARES_ORIGINAL_COMPONENT_TOTAL_CONFLICT')
        rows.append(dict(session_id=str(dates[1]),record_date=str(dates[0]),payable_date=str(dates[2]),
            original_amount=original['totalDistribution']['value'],displayed_amount=original['totalDistribution']['formatted'],
            original_columns=original,issuer_row_index=i,available_at=None,historical_PIT_verified=False,
            cash_per_old_share_basis_verified=False,broker_cash_credit_verified=False,native_wealth_event_applied=False))
    if [r['session_id'] for r in rows]!=sorted((r['session_id'] for r in rows),reverse=True):
        raise ValueError('ISHARES_ORIGINAL_TABLE_DATE_ORDER')
    return rows


def sheet(raw,name):
    # The download contains unescaped ampersands in disclaimer hyperlinks.
    # Select the exact original worksheet bytes; do not repair the workbook.
    matches=re.findall(r'<ss:Worksheet ss:Name="'+re.escape(name)+r'">.*?</ss:Worksheet>',raw.decode('utf-8-sig'),re.S)
    if len(matches)!=1:raise ValueError('ISHARES_UNIQUE_ORIGINAL_WORKSHEET_REQUIRED')
    root=ET.fromstring('<ss:Workbook xmlns:ss="'+SS+'">'+matches[0]+'</ss:Workbook>')
    rows=[]
    for row in root.findall('.//{'+SS+'}Row'):
        cells=row.findall('{'+SS+'}Cell');values=[]
        for cell in cells:
            data=cell.findall('{'+SS+'}Data')
            if len(data)!=1 or len(data[0]) or '{'+SS+'}Index' in cell.attrib or '{'+SS+'}MergeAcross' in cell.attrib:
                raise ValueError('ISHARES_ORIGINAL_WORKSHEET_CELL_COVERAGE')
            values.append(data[0].text)
        rows.append(values)
    return rows


def compare(rows,actions):
    observed=defaultdict(list)
    for r in rows:observed[r['session_id']].append(r)
    providers={'MASSIVE':[dict(session_id=r['session_id'],value=r['original_cash_amount'],event_id=r['event_id'])
        for r in actions['corporate_action_observations']['dividends']['records']]}
    ib=actions.get('cross_provider_comparison')
    if ib is not None:
        providers['IB']=[dict(session_id=r['session_id'],value=r['IB_original_value'])
            for key in ('matching_numeric_observations','differing_original_values') for r in ib[key] if r['kind']=='dividends']
        for key in ('IB_events_not_observed_in_Massive','ambiguous_same_date_events'):
            providers['IB'].extend(dict(session_id=r['session_id'],value=r['original_IB_event']['value']) for r in ib[key] if r['kind']=='dividends')
    results={};start=actions['requested_start'];end=actions['requested_end']
    for provider,records in providers.items():
        grouped=defaultdict(list)
        for r in records:grouped[r['session_id']].append(r)
        matches=[];diffs=[];ambiguous=[];missing=[]
        for stamp in sorted(set(grouped)|{s for s in observed if start<=s<=end}):
            a=observed.get(stamp,[]);b=grouped.get(stamp,[])
            entry=dict(session_id=stamp,issuer_original_rows=deepcopy(a),provider_original_rows=deepcopy(b))
            if not a or not b:missing.append(entry)
            elif len(a)!=1 or len(b)!=1:ambiguous.append(entry)
            else:
                (matches if amount(a[0]['original_amount'])==amount(b[0]['value']) else diffs).append(entry)
        results[provider]=dict(matching_values=matches,differing_values=diffs,ambiguous_events=ambiguous,
            missing_counterpart=missing,comparison_start=start,comparison_end=end,
            difference_reason_verified=False,original_values_repaired=False,cash_basis_reconciled=False)
    return results


def read(descriptor,symbol,evaluation_at):
    m=json.loads(pinned(descriptor));known=m['known_by']
    if (m.get('schema_version')!=SCHEMA or m.get('symbol')!=symbol or m.get('currency')!='USD'
        or not isinstance(symbol,str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]*',symbol)
        or not re.fullmatch(r'\d+',m.get('portfolio_id','')) or not re.fullmatch(r'[A-Z0-9]{9}',m.get('cusip',''))
        or not m.get('fund_name') or time(known)>time(evaluation_at)):
        raise PermissionError('ISHARES_MANIFEST_IDENTITY_OR_TIME_CONFLICT')
    url=urlparse(m['page']['url'])
    if (url.scheme!='https' or url.netloc!='www.ishares.com' or url.query or url.fragment
        or not re.fullmatch('/us/products/'+m['portfolio_id']+r'/[a-z0-9-]+',url.path)):
        raise PermissionError('ISHARES_OFFICIAL_PRODUCT_URL_REQUIRED')
    url=urlparse(m['download']['url']);query=parse_qs(url.query)
    expected=dict(appSubType=['ISHARES'],appType=['PRODUCT_PAGE'],component=['fundDownload'],locale=['en_US'],
        portfolioId=[m['portfolio_id']],targetSite=['us-ishares'],userType=['individual'])
    if (url.scheme!='https' or url.netloc!='www.blackrock.com' or url.fragment
        or url.path!='/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document' or query!=expected):
        raise PermissionError('ISHARES_OFFICIAL_PORTFOLIO_DOWNLOAD_REQUIRED')
    html,cap=acquired(m['page'],known);xls,export_cap=acquired(m['download'],known);rows=html_table(html,m)
    if sheet(xls,'Holdings')[1]!=[m['fund_name']]:raise PermissionError('ISHARES_DOWNLOAD_FUND_NAME_CONFLICT')
    exported=sheet(xls,'Distributions')
    if exported[0]!=list(LABELS) or len(exported)!=len(rows)+1:
        raise ValueError('ISHARES_DOWNLOAD_DISTRIBUTION_ROW_COVERAGE')
    for observed,values in zip(rows,exported[1:]):
        if len(values)!=len(COLUMNS):raise ValueError('ISHARES_DOWNLOAD_COLUMN_COVERAGE')
        for k,v in zip(COLUMNS,values):
            original=observed['original_columns'][k]
            if (day(v)!=day(original['formatted']) if k in COLUMNS[:3] else amount(v)!=amount(original['value'])):
                raise ValueError('ISHARES_HTML_DOWNLOAD_VALUE_CONFLICT')
        observed['original_download_row']=deepcopy(values)
    publications=[]
    for source in m.get('publication_context_sources',[]):
        if source['url']!=SCHEDULE_URL:raise PermissionError('ISHARES_OFFICIAL_SCHEDULE_URL_REQUIRED')
        raw,receipt=acquired(source,known)
        if not raw.startswith(b'%PDF-'):raise ValueError('ISHARES_ORIGINAL_PDF_REQUIRED')
        publications.append(dict(source_descriptor=deepcopy(source),observed_at=receipt['retrieved_at'],
            role='CURRENT_DISTRIBUTION_SCHEDULE_NOT_EVENT_ANNOUNCEMENT_OR_HISTORICAL_VINTAGE',historical_publication_at=None))
    comparison=None
    if m.get('comparison_actions_source') is not None:
        from massive_action_source import read as actions_read
        comparison=compare(rows,actions_read(m['comparison_actions_source'],symbol,evaluation_at))
    out=dict(schema_version='Family.W8.IsharesDistributionObservations.v1',symbol=symbol,
        portfolio_id=m['portfolio_id'],cusip=m['cusip'],currency='USD',fund_name=m['fund_name'],
        source_descriptor=deepcopy(descriptor),known_by=known,evaluation_at=evaluation_at,
        page_observed_at=cap['retrieved_at'],download_observed_at=export_cap['retrieved_at'],
        distributions=rows,publication_context_documents=publications,cross_provider_comparison=comparison,
        two_issuer_representations_numerically_agree=True,complete_event_coverage_verified=False,
        listing_and_share_class_history_verified=False,historical_publication_and_revision_verified=False,
        qualified_native_actions=None,qP_history_qualified=False,qV_history_qualified=False,
        bank_or_broker_cash_available=False,trade_action='NO_TRADE',
        issues=['CURRENT_ISSUER_SNAPSHOT_NOT_HISTORICAL_PUBLICATION_OR_REVISION_PROOF',
            'SCHEDULE_DATE_NOT_EVENT_AVAILABLE_AT','CURRENT_VALUES_NOT_VERIFIED_OLD_SHARE_GROSS_CASH_BASIS',
            'PAYABLE_DATE_NOT_PROOF_OF_ACCOUNT_CREDIT_OR_AVAILABLE_CASH'])
    out['digest']=digest(out);return out

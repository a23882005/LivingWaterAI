"""Original SEC filings, accepted times and observed public availability.

Accepted time, filing date, fact period and observed public availability are
different source facts. A download proves availability at capture, not an
earlier dissemination timestamp. No historical PIT, price, listing, valuation
or funding permission is inferred.
"""
from copy import deepcopy
from datetime import datetime,date
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import json,re
from family_input import digest

SCHEMA='Family.W8.SECFilingPublicationSource.v1'
FORMS={'10-K','10-Q','10-K/A','10-Q/A','20-F','20-F/A'}
NY=ZoneInfo('America/New_York')


def instant(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',value):
        raise ValueError('SEC_PUBLICATION_EXPLICIT_TIMEZONE_REQUIRED')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None:raise ValueError('SEC_PUBLICATION_EXPLICIT_TIMEZONE_REQUIRED')
    return result


def pinned(source):
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:
        raise PermissionError('SEC_PUBLICATION_ORIGINAL_BYTES_CHANGED')
    return raw


def acquired(source,url,evaluation_at):
    raw=pinned(source)
    if (source.get('status')!=200 or source.get('url')!=url
        or len(raw)!=source.get('bytes')
        or not instant(source['started_at'])<=instant(source['retrieved_at'])<=instant(evaluation_at)):
        raise PermissionError('SEC_PUBLICATION_SOURCE_URL_CAPTURE_OR_TIME_MISMATCH')
    return raw


class InlineFacts(HTMLParser):
    """Read consolidated US-GAAP EPS without rendering or fetching links."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.context=None;self.unit=None;self.fact=None
        self.contexts={};self.units={};self.facts=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.stack.append(tag)
        if tag=='xbrli:context':self.context={'id':a.get('id'),'dimensioned':False}
        elif tag=='xbrli:unit':self.unit={'id':a.get('id'),'numerator':[],'denominator':[]}
        elif tag=='ix:nonfraction' and a.get('name')=='us-gaap:EarningsPerShareDiluted':
            if self.fact is not None:raise ValueError('SEC_PUBLICATION_NESTED_NUMERIC_FACT')
            self.fact={'attributes':a,'text':[]}
        if self.context is not None and tag in ('xbrli:segment','xbrli:scenario','xbrldi:explicitmember','xbrldi:typedmember'):
            self.context['dimensioned']=True
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs);self.handle_endtag(tag)
    def handle_data(self,data):
        if self.context is not None:
            for tag,key in (('xbrli:identifier','entity_cik'),('xbrli:startdate','start'),('xbrli:enddate','end'),('xbrli:instant','instant')):
                if self.stack and self.stack[-1]==tag:self.context[key]=self.context.get(key,'')+data
        if self.unit is not None and self.stack and self.stack[-1]=='xbrli:measure':
            key='denominator' if 'xbrli:unitdenominator' in self.stack else 'numerator'
            self.unit[key].append(data)
        if self.fact is not None:self.fact['text'].append(data)
    def handle_endtag(self,tag):
        if tag=='xbrli:context' and self.context is not None:
            key=self.context['id']
            if not key or key in self.contexts:raise ValueError('SEC_PUBLICATION_CONTEXT_ID_CONFLICT')
            self.contexts[key]=self.context;self.context=None
        elif tag=='xbrli:unit' and self.unit is not None:
            key=self.unit['id']
            if not key or key in self.units:raise ValueError('SEC_PUBLICATION_UNIT_ID_CONFLICT')
            self.units[key]=self.unit;self.unit=None
        elif tag=='ix:nonfraction' and self.fact is not None:self.facts.append(self.fact);self.fact=None
        if tag in self.stack:
            # HTML void elements need not have closing tags. Keep only the
            # current ancestor path; no HTML recovery supplies financial facts.
            index=len(self.stack)-1-self.stack[::-1].index(tag);self.stack=self.stack[:index]


@lru_cache(maxsize=16)
def _eps_facts(raw,cik):
    parser=InlineFacts();parser.feed(raw.decode('utf-8-sig'));rows={};unresolved=[]
    for fact in parser.facts:
        a=fact['attributes'];ctx=parser.contexts.get(a.get('contextref'));unit=parser.units.get(a.get('unitref'))
        if ctx is None or unit is None:raise ValueError('SEC_PUBLICATION_FACT_CONTEXT_OR_UNIT_MISSING')
        if str(ctx.get('entity_cik','')).strip().zfill(10)!=cik:
            raise PermissionError('SEC_PUBLICATION_FACT_ENTITY_CONFLICT')
        if ctx['dimensioned']:
            unresolved.append({'context_id':ctx['id'],'reason':'DIMENSIONED_FACT_REQUIRES_OWN_SOURCE_MAPPING'});continue
        measures=([x.strip() for x in unit['numerator']],[x.strip() for x in unit['denominator']])
        if measures!=(['iso4217:USD'],['xbrli:shares']):
            unresolved.append({'context_id':ctx['id'],'reason':'ORIGINAL_EPS_UNIT_NOT_USD_PER_SHARE','original_unit':unit});continue
        if not ctx.get('start') or not ctx.get('end'):raise ValueError('SEC_PUBLICATION_EPS_DURATION_REQUIRED')
        start,end=date.fromisoformat(ctx['start'].strip()),date.fromisoformat(ctx['end'].strip())
        if start>end:raise ValueError('SEC_PUBLICATION_FACT_PERIOD_ORDER')
        text=''.join(fact['text']).strip().replace('\u00a0','')
        if a.get('xsi:nil')=='true':
            unresolved.append({'context_id':ctx['id'],'reason':'ORIGINAL_FACT_NIL'});continue
        fmt=a.get('format')
        if fmt not in (None,'ixt:num-dot-decimal','ixt:numdotdecimal'):
            raise ValueError('SEC_PUBLICATION_NUMERIC_FORMAT_UNSUPPORTED')
        if not re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',text):
            raise ValueError('SEC_PUBLICATION_ORIGINAL_NUMERIC_VALUE_REQUIRED')
        scale=a.get('scale','0')
        if not re.fullmatch(r'-?\d+',scale) or not -12<=int(scale)<=12 or a.get('sign') not in (None,'-'):
            raise ValueError('SEC_PUBLICATION_NUMERIC_SCALE_OR_SIGN')
        value=Decimal(text.replace(',',''))*(Decimal(10)**int(scale))
        if a.get('sign')=='-':
            if value<0:raise ValueError('SEC_PUBLICATION_DOUBLE_NEGATIVE_SIGN')
            value=-value
        key=(str(start),str(end),'USD_PER_SHARE');item={'concept':'us-gaap:EarningsPerShareDiluted',
            'period_start':str(start),'period_end':str(end),'value':str(value),'unit':'USD_PER_SHARE',
            'source_context_ids':[ctx['id']],'source_fact_ids':[a.get('id')],'source_scale':scale,
            'source_fact_observations':[{'attributes':deepcopy(a),'text':''.join(fact['text']),
                'context':deepcopy(ctx),'unit':deepcopy(unit)}]}
        if key in rows:
            if Decimal(rows[key]['value'])!=value:raise ValueError('SEC_PUBLICATION_CONFLICTING_AS_FILED_FACTS')
            rows[key]['source_context_ids'].append(ctx['id']);rows[key]['source_fact_ids'].append(a.get('id'))
            rows[key]['source_fact_observations'].extend(item['source_fact_observations'])
        else:rows[key]=item
    return [rows[k] for k in sorted(rows)],unresolved


def eps_facts(raw,cik):
    # Raw bytes are verified before this pure parse cache is used. Return an
    # independent projection so no consumer can mutate another run's facts.
    return deepcopy(_eps_facts(raw,cik))


def read(descriptor,symbol,evaluation_at):
    manifest=json.loads(pinned(descriptor));at=instant(evaluation_at)
    if (manifest.get('schema_version')!=SCHEMA or manifest.get('symbol')!=symbol
        or not re.fullmatch(r'\d{10}',manifest.get('cik',''))
        or instant(manifest['source_capture_complete_at'])>at):
        raise PermissionError('SEC_PUBLICATION_ISSUER_OR_CAPTURE_MISMATCH')
    cik=manifest['cik'];identity=manifest['company_identity_source'];receipt=identity['receipt']
    if identity['local_path']!=receipt['local_path'] or identity['sha256']!=receipt['sha256']:
        raise PermissionError('SEC_PUBLICATION_COMPANY_INDEX_DESCRIPTOR_MISMATCH')
    names=json.loads(acquired(receipt,'https://www.sec.gov/files/company_tickers.json',evaluation_at))
    matches=[r for r in names.values() if r['ticker']==symbol]
    if len(matches)!=1 or str(matches[0]['cik_str']).zfill(10)!=cik:
        raise PermissionError('SEC_PUBLICATION_ORIGINAL_COMPANY_CIK_MISMATCH')
    rows={};recent=None;raw_sources=[deepcopy(receipt)]
    for page in manifest['submission_pages']:
        source=page['source'];url='https://data.sec.gov/submissions/'+Path(source['local_path']).name
        table=json.loads(acquired(source,url,evaluation_at));raw_sources.append(deepcopy(source))
        if page['kind']=='RECENT':
            if recent is not None or str(table.get('cik')).zfill(10)!=cik or symbol not in table.get('tickers',[]):
                raise PermissionError('SEC_PUBLICATION_SUBMISSIONS_COMPANY_MISMATCH')
            recent=table;table=table['filings']['recent']
        elif page['kind']=='ARCHIVE':
            if recent is None or not any(f['name']==Path(source['local_path']).name for f in recent['filings'].get('files',[])):
                raise PermissionError('SEC_PUBLICATION_UNINDEXED_ARCHIVE')
        else:raise ValueError('SEC_PUBLICATION_PAGE_KIND')
        required=('accessionNumber','form','filingDate','reportDate','acceptanceDateTime','primaryDocument')
        if any(not isinstance(table.get(k),list) for k in required) or len({len(table[k]) for k in required})!=1:
            raise ValueError('SEC_PUBLICATION_PARALLEL_ARRAY_COVERAGE_MISMATCH')
        for i in range(len(table['accessionNumber'])):
            row={k:table[k][i] for k in required};acc=row['accessionNumber']
            if row['form'] not in FORMS or row['filingDate']<manifest['requested_filing_date_from']:continue
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',acc) or not re.fullmatch(r'[A-Za-z0-9_.-]+',row['primaryDocument']):
                raise ValueError('SEC_PUBLICATION_ACCESSION_OR_DOCUMENT_INVALID')
            accepted=instant(row['acceptanceDateTime']);filed=date.fromisoformat(row['filingDate']);period=date.fromisoformat(row['reportDate'])
            # After-hours submissions can have the next business filing date.
            # Keep the SEC's explicit accepted timestamp; never replace it with
            # midnight on filingDate or with the fact's older report period.
            if accepted.astimezone(NY).date()>filed or period>accepted.astimezone(NY).date():
                raise ValueError('SEC_PUBLICATION_FILING_PERIOD_OR_ACCEPTED_DATE_CONFLICT')
            if accepted>at:continue
            if acc in rows and rows[acc]!=row:raise ValueError('SEC_PUBLICATION_CONFLICTING_ACCESSION_REVISION')
            rows[acc]=row
    if recent is None:raise ValueError('SEC_PUBLICATION_RECENT_SUBMISSIONS_REQUIRED')
    metadata=[]
    for acc,row in sorted(rows.items()):
        metadata.append({'accession_number':acc,'form':row['form'],'period_end':row['reportDate'],
            'accepted_at':row['acceptanceDateTime'],'acceptance_time_source_verified':True,
            'historical_public_available_at':None,'historical_publication_PIT_qualified':False,
            'filing_revision_id':acc,'primary_document':row['primaryDocument']})
    documents=[];facts=[];seen=set()
    for doc in manifest['filing_documents']:
        acc=doc['accession_number']
        if acc in seen:raise ValueError('SEC_PUBLICATION_DUPLICATE_ORIGINAL_DOCUMENT')
        seen.add(acc)
        if 'source' not in doc:continue
        if acc not in rows:raise PermissionError('SEC_PUBLICATION_DOCUMENT_NOT_IN_ACCEPTED_SOURCE_AT_CUTOFF')
        row=rows[acc];url='https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+acc.replace('-','')+'/'+row['primaryDocument']
        raw=acquired(doc['source'],url,evaluation_at);raw_sources.append(deepcopy(doc['source']))
        if instant(row['acceptanceDateTime'])>instant(doc['source']['retrieved_at']):
            raise PermissionError('SEC_PUBLICATION_DOCUMENT_CAPTURE_PRECEDES_ACCEPTANCE')
        values,unresolved=eps_facts(raw,cik) if row['form'].startswith(('10-K','10-Q')) else ([],[{'reason':'IFRS_ADR_AND_CURRENCY_SOURCE_MAPPING_REQUIRED'}])
        for value in values:
            if date.fromisoformat(value['period_end'])>date.fromisoformat(row['reportDate']):
                raise ValueError('SEC_PUBLICATION_FACT_AFTER_REPORTED_PERIOD')
            facts.append({**value,'symbol':symbol,'cik':cik,'accession_number':acc,
                'accepted_at':row['acceptanceDateTime'],'available_at':doc['source']['retrieved_at'],
                'retrieved_at':doc['source']['retrieved_at'],
                'filing_revision_id':acc,'source_reference':url,'source_sha256':doc['source']['sha256'],
                'public_availability_observed_at_capture':True,'as_reported_filing_fact_bound':True,
                'historical_publication_PIT_qualified':False,
                'availability_basis':'OBSERVED_PUBLIC_ORIGINAL_DOCUMENT_DOWNLOAD',
                'current_valuation_metric_computed':False})
        documents.append({'accession_number':acc,'source':deepcopy(doc['source']),
            'accepted_at':row['acceptanceDateTime'],'available_at':doc['source']['retrieved_at'],
            'as_reported_eps_facts':len(values),'unresolved':unresolved})
    out=dict(schema_version=SCHEMA,symbol=symbol,cik=cik,evaluation_at=evaluation_at,
        source_descriptor=deepcopy(descriptor),company=deepcopy(matches[0]),filing_publications=metadata,
        original_documents=documents,as_reported_eps_facts=facts,raw_sources=raw_sources,
        scope='ISSUER_ACCEPTANCE_AND_AS_REPORTED_FACTS_OBSERVED_AT_CAPTURE_ONLY',
        market_listing_or_share_class_attested=False,historical_price_PIT_verified=False,
        qP_history_qualified=False,qV_history_qualified=False,current_PE_calculated=False,
        trade_action='NO_TRADE')
    if any(instant(s['retrieved_at'])>instant(manifest['source_capture_complete_at']) for s in raw_sources):
        raise PermissionError('SEC_PUBLICATION_MANIFEST_CAPTURE_PRECEDES_ORIGINAL_SOURCE')
    out['digest']=digest(out);return out

"""Replay issuer pages into typed observations, without quality decisions."""
from datetime import datetime,date,timedelta
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
import json,re

from v75_remaining_inputs import number,time

URLS={
    'SGOV':'https://www.ishares.com/us/products/314116/ishares-0-3-month-treasury-bond-etf',
    'SPSB':'https://www.ssga.com/us/en/individual/etfs/state-street-spdr-portfolio-short-term-corporate-bond-etf-spsb'}


class IssuerHTML(HTMLParser):
    def __init__(self):
        super().__init__();self.components={};self.product_ids=[];self.hidden={}
        self.text=[];self.sections=[];self.section_depth=0;self.section=None;self.skip=0
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag in ('script','style'):self.skip+=1
        if tag=='walrus-context' and d.get('value'):
            product_id=json.loads(d['value']).get('productId')
            if product_id is not None:self.product_ids.append(product_id)
        if tag=='walrus-render-on-client' and d.get('componentprops'):
            value=json.loads(d['componentprops']);self.components.setdefault(value.get('componentId'),[]).append(value)
        if tag=='input' and d.get('id')=='premium-history-chart':self.hidden[d['id']]=json.loads(d['value'])
        if tag=='section':
            if self.section_depth==0:self.section={'text':[],'html':[]}
            self.section_depth+=1
        if self.section is not None:self.section['html'].append(self.get_starttag_text())
    def handle_endtag(self,tag):
        if self.section is not None:self.section['html'].append('</'+tag+'>')
        if tag=='section':
            self.section_depth-=1
            if self.section_depth==0:
                self.sections.append(self.section);self.section=None
        if tag in ('script','style'):self.skip-=1
    def handle_data(self,value):
        if self.skip:return
        clean=' '.join(value.split())
        if clean:self.text.append(clean)
        if self.section is not None:
            if clean:self.section['text'].append(clean)
            # Table contents are text, never evaluated as markup/code.
            from html import escape
            self.section['html'].append(escape(value))


def day(value):
    for fmt in ('%b %d, %Y','%b %d %Y','%d-%b-%Y','%Y%m%d','%Y-%m-%d'):
        try:return datetime.strptime(str(value),fmt).date().isoformat()
        except ValueError:pass
    raise ValueError('V75_ISSUER_DATE_FORMAT')


def numeric(value):
    if value in (None,'','-','N/A'):return None
    clean=str(value).replace(',','').replace('$','').replace('%','').strip()
    clean=re.sub(r'\s+(?:yrs|years)$','',clean)
    return str(number(clean))


def point(value,observed,unit,field):
    return {'value':numeric(value),'observed_date':day(observed),'unit':unit,'source_field':field}


def ishares(parser):
    if not parser.product_ids or set(parser.product_ids)!={314116}:
        raise PermissionError('V75_ISSUER_SGOV_PRODUCT_ID')
    def component(name):
        found=parser.components.get(name,[])
        if len(found)!=1:raise ValueError('V75_ISSUER_COMPONENT_AMBIGUOUS:'+name)
        return found[0]
    facts=component('keyFundFacts')['dataPoints'];risk=component('fundamentalsAndRisk')
    if facts.get('cusip',{}).get('formattedValue')!='46436E718':raise PermissionError('V75_ISSUER_CUSIP')
    def item(mapping,key,unit):
        r=mapping[key];return point(r['formattedValue'],r['formattedAsOfDate'],unit,key)
    result={'aum':item(facts,'totalNetAssetsFundLevel','USD'),
        'effective_duration':item(risk['dataPoints'],'modelOad','YEARS'),
        'portfolio_ytm':item(risk['dataPoints'],'fxHedgedYield','PERCENT'),
        'sec_yield_30d':item(risk['dataPoints'],'thirtyDaySecYield','PERCENT'),
        'bid_ask_spread_30_calendar_days':item(facts,'thirtyDayMedianBidAskSpread','PERCENT')}
    chart=component('performance') if len(parser.components.get('performance',[]))==1 else next(
        r for r in parser.components['performance'] if 'containersByNameMap' in r)
    pd=chart['containersByNameMap']['premium-discount-chart']['dataPointsByNameMap']['premiumDiscountChartData']
    if len(pd['asOfDate'])!=len(pd['value']):raise ValueError('V75_ISSUER_PD_ARRAY_LENGTH')
    result['premium_discount_history']=[{'date':day(d),'value_pct':numeric(v)} for d,v in zip(pd['asOfDate'],pd['value'])]
    dist=next(r for r in parser.components['performance'] if 'distributionTableData' in r)
    cols={c['name']:c for c in dist['distributionTableData']}
    names=('exDate','totalDistribution','incomeAmount','shortTermCapitalGain','longTermCapitalGain','returnOnCapital')
    lengths={len(cols[k]['formattedValue']) for k in names}
    if len(lengths)!=1:raise ValueError('V75_ISSUER_DISTRIBUTION_ARRAY_LENGTH')
    result['distributions']=[{'date':day(cols['exDate']['formattedValue'][i]),
        **{k:numeric(cols[k]['formattedValue'][i]) for k in names[1:]}}
        for i in range(next(iter(lengths)))]
    warning=cols['totalDistribution'].get('infoBubble','')
    unclassified='not classified' in warning.lower() and 'year-end' in warning.lower()
    result['distribution_characterization']={
        'current_year_classification':'NOT_CLASSIFIED_UNTIL_YEAR_END' if unclassified else 'NOT_ATTESTED',
        'issuer_statement':warning,'explicit_12m_roc':risk.get('rocPct12Month'),
        'complete_trailing_12m_breakdown_attested':False}
    return result


def ssga(parser):
    from v75_macro_inputs import Tables
    text='\n'.join(parser.text)
    if not all(v in text for v in ('SPSB','78464A474','US78464A4748','USD')):
        raise PermissionError('V75_ISSUER_SPSB_IDENTITY')
    def section(title):
        matches=[s for s in parser.sections if ' '.join(s['text']).startswith(title+' as of ')]
        if len(matches)!=1:raise ValueError('V75_ISSUER_SECTION_AMBIGUOUS:'+title)
        s=matches[0];match=re.search(r'as of ([A-Z][a-z]{2} \d{1,2} \d{4})',' '.join(s['text']))
        if not match:raise ValueError('V75_ISSUER_SECTION_DATE:'+title)
        table=Tables();table.feed(''.join(s['html']))
        return day(match[1]),table.tables
    def field(section_value,label,unit):
        observed,tables=section_value
        rows=[r for t in tables for r in t if len(r)==2 and r[0].startswith(label)]
        # A label prefix cannot select the separate Unsubsidized variant.
        if label=='30 Day SEC Yield':rows=[r for r in rows if '(Unsubsidized)' not in r[0]]
        if len(rows)!=1:raise ValueError('V75_ISSUER_FIELD_AMBIGUOUS:'+label)
        return point(rows[0][-1],observed,unit,label)
    characteristics=section('Fund Characteristics');yields=section('Yields');market=section('Fund Market Price')
    aum=re.search(r'Assets Under Management\n\$([\d,.]+) M\nas of ([A-Z][a-z]{2} \d{1,2} \d{4})',text)
    if not aum:raise ValueError('V75_ISSUER_AUM_REQUIRED')
    pd=parser.hidden['premium-history-chart']
    return {'aum':point(str(number(aum[1].replace(',',''))*1_000_000),aum[2],'USD','Assets Under Management (millions)'),
        'effective_duration':field(characteristics,'Option Adjusted Duration','YEARS'),
        'portfolio_ytm':field(characteristics,'Yield to Maturity','PERCENT'),
        'sec_yield_30d':field(yields,'30 Day SEC Yield','PERCENT'),
        'bid_ask_spread_30_calendar_days':field(market,'30-Day Median Bid/Ask Spread','PERCENT'),
        'premium_discount_history':[{'date':day(r['period_date']),
            'value_pct':str(number(r['value'])/100)} for r in pd['attrs']],
        'premium_discount_unit_conversion':'ISSUER_GRAPH_BPS_DIV_100_TO_PERCENT',
        'distribution_characterization':{'complete_trailing_12m_breakdown_attested':False,
            'current_year_classification':'BREAKDOWN_NOT_PRESENT_IN_CAPTURED_PRODUCT_PAGE'}}


def read(sources,evaluation_at):
    at=time(evaluation_at);out={}
    for symbol,source in (sources or {}).items():
        if symbol not in URLS:raise PermissionError('V75_ISSUER_UNSUPPORTED_PRODUCT')
        raw=Path(source['local_path']).read_bytes();receipt_raw=Path(source['receipt_path']).read_bytes()
        if sha256(raw).hexdigest()!=source['sha256'] or sha256(receipt_raw).hexdigest()!=source['receipt_sha256']:
            raise PermissionError('V75_ISSUER_SOURCE_BYTES_CHANGED')
        receipt=json.loads(receipt_raw)
        if (receipt.get('url')!=URLS[symbol] or receipt.get('final_url',receipt['url'])!=URLS[symbol]
            or receipt.get('http_status')!=200 or receipt.get('sha256')!=source['sha256']
            or not time(receipt['requested_at'])<=time(receipt['available_at'])<=at):
            raise PermissionError('V75_ISSUER_SOURCE_RECEIPT')
        parser=IssuerHTML();parser.feed(raw.decode('utf-8-sig'))
        facts=(ishares if symbol=='SGOV' else ssga)(parser)
        for key,value in facts.items():
            if isinstance(value,dict) and value.get('observed_date'):
                if date.fromisoformat(value['observed_date'])>time(receipt['available_at']).astimezone(ZoneInfo('America/New_York')).date():
                    raise PermissionError('V75_ISSUER_FUTURE_OBSERVATION:'+key)
        out[symbol]={'schema_version':'Family.W8.V75IssuerFacts.v1','symbol':symbol,'currency':'USD',
            'market':'US','facts':facts,'source_reference':URLS[symbol],
            'source_sha256':source['sha256'],'receipt_sha256':source['receipt_sha256'],
            'available_at':receipt['available_at'],'absence_of_liquidation_inferred':False,
            'absence_of_unapproved_methodology_change_inferred':False,
            'bid_ask_30d_substituted_for_20d':False,'historical_publication_times_asserted':False}
    return out

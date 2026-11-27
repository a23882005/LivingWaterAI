"""Synthetic original filings: accepted time is not historical availability."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from sec_publication_source import read,eps_facts

CIK='0000001234';ACC='0000001234-26-000001';AT='2026-11-03T16:00:00Z'
HTML='''<html><xbrli:context id="C1"><xbrli:entity><xbrli:identifier>0000001234</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="U1"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="C1" unitRef="U1" scale="0" id="FACT1">1.25</ix:nonFraction></html>'''

def case(tmp_path):
    def write(name,value,url):
        p=tmp_path/name;p.write_bytes(value if isinstance(value,bytes) else json.dumps(value).encode())
        return dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,
            url=url,status=200,started_at='2026-11-03T15:00:00Z',retrieved_at='2026-11-03T15:00:01Z')
    index=write('index.json',{'0':{'ticker':'SYN','cik_str':1234,'title':'SYNTHETIC COMPANY'}},'https://www.sec.gov/files/company_tickers.json')
    table={'accessionNumber':[ACC],'form':['10-Q'],'filingDate':['2026-08-05'],'reportDate':['2026-06-30'],
        'acceptanceDateTime':['2026-08-05T20:36:00Z'],'primaryDocument':['original.htm']}
    metadata={'cik':CIK,'tickers':['SYN'],'filings':{'recent':table,'files':[]}}
    page=write('CIK'+CIK+'.json',metadata,'https://data.sec.gov/submissions/CIK'+CIK+'.json')
    document=write('original.htm',HTML.encode(),'https://www.sec.gov/Archives/edgar/data/1234/'+ACC.replace('-','')+'/original.htm')
    manifest=dict(schema_version='Family.W8.SECFilingPublicationSource.v1',symbol='SYN',cik=CIK,
        company_identity_source=dict(local_path=index['local_path'],sha256=index['sha256'],receipt=index),
        submission_pages=[dict(source=page,kind='RECENT')],filing_documents=[dict(accession_number=ACC,source=document)],
        requested_filing_date_from='2021-11-01',source_capture_complete_at='2026-11-03T15:00:02Z')
    def descriptor():
        # Re-pin test edits only; they still have to satisfy the original
        # timestamp, entity, document address and fact consistency contracts.
        for obj in (manifest['company_identity_source']['receipt'],page,document):
            p=Path(obj['local_path']);obj.update(sha256=sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
        manifest['company_identity_source']['sha256']=index['sha256']
        return write('manifest.json',manifest,'SYNTHETIC_MANIFEST')
    return manifest,metadata,document,descriptor


def test_report_period_and_acceptance_do_not_backdate_observed_public_availability(tmp_path):
    _,_,_,desc=case(tmp_path);out=read(desc(),'SYN',AT);f=out['as_reported_eps_facts'][0]
    assert f['period_end']=='2026-06-30' and f['accepted_at']=='2026-08-05T20:36:00Z'
    assert f['available_at']==f['retrieved_at']=='2026-11-03T15:00:01Z'
    assert f['value']=='1.25' and f['as_reported_filing_fact_bound']
    assert not f['historical_publication_PIT_qualified'] and not out['qV_history_qualified']
    assert not out['market_listing_or_share_class_attested'] and not out['current_PE_calculated']


def test_after_hours_next_business_filing_date_keeps_original_accepted_utc(tmp_path):
    m,meta,_,desc=case(tmp_path);tab=meta['filings']['recent'];tab['filingDate']=['2026-08-10']
    tab['acceptanceDateTime']=['2026-08-07T23:36:00Z']
    Path(m['submission_pages'][0]['source']['local_path']).write_text(json.dumps(meta))
    out=read(desc(),'SYN',AT)
    assert out['filing_publications'][0]['accepted_at']=='2026-08-07T23:36:00Z'
    assert out['filing_publications'][0]['historical_public_available_at'] is None


@pytest.mark.parametrize('change',['symbol','index_cik','metadata_cik','naive_time','date_only','future_capture',
    'parallel_arrays','wrong_url','future_fact','foreign_entity','capture_cohort'])
def test_cross_issuer_time_and_original_source_conflicts_are_rejected(tmp_path,change):
    m,meta,doc,desc=case(tmp_path)
    if change=='symbol':m['symbol']='OTHER'
    elif change=='index_cik':Path(m['company_identity_source']['local_path']).write_text(json.dumps({'0':{'ticker':'SYN','cik_str':9876}}))
    elif change=='metadata_cik':meta['cik']='0000009876'
    elif change=='naive_time':meta['filings']['recent']['acceptanceDateTime']=['20260805203600']
    elif change=='date_only':meta['filings']['recent']['acceptanceDateTime']=['2026-08-05']
    elif change=='future_capture':doc['retrieved_at']='2026-11-04T15:00:01Z'
    elif change=='parallel_arrays':meta['filings']['recent']['primaryDocument']=[]
    elif change=='wrong_url':doc['url']=doc['url'].replace('/1234/','/9876/')
    elif change=='future_fact':Path(doc['local_path']).write_text(HTML.replace('2026-06-30','2026-09-30'))
    elif change=='foreign_entity':Path(doc['local_path']).write_text(HTML.replace('0000001234','0000009876'))
    else:m['source_capture_complete_at']='2026-11-03T15:00:00Z'
    Path(m['submission_pages'][0]['source']['local_path']).write_text(json.dumps(meta))
    with pytest.raises((ValueError,PermissionError)):read(desc(),'SYN',AT)


def test_changed_original_bytes_fail_before_cached_parse_and_cached_facts_cannot_be_mutated(tmp_path):
    _,_,doc,desc=case(tmp_path);d=desc();out=read(d,'SYN',AT)
    out['as_reported_eps_facts'][0]['source_context_ids'].append('INJECTED')
    assert read(d,'SYN',AT)['as_reported_eps_facts'][0]['source_context_ids']==['C1']
    Path(doc['local_path']).write_text(HTML.replace('1.25','9.99'))
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read(d,'SYN',AT)


@pytest.mark.parametrize('html,value',[(HTML,'1.25'),(HTML.replace('scale="0"','scale="1"'),'12.50'),
    (HTML.replace('scale="0"','scale="0" sign="-"'),'-1.25')])
def test_explicit_original_xbrl_scale_and_sign_are_preserved(html,value):
    facts,issues=eps_facts(html.encode(),CIK);assert facts[0]['value']==value and not issues


@pytest.mark.parametrize('change',['dimension','unit','nil'])
def test_unresolved_dimensions_units_and_nil_do_not_create_consolidated_usd_eps(change):
    html=HTML
    if change=='dimension':html=html.replace('</xbrli:entity>','<xbrli:segment><xbrldi:explicitMember>CLASS_A</xbrldi:explicitMember></xbrli:segment></xbrli:entity>')
    elif change=='unit':html=html.replace('iso4217:USD','iso4217:TWD')
    else:html=html.replace('scale="0"','scale="0" xsi:nil="true"')
    facts,issues=eps_facts(html.encode(),CIK);assert not facts and issues


def test_two_conflicting_original_values_for_one_consolidated_period_are_not_selected_arbitrarily():
    extra='<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="C1" unitRef="U1" scale="0">1.26</ix:nonFraction>'
    with pytest.raises(ValueError,match='CONFLICTING_AS_FILED'):eps_facts(HTML.replace('</html>',extra+'</html>').encode(),CIK)


def test_amendment_remains_a_separate_accession_vintage(tmp_path):
    m,meta,_,desc=case(tmp_path);t=meta['filings']['recent'];new='0000001234-26-000002'
    for key in list(t):t[key].append(t[key][0])
    t['accessionNumber'][1]=new;t['form'][1]='10-Q/A';t['acceptanceDateTime'][1]='2026-08-06T12:00:00Z';t['filingDate'][1]='2026-08-06'
    Path(m['submission_pages'][0]['source']['local_path']).write_text(json.dumps(meta))
    out=read(desc(),'SYN',AT);assert len(out['filing_publications'])==2
    assert {r['filing_revision_id'] for r in out['filing_publications']}=={ACC,new}
    assert len(out['as_reported_eps_facts'])==1


def test_equal_values_keep_each_original_precision_scale_sign_and_context():
    first=HTML.replace('scale="0"','scale="0" decimals="2"')
    second='<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="C1" unitRef="U1" scale="-2" decimals="INF" id="FACT2">125</ix:nonFraction>'
    facts,issues=eps_facts(first.replace('</html>',second+'</html>').encode(),CIK)
    assert not issues and len(facts)==1 and facts[0]['value']=='1.25'
    originals=facts[0]['source_fact_observations']
    assert [r['attributes']['decimals'] for r in originals]==['2','INF']
    assert [r['attributes']['scale'] for r in originals]==['0','-2']
    assert [r['text'] for r in originals]==['1.25','125']
    assert all(r['context']['entity_cik']==CIK and r['unit']['denominator']==['xbrli:shares'] for r in originals)
    negative,_=eps_facts(HTML.replace('scale="0"','scale="0" sign="-" decimals="2"').encode(),CIK)
    assert negative[0]['value']=='-1.25'
    assert negative[0]['source_fact_observations'][0]['attributes']['sign']=='-'


def test_original_document_cannot_be_observed_before_its_accepted_time(tmp_path):
    m,meta,_,desc=case(tmp_path)
    meta['filings']['recent']['acceptanceDateTime']=['2026-11-03T15:30:00Z']
    meta['filings']['recent']['filingDate']=['2026-11-03']
    Path(m['submission_pages'][0]['source']['local_path']).write_text(json.dumps(meta))
    with pytest.raises(PermissionError,match='CAPTURE_PRECEDES_ACCEPTANCE'):
        read(desc(),'SYN',AT)

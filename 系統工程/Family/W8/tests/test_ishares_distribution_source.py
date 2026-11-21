"""Synthetic source/clock/currency guards and original C7 observation route."""
from copy import deepcopy
from datetime import date
from decimal import getcontext,localcontext
from hashlib import sha256
from html import escape
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from ishares_distribution_source import read,COLUMNS,LABELS,SS,SCHEDULE_URL,compare
from historical_source_qualification import bind


def case(tmp_path,at='2026-11-05T21:00:00Z'):
    def save(name,value):
        p=tmp_path/name;p.write_bytes(value if isinstance(value,bytes) else (value if isinstance(value,str) else json.dumps(value)).encode())
        return dict(local_path=str(p),sha256=sha256(p.read_bytes()).hexdigest())
    dates=['Nov 03, 2021','Nov 03, 2021','Nov 05, 2021']
    vals=[20211103,20211103,20211105,'0.27239','0.27239','0.0','0.0','0.0']
    display=dates+['0.272390','0.272390','0.000000','0.000000','0.000000']
    components=[dict(componentId='fundHeader',context=dict(ticker='SYN',productId='99999',currencyCode='USD'),fundName='Synthetic Fund'),
        dict(componentId='keyFundFacts',dataPoints=dict(cusip={'formattedValue':'000000000'})),
        dict(componentId='performance',distributionTableData=[dict(name=k,value=[v],formattedValue=[s],
            **({'prefix':['$']} if i>=3 else {})) for i,(k,v,s) in enumerate(zip(COLUMNS,vals,display))])]
    exported=[dates+['0.27239','0.27239','0','0','0']]
    m=dict(schema_version='Family.W8.IsharesDistributionSources.v1',symbol='SYN',portfolio_id='99999',
        cusip='000000000',fund_name='Synthetic Fund',currency='USD',known_by=at)
    captures={};raws={};descriptors={}
    urls=dict(page='https://www.ishares.com/us/products/99999/synthetic-fund',
        download='https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=99999&targetSite=us-ishares&userType=individual',schedule=SCHEDULE_URL)
    for kind in urls:captures[kind]=dict(status=200,url=urls[kind],final_url=urls[kind],started_at=at,retrieved_at=at)
    def xmlrow(values):return '<ss:Row>'+''.join('<ss:Cell><ss:Data ss:Type="String">'+escape(str(v))+'</ss:Data></ss:Cell>' for v in values)+'</ss:Row>'
    def descriptor():
        raws['page']=''.join('<walrus-render-on-client componentprops="'+escape(json.dumps(c),quote=True)+'"></walrus-render-on-client>' for c in components).encode()
        # An invalid disclaimer URL is not silently repaired to parse the file.
        raws['download']=('<ss:Workbook xmlns:ss="'+SS+'"><disclaimer href="a&b"/>'
            '<ss:Worksheet ss:Name="Holdings"><ss:Table>'+xmlrow(['old holdings date'])+xmlrow([m['fund_name']])+'</ss:Table></ss:Worksheet>'
            '<ss:Worksheet ss:Name="Distributions"><ss:Table>'+xmlrow(LABELS)+''.join(xmlrow(r) for r in exported)+'</ss:Table></ss:Worksheet></ss:Workbook>').encode()
        raws['schedule']=b'%PDF-1.6 SYNTHETIC CURRENT SCHEDULE, NOT A VINTAGE'
        for kind in urls:
            source=save(kind+'.raw',raws[kind]);captures[kind].update(sha256=source['sha256'],bytes=len(raws[kind]))
            descriptors[kind]={**source,'url':urls[kind],'acquisition_source':save(kind+'.capture.json',captures[kind])}
        m['page']=descriptors['page'];m['download']=descriptors['download'];m['publication_context_sources']=[descriptors['schedule']]
        return save('issuer.json',m)
    return m,components,exported,captures,descriptor,descriptors


def test_original_precision_ex_record_pay_and_schedule_never_become_pit_or_cash(tmp_path):
    m,_,_,_,desc,_=case(tmp_path);result=read(desc(),'SYN',m['known_by']);row=result['distributions'][0]
    assert row['original_amount']=='0.27239' and row['displayed_amount']=='0.272390'
    assert row['session_id']=='2021-11-03' and row['record_date']=='2021-11-03' and row['payable_date']=='2021-11-05'
    assert row['original_download_row'][3]=='0.27239' and row['available_at'] is None
    assert not row['historical_PIT_verified'] and not row['broker_cash_credit_verified'] and not row['native_wealth_event_applied']
    assert result['publication_context_documents'][0]['historical_publication_at'] is None
    assert not result['qP_history_qualified'] and not result['qV_history_qualified'] and result['qualified_native_actions'] is None
    assert not result['complete_event_coverage_verified'] and not result['historical_publication_and_revision_verified']
    assert not result['bank_or_broker_cash_available'] and result==read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('field',['symbol','currency','cusip','portfolio_id','fund_name','schema_version','known_by'])
def test_foreign_or_future_identity_is_rejected(tmp_path,field):
    m,_,_,_,desc,_=case(tmp_path);m[field]='2027-01-01T00:00:00Z' if field=='known_by' else 'OTHER'
    with pytest.raises((PermissionError,ValueError)):read(desc(),'SYN','2026-11-05T21:00:00Z')


@pytest.mark.parametrize('kind',['page','download','schedule'])
@pytest.mark.parametrize('part',['raw','capture'])
def test_every_original_and_capture_byte_is_pinned(tmp_path,kind,part):
    m,_,_,_,desc,sources=case(tmp_path);d=desc();p=sources[kind] if part=='raw' else sources[kind]['acquisition_source']
    Path(p['local_path']).write_text('CHANGED')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read(d,'SYN',m['known_by'])


@pytest.mark.parametrize('change',['status','redirect','started_at','retrieved_at','url'])
def test_capture_http_route_and_chronology_are_bound(tmp_path,change):
    m,_,_,cap,desc,_=case(tmp_path)
    if change=='status':cap['page']['status']=200.0
    elif change=='redirect':cap['page']['final_url']='https://other.example/a'
    elif change=='url':cap['page']['url']='https://other.example/a'
    else:cap['page'][change]='2027-01-01T00:00:00Z'
    with pytest.raises(PermissionError):read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('change',['currency','ticker','product','cusip','fund','extra_header','extra_table'])
def test_embedded_original_identity_and_table_conflicts_are_rejected(tmp_path,change):
    m,c,_,_,desc,_=case(tmp_path)
    if change in ('currency','ticker','product'):c[0]['context'][{'currency':'currencyCode','ticker':'ticker','product':'productId'}[change]]='OTHER'
    elif change=='cusip':c[1]['dataPoints']['cusip']['formattedValue']='OTHER'
    elif change=='fund':c[0]['fundName']='OTHER'
    elif change=='extra_header':c.append({**deepcopy(c[0]),'fundName':'OTHER'})
    else:c.append(deepcopy(c[2]))
    with pytest.raises((PermissionError,ValueError)):read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('change',['duplicate_column','missing','parallel','date','date_bool','prefix','nan','negative','rounded_display','component_sum','pay_order'])
def test_original_arrays_dates_units_and_exact_components_fail_closed(tmp_path,change):
    m,c,_,_,desc,_=case(tmp_path);cols=c[2]['distributionTableData']
    if change=='duplicate_column':cols.append(deepcopy(cols[-1]))
    elif change=='missing':cols.pop()
    elif change=='parallel':cols[0]['value'].append(20211103)
    elif change=='date':cols[0]['formattedValue'][0]='Nov 04, 2021'
    elif change=='date_bool':cols[0]['value'][0]=True
    elif change=='prefix':cols[3]['prefix'][0]='EUR'
    elif change in ('nan','negative'):cols[3]['value'][0]='NaN' if change=='nan' else '-0.1'
    elif change=='rounded_display':cols[3]['formattedValue'][0]='0.272400'
    elif change=='component_sum':cols[4]['value'][0]='0.2';cols[4]['formattedValue'][0]='0.200000'
    else:cols[2]['value'][0]=20211102;cols[2]['formattedValue'][0]='Nov 02, 2021'
    with pytest.raises((PermissionError,ValueError)):read(desc(),'SYN',m['known_by'])


@pytest.mark.parametrize('change',['missing_row','amount','date','extra_cell'])
def test_html_and_download_must_agree_without_repair(tmp_path,change):
    m,_,rows,_,desc,_=case(tmp_path)
    if change=='missing_row':rows.clear()
    elif change=='amount':rows[0][3]='0.2724'
    elif change=='date':rows[0][0]='Nov 04, 2021'
    else:rows[0].append('OTHER')
    with pytest.raises(ValueError):read(desc(),'SYN',m['known_by'])


def test_manifest_cannot_promote_publication_or_funding_and_decimal_is_isolated(tmp_path):
    m,_,_,_,desc,_=case(tmp_path);m.update(available_at='2021-11-01T00:00:00Z',historical_PIT_verified=True,qualified_native_actions=[])
    original=getcontext().prec
    with localcontext() as ctx:
        ctx.prec=6;r=read(desc(),'SYN',m['known_by']);assert ctx.prec==6
    assert getcontext().prec==original and not r['historical_publication_and_revision_verified'] and r['qualified_native_actions'] is None


def test_scientific_notation_in_original_issuer_data_is_preserved_exactly(tmp_path):
    m,c,_,_,desc,_=case(tmp_path)
    for i in (3,4):c[2]['distributionTableData'][i]['value'][0]='2.7239E-1'
    result=read(desc(),'SYN',m['known_by'])
    assert result['distributions'][0]['original_amount']=='2.7239E-1'
    assert result['distributions'][0]['displayed_amount']=='0.272390'


def test_numeric_difference_is_preserved_and_same_date_events_are_not_collapsed(tmp_path):
    m,_,_,_,desc,_=case(tmp_path);r=read(desc(),'SYN',m['known_by']);rows=r['distributions']
    actions={'requested_start':'2021-11-01','requested_end':'2021-11-05','cross_provider_comparison':None,
        'corporate_action_observations':{'dividends':{'records':[dict(session_id='2021-11-03',original_cash_amount='0.2724',event_id='D1')]}}}
    compared=compare(rows,actions)['MASSIVE'];assert len(compared['differing_values'])==1 and not compared['matching_values']
    assert rows[0]['original_amount']=='0.27239' and not compared['original_values_repaired'] and not compared['difference_reason_verified']
    actions['corporate_action_observations']['dividends']['records'].append(dict(session_id='2021-11-03',original_cash_amount='0.1',event_id='D2'))
    ambiguous=compare(rows,actions)['MASSIVE'];assert not ambiguous['matching_values'] and not ambiguous['differing_values']
    assert len(ambiguous['ambiguous_events'][0]['provider_original_rows'])==2


def test_public_comparison_uses_the_accepted_massive_original_reader(tmp_path):
    from test_massive_action_source import case as actions_case
    m,_,_,_,desc,_=case(tmp_path);a,_,_,_,ad,_=actions_case(tmp_path,m['known_by'])
    m['comparison_actions_source']=ad();result=read(desc(),'SYN',m['known_by'])
    assert len(result['cross_provider_comparison']['MASSIVE']['differing_values'])==1
    assert result['cross_provider_comparison']['MASSIVE']['differing_values'][0]['provider_original_rows'][0]['value']=='1.00'


def test_new_source_reaches_original_c7_same_run_observations_without_releasing_qualification(tmp_path):
    from test_family_c7_source_assembly import original_case
    from family_c7_source_assembly import assemble
    _,_,request,context,tactical,identities,_,_=original_case(tmp_path)
    m,_,_,_,desc,_=case(tmp_path,request['evaluation_at']);sources={'issuer_distributions':desc()}
    observed=bind(sources,request,'SYN');context['public_history_source_binding']={**{k:request[k] for k in ('client_id','run_id')},
        'source_db_sha256':request['client_snapshot']['payload']['source_sha256'],'asset_id':'SYN','source_descriptors':sources,'digest':observed['digest']}
    result=assemble(ROOT,request,context,artifact_directory=tmp_path/'private',tactical=tactical,identities=identities)
    assert result['original_observations']['public_history_source_qualification']==observed
    assert not observed['financial_qualification_released'] and observed['qualified_qP_history'] is None

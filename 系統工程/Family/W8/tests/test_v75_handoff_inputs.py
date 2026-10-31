"""Delivered-source reconciliation, weekly identity and incomplete ROC."""
from copy import deepcopy
from datetime import date,timedelta
from hashlib import sha256
from pathlib import Path
import io,json,sys,zipfile
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_handoff_inputs as H


def observations():
    rows=[];day=date(2021,10,29)
    while day<=date(2026,10,28):
        if day.weekday()==4:rows.append({'date':str(day),'BC_1MONTH':'4','BC_2MONTH':'9','BC_3MONTH':'12'})
        day+=timedelta(days=1)
    rows.append({'date':'2026-10-28','BC_1MONTH':'3','BC_2MONTH':'8','BC_3MONTH':'11'})
    return rows


def test_weekly_last_published_grid_is_a_labelled_treasury_backup_not_fund_yield():
    metrics,proof=H.weekly_benchmark(observations(),'0.11')
    assert metrics['history_years']=='5' and proof['weekly_observations']==262
    assert proof['selected_tenor_months']==1 and proof['latest_yield_pct']=='3'
    assert not proof['latest_week_complete'] and proof['observed_date']=='2026-10-28'
    assert proof['latest_week_nominal_end']=='2026-10-30'
    assert proof['identity']=='PROXY' and not proof['is_fund_ytm'] and not proof['is_sec_yield']
    assert not proof['historical_fund_duration_inferred'] and not proof['interpolated_or_forward_filled']
    assert proof['methodology_break_date']=='2021-12-06'


def test_missing_week_and_equal_distance_tenor_are_not_filled_or_guessed():
    rows=observations();rows.pop(20)
    with pytest.raises(ValueError,match='WEEKLY_YIELD_COVERAGE'):H.weekly_benchmark(rows,'0.11')
    with pytest.raises(ValueError,match='TENOR_MATCH_AMBIGUOUS'):H.weekly_benchmark(observations(),'0.125')


def test_malformed_or_substituted_xml_is_rejected_without_rewriting_raw_bytes():
    raw=b'<root><name>A & B</name></root>';before=bytes(raw)
    assert H.xml(raw,True).find('name').text=='A & B' and raw==before
    with pytest.raises(ValueError,match='DTD_FORBIDDEN'):H.xml(b'<!DOCTYPE x><root/>')


def test_csv_extraction_must_match_bound_annual_treasury_xml():
    rows=[{'date':'2021-10-29','BC_1MONTH':'0.05','BC_2MONTH':'0.06','BC_3MONTH':'0.07'}]
    xml=b'<feed><properties><NEW_DATE>2021-10-29T00:00:00</NEW_DATE><BC_1MONTH>0.05</BC_1MONTH><BC_2MONTH>0.06</BC_2MONTH><BC_3MONTH>0.07</BC_3MONTH></properties></feed>'
    manifest={'sources':[{'key':'2021','status':200,'sha256':sha256(xml).hexdigest(),
        'url':'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2021'}]}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:z.writestr('raw/2021.xml',xml)
    data={'metadata':{'first':'2021-10-29','last':'2021-10-29','row_count':1},'observations':rows}
    files={'rates/treasury_short_tenor_daily_20211029_20261028.json':json.dumps(data).encode(),
        'rates/source_manifest.json':json.dumps(manifest).encode(),'rates/treasury_source_bundle_20261029.zip':buf.getvalue()}
    assert H.treasury(files)['xml_observations_reconciled']==1
    data['observations'][0]['BC_1MONTH']='0.5'
    files['rates/treasury_short_tenor_daily_20211029_20261028.json']=json.dumps(data).encode()
    with pytest.raises(PermissionError,match='EXTRACT_XML_MISMATCH'):H.treasury(files)


def test_complete_issuer_breakdown_is_usable_while_tax_finality_stays_provisional():
    rows=[{'ex_date':f'2026-{m:02d}-01','total':'1','roc':'0',
        'characterization':'PROVISIONAL_ISSUER_DISPLAY','final_tax_characterization':False} for m in range(1,11)]
    rows+=[{'ex_date':'2025-'+m+'-01','total':'1','roc':'0',
        'characterization':'OFFICIAL_2025_TAX_BREAKDOWN','final_tax_characterization':True} for m in ('11','12')]
    out=H.distribution_window(rows,'2026-10-28')
    assert out['as_reported_roc_pct']=='0' and out['complete_source_breakdown']
    assert out['provisional_issuer_components'] and not out['complete_final_breakdown']
    assert out['native_distribution_quality_state'] is None
    from v75_etf_quality_inputs import components
    assert components({'trailing_12m_roc_pct':out['as_reported_roc_pct']},'US')[0]['distribution_quality_state']=='DISTRIBUTION_OK'
    rows[0]['roc']=None;out=H.distribution_window(rows,'2026-10-28')
    assert out['as_reported_roc_pct'] is None and out['missing_roc_dates']==['2026-01-01']
    assert not out['complete_source_breakdown'] and out['native_distribution_quality_state']=='UNKNOWN'
    rows.pop()
    with pytest.raises(ValueError,match='WINDOW_COVERAGE'):H.distribution_window(rows,'2026-10-28')


def test_source_ingestion_cannot_be_backdated_or_changed_after_binding(tmp_path):
    source={'schema_version':'Family.W8.V75SourceHandoff.v1','ingested_at':'2026-10-29T07:30:00Z',
        'root':str(tmp_path),'manifest_sha256':'0'*64}
    with pytest.raises(PermissionError,match='SCHEMA_OR_AVAILABILITY'):H.read(source,'2026-10-29T07:00:00Z')
    (tmp_path/'PACKAGE_MANIFEST.json').write_text('[]')
    with pytest.raises(PermissionError,match='MANIFEST_HASH'):H.read(source,'2026-10-29T08:00:00Z')

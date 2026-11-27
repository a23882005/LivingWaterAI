"""Synthetic schedule counterexamples; no customer source files are used."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import tpex_calendar_source as C


def fixture():
    return json.dumps({'stat':'ok','endDate':'20270101','data':{'html':
        '<table><tr><td>中華民國115年有價證券櫃檯買賣市場開（休）市日期表</td></tr></table>'
        '<table><tr><th>紀念節日名稱</th><th>日期</th><th>星期</th><th>說明</th></tr>'
        '<tr><td>國曆新年開始交易日</td><td>1月2日</td><td>五</td><td>國曆新年開始交易。</td></tr>'
        '<tr><td>農曆春節前國際債券交易系統最後交易日</td><td>2月10日</td><td>二</td>'
        '<td>2月11日、2月12日及2月13日市場無交易，僅辦理給付結算。</td></tr>'
        '<tr><td>農曆春節前股票交易系統最後交易日</td><td>2月11日</td><td>三</td>'
        '<td>2月12日及2月13日市場無交易，僅辦理給付結算。</td></tr>'
        '<tr><td rowspan="2">農曆春節</td><td>2月15日</td><td>日</td><td>放假1日</td></tr>'
        '<tr><td>2月16日</td><td>一</td><td>補假1日</td></tr></table>'}},ensure_ascii=False).encode()


def test_stock_schedule_ignores_international_bond_earlier_close_and_expands_rowspan():
    plan=C.annual_plan(fixture(),2026)
    assert plan['closed_dates']==['2026-02-12','2026-02-13','2026-02-15','2026-02-16']
    assert plan['explicit_open_dates']==['2026-01-02']
    assert len(plan['excluded_other_trading_system_rows'])==1
    # endDate is the website's latest selectable year, not this table's year.
    assert plan['year']==2026


def test_html_omitted_cell_end_tag_has_browser_table_semantics():
    raw=fixture().decode();changed=raw.replace('放假1日</td></tr>','放假1日</tr>')
    assert changed!=raw
    assert C.annual_plan(changed.encode(),2026)==C.annual_plan(raw.encode(),2026)


def test_explicit_roc_previous_year_closure_does_not_move_to_current_december():
    raw=fixture().decode().replace('2月15日','114年12月31日')
    plan=C.annual_plan(raw.encode(),2026)
    assert '2025-12-31' in plan['closed_dates'] and '2026-12-31' not in plan['closed_dates']


@pytest.mark.parametrize('change',[
    lambda s:s.replace('115年','114年'),
    lambda s:s.replace('2月15日','2月15日至2月20日'),
    lambda s:s.replace('2月15日','2月30日'),
    lambda s:s.replace('補假1日','語意尚未定義'),
    lambda s:s.replace('股票交易系統','國際債券交易系統'),
    lambda s:s.replace('rowspan=\\"2\\"','rowspan=\\"8\\"'),
])
def test_unknown_or_incomplete_schedule_is_rejected(change):
    raw=fixture().decode();changed=change(raw)
    assert changed!=raw
    with pytest.raises(ValueError):C.annual_plan(changed.encode(),2026)


def sources(tmp_path):
    sources=[]
    for name,raw,url in [('annual',fixture(),
        'https://www.tpex.org.tw/www/zh-tw/bulletin/tradingDate?date=2026&response=json'),
        ('rules',b'9:00 13:30 13:33',
        'https://www.tpex.org.tw/zh-tw/mainboard/trading/rules/system.html')]:
        p=tmp_path/(name+'.json');p.write_bytes(raw)
        sources.append(dict(year=2026,local_path=str(p),sha256=sha256(raw).hexdigest(),
            source_reference=url,retrieved_at='2026-02-10T00:00:00Z'))
    return sources


def test_published_plan_is_wired_to_observations_without_claiming_actual_history(tmp_path):
    annual,rules=sources(tmp_path)
    out=C.produce([annual],rules,start_date='2026-02-10',end_date='2026-02-17',
        evaluation_at='2026-02-17T08:00:00Z')
    assert [r['session_id'] for r in out['sessions']]==['2026-02-10','2026-02-11','2026-02-17']
    assert out['sessions'][-1]['close_at']=='2026-02-17T13:33:00+08:00'
    assert out['exchange']=='ROCO' and out['scope']==C.SCOPE
    assert not out['actual_session_coverage_verified']
    assert not out['historical_pit_verified'] and not out['formal_deployment_eligible']
    assert out['source_documents']==[annual]


@pytest.mark.parametrize('issue',['changed_bytes','future','wrong_venue','duplicate','missing_year','wrong_year'])
def test_source_receipts_and_calendar_window_fail_closed(tmp_path,issue):
    annual,rules=sources(tmp_path);items=[annual];start='2026-01-01'
    if issue=='changed_bytes':Path(annual['local_path']).write_bytes(b'{}')
    elif issue=='future':annual['retrieved_at']='2026-02-18T00:00:00Z'
    elif issue=='wrong_venue':annual['source_reference']=annual['source_reference'].replace('www.tpex.org.tw','www.twse.com.tw')
    elif issue=='duplicate':items.append(deepcopy(annual))
    elif issue=='missing_year':start='2025-12-31'
    elif issue=='wrong_year':annual['year']=2025
    with pytest.raises((ValueError,PermissionError)):
        C.produce(items,rules,start_date=start,end_date='2026-02-17',evaluation_at='2026-02-17T08:00:00Z')

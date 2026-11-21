"""Synthetic official-response coverage, with explicitly bounded date scope."""
from copy import deepcopy
from datetime import date,timedelta
from hashlib import sha256
from pathlib import Path
import json
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from tpex_actual_sessions import produce


def case(tmp_path):
    at='2026-11-03T01:00:00Z';sessions=[];day=date(2026,10,1)
    while day<=date(2026,11,5):
        if day.weekday()<5:
            text=day.isoformat();sessions.append(dict(session_id=text,open_at=text+'T09:00:00+08:00',close_at=text+'T13:33:00+08:00'))
        day+=timedelta(days=1)
    plan=dict(start_date='2026-10-01',end_date='2026-11-05',sessions=sessions,
        actual_session_coverage_verified=False,historical_pit_verified=False,formal_deployment_eligible=False)
    sources=[]
    for month,days in [('2026-10',['2026/10/01','2026/10/05','2026/10/30']),('2026-11',['2026/11/02'])]:
        data=dict(stat='ok',tables=[dict(title='櫃買指數(月查詢)',date=month.replace('2026-','115/'),
            fields=['日期','開市','最高','最低','收市','漲/跌'],totalCount=len(days),
            data=[[d,'100','101','99','100','0'] for d in days])])
        path=tmp_path/(month+'.json');path.write_text(json.dumps(data))
        sources.append(dict(month=month,local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),
            retrieved_at=at,source_reference='https://www.tpex.org.tw/www/zh-tw/indexInfo/inx?date='+month.replace('-','/')+'/01'))
    return plan,sources,at


def test_missing_planned_date_does_not_become_a_trade_or_a_closure_decree(tmp_path):
    plan,sources,at=case(tmp_path);before=deepcopy(plan);out=produce(plan,sources,evaluation_at=at)
    assert plan==before
    assert out['actual_session_window']['through']=='2026-11-02' and out['actual_session_window']['verified']
    assert '2026-10-02' in out['planned_dates_absent_from_official_index']
    assert '2026-10-02' not in {r['session_id'] for r in out['sessions']}
    assert '2026-11-03' in {r['session_id'] for r in out['sessions']}  # Still a future completion at cutoff.
    assert out['missing_date_is_not_a_closure_decree']
    assert not out['actual_session_coverage_verified'] and not out['historical_pit_verified'] and not out['formal_deployment_eligible']


@pytest.mark.parametrize('issue',['missing_month','duplicate_month','changed_bytes','incomplete_response','wrong_month','future_source','bad_ohlc'])
def test_monthly_sources_must_be_complete_original_responses(tmp_path,issue):
    plan,sources,at=case(tmp_path)
    if issue=='missing_month':sources.pop()
    elif issue=='duplicate_month':sources.append(deepcopy(sources[0]))
    elif issue=='future_source':sources[0]['retrieved_at']='2026-12-01T00:00:00Z'
    else:
        source=sources[0];path=Path(source['local_path']);data=json.loads(path.read_bytes())
        if issue=='changed_bytes':path.write_text('{}')
        else:
            if issue=='incomplete_response':data['tables'][0]['totalCount']+=1
            elif issue=='wrong_month':data['tables'][0]['date']='114/10'
            else:data['tables'][0]['data'][0][3]='102'
            path.write_text(json.dumps(data));source['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError,PermissionError)):produce(plan,sources,evaluation_at=at)

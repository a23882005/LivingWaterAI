"""Synthetic TWSE-shaped originals: holes and public dates never confer PIT."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from twse_own_history_source import read,PRICE_FIELDS,MARKET_FIELDS
from historical_source_qualification import bind

AT='2026-11-04T04:00:00Z'


def case(tmp_path):
    def save(name,data):
        path=tmp_path/name;path.write_text(json.dumps(data,ensure_ascii=False))
        return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())
    m=dict(schema_version='Family.W8.TwseOwnHistoryIntake.v1',provider='TWSE',symbol='9001',
        currency='TWD',exchange='XTAI',timezone='Asia/Taipei',requested_start='2026-09-01',
        requested_end='2026-10-31',known_by=AT,source_reference='SYNTHETIC_EXCHANGE_ORIGINALS',months=[])
    for month in ('09','10'):
        stamp='2026'+month+'01';page={'month':stamp}
        for kind,fields,endpoint in [('prices',PRICE_FIELDS,'STOCK_DAY'),('market',MARKET_FIELDS,'FMTQIK')]:
            rows=[]
            for day in ('01','02','05'):
                row=([f'115/{month}/{day}','1,000','10,500','10.00','11.00','9.00','10.50','+0.50','30']
                     if kind=='prices' else [f'115/{month}/{day}','1,000','10,500','30','100.00','+1.00'])
                rows.append(row)
            data=dict(stat='OK',date=stamp,title=f'115年{month}月 '+('9001 合成證券 各日成交資訊' if kind=='prices' else '市場成交資訊'),fields=list(fields),data=rows)
            raw=save(kind+stamp+'.json',data)
            url='https://www.twse.com.tw/exchangeReport/'+endpoint+'?response=json&date='+stamp
            if kind=='prices':url+='&stockNo=9001'
            receipt=dict(source_url=url,started_at=AT,retrieved_at=AT,sha256=raw['sha256'],status=200,rows=3)
            page[kind]=dict(status='ACQUIRED',source=raw,receipt_source=save(kind+stamp+'.receipt.json',receipt))
        m['months'].append(page)
    def desc():return save('manifest.json',m)
    return m,desc


def change(source,fn):
    path=Path(source['local_path']);data=json.loads(path.read_text());fn(data)
    path.write_text(json.dumps(data,ensure_ascii=False));source['sha256']=sha256(path.read_bytes()).hexdigest()


def rebind(page):
    change(page['receipt_source'],lambda d:d.update(sha256=page['source']['sha256']))


def test_original_raw_rows_and_independent_market_dates_do_not_become_wealth_or_pit(tmp_path):
    _,desc=case(tmp_path);out=read(desc(),'9001',AT)
    assert out['returned_bar_count']==6 and out['requested_month_pages_complete']
    assert out['raw_observed_bars'][0]['close']=='10.50'
    assert out['raw_observed_bars'][0]['original_values']['成交股數']=='1,000'
    assert len(out['market_transaction_dates'])==6 and out['missing_security_bars']==[]
    assert all(r['available_at'] is None and not r['historical_PIT_verified'] for r in out['raw_observed_bars'])
    assert out['qualified_native_price_history'] is None
    assert not any(out[k] for k in ('qP_history_qualified','qV_history_qualified','completed_calendar_qualified',
        'historical_price_PIT_verified','complete_corporate_action_coverage_verified','adjusted_close_or_split_reconstruction_used'))


def test_market_open_missing_security_row_requires_suspension_or_data_proof(tmp_path):
    m,desc=case(tmp_path);page=m['months'][0]['prices']
    change(page['source'],lambda d:d['data'].pop(1));rebind(page)
    change(page['receipt_source'],lambda d:d.update(rows=2))
    out=read(desc(),'9001',AT)
    assert out['missing_security_bars']==['2026-09-02'] and out['returned_bar_count']==5
    assert any(i['code'].startswith('MARKET_OPEN_WITHOUT_SECURITY_BAR') for i in out['issues'])


@pytest.mark.parametrize('kind',['prices','market'])
def test_missing_month_is_unknown_never_an_empty_successful_page(tmp_path,kind):
    m,desc=case(tmp_path);m['months'][0][kind]=dict(status='NOT_ACQUIRED')
    out=read(desc(),'9001',AT)
    assert not out['requested_month_pages_complete'] and len(out['unavailable_month_sources'])==1
    assert out['monthly_coverage'][0]['month']=='20261001'
    assert out['missing_security_bars']==[]  # unknown coverage is not proof of a security suspension


def test_failed_original_request_receipt_retains_the_exact_scope(tmp_path):
    m,desc=case(tmp_path);source=m['months'][0]['prices']['source']
    change(source,lambda d:(d.clear(),d.update(symbol='9001',month='20260901',status='SOURCE_UNAVAILABLE',errors=['SYNTHETIC_DENIAL'])))
    m['months'][0]['prices']=dict(status='UNAVAILABLE',failure_source=source)
    assert read(desc(),'9001',AT)['unavailable_month_sources'][0]['status']=='UNAVAILABLE'
    change(source,lambda d:d.update(symbol='OTHER'))
    with pytest.raises(PermissionError,match='FAILURE_RECEIPT_SCOPE'):read(desc(),'9001',AT)


@pytest.mark.parametrize('mutate',[
    lambda m:m.update(symbol='OTHER'),lambda m:m.update(currency='USD'),lambda m:m.update(exchange='OTHER'),
    lambda m:m.update(timezone='UTC'),lambda m:m.update(provider='YAHOO'),
    lambda m:m.update(known_by='2026-11-05T00:00:00Z'),lambda m:m.update(requested_end='2026-11-05'),
    lambda m:m['months'].pop(),lambda m:m['months'].reverse(),lambda m:m['months'].append(deepcopy(m['months'][0]))])
def test_identity_date_and_complete_requested_month_inventory_required(tmp_path,mutate):
    m,desc=case(tmp_path);mutate(m)
    with pytest.raises((PermissionError,ValueError)):read(desc(),'9001',AT)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(source_url=d['source_url'].replace('9001','9002')),
    lambda d:d.update(source_url=d['source_url']+'&stockNo=9002'),
    lambda d:d.update(source_url=d['source_url'].replace('www.twse.com.tw','example.com')),
    lambda d:d.update(final_url='https://example.com/redirect'),
    lambda d:d.update(status=True),lambda d:d.update(status=307),lambda d:d.update(sha256='a'*64),
    lambda d:d.update(rows=2),lambda d:d.update(started_at='2026-11-05T00:00:00Z'),
    lambda d:d.update(retrieved_at='2026-11-05T00:00:00Z')])
def test_exact_public_query_response_digest_and_capture_clock_required(tmp_path,mutate):
    m,desc=case(tmp_path);change(m['months'][0]['prices']['receipt_source'],mutate)
    with pytest.raises((PermissionError,ValueError)):read(desc(),'9001',AT)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(stat='NOT OK'),lambda d:d.update(date='20260801'),
    lambda d:d.update(title='115年09月 9002 其他證券 各日成交資訊'),
    lambda d:d['data'][0].__setitem__(0,'115/08/31'),
    lambda d:d['data'][0].__setitem__(0,'2026-09-01'),
    lambda d:d['data'][0].__setitem__(1,'1,00'),
    lambda d:d['data'][0].__setitem__(6,'99'),
    lambda d:d['data'][0].__setitem__(6,'NaN'),
    lambda d:d['data'][0].pop(),lambda d:d['data'].__setitem__(1,deepcopy(d['data'][0])),
    lambda d:d['fields'].__setitem__(3,'日期')])
def test_malformed_originals_are_rejected_without_price_or_date_repairs(tmp_path,mutate):
    m,desc=case(tmp_path);page=m['months'][0]['prices'];change(page['source'],mutate);rebind(page)
    with pytest.raises((PermissionError,ValueError)):read(desc(),'9001',AT)


def test_changed_original_cannot_be_hidden_by_saved_manifest(tmp_path):
    m,desc=case(tmp_path);source=desc();Path(m['months'][0]['prices']['source']['local_path']).write_text('{}')
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):read(source,'9001',AT)


def test_partial_month_excludes_capture_day_and_preserves_boundary_rows(tmp_path):
    m,desc=case(tmp_path);m.update(requested_end='2026-10-02',known_by='2026-10-02T04:00:00Z')
    for page in m['months']:
        for kind in ('prices','market'):
            change(page[kind]['receipt_source'],lambda d:d.update(started_at=m['known_by'],retrieved_at=m['known_by']))
    out=read(desc(),'9001',AT)
    assert out['raw_observed_bars'][-1]['session_id']=='2026-10-01'
    assert any(r['reason']=='CURRENT_OR_FUTURE_CAPTURE_DATE_NOT_FINAL_ATTESTED' for r in out['excluded_rows'])
    assert any(r['reason']=='OUTSIDE_REQUESTED_DATE_RANGE' for r in out['excluded_rows'])


def test_public_history_binding_keeps_member_scope_without_formal_promotion(tmp_path):
    _,desc=case(tmp_path);request=dict(client_id='SYNTHETIC_CLIENT',run_id='SYNTHETIC_RUN',evaluation_at=AT,
        client_snapshot={'payload':{'source_sha256':'a'*64}})
    out=bind({'twse_own_history':desc()},request,'9001')
    assert out['sources']['twse_own_history']['returned_bar_count']==6
    assert out['run_id']==request['run_id'] and out['source_db_sha256']=='a'*64
    assert out['qualified_qP_history'] is out['qualified_qV_history'] is None
    assert not out['financial_qualification_released']

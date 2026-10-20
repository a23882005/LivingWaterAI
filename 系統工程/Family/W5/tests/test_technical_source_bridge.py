from copy import deepcopy
from datetime import datetime,timedelta,timezone
import gzip
import hashlib
import json
import pytest
from family_input import digest
from technical_source_bridge import build_partial_technical,read_history,NAMES,VERSION,_originals
from test_native_adapters import ROOT


def case(n=65):
    # Explicit synthetic session calendar; no claim of real exchange dates.
    rows=[];receipts=[];start=datetime(2026,1,1,20,tzinfo=timezone.utc)
    for i in range(n):
        t=start+timedelta(days=i);v=100+i*.3+(i%6)*.2
        rows.append({'Date':t.date().isoformat(),'Close':v,'High':v+2,'Low':v-2,'Volume':1000+i})
        receipts.append({'session':rows[-1]['Date'],'completed':True,'formal_close_available':True,
                         'close_at':t.isoformat(),'available_at':(t+timedelta(minutes=1)).isoformat()})
    meta={'history_digest':digest(rows),'asset_id':'SYNTH','symbol':'SYNTH','exchange':'SYNTHETIC',
        'currency':'USD','instrument_reference':'SYNTHETIC_INSTRUMENT','source_reference':'SYNTHETIC_HISTORY',
        'receipt_reference':'SYNTHETIC_RECEIPT','calendar_reference':'SYNTHETIC_CALENDAR',
        'session_timezone':'UTC','provider_price_basis':'SYNTHETIC_NO_ACTIONS',
        'source_run':'OLD_SYNTHETIC_RUN','producer_version':VERSION,'timeframe':'DAILY',
        'price_field':'Close','auto_adjust':False,'split_basis_verified':True,
        'calendar_sessions':[r['Date'] for r in rows],'bar_receipts':receipts,
        'fetch_completed_at':'2026-04-01T00:00:00+00:00','artifact_written_at':'2026-04-01T00:01:00+00:00','data_provenance':'SYNTHETIC'}
    return rows,meta


def run(rows,meta):return build_partial_technical(rows,metadata=meta,evaluated_at='2026-04-02T00:00:00+00:00',repo_path=ROOT)


def test_original_functions_numeric_and_partial_vectors_are_immutable():
    rows,m=case();before=deepcopy((rows,m));out=run(rows,m)
    assert (rows,m)==before and out['status']=='PARTIAL_KNOWN'
    assert out['td9']['high_count']==9 and len(out['td9']['events'])==1
    assert {k:len(v) for k,v in out['signals'].items()}=={'right_signals':10,'up_price':3,'up_confirm':8,'down_break':3,'down_accel':8}
    assert out['ma20_ok']=='UNKNOWN' and out['native_technical_aggregation']['runaway_up']=='UNKNOWN'
    assert out['execution_advice_allowed'] is False and not out['formal_producer_complete']
    assert out['raw_numeric']['current']['emv_14'] is not None
    for group,name in [('right_signals','emv_positive'),('right_signals','kd_golden_cross'),('up_confirm','emv_positive_or_improving'),('down_accel','atr_expanding_fast')]:
        assert next(x for x in out['signals'][group] if x['name']==name)['truth']=='UNKNOWN'
    json.dumps(out,allow_nan=False)


@pytest.mark.parametrize('field',['High','Low','Volume'])
def test_missing_other_fields_does_not_erase_valid_td9(field):
    r,m=case();r[20][field]=None;m['history_digest']=digest(r)
    out=run(r,m);assert out['td9']['high_count']==9
    assert out['raw_numeric']=={}


@pytest.mark.parametrize('change',['split','calendar','receipt','future','timezone','version','weekly','adjclose','generated_only'])
def test_metadata_gaps_are_unknown_not_default_true(change):
    r,m=case()
    if change=='split':m['split_basis_verified']=False
    elif change=='calendar':m['calendar_sessions'].pop(3)
    elif change=='receipt':m.pop('bar_receipts')
    elif change=='future':m['bar_receipts'][-1]['available_at']='2027-01-01T00:00:00+00:00'
    elif change=='timezone':m['bar_receipts'][0]['close_at']='2026-01-01T20:00:00'
    elif change=='version':m['producer_version']='latest'
    elif change=='weekly':m['timeframe']='WEEKLY'
    elif change=='adjclose':m['price_field']='Adj Close'
    else:m.pop('fetch_completed_at');m['generated_at_utc']='2026-01-01T00:00:00Z'
    out=run(r,m);assert out['status']=='DATA_UNAVAILABLE'
    assert out['td9']['state']=='UNKNOWN' and out['ma20_ok']=='UNKNOWN'
    assert all(x['truth']=='UNKNOWN' for v in out['signals'].values() for x in v)


def test_td9_minimum_and_equal_reset_and_unknown_close():
    r,m=case(12);assert run(r,m)['td9']['state']=='UNKNOWN'
    r,m=case();r[-1]['Close']=r[-5]['Close'];m['history_digest']=digest(r)
    out=run(r,m);assert out['td9']['state']=='INACTIVE'
    r[20]['Close']=None;m['history_digest']=digest(r)
    assert run(r,m)['td9']['state']=='UNKNOWN'


def test_swing_uses_second_right_bar_availability_and_strict_ties():
    r,m=case(13)
    for row in r:row['Low']=90;row['High']=120
    r[3]['Low']=80;r[8]['Low']=85;r[6]['High']=130
    m['history_digest']=digest(r);out=run(r,m)
    low=out['swings']['lows'][0]
    assert low['pivot_session']==r[3]['Date'] and low['confirmed_at']==m['bar_receipts'][5]['available_at']
    assert next(x for x in out['signals']['right_signals'] if x['name']=='higher_low')['truth']=='TRUE'
    m['bar_receipts'][9]['completed']=False
    for rec in m['bar_receipts'][10:]:rec['completed']=False
    out=run(r,m);assert [x['index'] for x in out['swings']['lows']]==[3]
    r[2]['Low']=80;m['history_digest']=digest(r)
    assert run(r,m)['swings']['lows']==[]


def test_full_csv_digest_and_no_summary_or_row_reordering(tmp_path):
    p=tmp_path/'history.csv.gz';raw=gzip.compress(b'Date,Close\n2026-01-01,100\n');p.write_bytes(raw)
    assert read_history(p,hashlib.sha256(raw).hexdigest())[0]['Close']=='100'
    with pytest.raises(ValueError,match='HISTORY_HASH'):read_history(p,'0'*64)
    r,m=case();r.reverse();m['history_digest']=digest(r)
    with pytest.raises(ValueError,match='SESSION_ORDER'):run(r,m)


def test_no_duplicate_vote_alias_and_raw_original_td9_equivalence():
    r,m=case();out=run(r,m)
    for group,names in NAMES.items():assert [x['name'] for x in out['signals'][group]]==names and len(set(names))==len(names)
    legacy,numeric=_originals()
    import pandas as pd
    c=pd.Series([r['Close'] for r in r]);old=legacy['calculate_td9'](c.tolist())
    assert numeric.td9(c)==(old.high_count,old.low_count)

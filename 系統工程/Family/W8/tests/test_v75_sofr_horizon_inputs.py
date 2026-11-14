"""Contract-specific SOFR fallback; no OIS spread or tenor substitution."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_sofr_horizon_inputs as S


def fixture(tmp_path):
    def response(value):return {'isError':False,'structuredContent':value}
    dates=['2026-10-21','2026-10-22','2026-10-23','2026-10-26','2026-10-27','2026-10-28']
    prices=['95.50','95.51','95.52','95.53','95.54','95.55']
    packet={'root_search':{'tool_name':'search_contracts','arguments':{'query':'SOFR'},
        'requested_at':'2026-10-29 05:50:00 UTC','result':response({'results':[
            {'symbol':'SOFR1','exchange':'CME','country_code':'US','description':'1-month Average of Rates',
                'underlying_contract_id':1001,'sections':[{'security_type':'FUT'}]},
            {'symbol':'SOFR','exchange':'ARCA','description':'SYNTHETIC ETF','sections':[{'security_type':'STK'}]}]})},
        'ladder':{'tool_name':'search_futures','arguments':{'underlying_contract_id':1001},
            'requested_at':'2026-10-29 05:51:00 UTC','result':response({'contracts':[
                {'contract_id':1002,'exchange':'CME','contract_month':'202704','last_trading_date':'20270430'}]})},
        'history':{'tool_name':'get_price_history','requested_at':'2026-10-29T05:52:00Z',
            'available_at':'2026-10-29T06:00:00Z','arguments':{'contract_id':1002,'exchange':'CME','outside_rth':False,
                'period':'THREE_MONTHS','step':'ONE_DAY','security_type':'FUT','include_corporate_actions':False},
            'response':response({'chart_step':86400,'chart_start':'2026-10-21T00:00:00Z',
                'chart_end':'2026-10-29T00:00:00Z','source':'Last','time':[d+'T13:30:00Z' for d in dates],
                'close':prices,'open':prices,'high':prices,'low':prices,'volume':[100]*6})}}
    path=tmp_path/'synthetic-sofr-packet.json';path.write_text(json.dumps(packet));guide=tmp_path/'synthetic-cme.html'
    guide.write_text('<h1>One-Month SOFR</h1><p>The final settlement price is 100 contract price points minus '
        'the arithmetic average of daily SOFR values.</p>')
    receipt=tmp_path/'synthetic-cme.receipt.json';h=sha256(guide.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({'url':S.CME_GUIDE,'http_status':200,'sha256':h,
        'requested_at':'2026-10-29T06:01:00Z','available_at':'2026-10-29T06:02:00Z'}))
    return {'schema_version':'Family.W8.SOFROneMonthSource.v1','local_path':str(path),
        'sha256':sha256(path.read_bytes()).hexdigest(),'available_at':'2026-10-29T06:00:00Z',
        'cme_quote_source':{'local_path':str(guide),'sha256':h,'receipt_path':str(receipt),
            'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}},packet


def pool():
    return {'formal_parameters':{'parameter_version':'SYNTHETIC_FOR_UNIT_TEST_ONLY'},
        'qualified_shared_predicate_inputs':{'PRED-002':{'meeting_roll_dates':['2026-10-28'],'checks':[{'state':'FRESH'}]}},
        'calculations':{'PRED-002':{'observed_date':'2026-10-28','comparison_date':'2026-10-21'}},
        'shared_metrics':{'PRED-002':{'expected_policy_rate_6m_delta_5bd_bps':'-10'},
            'PRED-007':{'srf_usage_usd':'0'}},'unprovided_inputs':{'PRED-002':['fallback required'],
                'PRED-007':['sofr_ois_bps','fra_ois_bps']},'source_proofs':{},'available_at':'2026-10-29T01:00:00Z'}


def test_same_six_month_contract_delta_and_meeting_roll_fallback_keep_p007_unresolved(tmp_path):
    source,_=fixture(tmp_path);value=S.read(source,'2026-10-29T07:00:00Z')
    assert value['metrics']=={'expected_policy_rate_6m_delta_5bd_bps':'-5.00'}
    assert value['calculation']['contract_month']=='202704'
    out=S.extend(pool(),source,'2026-10-29T07:00:00Z')
    assert out['qualified_shared_predicate_inputs']['PRED-002']['input_freshness_verified']
    assert out['shared_metrics']['PRED-007']=={'srf_usage_usd':'0'}
    assert out['unprovided_inputs']['PRED-007']==['sofr_ois_bps','fra_ois_bps']
    assert out['unprovided_inputs']['PRED-002']==[]


def test_mismatched_root_expiry_changed_bytes_and_future_availability_fail_closed(tmp_path):
    source,packet=fixture(tmp_path)
    with pytest.raises(PermissionError,match='TIME_ORDER'):S.read(source,'2026-10-29T05:00:00Z')
    path=Path(source['local_path']);path.write_text('{}')
    with pytest.raises(PermissionError,match='SOURCE_BYTES'):S.read(source,'2026-10-29T07:00:00Z')
    source,packet=fixture(tmp_path);packet['ladder']['result']['structuredContent']['contracts'][0]['contract_month']='202705'
    path.write_text(json.dumps(packet));source['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError,match='SIX_MONTH_EXPIRY'):S.read(source,'2026-10-29T07:00:00Z')
    source,packet=fixture(tmp_path);packet['root_search']['result']['structuredContent']['results'][0]['sections']=[{'security_type':'STK'}]
    path.write_text(json.dumps(packet));source['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError,match='ROOT_IDENTITY'):S.read(source,'2026-10-29T07:00:00Z')


def test_source_conflict_and_misaligned_windows_never_promote_default_no_repricing(tmp_path):
    source,_=fixture(tmp_path);out=pool();out['shared_metrics']['PRED-002']['expected_policy_rate_6m_delta_5bd_bps']='50'
    out=S.extend(out,source,'2026-10-29T07:00:00Z')
    assert not out['qualified_shared_predicate_inputs']['PRED-002']['input_freshness_verified']
    assert out['auxiliary_policy_rate_observations']['source_conflict_unresolved']
    assert out['shared_metrics']['PRED-002']['expected_policy_rate_6m_delta_5bd_bps']=='50'
    out=pool();out['calculations']['PRED-002']['comparison_date']='2026-10-20'
    out=S.extend(out,source,'2026-10-29T07:00:00Z')
    assert not out['qualified_shared_predicate_inputs']['PRED-002']['input_freshness_verified']

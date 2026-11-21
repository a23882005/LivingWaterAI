"""Independent plugin evidence never replaces qualified primary financial inputs."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv
import io
import json
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5')]
import v75_plugin_data_inputs as P
from mentor_bridge import plugin_evidence_notes

AT = '2026-10-29T19:30:00Z'


def csv_bytes(rows):
    out = io.StringIO(); w = csv.DictWriter(out, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return out.getvalue().encode()


def response(data, args=None):
    text = data['result'] if set(data) == {'result'} else json.dumps(data)
    out = {'isError': False, 'content': [{'type': 'text', 'text': text}], 'structuredContent': data}
    return json.dumps({'args': args, 'result': out} if args else out).encode()


def weekly(symbol='SGOV'):
    dates = ['2026-09-21', '2026-09-28', '2026-09-29', '2026-10-05', '2026-10-26', '2026-10-29']
    raw = {'chart_step': 604800, 'source': 'Last', 'time': [d+'T00:00:00Z' for d in dates],
        'chart_end': '2026-10-30T19:00:00Z', 'open': [100]*6, 'high': [101]*6,
        'low': [99]*6, 'close': [100,100,100,102,100,100], 'volume': [1000]*6,
        'corp_actions': [{'type': 'CashDividends', 'date': '20261001', 'payment_date': '20261006',
            'value': '.3', 'currency': 'USD'}]}
    args = {'contract_id': 123, 'security_type': 'STK', 'outside_rth': False, 'period': 'FIVE_YEARS',
        'step': 'ONE_WEEK', 'include_corporate_actions': True}
    rows = [{'time': t, **{k: raw[k][i] for k in ('open','high','low','close','volume')}} for i,t in enumerate(raw['time'])]
    contracts = {'results': [{'symbol': symbol, 'country_code': 'US', 'exchange': 'NYSE',
        'underlying_contract_id': 123, 'sections': [{'security_type': 'STK'}]}]}
    return {f'ibkr/{symbol}_5y_weekly_raw.json': response(raw, args),
        f'ibkr/{symbol}_5y_weekly.csv': csv_bytes(rows), f'ibkr/{symbol}_contracts.json': response(contracts),
        'ibkr/qa.json': json.dumps({symbol+'_5y_weekly.csv': {'rows': 6, 'first': raw['time'][0],
            'last': raw['time'][-1], 'latest_week_incomplete': True}}).encode()}


def daily(symbol='SGOV'):
    dates = ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29']
    rows = [{'v':'1000.5','vw':'100.7','o':'100.7','c':'100.7','h':'100.8','l':'100.6',
        't': str(int(datetime.fromisoformat(d+'T04:00:00+00:00').timestamp()*1000)), 'n':'100'} for d in dates]
    extracted = [{**r,'date_et':d} for r,d in zip(rows,dates)]
    text = csv_bytes(rows).decode()
    data = {f'massive/{symbol}_daily_raw.json': response({'result':text}),
        f'massive/{symbol}_daily.csv': csv_bytes(extracted),
        'massive/qa.json': json.dumps({symbol:{'count':4,'first':dates[0],'last':dates[-1],
            'request_adjusted':True,'source':f'Massive /v2/aggs/ticker/{symbol}/range/1/day/{dates[0]}/{dates[-1]}'}}).encode()}
    primary = {'chart':{'result':[{'timestamp':[int(int(r['t'])/1000) for r in rows],
        'indicators':{'quote':[{'close':[100.69999694824219]*4}]}}]}}
    return data,json.dumps(primary).encode()


def dividends(symbol='SGOV'):
    raw = {'symbol':symbol,'data':[
        {'ex_dividend_date':'2026-10-01','payment_date':'2026-10-06','amount':'.300547'},
        {'ex_dividend_date':'2026-03-02','payment_date':'None','amount':'.2724'}]}
    rows = [{'symbol':symbol,'ex_date':r['ex_dividend_date'],'pay_date':'' if r['payment_date']=='None' else r['payment_date'],
        'amount':r['amount'],'ROC':'null'} for r in raw['data']]
    return {f'alpha/{symbol}_dividends_raw.json':response(raw), f'alpha/{symbol}_dividends.csv':csv_bytes(rows),
        'alpha/provenance_qa.json':json.dumps({'symbols':{symbol:{'rows':2,'payment_dates_missing':1,'ROC_nonnull':0}}}).encode()}


def test_weekly_quarantines_forming_duplicate_and_invalid_bars_without_rewriting():
    files = weekly(); before = deepcopy(files); out = P.ibkr_history(files,'SGOV',AT)
    assert files == before and out['raw_bar_count']==6 and out['usable_unique_completed_weeks']==1
    assert out['last_observed_provider_timestamp']=='2026-10-29T00:00:00Z'
    assert not out['chart_end_used_as_observed_date'] and out['provider_chart_end'].startswith('2026-10-30')
    assert len(out['invalid_ohlcv_bars'])==1 and out['invalid_ohlcv_bars'][0]['close']=='102'
    assert len(out['multiple_bars_per_iso_week'])==2
    assert {r['reason'] for r in out['excluded_bars']}=={'LATEST_SOURCE_WEEK_INCOMPLETE','MULTIPLE_PROVIDER_BARS_IN_HISTORICAL_WEEK','INVALID_OHLCV'}
    assert not out['provider_midnight_labels_shifted_to_previous_ET_date']
    assert not out['daily_MA_or_YTM_derived_from_weekly_prices']


def test_weekly_csv_or_contract_change_is_not_treated_as_a_price_difference():
    files=weekly();files['ibkr/SGOV_5y_weekly.csv']=files['ibkr/SGOV_5y_weekly.csv'].replace(b'1000',b'1001',1)
    with pytest.raises(PermissionError,match='CSV_MISMATCH'):P.ibkr_history(files,'SGOV',AT)
    files=weekly();_,c=P.tool_response(files['ibkr/SGOV_contracts.json']);c['results'][0]['symbol']='SGOVX'
    files['ibkr/SGOV_contracts.json']=response(c)
    with pytest.raises(PermissionError,match='IDENTITY_OR_REQUEST'):P.ibkr_history(files,'SGOV',AT)


def test_daily_uses_completed_sessions_and_reports_numeric_precision_without_promoting_source():
    files,primary=daily();out=P.daily_history(files,'SGOV',primary,AT)
    assert out['raw_bar_count']==4 and len(out['completed_daily_bars'])==3
    assert out['forming_sessions_excluded']==['2026-10-29']
    assert out['overlap_count']==out['four_decimal_close_matches']==3 and out['exact_close_matches']==0
    assert number(out['max_abs_close_difference'])>0
    assert not out['canonical_market_source_replaced'] and not out['used_as_NBBO'] and not out['total_return_attested']
    assert not out['volume_basis_qualified_for_canonical_liquidity']


def test_daily_date_tampering_and_future_data_are_rejected():
    files,primary=daily();files['massive/SGOV_daily.csv']=files['massive/SGOV_daily.csv'].replace(b'2026-10-26',b'2026-10-25',1)
    with pytest.raises(PermissionError,match='CSV_MISMATCH'):P.daily_history(files,'SGOV',primary,AT)
    files,primary=daily()
    with pytest.raises(PermissionError,match='DATE_ORDER_OR_FUTURE'):P.daily_history(files,'SGOV',primary,'2026-10-28T19:30:00Z')


def test_alpha_missing_payment_and_roc_remain_unknown_and_small_difference_stays_explicit():
    files=dividends();out=P.alpha_dividends(files,'SGOV',AT)
    files['alpha/SGOV_dividends.csv']=files['alpha/SGOV_dividends.csv'].replace(b'2026-03-02,,',b'2026-03-02,null,')
    assert P.alpha_dividends(files,'SGOV',AT)==out
    assert out['rows'][1]['pay_date'] is None and all(r['roc'] is None for r in out['rows'])
    issuer=[{'ex_date':'2026-10-01','pay_date':'2026-10-06','amount':'.300547'},
        {'ex_date':'2026-03-02','pay_date':'2026-03-05','amount':'.27239'}]
    check=P.compare_dividends(out['rows'],issuer)
    amount=next(r for r in check['differences'] if r['field']=='amount')
    assert Decimal(amount['difference'])==Decimal('.00001') and check['issuer_primary_preserved']
    assert any(r['field']=='payment_date' and r['provider'] is None for r in check['differences'])
    assert not check['missing_payment_date_or_ROC_filled_from_other_provider']


def test_alpha_unknown_roc_cannot_be_replaced_with_zero_or_duplicate_date():
    files=dividends();files['alpha/SGOV_dividends.csv']=files['alpha/SGOV_dividends.csv'].replace(b'null',b'0',1)
    with pytest.raises(PermissionError,match='CSV_MISMATCH'):P.alpha_dividends(files,'SGOV',AT)
    with pytest.raises(PermissionError,match='DUPLICATE_DIVIDEND_EX_DATE'):
        P.compare_dividends([{'ex_date':'2026-10-01'}]*2,[])
    events=[{'ex_date':'2021-12-17','amount':'.02','pay_date':'2021-12-23'},
        {'ex_date':'2021-12-17','amount':'.04','pay_date':'2021-12-23'}]
    check=P.compare_dividends(events,[{'ex_date':'2021-12-17','amount':'.06','pay_date':'2021-12-23'}],allow_ambiguous=True)
    assert len(check['ambiguous_provider_events']['2021-12-17'])==2
    assert check['provider_total_for_same_ex_dates'] is None and check['records_compared']==0


def test_raw_text_and_structured_tool_result_must_agree():
    raw=json.loads(response({'symbol':'SGOV'}));raw['content'][0]['text']=json.dumps({'symbol':'SPSB'})
    with pytest.raises(PermissionError,match='RAW_STRUCTURED_MISMATCH'):P.tool_response(json.dumps(raw).encode())


def test_manifest_bound_integration_keeps_primary_metrics_and_issuer_composition(tmp_path):
    files={};data={}
    for symbol in ('SGOV','SPSB'):
        daily_files,primary=daily(symbol);parts=[weekly(symbol),daily_files,dividends(symbol)]
        for part in parts:
            for key,value in part.items():
                if key in files and key.endswith(('qa.json','provenance_qa.json')):
                    old=json.loads(files[key]);new=json.loads(value)
                    if 'symbols' in old:old['symbols'].update(new['symbols'])
                    else:old.update(new)
                    files[key]=json.dumps(old).encode()
                else:files[key]=value
        data['YAHOO_'+symbol]=primary
    files['alpha/SPSB_profile_raw.json']=response({'dividend_yield':'.051','last_updated':'2026-10-23 00:01 UTC'})
    manifest=[]
    for name,raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        manifest.append({'path':name,'bytes':len(raw),'sha256':sha256(raw).hexdigest()})
    raw=json.dumps(manifest).encode();(tmp_path/'manifest.json').write_bytes(raw)
    source={'schema_version':'Family.W8.V75PluginDataSource.v1','root':str(tmp_path),'ingested_at':AT,
        'manifest_sha256':sha256(raw).hexdigest(),'source_reference':'SYNTHETIC_PLUGIN_HANDOFF'}
    pool={'additional_delta_handoff':{},'ready_data_handoff':{'spsb_distribution_and_qii':{'dividends':{'rows':[
        {'EX-DATE':'10/01/2026','PAYABLE DATE':'10/06/2026','DIVIDEND ($)':'.300547'}]}}},
        'issuer_observations':{'SGOV':{'facts':{'distribution_source_observation':{'rows':[
            {'ex_date':'2026-10-01','pay_date':'2026-10-06','total':'.300547','roc':'0'}]}}}},
        'shared_metrics':{'UNCHANGED':'1'},'asset_metrics':{'UNCHANGED':'2'},'available_at':'2026-10-28T23:00:00Z'}
    pool['additional_delta_handoff']={'prior_evidence':'BOUND'};before=deepcopy(pool)
    result=P.extend(pool,source,data,AT)
    assert {k:result[k] for k in before}==before
    receipt=result['plugin_data_cross_checks'];assert not receipt['primary_financial_inputs_changed']
    assert not receipt['qualified_weekly_YTM_or_SEC_history_supplied'] and not receipt['NBBO_quotes_acquired']
    assert receipt['SPSB_profile_auxiliary']['yield_kind']=='DISTRIBUTION_YIELD_RATIO__NOT_PORTFOLIO_YTM_OR_SEC_YIELD'
    assert 'IB最新週尚未完成' in ''.join(plugin_evidence_notes(receipt,'SGOV'))
    assert P.summary(receipt,'SGOV')['IBKR_invalid_ohlcv_count']==1


def number(value):
    return Decimal(value)

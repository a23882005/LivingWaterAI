"""Raw evidence, session coverage and distinct yield dates survive QA ingestion."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent/'W5')]
import v75_ib_qa_inputs as Q
import v75_plugin_data_inputs as P
from mentor_bridge import plugin_evidence_notes, ready_data_evidence_notes
from test_v75_plugin_data_inputs import csv_bytes, response, daily

AT = '2026-10-29T21:00:00Z'


def yield_case():
    files = {}; manifest = []; extracted = []
    for i, audience in enumerate(('individual','intermediary')):
        raw = ('<h2>Fund Characteristics as of Mar 23 2023</h2><table><tr><td>Yield to Maturity</td><td>5.14%</td></tr></table>'
            '<h2>Yields as of Mar 23 2023</h2><table><tr><td>30 Day SEC Yield</td><td>5.26%</td></tr></table>').encode()
        path = f'arquivo_replay_{i}.raw'; capture = f'2023032617075{i}'
        url = 'https://ssga.com/us/en/'+audience+'/etfs/funds/spdr-portfolio-short-term-corporate-bond-etf-spsb'
        proof = {'path':path,'capture_timestamp':capture,'original_url':url,'status':200,
            'url':'https://arquivo.pt/noFrame/replay/'+capture+'id_/'+url,'sha256':sha256(raw).hexdigest()}
        files['yield/'+path] = raw; manifest.append(proof)
        for metric, value in [('portfolio_ytm','5.14'),('sec_yield_30day','5.26')]:
            extracted.append({'ticker':'SPSB','metric':metric,'as_of':'2023-03-23','value_percent':value,
                'raw_file':path,'capture_timestamp':capture,'original_url':url,'archive_replay_url':proof['url']})
    unique = []
    for metric in ('portfolio_ytm','sec_yield_30day'):
        group = [r for r in extracted if r['metric']==metric]
        unique.append({k:v for k,v in group[0].items() if k in ('ticker','metric','as_of','value_percent')})
        unique[-1]['sources'] = [{k:r[k] for k in ('raw_file','capture_timestamp','original_url','archive_replay_url')} for r in group]
    files['yield/arquivo_replay_manifest.json'] = json.dumps(manifest).encode()
    files['yield/arquivo_extracted_source_rows.json'] = json.dumps(extracted).encode()
    files['yield/NEW_ARQUIVO_OBSERVATIONS.json'] = json.dumps(unique).encode()
    files['yield/DELTA_MANIFEST.json'] = json.dumps({'prior_unique_metric_observations':2,
        'new_unique_metric_observations':2,'qualified_weekly_series':False,'files':[]}).encode()
    old = {'observations':[{'metric':m,'as_of':'2020-01-02','value_percent':'1','sources':[]}
        for m in ('portfolio_ytm','sec_yield_30day')], 'distinct_observations':2,'raw_source_rows':2,
        'counts_by_metric':{'portfolio_ytm':1,'sec_yield_30day':1},'missing_weeks_filled':False,'percentile_calculated':False}
    source = {'root':'/synthetic/qa','manifest_sha256':'0'*64,'ingested_at':AT}
    return files, old, source


def ib_case():
    files = {}; prior = {'ibkr_weekly':{}}; report = {}; saved_daily = {}
    for symbol, contract in [('SGOV',123),('SPSB',456)]:
        dates = ['2023-03-20']+(['2023-03-24'] if symbol=='SPSB' else [])+['2026-10-26','2026-10-29']
        raw = {'time':[d+'T00:00:00Z' for d in dates], 'open':[100]*len(dates),'high':[101]*len(dates),
            'low':[99]*len(dates),'close':[100]*len(dates),'volume':[100]*len(dates),
            'chart_step':604800,'source':'Last','chart_end':'2026-10-30T20:00:00Z','corp_actions':[]}
        raw['volume'][0] = 500 if symbol=='SGOV' else 400
        if symbol=='SGOV':raw['close'][0]=102
        args = {'contract_id':contract,'security_type':'STK','outside_rth':False,'period':'FIVE_YEARS',
            'step':'ONE_WEEK','include_corporate_actions':True}
        contracts = {'results':[{'symbol':symbol,'country_code':'US','exchange':'NYSE',
            'underlying_contract_id':contract,'sections':[{'security_type':'STK'}]}]}
        part = {f'ibkr/{symbol}_5y_weekly_raw.json':response(raw,args),
            f'ibkr/{symbol}_contracts.json':response(contracts),
            'ibkr/qa.json':json.dumps({symbol+'_5y_weekly.csv':{'rows':len(dates),'first':raw['time'][0],
                'last':raw['time'][-1],'latest_week_incomplete':True}}).encode()}
        old = [dict(zip(Q.FIELDS, row)) for row in zip(*(raw[f] for f in Q.FIELDS))]
        part[f'ibkr/{symbol}_5y_weekly.csv'] = csv_bytes(old)
        prior['ibkr_weekly'][symbol] = P.ibkr_history(part,symbol,AT)
        for key, value in part.items():
            key = key.replace('ibkr/','original_ibkr/')
            if key=='original_ibkr/qa.json' and key in files:
                qa=json.loads(files[key]);qa.update(json.loads(value));value=json.dumps(qa).encode()
            files[key]=value
        files[f'ibkr/{symbol}_ONE_WEEK_refetch.json']=response(raw,args)
        dd=deepcopy(raw);days=['2023-03-'+str(d) for d in range(20,25)]+['2026-10-29']
        dd.update(time=[d+'T13:30:00Z' for d in days],chart_step=86400)
        for f in Q.FIELDS[1:]:dd[f]=[100 if f in ('open','close','volume') else 101 if f=='high' else 99]*6
        if symbol=='SGOV':dd['close'][4]=102
        files[f'ibkr/{symbol}_ONE_DAY_refetch.json']=response(dd,{**args,'step':'ONE_DAY'})
        daily_rows=[dict(zip(Q.FIELDS,row)) for row in zip(*(dd[f] for f in Q.FIELDS))]
        window=daily_rows[:5];files[f'ibkr/{symbol}_affected_daily_windows.csv']=csv_bytes(window)
        saved_daily[symbol]=daily_rows
        report[symbol]={'raw_text_matches_structured':True,'csv_matches_raw':True,
            'original_weekly_validation':Q.audit(old,weekly=True),'refetch_weekly_validation':Q.audit(old,weekly=True),
            'refetch_weekly_row_differences':[],'daily_validation':Q.audit(daily_rows),
            'affected_week_daily_evidence':[{'iso_week':[2023,12],'provider_weekly':[r for r in old if r['time'].startswith('2023')],
                'daily_bars':window,'daily_derived_ohlcv':{'open':100,'high':101,'low':99,
                    'close':102 if symbol=='SGOV' else 100,'volume':500}}]}
    files['ibkr/validation_report.json']=json.dumps(report).encode()
    files['SPSB_20230320_reconstructed.json']=json.dumps({'symbol':'SPSB','week_start':'2023-03-20','week_end':'2023-03-24',
        'open':100,'high':101,'low':99,'close':100,'volume':500,'status':'DERIVED_RECONSTRUCTION'}).encode()
    return files, prior, saved_daily


def massive_case():
    files={};prior={'massive_daily':{}};data={};coverage={}
    for symbol in ('SGOV','SPSB'):
        part, primary=daily(symbol);data['YAHOO_'+symbol]=primary
        prior['massive_daily'][symbol]=P.daily_history(part,symbol,primary,AT)
        for key in (f'massive/{symbol}_daily_raw.json',f'massive/{symbol}_daily.csv'):
            files[key.replace('_daily_raw','_5y_daily_raw').replace('_daily.csv','_actual_daily.csv')]=part[key]
        coverage[symbol]={'rows':4,'actual_first':'2026-10-26','actual_last':'2026-10-29','requested_start':'2021-10-29','bad_ohlc':0}
    files['massive/coverage_qa.json']=json.dumps(coverage).encode()
    files['massive/SGOV_two_week_crosscheck.json']=b'[]'
    return files,prior,data


def test_arquivo_two_pages_are_two_observations_with_real_asof_and_idempotent_metric_counts():
    files,old,source=yield_case();before=deepcopy(old)
    result=Q.arquivo_yields(files,old,source,AT)
    assert old==before and result['distinct_observations']==4
    assert result['counts_by_metric']=={'portfolio_ytm':2,'sec_yield_30day':2}
    added=[r for r in result['observations'] if r['as_of']=='2023-03-23']
    assert len(added)==2 and all(len(r['sources'])==2 for r in added)
    repeated=Q.arquivo_yields(files,result,source,AT)
    assert repeated['distinct_observations']==4 and repeated['delta_summary']['new_unique_metric_observations']==0
    assert repeated['raw_source_rows']==result['raw_source_rows']==6
    assert all(len(r['sources'])==2 for r in repeated['observations'] if r['as_of']=='2023-03-23')
    assert not result['weekly_history_available'] and not result['engine_input_eligible']
    assert not result['capture_date_used_as_asof'] and not result['missing_weeks_filled']


def test_arquivo_capture_date_asof_and_conflicting_same_metric_date_are_rejected():
    files,old,source=yield_case();rows=json.loads(files['yield/arquivo_extracted_source_rows.json'])
    rows[0]['as_of']='2023-03-26';files['yield/arquivo_extracted_source_rows.json']=json.dumps(rows).encode()
    with pytest.raises(PermissionError,match='EXTRACTION_MISMATCH'):Q.arquivo_yields(files,old,source,AT)
    files,old,source=yield_case();old['observations'][0].update(as_of='2023-03-23',value_percent='5.15')
    with pytest.raises(PermissionError,match='SAME_DATE_VALUE_CONFLICT'):Q.arquivo_yields(files,old,source,AT)


def test_ib_audit_replays_raw_and_csv_instead_of_trusting_the_delivered_report():
    files,prior,daily_rows=ib_case();before=deepcopy(files)
    result,actual_daily=Q.ibkr_audit(files,prior,AT)
    assert files==before and actual_daily==daily_rows
    assert len(result['SGOV']['invalid_weekly_bars_reproduced'])==1
    assert len(result['SGOV']['invalid_daily_bars'])==1
    assert result['SGOV']['invalid_daily_bars'][0]['close']==102
    report=json.loads(files['ibkr/validation_report.json']);report['SGOV']['daily_validation']['invalid_ohlc']=[]
    files['ibkr/validation_report.json']=json.dumps(report).encode()
    with pytest.raises(PermissionError,match='VALIDATION_REPORT_MISMATCH'):Q.ibkr_audit(files,prior,AT)


def test_ib_original_hash_and_refetch_contract_or_text_are_bound():
    files,prior,_=ib_case();prior['ibkr_weekly']['SGOV']['source_raw_sha256']='0'*64
    with pytest.raises(PermissionError,match='ORIGINAL_SOURCE_MISMATCH'):Q.ibkr_audit(files,prior,AT)
    files,prior,_=ib_case();raw=json.loads(files['ibkr/SGOV_ONE_DAY_refetch.json']);raw['args']['outside_rth']=True
    with pytest.raises(PermissionError,match='REQUEST_OR_IDENTITY'):Q.series(json.dumps(raw).encode(),123,'ONE_DAY',AT)
    raw['result']['content'][0]['text']='{}'
    with pytest.raises(PermissionError,match='RAW_STRUCTURED_MISMATCH'):Q.series(json.dumps(raw).encode(),123,'ONE_DAY',AT)


def test_derived_week_requires_every_real_session_valid_bounds_and_exact_recalculation():
    files,_,daily_rows=ib_case();before=deepcopy(daily_rows)
    result=Q.derived_week(files,daily_rows['SPSB'])
    assert daily_rows==before and result['volume']=='500' and result['all_expected_sessions_present']
    assert not result['provider_corrected_weekly'] and not result['original_weekly_bars_replaced']
    with pytest.raises(PermissionError,match='INCOMPLETE_OR_INVALID'):Q.derived_week(files,daily_rows['SPSB'][1:])
    bad=deepcopy(daily_rows['SPSB']);bad[0]['close']=102
    with pytest.raises(PermissionError,match='INCOMPLETE_OR_INVALID'):Q.derived_week(files,bad)
    claim=json.loads(files['SPSB_20230320_reconstructed.json']);claim['volume']=501
    files['SPSB_20230320_reconstructed.json']=json.dumps(claim).encode()
    with pytest.raises(PermissionError,match='VALUES_MISMATCH'):Q.derived_week(files,daily_rows['SPSB'])


def test_massive_extension_reconciles_prior_bars_without_claiming_five_years_or_total_return():
    files,prior,data=massive_case();result=Q.massive_extension(files,prior,data,AT)
    assert result['SGOV']['previous_daily_bars_reconciled']==4
    assert not result['SGOV']['actual_is_full_requested_five_years']
    assert not result['SGOV']['total_return_attested'] and not result['SGOV']['canonical_liquidity_qualified']
    prior['massive_daily']['SGOV']['completed_daily_bars'][0]['c']='100.71'
    with pytest.raises(PermissionError,match='PRIOR_OVERLAP_MISMATCH'):Q.massive_extension(files,prior,data,AT)


def test_manifest_integration_preserves_issuer_and_prior_sources_and_updates_sparse_audit_only(tmp_path):
    files,prior,_=ib_case();massive,other,data=massive_case();yields,old,_=yield_case()
    files.update(massive);files.update(yields);prior.update(other)
    prior['alpha_dividends']={s:{'row_count':2} for s in ('SGOV','SPSB')}
    prior['issuer_dividend_comparisons']={s:{'alpha':{'differences':[]},'ibkr':{'ambiguous_provider_events':{}}} for s in ('SGOV','SPSB')}
    rows=[]
    for name,raw in files.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        rows.append({'path':name,'bytes':len(raw),'sha256':sha256(raw).hexdigest()})
    raw=json.dumps(rows).encode();(tmp_path/'manifest.json').write_bytes(raw)
    source={'schema_version':'Family.W8.V75IBQAAdditionalSource.v1','root':str(tmp_path),
        'manifest_sha256':sha256(raw).hexdigest(),'ingested_at':AT,'source_reference':'SYNTHETIC_QA'}
    pool={'plugin_data_cross_checks':prior,'additional_delta_handoff':{'sparse_yield_evidence':old},
        'canonical_yield_observations':{'SPSB':{'sparse_audit_evidence':old}},'available_at':'2026-10-28T00:00:00Z',
        'issuer_observations':{'SGOV':{'ROC':'0','tax_final':False},'SPSB':{'ROC':None}},
        'shared_metrics':{'unchanged':1},'asset_metrics':{'unchanged':2},'source_proofs':{'primary':'unchanged'}}
    before=deepcopy(pool);out=Q.extend(pool,source,data,AT);receipt=out['ib_qa_handoff']
    for key in before:
        if key!='canonical_yield_observations':assert out[key]==before[key]
    assert out['canonical_yield_observations']['SPSB']['sparse_audit_evidence']['distinct_observations']==4
    assert out['additional_delta_handoff']['sparse_yield_evidence']['distinct_observations']==2
    assert not receipt['primary_financial_inputs_changed'] and not receipt['issuer_composition_overwritten']
    assert not receipt['NBBO_quotes_acquired'] and receipt['trade_action']=='NO_TRADE'
    assert Q.summary(receipt,'SPSB')['derived_week']['status']=='DERIVED_RECONSTRUCTION'
    notes=''.join(plugin_evidence_notes(prior,'SPSB',receipt))
    assert '不是IB官方修正版' in notes and '並非五年完整序列' in notes
    assert '2筆組合YTM' in ''.join(ready_data_evidence_notes({'retained':True},'SPSB',ib_qa=receipt))
    (tmp_path/'ibkr/SGOV_ONE_DAY_refetch.json').write_bytes(b'{}')
    with pytest.raises(PermissionError,match='SOURCE_HASH'):Q.extend(before,source,data,AT)

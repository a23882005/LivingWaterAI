"""New authorized rule with SYNTHETIC source transports and real native engines.

No fixture is an assertion of historical official quotes or household holdings.
K8's published 2026–2030 dates are fixed external calendar expectations.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import product
from pathlib import Path
import csv,io,json,sys
import pytest
import v75_pred007_policy as P
import v75_pred007_source as S
from family_input import digest
from bond_engine import V75_PATH,run_bond_engine
from test_native_adapters import ROOT,request
from test_bond_engine import evidence

sys.path.insert(0,str(ROOT/V75_PATH))
AT='2026-10-29T10:00:00+00:00'
RULES=Path(S.__file__).parent/'policies/V75_PRED007_20261029_01.v1.0.json'
K8_ROWS=[
 ["New Year's Day",'January 1','January 1','January 1*','January 1','January 1'],
 ['Birthday of Martin Luther King, Jr.','January 19','January 18','January 17','January 15','January 21'],
 ["Washington's Birthday",'February 16','February 15','February 21','February 19','February 18'],
 ['Memorial Day','May 25','May 31','May 29','May 28','May 27'],
 ['Juneteenth National Independence Day','June 19','June 19*','June 19','June 19','June 19'],
 ['Independence Day','July 4*','July 4**','July 4','July 4','July 4'],
 ['Labor Day','September 7','September 6','September 4','September 3','September 2'],
 ['Columbus Day','October 12','October 11','October 9','October 8','October 14'],
 ['Veterans Day','November 11','November 11','November 11*','November 11**','November 11'],
 ['Thanksgiving Day','November 26','November 25','November 23','November 22','November 28'],
 ['Christmas Day','December 25','December 25*','December 25','December 25','December 25']]


def raw_source(folder,key,raw):
    path=folder/(key+'.raw');path.write_bytes(raw)
    url='https://www.federalreserve.gov/aboutthefed/k8.htm' if key=='FED_K8' else (
        'https://fred.stlouisfed.org/graph/fredgraph.csv?id='+key+'&cosd=2021-07-29&coed=2026-10-29')
    rec={'url':url,'http_status':200,'sha256':sha256(raw).hexdigest(),
        'requested_at':'2026-10-29T09:06:00Z','retrieved_at':'2026-10-29T09:07:00Z',
        'data_provenance':'SYNTHETIC','scope':'ENGINEERING_TEST_NOT_REAL_QUOTES'}
    rp=folder/(key+'.receipt.json');rp.write_text(json.dumps(rec))
    return {'local_path':str(path),'sha256':rec['sha256'],'receipt_path':str(rp),
        'receipt_sha256':sha256(rp.read_bytes()).hexdigest()}


def fixture(folder):
    table=[['','2026','2027','2028','2029','2030'],*K8_ROWS]
    html='K.8 2026-2030. Federal Reserve Banks and Branches will be open the preceding Friday. For holidays falling on Sunday.'
    html+='<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in r)+'</tr>' for r in table)+'</table>'
    source={'schema_version':'Family.W5.Pred007AmendmentSource.v1','data_provenance':'SYNTHETIC',
        'ruleset':{'local_path':str(RULES),'sha256':P.RULESET_SHA256,'ingested_at':'2026-10-29T09:05:00Z'},
        'calendar':raw_source(folder,'FED_K8',html.encode()),'series':{}}
    for key,last,value in [('SOFR','2026-10-27','3.95'),('IORB','2026-10-29','3.90'),
            ('DCPF3M','2026-10-26','4.12'),('DTB3','2026-10-28','4.05')]:
        day=date(2023,10,23);rows=[]
        while day<=date.fromisoformat(last):
            if day.weekday()<5:rows.append([str(day),value])
            day+=timedelta(days=1)
        text=io.StringIO();writer=csv.writer(text);writer.writerow(['observation_date',key]);writer.writerows(rows)
        source['series'][key]={**raw_source(folder,key,text.getvalue().encode()),'unit':'PERCENT',
            **({'basis':'DISCOUNT_360'} if key in ('DCPF3M','DTB3') else {})}
    legacy={'S':{'value':'6000000','units':'USD','observation_date':'2026-10-28',
        'retrieved_at':'2026-10-29T09:07:00Z','source_ids':['SYNTHETIC_SRF_SOURCE'],
        'freshness_verified':True},'D':{'value':None,'reason':'NOT_ACQUIRED'}}
    return source,legacy


def rewrite(source,key,change):
    item=source['series'][key];path=Path(item['local_path']);path.write_bytes(change(path.read_bytes()))
    item['sha256']=sha256(path.read_bytes()).hexdigest();rp=Path(item['receipt_path']);rec=json.loads(rp.read_text())
    rec['sha256']=item['sha256'];rp.write_text(json.dumps(rec));item['receipt_sha256']=sha256(rp.read_bytes()).hexdigest()


def test_all_256_states_and_quality_precedence_are_exact():
    for states in product((None,'NORMAL','ABNORMAL','SEVERE'),repeat=4):
        signals={k:{'state':v,'reason':'MISSING' if v is None else None} for k,v in zip(P.FIELDS,states)}
        n=sum(v is not None for v in states);a=states.count('ABNORMAL')+states.count('SEVERE');v=states.count('SEVERE')
        expected='SEVERE_ABNORMAL' if v>=2 else 'ABNORMAL' if a>=2 else None if n<3 else 'MIXED' if a==1 else 'NORMAL'
        out=P.aggregate(signals)
        assert out['aggregate_state']==expected and out['sub_states']==([expected] if expected else [])
        assert (out['N'],out['A'],out['V'])==(n,a,v) and out['single_severe_warning']==(v==1)
        assert P.aggregate(signals,['REVIEW_REQUIRED','INVALID_INPUT'])['assessment_status']=='INVALID_INPUT'


def test_precise_units_quantiles_floors_and_ties():
    assert P.spread('4.12','4.05')==Decimal('7')
    assert P.spread('4.05000000000000000000000000000001','4.05')==Decimal('0.000000000000000000000000000001')
    assert P.nearest_rank(range(1,101),'.95')==95 and P.nearest_rank([1,2,3],'.99')==3
    with pytest.raises(P.InvalidInput):P.spread(None,'bad')
    with pytest.raises(P.InvalidInput):P.exact(4.12)
    rules=json.loads(RULES.read_text());t=date(2026,10,29);rows=[(date(2023,11,1)+timedelta(days=i*3),'100') for i in range(252)]
    out=P.calibrated('C',rows,t,rules);assert (out['A'],out['S'])==('100','101')


@pytest.mark.parametrize('n,span,valid',[(252,730,True),(251,730,False),(252,729,False)])
def test_minimum_history_boundaries_exclude_today_and_deduplicate(n,span,valid):
    start=date(2023,11,1);t=date(2026,10,29);rules=json.loads(RULES.read_text())
    rows=[(start+timedelta(days=i),'0') for i in range(n-1)]+[(start+timedelta(days=span),'0')]
    out=P.calibrated('R',rows+[rows[0],(t,'99999')],t,rules)
    assert out['history_n']==n and (out['A'] is not None)==valid
    assert P.start_date(date(2024,2,29))==date(2021,2,28)


def test_official_k8_bank_dates_and_sunday_observance_are_not_board_calendar(tmp_path):
    source,_=fixture(tmp_path);raw=Path(source['calendar']['local_path']).read_bytes()
    assert S.calendar(raw)['published_holiday_dates_validated']==55
    assert S.is_fed_business(date(2026,7,3)) and not S.is_fed_business(date(2027,7,5))
    assert S.age(date(2026,7,2),date(2026,7,3))==1
    assert S.age(date(2027,7,2),date(2027,7,5))==0
    with pytest.raises(P.ReviewRequired):S.calendar(raw.replace(b'January 19',b'January 20'))


def test_partial_normal_uses_three_signals_and_preserves_recent_cp_pair(tmp_path):
    source,legacy=fixture(tmp_path);before=deepcopy((source,legacy));model,out=S.evaluate({'amendment_source':source,'legacy_candidates':legacy},AT)
    assert out['assessment_status']=='VALID' and out['aggregate_state']=='NORMAL' and out['coverage_count']=='3/4'
    assert set(out['warnings'])=={'PARTIAL_COVERAGE','HELD_RECENT_CP_PAIR'}
    assert out['signals']['C']['age_business_days']==3 and out['signals']['C']['value']=='7.00'
    assert out['signals']['D']['abnormal'] is None and out['signals']['D']['value'] is None
    assert out['normalized_fields']['sofr_iorb_spread_bps']=='5.00'
    assert out['normalized_fields']['aa_financial_cp90d_tbill3m_discount_spread_bps']=='7.00'
    assert 'sofr_ois_bps' not in out['normalized_fields']
    assert model.predicate_version==P.BASE_VERSION and P.RULESET_SHA256 in model.source_lineage[0]
    assert out['amendment_id']==P.AMENDMENT_ID and (source,legacy)==before
    shifted=S.assess(source,'2026-10-29T14:00:00+04:00',legacy)
    assert shifted['eval_at_utc']==AT and shifted['eval_date_ny']=='2026-10-29'


def test_two_missing_signals_do_not_become_normal_or_hide_one_severe_warning(tmp_path):
    source,legacy=fixture(tmp_path);source['series'].pop('DCPF3M');legacy['S']['value']='20000000000'
    _,out=S.evaluate({'amendment_source':source,'legacy_candidates':legacy},AT)
    assert out['assessment_status']=='INSUFFICIENT_DATA' and out['aggregate_state'] is None
    assert out['coverage_count']=='2/4' and out['single_severe_warning']
    assert out['signals']['S']['state']=='SEVERE'


def test_missing_leg_cannot_hide_malformed_other_leg_or_bad_missing_candidate_unit(tmp_path):
    source,legacy=fixture(tmp_path);source['series'].pop('SOFR');source['series']['IORB']['unit']='bps'
    legacy['D']['units']='fraction_0_1'
    out=S.assess(source,AT,legacy)
    assert out['assessment_status']=='INVALID_INPUT'
    assert out['signals']['R']['reason']=='RATE_UNIT_OR_DISCOUNT_BASIS:IORB'
    assert out['signals']['C']['available'] and out['signals']['S']['available']


def test_invalid_unit_wins_conflict_and_keeps_available_severe_signal(tmp_path):
    source,legacy=fixture(tmp_path);source['series']['SOFR']['unit']='bps'
    rewrite(source,'DCPF3M',lambda raw:raw+b'2026-10-26,9.99\r\n');legacy['S']['value']='20000000000'
    _,out=S.evaluate({'amendment_source':source,'legacy_candidates':legacy},AT)
    assert out['assessment_status']=='INVALID_INPUT' and out['sub_states']==[]
    assert set(out['quality_vetoes'])=={'INVALID_INPUT','REVIEW_REQUIRED'}
    assert out['single_severe_warning'] and out['signals']['S']['value']=='20000000000'


def test_rules_version_conflict_veto_does_not_hide_severe_diagnostics(tmp_path):
    source,legacy=fixture(tmp_path);source['ruleset']['sha256']='0'*64;legacy['S']['value']='20000000000'
    out=S.assess(source,AT,legacy)
    assert out['assessment_status']=='REVIEW_REQUIRED' and out['aggregate_state'] is None
    assert out['single_severe_warning']


def test_global_version_review_cannot_mask_invalid_rate_units(tmp_path):
    source,legacy=fixture(tmp_path);source['ruleset']['sha256']='0'*64;source['series']['SOFR']['unit']='bps'
    out=S.assess(source,AT,legacy)
    assert out['assessment_status']=='INVALID_INPUT'
    assert set(out['quality_vetoes'])=={'INVALID_INPUT','REVIEW_REQUIRED'}


def test_conflict_in_one_leg_cannot_mask_invalid_numeric_in_other_leg(tmp_path):
    source,legacy=fixture(tmp_path)
    rewrite(source,'SOFR',lambda raw:raw+b'2026-10-27,9.99\r\n')
    rewrite(source,'IORB',lambda raw:raw.replace(b'3.90',b'bad',1))
    out=S.assess(source,AT,legacy)
    assert out['assessment_status']=='INVALID_INPUT' and out['signals']['C']['available']


def test_query_boundary_is_required_even_if_physical_file_has_old_dates(tmp_path):
    source,legacy=fixture(tmp_path);item=source['series']['DCPF3M'];rp=Path(item['receipt_path']);r=json.loads(rp.read_text())
    r['url']=r['url'].replace('2021-07-29','2023-10-29');rp.write_text(json.dumps(r));item['receipt_sha256']=sha256(rp.read_bytes()).hexdigest()
    out=S.assess(source,AT,legacy)
    assert out['signals']['C']['reason']=='SOURCE_REQUEST_WINDOW_NOT_COVERED'
    assert out['assessment_status']=='INSUFFICIENT_DATA' and out['N']==2


def test_new_values_never_use_retired_names_or_apply_to_twd(tmp_path):
    source,legacy=fixture(tmp_path);metrics={'amendment_source':source,'legacy_candidates':legacy}
    with pytest.raises(P.InvalidInput,match='NO_RETIRED_ALIASES'):S.evaluate({**metrics,'sofr_ois_bps':'5'},AT)
    with pytest.raises(P.InvalidInput,match='USD_ONLY'):S.evaluate(metrics,AT,'TWD')


def test_amended_predicate_reaches_original_step10_and_ready_snapshot(tmp_path):
    source,legacy=fixture(tmp_path);facts=evidence();req=request(5)
    req['work3_handoff']['temporal']['as_of']=AT
    shared=req['work3_handoff']['shared_decision_context'];shared['as_of']=AT
    for binding in req['work3_handoff']['engine_bindings'].values():binding['shared_context_digest_sha256']=digest(shared)
    # The fixture is explicitly synthetic; every observed date remains in its
    # own evidence record. No household target or real historical price changes.
    for row in facts.values():
        row['as_of']=row['available_at']=AT
        row['metrics']['PRED-007']={'amendment_source':source,'legacy_candidates':legacy}
    out=run_bond_engine(ROOT,req,facts)
    assert out['status']=='COMPLETE' and out['runtime_ready']['runtime_ready']
    assert set(out['predicate_amendments'])=={'SGOV','SPSB'}
    for name in ('SGOV','SPSB'):
        assert out['predicate_amendments'][name]['coverage_count']=='3/4'
        result=next(p for p in out['predicate_results'][name] if p['predicate_id']=='PRED-007')
        assert result['aggregate_state']=='NORMAL' and P.RULESET_SHA256 in result['source_lineage'][0]
        assert 'V75.evaluate_step10:'+name in out['call_trace']


def full_case(folder):
    from test_family_end_to_end import full_family_case
    from test_stock_source_bridge import refresh
    from family_boundary import prepare_input
    from c7_engine import run_c7_engine
    req,ctx=full_family_case();source,legacy=fixture(folder);req['evaluation_at']=AT
    ctx['v75_pred007_source']=source;ctx['v75_pred007_legacy_candidates']=legacy
    req['v75_pred007_source_digest']=digest({'source':source,'legacy_candidates':legacy})
    req['expected_versions']['v75_pred007']=ctx['expected_versions']['v75_pred007']=P.EFFECTIVE_VERSION
    b=req['native_bundle'];b['stock_evidence']['evaluated_at']=AT
    for branch in ('stock_request','bond_request'):
        w=b[branch]['work3_handoff'];w['temporal']['as_of']=AT;w['shared_decision_context']['as_of']=AT
        w['versions']['rule']['v75_pred007']=P.EFFECTIVE_VERSION
        for binding in w['engine_bindings'].values():binding['shared_context_digest_sha256']=digest(w['shared_decision_context'])
    for row in b['bond_evidence'].values():
        row['as_of']=row['available_at']=AT
        row['metrics']['PRED-007']={'amendment_source':deepcopy(source),'legacy_candidates':deepcopy(legacy)}
    ctx['c7_source']['evaluated_at']=AT;b['asset_framework']=run_c7_engine(ROOT,ctx['c7_source'])['result']
    req['c7_source_digest']=digest(ctx['c7_source']);refresh(req,ctx)
    ctx['native_binding']['target_binding_digest']=prepare_input(req,trusted_context=ctx).payload['target_binding']['binding_digest']
    return req,ctx


def test_full_family_work6_c7_work9_mentor_and_replay_keep_amendment_identity(tmp_path):
    from family_runner import FamilyRunner
    req,ctx=full_case(tmp_path);before=deepcopy((req,ctx));runner=FamilyRunner(ROOT,context_provider=lambda:ctx)
    first=runner.analyze(req);assert first['status']=='OK',first
    assert first['native_result']['status']=='NATIVE_PIPELINE_COMPLETE'
    assert first['native_result']['family_sources']['c7']['result']['status']=='READY_FOR_PM_GATE'
    assert first['native_result']['funding_aggregate']['bond_used']=='160.00'
    assert first['mentor']['liquidity_amendment']['assessment']['ruleset_sha256']==P.RULESET_SHA256
    assert '3/4' in first['mentor']['liquidity_amendment']['explanation']
    second=runner.analyze(req);assert second['status']=='OK' and second['replay_status']=='REPLAYED'
    assert (req,ctx)==before and first['trade_action']=='NO_TRADE'


@pytest.mark.parametrize('change',['rule_version','source_digest','old_metrics','synthetic_relabel'])
def test_amended_full_family_rejects_old_or_mixed_inputs_before_dispatch(tmp_path,change,monkeypatch):
    from family_runner import FamilyRunner
    from test_stock_source_bridge import refresh
    req,ctx=full_case(tmp_path);old=digest(req)
    if change=='rule_version':req['expected_versions']['v75_pred007']=ctx['expected_versions']['v75_pred007']=P.BASE_VERSION
    elif change=='source_digest':req['v75_pred007_source_digest']='0'*64
    elif change=='old_metrics':req['native_bundle']['bond_evidence']['SGOV']['metrics']['PRED-007']={'sofr_ois_bps':'0'}
    else:ctx['native_binding']['data_provenance']='SOURCE_BACKED'
    refresh(req,ctx);calls=[];monkeypatch.setattr('family_runner.run_native_pipeline',lambda *a:calls.append(1))
    out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['status']!='OK' and calls==[] and out['mentor'] is None
    if change!='synthetic_relabel':assert old!=digest(req)


def test_completed_legacy_cache_cannot_be_replayed_under_amended_rule_identity(tmp_path):
    from test_family_end_to_end import full_family_case
    from family_runner import FamilyRunner
    old_request,old_context=full_family_case();current={'context':old_context}
    runner=FamilyRunner(ROOT,context_provider=lambda:current['context'])
    assert runner.analyze(old_request)['status']=='OK'
    new_request,new_context=full_case(tmp_path);current['context']=new_context
    assert digest(old_request)!=digest(new_request)
    result=runner.analyze(new_request)
    assert result['status']=='BLOCKED' and result['issue_codes'][0]['code']=='IDEMPOTENCY_CONFLICT'
    assert result['mentor'] is None and next(iter(runner.store._entries.values()))['publication_count']==1


def test_incomplete_family_keeps_observable_amendment_diagnostics(tmp_path):
    from family_runner import FamilyRunner
    from test_stock_source_bridge import refresh
    req,ctx=full_case(tmp_path);source=ctx['v75_pred007_source'];source['series']['SOFR']['unit']='bps'
    req['v75_pred007_source_digest']=digest({'source':source,'legacy_candidates':ctx['v75_pred007_legacy_candidates']})
    for row in req['native_bundle']['bond_evidence'].values():row['metrics']['PRED-007']['amendment_source']=deepcopy(source)
    refresh(req,ctx);out=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert out['status']=='DATA_UNAVAILABLE' and out['mentor'] is None
    assessment=out['issue_codes'][0]['pred007_amendment']
    assert assessment['assessment_status']=='INVALID_INPUT' and assessment['aggregate_state'] is None
    assert assessment['signals']['C']['available'] and assessment['signals']['S']['available']


def test_current_usd_legacy_configuration_cannot_dispatch_after_effective_time(monkeypatch):
    from test_family_end_to_end import full_family_case
    from test_stock_source_bridge import refresh
    from family_runner import FamilyRunner
    req,ctx=full_family_case();req['evaluation_at']=AT;refresh(req,ctx);calls=[]
    monkeypatch.setattr('family_runner.run_native_pipeline',lambda *args:calls.append(1))
    result=FamilyRunner(ROOT,context_provider=lambda:ctx).analyze(req)
    assert result['issue_codes'][0]['code']=='PRED007_AMENDMENT_SOURCE_REQUIRED' and calls==[]

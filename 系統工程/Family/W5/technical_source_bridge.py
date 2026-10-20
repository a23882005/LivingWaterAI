"""Partial technical intake under the PM's W5-09 specification.

Caller supplies verified session/instrument/price-basis metadata. No downloader,
calendar inference, narrative strategy, or permission is introduced here.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import ast
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import sys
from typing import Sequence
from family_input import digest

HOME=Path(__file__).resolve().parent
VERSION='cd1e1dbc9fd7e226a0c31efe80def9ffb5f947cb'
NAMES={
 'right_signals':['higher_low','kd_golden_cross','macd_bear_hist_shrinking_or_positive','dif_up','emv_positive','rsi_improving_or_near_50','above_ma20','volume_breakout','pressure_breakout','breakout_retest_success'],
 'up_price':['new_20d_close_high','break_confirmed_swing_high','higher_high_higher_low'],
 'up_confirm':['kd_high_strong_not_breaking','macd_bull_hist_expanding','ma5_gt_ma10_gt_ma20','emv_positive_or_improving','price_volume_healthy','high_td9_then_new_high','rsi_high_no_divergence','eps_guidance_not_worse'],
 'down_break':['keeps_breaking_lows','break_confirmed_swing_low','break_support_no_quick_reclaim'],
 'down_accel':['macd_bear_hist_expanding','kd_low_weak','emv_worsening','rsi_falling','price_down_volume_up','atr_expanding_fast','decline_accelerating','rebounds_weaker']}


def _time(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.utcoffset() is None:raise ValueError('TIMEZONE_REQUIRED')
    return d


def _number(v):
    if isinstance(v,bool):return False
    try:return math.isfinite(float(v))
    except (ValueError,TypeError):return False


def read_history(path,expected_sha256):
    """Read a full immutable CSV/CSV.GZ, retaining the raw-file digest."""
    p=Path(path);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('HISTORY_HASH_MISMATCH')
    text=(gzip.decompress(raw) if p.suffix=='.gz' else raw).decode('utf-8-sig')
    rows=list(csv.DictReader(text.splitlines()))
    if not rows or 'Date' not in rows[0]:raise ValueError('FULL_HISTORY_REQUIRED')
    return rows


def _originals():
    for row in json.loads((HOME/'technical_source_lock.json').read_text())['files']:
        if hashlib.sha256((HOME/row['destination']).read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('TECHNICAL_SOURCE_HASH_MISMATCH:'+row['destination'])
    # Compile only these exact original definitions; no imports/decide/default
    # TechnicalSignals from the legacy strategy enter the runtime.
    source=(HOME/'vendor/technical/v82_engine.py').read_text()
    allowed={'TD9Result','SwingPoint','calculate_td9','confirmed_swing_lows','confirmed_swing_highs'}
    nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in allowed]
    if {n.name for n in nodes}!=allowed:raise ValueError('LEGACY_FUNCTION_SET_MISMATCH')
    scope={'dataclass':dataclass,'Sequence':Sequence,'__name__':__name__}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(HOME/'vendor/technical/v82_engine.py'),'exec'),scope)
    spec=importlib.util.spec_from_file_location('w5_pinned_numeric_analytics',HOME/'vendor/technical/analytics.py')
    numeric=importlib.util.module_from_spec(spec);spec.loader.exec_module(numeric)
    return scope,numeric


def _aggregate(repo_path,vectors):
    from verify_dependencies import verify
    verify(repo_path)
    source=Path(repo_path).resolve()/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'
    sys.path.insert(0,str(source))
    try:
        import livingwater_v82_runtime as native
        from livingwater_v82_runtime.core_rules import evaluate_technical
        from livingwater_v82_runtime.enums import PredicateTruth
    finally:sys.path.remove(str(source))
    if Path(native.__file__).resolve().parent!=source/'livingwater_v82_runtime':raise ValueError('RUNTIME_SOURCE_MISMATCH')
    kwargs={k:[PredicateTruth(x['truth']) for x in vectors[k]] for k in NAMES}
    result=evaluate_technical(**kwargs,ma20_ok=PredicateTruth.UNKNOWN)
    return {k:getattr(result,k).value for k in ('right_confirmation','runaway_up','runaway_down')}


def build_partial_technical(history,*,metadata,evaluated_at,repo_path):
    """Return partial facts and original aggregation, never deployment permission.

    metadata is supplied by the trusted source adapter, not inferred from ticker.
    Its history_digest binds exact parsed rows; calendar_sessions covers all rows.
    Each bar_receipt binds session, close/available times, and formal Close status.
    """
    legacy,numeric=_originals();rows=deepcopy(history);meta=deepcopy(metadata)
    if meta.get('history_digest')!=digest(rows):raise ValueError('HISTORY_DIGEST_MISMATCH')
    now=_time(evaluated_at);dates=[r.get('Date') for r in rows]
    if not dates or any(not isinstance(x,str) for x in dates) or dates!=sorted(set(dates)):
        raise ValueError('HISTORY_SESSION_ORDER')
    issues=[]
    snapshot_mode=meta.get('evaluation_mode')=='SNAPSHOT_AFTER_ACQUISITION'
    snapshot_at=None
    if snapshot_mode:
        approved_times={'global':'2026-10-19T23:20:09Z','taiwan':'2026-10-20T07:14:26Z'}
        snapshot_at=approved_times.get(meta.get('market_region'))
        if meta.get('data_provenance')=='SYNTHETIC':snapshot_at=meta.get('artifact_written_at')
        if snapshot_at is None or _time(snapshot_at)>now:issues.append('SNAPSHOT_NOT_YET_AVAILABLE')
    required=('asset_id','symbol','exchange','currency','instrument_reference','source_reference','receipt_reference','calendar_reference','session_timezone','provider_price_basis','source_run')
    if any(not meta.get(k) for k in required):issues.append('SOURCE_METADATA_REQUIRED')
    if meta.get('producer_version')!=VERSION:issues.append('PRODUCER_VERSION_MISMATCH')
    if meta.get('timeframe')!='DAILY':issues.append('DAILY_SOURCE_REQUIRED')
    if meta.get('price_field')!='Close':issues.append('CLOSE_REQUIRED')
    if meta.get('auto_adjust') is not False or meta.get('split_basis_verified') is not True:
        issues.append('PRICE_BASIS_UNVERIFIED')
    if meta.get('calendar_sessions')!=dates:issues.append('SESSION_CONTINUITY_UNVERIFIED')
    receipts=deepcopy(meta.get('bar_receipts',[]))
    if len(receipts)!=len(rows) or [r.get('session') for r in receipts]!=dates:
        issues.append('BAR_RECEIPTS_REQUIRED');receipts=[]
    count=0;last_close=None;last_available=None;incomplete=False
    for rec in receipts:
        if rec.get('completed') is not True or rec.get('formal_close_available') is not True:
            incomplete=True;continue
        if incomplete:issues.append('NONCONTIGUOUS_COMPLETED_BARS');break
        if snapshot_mode:
            rec['available_at']=snapshot_at
            count+=1
            continue
        try:
            close=_time(rec['close_at']);available=_time(rec['available_at'])
            if close>available or available>now or (last_close is not None and close<=last_close) or (last_available is not None and available<last_available):raise ValueError()
        except (KeyError,TypeError,ValueError):issues.append('BAR_TIME_UNVERIFIED');break
        last_close=close;last_available=available;count+=1
    if meta.get('fetch_completed_at') is None or meta.get('artifact_written_at') is None:
        issues.append('FETCH_COMPLETION_RECEIPT_REQUIRED')
    else:
        try:
            fetched=_time(meta['fetch_completed_at']);written=_time(meta['artifact_written_at'])
            if fetched>written or written>now or (last_available is not None and last_available>fetched):raise ValueError()
        except (ValueError,TypeError):issues.append('FETCH_RECEIPT_TIME_INVALID')
    approved=not issues and count>0
    signals={group:[{'name':name,'truth':'UNKNOWN','reason':'RULE_OR_SOURCE_PENDING',
        'dependencies':['original_source.'+name],'source_digest':digest(rows),'sot_section':'W5-09 §4',
        'event_id':None} for name in names] for group,names in NAMES.items()}
    def put(group,name,value,deps):
        row=next(x for x in signals[group] if x['name']==name)
        row.update(truth='TRUE' if value else 'FALSE',reason='KNOWN_ORIGINAL_RULE',dependencies=deps,event_id=name+':'+dates[count-1])
    pending_reasons={'kd_golden_cross':'KD_SMOOTHING_NOT_APPROVED',
        'emv_positive':'EMV_3_3_SOURCE_AND_EVENT_SEMANTICS_PENDING',
        'emv_positive_or_improving':'EMV_3_3_SOURCE_REQUIRED','emv_worsening':'EMV_3_3_AND_DURATION_PENDING',
        'macd_bear_hist_shrinking_or_positive':'EVENT_VERSUS_STATE_PENDING',
        'above_ma20':'ABOVE_VERSUS_RECLAIM_PENDING','eps_guidance_not_worse':'FUNDAMENTAL_SOURCE_REQUIRED',
        'atr_expanding_fast':'FAST_THRESHOLD_NOT_APPROVED',
        'rsi_high_no_divergence':'COMPARABLE_SWING_PAIR_RULE_PENDING',
        'new_20d_close_high':'WINDOW_AND_TIE_RULE_PENDING'}
    for values in signals.values():
        for item in values:item['reason']=pending_reasons.get(item['name'],'NAMED_RULE_OR_SOURCE_REQUIRED:'+item['name'])
    td={'state':'UNKNOWN','high_count':None,'low_count':None,'events':[],'reason':'SOURCE_OR_SAMPLE_UNAVAILABLE'}
    swings={'lows':[],'highs':[],'state':'UNKNOWN','pending_tail_sessions':dates[max(0,count-2):]}
    raw={};known={};base=rows[:count]
    if approved:
        close_ok=all(_number(r.get('Close')) and float(r['Close'])>0 for r in base)
        if close_ok and count>=13:
            close=[float(r['Close']) for r in base];prev=(None,None)
            for n in range(13,count+1):
                value=legacy['calculate_td9'](close[:n]);pair=(value.high_count,value.low_count)
                for side,i in [('HIGH',0),('LOW',1)]:
                    if pair[i]==9 and prev[i]!=9:
                        td['events'].append({'side':side,'session':dates[n-1],'available_at':receipts[n-1]['available_at']})
                prev=pair
            td.update(high_count=pair[0],low_count=pair[1],state='COMPLETED' if 9 in pair else 'COUNTING' if max(pair)>0 else 'INACTIVE',reason='ORIGINAL_TD9_13_CONTIGUOUS_SESSIONS')
        for key,col,func in [('lows','Low','confirmed_swing_lows'),('highs','High','confirmed_swing_highs')]:
            if count>=5 and all(_number(r.get(col)) and float(r[col])>0 for r in base):
                for p in legacy[func]([float(r[col]) for r in base]):
                    swings[key].append({'asset_id':meta['asset_id'],'index':p.index,'value':p.value,
                        'pivot_session':dates[p.index],'confirmation_session':dates[p.index+2],
                        'confirmed_at':receipts[p.index+2]['available_at'],
                        'source_available_at':receipts[p.index+2]['available_at']})
        swings['state']='PARTIAL_KNOWN'
        lows=swings['lows']
        if len(lows)>=2:put('right_signals','higher_low',lows[-1]['value']>lows[-2]['value'],['confirmed_lows[-2:]'])
        numeric_ok=close_ok and all(_number(r.get(k)) and float(r[k])>0 for r in base for k in ('High','Low')) and all(_number(r.get('Volume')) and float(r['Volume'])>=0 for r in base) and all(float(r['Low'])<=float(r['Close'])<=float(r['High']) for r in base)
        if numeric_ok and count>=2:
            import pandas as pd
            df=pd.DataFrame([{k:float(r[k]) for k in ('Close','High','Low','Volume')} for r in base])
            current=numeric.technical(df);previous=numeric.technical(df.iloc[:-1]);raw={'current':current,'previous':previous}
            def pair(name):return _number(current.get(name)) and _number(previous.get(name))
            if pair('macd_12_26'):put('right_signals','dif_up',current['macd_12_26']>previous['macd_12_26'],['DIF[t]','DIF[p]'])
            if pair('macd_histogram'):
                a,b=previous['macd_histogram'],current['macd_histogram']
                put('up_confirm','macd_bull_hist_expanding',a>0 and b>0 and abs(b)>abs(a),['H[p]','H[t]'])
                put('down_accel','macd_bear_hist_expanding',a<0 and b<0 and abs(b)>abs(a),['H[p]','H[t]'])
                known['macd_cross_positive']=a<=0 and b>0
            if all(_number(current.get(k)) for k in ('ma5','ma10','ma20')):put('up_confirm','ma5_gt_ma10_gt_ma20',current['ma5']>current['ma10']>current['ma20'],['MA5[t]','MA10[t]','MA20[t]'])
            if pair('ma20'):
                known['above_ma20']=float(base[-1]['Close'])>current['ma20']
                known['reclaim_ma20']=float(base[-2]['Close'])<=previous['ma20'] and float(base[-1]['Close'])>current['ma20']
        else:issues.append('PARTIAL_OHLCV_NUMERIC_UNAVAILABLE')
    # Derived values above retain upstream nfloat rounding, never relabel EMV14.
    for group in signals:
        ids=[x['event_id'] for x in signals[group] if x['event_id'] is not None]
        if len(ids)!=len(set(ids)):raise ValueError('DUPLICATE_EVENT_VOTE')
    aggregation=_aggregate(repo_path,signals)
    return {'schema_version':'Family.W5.PartialTechnical.v1','status':'PARTIAL_KNOWN' if approved else 'DATA_UNAVAILABLE',
        'evaluation_mode':meta.get('evaluation_mode','HISTORICAL_RECEIPTS'),'snapshot_available_at':snapshot_at,'historical_pit_verified':False if snapshot_mode else None,
        'source_metadata':meta,'history_digest':digest(rows),'source_history':rows,
        'evaluated_at':evaluated_at,'completed_bar_count':count,'sample_state':'COMPLETE' if approved and all(_number(r.get('Close')) and float(r['Close'])>0 for r in base) else 'UNKNOWN',
        'td9':td,'swings':swings,'raw_numeric':raw,'base_facts':known,'signals':signals,
        'ma20_ok':'UNKNOWN','native_technical_aggregation':aggregation,'issue_codes':issues,
        'formal_producer_complete':False,'execution_advice_allowed':False,'trade_action':'NO_TRADE',
        'data_provenance':meta.get('data_provenance','UNKNOWN')}


if __name__=='__main__':
    import argparse,os
    parser=argparse.ArgumentParser(description='W5-09 partial facts; no deployment permission')
    parser.add_argument('--history',required=True);parser.add_argument('--history-sha256',required=True)
    parser.add_argument('--metadata',required=True);parser.add_argument('--evaluated-at',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    rows=read_history(args.history,args.history_sha256)
    result=build_partial_technical(rows,metadata=json.loads(Path(args.metadata).read_text()),
        evaluated_at=args.evaluated_at,repo_path=os.environ.get('W5_SOURCE_ROOT',str(HOME.parents[2])) )
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

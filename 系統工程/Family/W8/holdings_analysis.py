"""Family holding analysis A, independent of new-money deployment B.

Only existing native numeric/predicate/core routines make investment facts.
This module binds sources, preserves gaps, and explains their actual outputs.
It never publishes native canonical_result, Work9 Mentor, amounts or orders.
"""
from copy import deepcopy
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
import hashlib
import json
import re

from family_input import digest
from family_boundary import prepare_input
from analysis_requirements import audit as audit_requirements
from core_analysis_inputs import issuer_inputs
from formal_mode_analysis import build_formal_conclusion
from v10_source_observations import forward_observations,macro_observations

STATES=('ANALYSIS_COMPLETE','ANALYSIS_PARTIAL','ANALYSIS_BLOCKED')
CATALOG_BLOB='4cd333be719252034b6b9d6e8a787c838db816c4'


def issue(path,reason,impact,*,category=3,source=None,code='ANALYSIS_SOURCE_GAP'):
    return {'code':code,'field_path':path,'unknown_category':category,
        'reason':reason,'impact':impact,'source_id':source,
        'checked_sources':['Official member snapshot and approved project source',
            'W5/technical_source_bridge.py','V82.md v1.21.0 / original V82 Core'],
        'blocks_deployment':True,'trade_authorization':'NONE'}


def scenario_class(root, asset_class):
    path=Path(root)/'系統工程/Family/W6/runtime/W6_17類六情境攻防評等_v1.0.json'
    raw=path.read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=CATALOG_BLOB:
        raise ValueError('OFFICIAL_SCENARIO_CATALOG_CHANGED')
    from native_asset_source import FORMAL_CLASSES
    primary=asset_class['primary_class']
    row=next((r for r in json.loads(raw)['rows']
        if r['id']==f'S{FORMAL_CLASSES.index(primary)+1:02d}'),None) if primary in FORMAL_CLASSES else None
    return {'id':row['id'] if row else 'UNKNOWN','name':row['name'] if row else 'UNKNOWN',
        'formal_v82_class':primary,'source_blob':CATALOG_BLOB,
        'basis':'EXPLICIT_V82_EXAMPLE_TO_EXISTING_SXX__NOT_NATIVE_PRODUCT_IDENTITY',
        'method':'heuristic_policy_not_backtest','horizon':'6–12個月情境比較；非短線交易訊號'}


def vt_valuation_observations(context):
    """Read actual dated issuer multiples already in the approved source.

    These are trailing P/E and P/B, never forward P/E. Missing histories and
    current freshness stay unknown; operational forward-P/E ranges cannot apply.
    """
    proof=context['approved_document_target_source'];path=Path(proof['local_source_path'])
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=proof['source_sha256']:
        raise PermissionError('VALUATION_PROJECT_SOURCE_CHANGED')
    lines=[(i,line) for i,line in enumerate(raw.decode('utf-8-sig').splitlines(),1)
        if re.match(r'\s*-\s*VT[：:]',line) and 'P/E' in line]
    records=[]
    for name,pattern in [('TRAILING_PE',r'(?<!Forward )P/E\s*(?:約)?\s*([0-9]+(?:\.[0-9]+)?)'),
                         ('PB',r'P/B\s*([0-9]+(?:\.[0-9]+)?)')]:
        matches=[(i,line,re.search(pattern,line)) for i,line in lines]
        matches=[(i,line,m) for i,line,m in matches if m]
        values={m.group(1) for _,_,m in matches}
        if len(values)==1:
            records.append({'metric_name':name,'current':next(iter(values)),
                'historical_median':None,'expensiveness_percentile':None,
                'data_quality':'OK','freshness':'UNKNOWN','pit_status':'UNVERIFIABLE',
                'source_reference':proof['source_reference'],'source_sha256':proof['source_sha256'],
                'observed_date_text':'2026/07/31' if any('2026/07/31' in l for _,l,_ in matches) else '7/31 (year not stated in this row)',
                'source_lines':[{'line_number':i,'text':line} for i,line,_ in matches],
                'scope':'DATED_ISSUER_MULTIPLE__NOT_CURRENT_VALUATION_OR_FORWARD_PE'})
    return records


def read_issuer_facts(source,symbol,evaluation_at):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('ISSUER_FACTS_SOURCE_CHANGED')
    facts=json.loads(raw)
    if facts.get('schema_version')!='Family.W8.IssuerFacts.v1' or facts.get('symbol')!=symbol:
        raise ValueError('ISSUER_FACTS_IDENTITY_OR_SCHEMA_MISMATCH')
    when=datetime.fromisoformat(evaluation_at.replace('Z','+00:00'))
    retrieved=datetime.fromisoformat(facts['retrieved_at'].replace('Z','+00:00'))
    if retrieved>when or facts['as_of']>when.date().isoformat():raise ValueError('ISSUER_FACTS_IN_FUTURE')
    return {**facts,'source_sha256':source['sha256']}


def signal_gaps(observed):
    # These reasons are retained from the original reviewed partial bridge;
    # raw numeric alternatives remain visible and are not renamed as votes.
    pending={
        'kd_golden_cross':'V82 §24-A defines the crossing; pinned analytics uses rolling smoothing, whose compatibility with canonical KD(9,3,3) has not been verified',
        'kd_high_strong_not_breaking':'Canonical KD series and high-persistence event producer are not connected',
        'kd_low_weak':'Canonical KD series and weak-persistence event producer are not connected',
        'emv_positive':'Formal EMV(3,3) producer is not implemented in the pinned analytics; available EMV14 is a different series',
        'emv_positive_or_improving':'Formal EMV(3,3) producer is not connected; EMV14 cannot substitute',
        'emv_worsening':'Formal EMV(3,3) and duration producer are not connected',
        'macd_bear_hist_shrinking_or_positive':'Formal MACD inputs are absent for this history window',
        'above_ma20':'At least one completed Close/MA20 pair required for the formal reclaim is absent',
        'rsi_improving_or_near_50':'Exact near-50/duration predicate is not produced; RSI14 values and change are available',
        'atr_expanding_fast':'FAST threshold is not approved; ATR14 itself is calculated',
        'new_20d_close_high':'Original bridge retains window/tie rule pending',
        'rsi_high_no_divergence':'Comparable swing-pair rule remains pending in original bridge'}
    out=[]
    for group,rows in observed['observed_named_signals'].items():
        for row in rows:
            if row['truth']=='UNKNOWN':
                if observed.get('approved_technical'):
                    problem=issue('technical.signals.'+group+'.'+row['name'],
                        row.get('reason','MISSING_REQUIRED_INPUT_OR_REFERENCE')+'; dependencies: '+
                            ', '.join(row.get('dependencies',[])),
                        'Approved rule is implemented; only this source-dependent predicate is unavailable',
                        category=3,source=observed['source_path'])
                    problem['gap_kind']='SOURCE_OR_CONFIRMED_REFERENCE_MISSING'
                    out.append(problem)
                    continue
                reason=pending.get(row['name'],'Required named event evidence is absent: '+row['name'])
                program_missing=row['name'].startswith(('emv_','kd_'))
                problem=issue('technical.signals.'+group+'.'+row['name'],reason,
                    'This predicate cannot vote in native confirmation; other computed facts remain available',
                    category=2 if program_missing else 4 if row['name'] in pending else 3,source=observed['source_path'])
                problem['gap_kind']='PRODUCER_NOT_CONNECTED' if program_missing else 'SOURCE_OR_RULE_DEPENDENCY_UNRESOLVED'
                out.append(problem)
    return out


def explain(row):
    obs=row.get('market') or {};num=obs.get('numeric',{});facts=obs.get('base_facts',{})
    text=(f"{row['symbol']}｜{row['scenario_class']['name']}；本人帳戶持股 {row['holding']['quantity']}。"
        f"來源持倉日期：{row['holding']['observed_at'] or '原件未記錄，未以讀取時間代替'}。")
    if num:
        text+=(f"快取收盤 {obs['observed_close']:.6f}（{obs['observed_date']}）；"
            f"MA20={num.get('ma20')}，MA50={num.get('ma50')}，RSI14={num.get('rsi14')}，"
            f"ATR14={num.get('atr14')}；TD9 高／低={obs['td9']['high_count']}/{obs['td9']['low_count']}。"
            f"原橋接事實：收盤高於MA20={facts.get('above_ma20','UNKNOWN')}，站回MA20={facts.get('reclaim_ma20','UNKNOWN')}。")
        mapping=obs.get('analysis_identity_mapping')
        if mapping:
            text+=f"行情參考市場 {mapping['reference_exchange']}／{mapping['quote_currency']}，持倉原交易所欄位未因此改寫。"
        quality=obs.get('history_quality',{})
        if quality.get('excluded_unverified_session_rows'):
            text+='來源另有同UTC日期資料，尚未核實市場最終收盤，已隔離；本分析只使用上列歷史截止日。'
        if quality.get('invalid_source_rows'):
            if quality['scope'].startswith('CLOSE_ONLY'):
                text+=(f"原檔有 {len(quality['invalid_source_rows'])} 列 OHLC 關係異常；本輪僅將 "
                    f"{quality['used_rows']} 根有效收盤交給原收盤價獨立算法，高低價／成交量相依元件不輸出；原價格未修改。")
            else:
                text+=(f"原檔有 {len(quality['invalid_source_rows'])} 列異常；本輪僅計算 "
                    f"{quality['analysis_start']}～{quality['analysis_end']} 的 {quality['used_rows']} 根連續有效資料，原價格未修改。")
        receipt=obs.get('alternative_source_receipt')
        if receipt:
            text+=f"替代來源僅提供 {obs['rows']} 根已完成資料；不足的長均線不補值。"
            if receipt.get('provider_currency_label_conflict'):
                text+='來源頁同時標示 Currency GBP／Price in USD，依明示美元價格列作分析參考，幣別標籤矛盾仍保留缺項。'
    else:text+='沒有通過本輪讀取檢查的同標的行情，未借用其他標的資料。'
    if row.get('core_observation'):
        state=row['core_observation']['result']
        text+=f"原 V82 確認：{state['technical']}；估值={state['valuation']['level']}（{','.join(state['valuation']['reason_codes'])}）。"
        groups=obs['observed_named_signals']
        for group,label in [('up_price','Runaway Up價格結構'),('right_signals','右側確認'),
                ('down_break','Runaway Down結構破壞'),('down_accel','下跌加速')]:
            signals=groups[group]
            values={truth:[s['name'] for s in signals if s['truth']==truth] for truth in ('TRUE','FALSE','UNKNOWN')}
            text+=f"{label}：成立 {len(values['TRUE'])}、不成立 {len(values['FALSE'])}、不可判定 {len(values['UNKNOWN'])}。"
            if group=='up_price' and len(values['FALSE'])==len(signals):
                text+='三項原生價格結構均不成立，所以Core判定Runaway Up不成立；並非將缺項當False。'
        text+='個股Thesis計分不適用本ETF；Core空Thesis輸出的NONE不代表ETF結構安全已通過。'
    if row.get('issuer_facts'):
        facts=row['issuer_facts'];metrics=facts['metrics']
        text+=(f"官方 {facts['as_of']}：trailing P/E={metrics.get('TRAILING_PE',{}).get('value','UNKNOWN')}，P/B={metrics.get('PB',{}).get('value','UNKNOWN')}，"
            f"ROE={metrics.get('ROE',{}).get('value','UNKNOWN')}%，盈餘成長率={metrics.get('EARNINGS_GROWTH',{}).get('value','UNKNOWN')}%；"
            '未將這些值轉成Forward預估或基本面改善判斷。')
    if row.get('requirements'):
        text+='必要結果尚缺：'+','.join(row['requirements']['required_missing'])+'；選填缺項另列，不混入完成門檻。'
    if row.get('formal_conclusion'):
        conclusion=row['formal_conclusion']
        text+=(f"四模式：Base可進入={conclusion['four_modes']['Base']['entry_eligibility']}，"
            f"Left={conclusion['market_predicates']['left']}、Right={conclusion['market_predicates']['right']}、Trend={conclusion['market_predicates']['runaway_up']}；"
            f"原模式選擇={conclusion['selected_mode']}，正式階段={conclusion['formal_stage']}。"
            '右側／Runaway不成立不等於禁止Base／Left；部署缺口所缺欄位：'+','.join(conclusion['deployment_gap']['missing_fields'])+'。')
    text+=f"尚有 {len(row['issues'])} 項明列缺項。持股分析說明；不是完整部署 Mentor，未計算買賣金額或授權交易。"
    return text


def build_analysis_report(producer,request,context,prepared,holdings,observations,trial):
    from native_asset_source import classification
    by_symbol={row['symbol']:row for row in observations['assets']}
    missing={row.get('symbol'):row for row in observations['missing']}
    positions=prepared.payload['positions']
    if not producer.analyze_all:
        positions=[r for r in positions if r['source_instrument'].get('ticker')==producer.symbol]
    rows=[];trace=['W8.menu04.holdings_analysis','W5.prepare_input','W5.project_official_holdings']
    dated_valuation=vt_valuation_observations(context) if any(r['source_instrument'].get('ticker')=='VT' for r in positions) else []
    for position in positions:
        instrument=position['source_instrument'];symbol=instrument.get('ticker');source=position['source_position']
        cls=classification(symbol,producer.class_source,producer.product_sources.get(symbol))
        observed=deepcopy(by_symbol.get(symbol));problems=[]
        row={'instrument_id':position['instrument_key'],'symbol':symbol,'owner':deepcopy(request['owner']),
            'holding':{'quantity':position['quantity'],'quantity_state':position['quantity_state'],
                'observed_at':source.get('as_of_utc'),'received_at':source.get('received_at_utc'),
                'source_kind':source.get('source_kind'),'source_reference':deepcopy(source.get('source_row'))},
            'scenario_class':scenario_class(producer.root,cls),
            'native_product_identity':{'registry_identity':deepcopy(instrument),
                'asset_type':cls['asset_type'],'asset_grade':cls['asset_grade'],
                'product_evidence':cls.get('grade_evidence'),
                'engine_route':'V75_PREDICATES' if observed and observed['v75_original_predicates'] else 'V82_TECHNICAL_OBSERVATIONS',
                'scope':'ANALYSIS_ONLY__NOT_DEPLOYMENT_IDENTITY_ATTESTATION'},
            'market':observed,'valuation_observations':deepcopy(dated_valuation) if symbol=='VT' else [],
            'core_observation':None,'primary_framework':cls['primary_framework'],
            'issuer_facts':read_issuer_facts(producer.issuer_facts_sources.get(symbol),symbol,request['evaluation_at']),
            'macro_observations':macro_observations(request['macro_snapshot'],request['evaluation_at'])
                if request.get('macro_snapshot') else None,
            'issues':problems,'source_refs':[
                {'source_kind':'OFFICIAL_MEMBER_DB','sha256':holdings['source_db_sha256'],
                    'source_reference':deepcopy(source.get('source_row'))},
                {'source_kind':'FORMAL_CLASSIFICATION','sha256':producer.class_source['sha256'],
                    'source_reference':producer.class_source['source_reference'],'scenario_blob':CATALOG_BLOB}],
            'call_trace':[]}
        if source.get('as_of_utc') is None:
            problems.append(issue('holding.observed_at','Original sealed holding has no observation timestamp',
                'Quantity is retained as accepted; current-as-of completeness is not asserted',source='DB:'+holdings['source_db_sha256']))
        if not observed:
            problems.append(issue('market.history',missing.get(symbol,{}).get('code','EXACT_SYMBOL_CACHE_UNAVAILABLE'),
                'Native price/technical calculations for this instrument cannot execute',source='data/market_history/global/manifest.json'))
            row['status']='ANALYSIS_BLOCKED'
        else:
            row['call_trace']=deepcopy(observed['call_trace'])
            receipt=observed.get('alternative_source_receipt')
            if receipt:
                problems.append(issue('market.history_length',
                    f"Alternative source provides {observed['rows']} completed bars, ending {observed['observed_date']}; full history is not available from this table",
                    'Calculations are explicitly limited to this source window; unavailable longer-period indicators stay unknown',
                    source=receipt['source_url']))
                if receipt.get('provider_currency_label_conflict'):
                    problems.append(issue('market.provider_currency_label',
                        'Provider labels Currency GBP and Price in USD; original USD listing checked separately, but the inconsistent label is unresolved',
                        'Only displayed USD reference prices are analyzed; no FX conversion or formal currency attestation',
                        source=receipt['source_url']))
                latest=max((a['observed_date'] for a in observations['assets']),default=observed['observed_date'])
                if observed['observed_date']<latest:
                    problems.append(issue('market.latest_observation',
                        f"This source ends {observed['observed_date']}, while another same-run public observation reaches {latest}",
                        'Outputs describe the recorded historical date, not current-market confirmation',source=receipt['source_url']))
            for field,value in observed['numeric'].items():
                if value is None:
                    match=re.fullmatch(r'(?:ma|volume_ratio_)(\d+)',field)
                    required=int(match.group(1)) if match else None
                    problems.append(issue('technical.numeric.'+field,
                        observed.get('component_gaps',{}).get(field,
                        f"Original algorithm returned unavailable with {observed['rows']} bars"+
                        (f"; its rolling minimum is {required} bars" if required else '; required sample/denominator is unavailable')),
                        'This indicator is not replaced by zero or a neutral signal',source=observed['source_path']))
            quality=observed.get('history_quality',{})
            if quality.get('excluded_unverified_session_rows'):
                problems.append(issue('market.unverified_same_day_session',
                    'Source includes '+str(quality['excluded_unverified_session_rows'])+'; these rows were retained in source but excluded from analysis',
                    'Independent prior-session components execute; same-day final-close state remains unverified',source=observed['source_path']))
            if quality.get('invalid_source_rows'):
                problems.append(issue('market.history_quality.invalid_source_rows',
                    f"Source has {len(quality['invalid_source_rows'])} invalid OHLC bars; analysis scope is {quality['scope']} with {quality['used_rows']} observations from {quality['analysis_start']}",
                    'Only explicitly independent components/window are evaluated; source history is not repaired or fully validated',
                    source=observed['source_path']))
            row['numeric_semantics']={'rounding':'Original analytics.nfloat: six decimal places',
                'kd_k_9_3_and_kd_d_9_3_3':'Original rolling smoothing; not approved canonical KD',
                'emv_14':'Original EMV14; not formal EMV(3,3)',
                'above_ma20_and_reclaim_ma20':'Existing W5 base facts; not canonical event votes'}
            if observed.get('approved_technical'):
                row['numeric_semantics']['approved_v10']='Owner-approved Decimal(50) producer; no display rounding in predicate comparisons'
                row['numeric_semantics']['kd_k_9_3_and_kd_d_9_3_3']='Legacy observations retained; approved KD_SMA3_SMA3 is separately bound in approved_technical'
                row['numeric_semantics']['emv_14']='Legacy EMV14 retained; approved EMV_ARMS_SMA3_SMA3_SCALE1E8 is separately bound'
            row['unknown_resolution']=[{'field_path':'technical.'+key,'category':2,
                'resolution':'COMPUTED_WITH_ORIGINAL_ALGORITHM','function':'ORIGINAL.analytics.technical'}
                for key,value in observed['numeric'].items() if value is not None]
            row['unknown_resolution'] += [{'field_path':'technical.base_facts.'+key,'category':2,
                'resolution':'EXISTING_W5_BASE_FACT_NOW_PASSED_THROUGH','value':value}
                for key,value in observed['base_facts'].items()]
            for gap in observed['source_gaps']:
                if gap!='CANONICAL_NAMED_PREDICATES':
                    problems.append(issue('market.'+gap.lower(),gap,
                        'Provider cache numerics may be shown; formal exchange/session/deployment attestation is unavailable',source=observed['source_path']))
            problems.extend(signal_gaps(observed))
            if 'V82_GLOBAL_ETF_CORE' in cls.get('analysis_capabilities',[]):
                issuer=row['issuer_facts']
                current_metrics,fundamental_fields=issuer_inputs(issuer,row['valuation_observations'])
                current_metrics=forward_observations(request['macro_snapshot'],symbol,request['evaluation_at'])+current_metrics \
                    if request.get('macro_snapshot') else current_metrics
                row['valuation_observations']=current_metrics
                row['fundamental_fields']=fundamental_fields
                row['native_product_identity']['engine_route']='V82_GLOBAL_ETF_CORE'
                row['core_observation']=producer.core_observation(observed,
                    valuation_metrics=current_metrics,fundamental_fields=fundamental_fields)
                row['call_trace'].append('V82.evaluate_core_rule_state')
                for candidate in row['core_observation']['valuation_path_audit']:
                    for field in candidate['missing_fields']:
                        problems.append(issue('valuation.'+candidate['metric']+'.'+field,
                            'No verified input for this waterfall candidate; other legal candidates are evaluated independently',
                            'Candidate unavailable; not a requirement that all optional valuation methods succeed',
                            source=candidate['source_reference']))
                for item in fundamental_fields:
                    if item.get('field_value_state')=='UNKNOWN' or item.get('direction')=='UNKNOWN':
                        field='value' if item.get('field_value_state')=='UNKNOWN' else 'direction'
                        problems.append(issue('fundamentals.'+item['field_name']+'.'+field,
                            'Issuer value is mapped' if field=='direction' else 'Required issuer context is absent',
                            'Comparable period/method and direction evidence are required by native fundamentals; positive level alone is insufficient',
                            source=item.get('source_reference')))
                for gap in row['core_observation']['input_gaps']:
                    problems.append(issue(gap['field_path'],gap['reason'],
                        'Only dependent native outputs remain UNKNOWN; independent analysis continues',
                        category=2 if gap['kind']=='DEFINITION_OR_PRODUCER_UNRESOLVED' else 3,
                        source=gap['sot_section']))
                if issuer:
                    row['source_refs'].append({'source_kind':'ISSUER_FACTS','sha256':issuer['source_sha256'],
                        'source_reference':issuer['source_url'],'observed_at':issuer['as_of']})
            elif not observed['v75_original_predicates']:
                problems.append(issue('native_product_identity.asset_type',
                    'Registry product identity does not establish approved native subtype/grade; technical components are asset-independent',
                    'Full product-specific Core judgement is not invoked; original technical aggregation is retained',category=1))
            if cls['primary_class']=='UNKNOWN':
                problems.append(issue('scenario_class','No approved Sxx membership for this instrument in the explicit mapping',
                    'Display classification is UNKNOWN; independent native numeric components still execute',category=1))
            row['status']='ANALYSIS_PARTIAL'
            row['source_refs'] += [{'path':observed['source_path'],'sha256':observed['source_sha256'],
                'observed_at':observed['observed_date'],'provider':observed['provider'],
                'provider_verified_at':observed['provider_verified_at'],'validation':observed['cache_validation'],
                'formal_identity_verified':observed['formal_identity_verified']}]
            if observed.get('analysis_identity_mapping'):
                mapping=observed['analysis_identity_mapping']
                row['source_refs'].append({'source_kind':'ISSUER_LISTING_ANALYSIS_REFERENCE',
                    'url':mapping['source_url'],'sha256':mapping['catalog_sha256'],
                    'provider_symbol':observed['provider_symbol'],'scope':mapping['scope']})
            row['source_refs'] += [{'source_kind':'DATED_VALUATION','sha256':v['source_sha256'],
                'source_reference':v['source_reference'],'observed_at':v['observed_date_text']}
                for v in row['valuation_observations']]
        row['requirements']=audit_requirements(row,producer.class_source)
        if observed and row['requirements']['complete']:row['status']='ANALYSIS_COMPLETE'
        row['position_valuation_allowed']=False
        if row.get('core_observation'):
            row['formal_conclusion']=build_formal_conclusion(producer.root,row,request)
            row['call_trace']+=row['formal_conclusion']['call_trace']
        row['analysis_explanation']=explain(row);rows.append(row)
        trace.extend({'instrument_id':row['instrument_id'],'function':name} for name in row['call_trace'])
    status=('ANALYSIS_BLOCKED' if not rows or all(r['status']=='ANALYSIS_BLOCKED' for r in rows)
        else 'ANALYSIS_PARTIAL' if any(r['status']!='ANALYSIS_COMPLETE' for r in rows) else 'ANALYSIS_COMPLETE')
    # Other brokers remain distinct rows. An IB account proof cannot authorize
    # a different broker binding; preserve those holdings and exact gaps.
    other_sources=[r for r in holdings['analysis_security_positions'] if
        not ((r.get('source_kind')=='SEALED_W6' and r.get('broker_label')=='IB')
             or r.get('source_kind')=='OWNER_SCREENSHOT_SOURCE')]
    other_sources.extend(holdings['ledger_only_positions'])
    other_coverage=[{'status':'ANALYSIS_BLOCKED','symbol':r.get('symbol'),
        'holding_source':deepcopy(r),'issues':[issue('owner.account_scope',
            'This source belongs to another account/broker, outside the verified IB request scope',
            'Preserved separately; needs its own original account binding before native analysis',
            category=1,code='ACCOUNT_SCOPE_MAPPING_REQUIRED')]} for r in other_sources]
    report={'schema_version':'Family.W8.HoldingsAnalysisReport.v1','status':status,
        'client_id':request['client_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
        'source_db_sha256':holdings['source_db_sha256'],'request_digest':digest(request),
        'snapshot_digest':digest(request['client_snapshot']['payload']),
        'mode':'CASH_ZERO_SIMULATION','source_data_provenance':'SOURCE_BACKED',
        'analysis_result':{'scope':'SELECTED_ACCEPTED_IB_ACCOUNT__NOT_ALL_HOUSEHOLD_ASSETS',
            'positions':rows,'coverage':{'requested':len(positions),'returned':len(rows),
                'partial':sum(r['status']=='ANALYSIS_PARTIAL' for r in rows),
                'blocked':sum(r['status']=='ANALYSIS_BLOCKED' for r in rows)}},
        'other_account_coverage':other_coverage,
        'deployment_status':{'status':'NOT_RUN','reason':'HOLDINGS_ANALYSIS_FLOW__NO_NEW_MONEY_REQUIRED',
            'full_native_canonical_complete':False},'cash_trial':trial,
        'issues':[dict(p,instrument_id=r['instrument_id']) for r in rows for p in r['issues']]+
            [dict(p,scope='CASH_DIAGNOSTIC__DOES_NOT_BLOCK_HOLDING_ANALYSIS') for p in trial['issues']],
        'source_refs':[s for r in rows for s in r['source_refs']], 'call_trace':trace,
        'mentor':None,'canonical_result':None,'trade_authorization':'NONE','trade_action':'NO_TRADE'}
    report['manifest']=[{'instrument_id':r['instrument_id'],'field_path':key,
        'source_db_sha256':holdings['source_db_sha256'],'output_digest':digest(r.get(key)),
        'builder':r['call_trace']} for r in rows for key in ('holding','scenario_class','native_product_identity','market','valuation_observations','core_observation','formal_conclusion')]
    grouped={}
    for problem in report['issues']:
        field=problem['field_path'];group=(field if field.startswith(('valuation.','fundamentals.')) else
            '.'.join(field.split('.')[:2]))
        item=grouped.setdefault(group,{'positions':[],'field_paths':[],'shared_producer':'W8 holding analysis source mapping'})
        instrument_id=problem.get('instrument_id','CASH_SCENARIO')
        if instrument_id not in item['positions']:item['positions'].append(instrument_id)
        if field not in item['field_paths']:item['field_paths'].append(field)
    report['common_gap_groups']=grouped
    report['manifest_digest']=digest(report['manifest']);report['report_digest']=digest(report)
    return report


class HoldingsAnalysisRunner:
    """Identity-checked analysis result seam; original deployment runner is intact."""
    def __init__(self, *, context, report):
        self.context=deepcopy(context);self.report=deepcopy(report)

    def context_provider(self):return deepcopy(self.context)

    def analyze(self,request):
        prepared=prepare_input(request,trusted_context=self.context)
        report=deepcopy(self.report)
        if (report.get('schema_version')!='Family.W8.HoldingsAnalysisReport.v1'
            or report.get('status') not in STATES or report.get('request_digest')!=digest(request)
            or report.get('client_id')!=request['client_id'] or report.get('run_id')!=request['run_id']
            or report.get('owner')!=request['owner']
            or report.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
            or report.get('snapshot_digest')!=digest(request['client_snapshot']['payload'])
            or report.get('report_digest')!=digest({k:v for k,v in report.items() if k!='report_digest'})
            or report.get('deployment_status',{}).get('status')!='NOT_RUN'
            or report.get('mentor') is not None or report.get('canonical_result') is not None
            or report.get('trade_authorization')!='NONE' or report.get('trade_action')!='NO_TRADE'):
            raise PermissionError('HOLDINGS_ANALYSIS_BINDING_MISMATCH')
        source_positions={p['instrument_key']:p for p in prepared.payload['positions']}
        seen=set()
        for row in report['analysis_result']['positions']:
            source=source_positions.get(row['instrument_id'])
            if (source is None or row['instrument_id'] in seen or row['owner']!=request['owner']
                or row['symbol']!=source['source_instrument'].get('ticker')
                or row['holding']['quantity']!=source['quantity']):
                raise PermissionError('HOLDINGS_ANALYSIS_POSITION_BINDING_MISMATCH')
            seen.add(row['instrument_id'])
            if row.get('market'):
                market=row['market']
                evaluation=datetime.fromisoformat(request['evaluation_at'].replace('Z','+00:00'))
                verified=datetime.fromisoformat(market['provider_verified_at'].replace('Z','+00:00'))
                if (market['symbol']!=row['symbol'] or verified>evaluation or
                        market['observed_date']>=evaluation.astimezone(timezone.utc).date().isoformat()):
                    raise PermissionError('HOLDINGS_ANALYSIS_MARKET_BINDING_OR_TIME_MISMATCH')
        return report

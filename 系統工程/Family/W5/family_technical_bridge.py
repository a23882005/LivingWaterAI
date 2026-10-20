"""Trusted full-history producer -> Family -> native stock evidence.

Snapshot timing is an evaluation boundary, not historical point-in-time proof.
Unapproved predicates remain UNKNOWN. SYNTHETIC inputs remain labelled.
"""
from copy import deepcopy
from family_input import digest
from family_boundary import require,BoundaryError,timestamp
from technical_source_bridge import build_partial_technical,read_history,NAMES


def bind_technical_source(repo_path,request,context):
    source=context.get('technical_source')
    if source is None:
        require(not request.get('technical_source_digest') and context['native_binding']['data_provenance']=='SYNTHETIC',
            'TECHNICAL_SOURCE_REQUIRED','technical_source',status='DATA_UNAVAILABLE')
        return None
    require(request.get('technical_source_digest')==digest(source),'TECHNICAL_SOURCE_BINDING_MISMATCH','technical_source_digest')
    require(source.get('client_id')==request['client_id'] and source.get('family_owner')==request['owner'],
            'TECHNICAL_SOURCE_OWNER_MISMATCH','technical_source.owner')
    meta=source['metadata']
    require(meta.get('symbol')==request['native_bundle']['stock_request']['asset_context']['asset']['asset_id'],
            'TECHNICAL_ASSET_MISMATCH','technical_source.symbol')
    if source.get('csv_path') is not None:
        rows=read_history(source['csv_path'],source['sha256'])
    else:
        require(meta.get('data_provenance')=='SYNTHETIC','REAL_HISTORY_FILE_REQUIRED','technical_source.csv_path')
        rows=source['history']
    if meta.get('data_provenance')!='SYNTHETIC':
        require(meta.get('evaluation_mode')=='SNAPSHOT_AFTER_ACQUISITION',
                'SNAPSHOT_MODE_REQUIRED','technical_source.evaluation_mode')
    out=build_partial_technical(rows,metadata=meta,evaluated_at=request['evaluation_at'],repo_path=repo_path)
    summary={k:deepcopy(v) for k,v in out.items() if k not in ('source_history','source_metadata')}
    summary['source_reference']=meta.get('source_reference')
    summary['call_trace']=['W5.read_history' if source.get('csv_path') else 'W5.synthetic_history',
        'W5.build_partial_technical','V82.evaluate_technical']
    if out['sample_state']!='COMPLETE':
        error=BoundaryError('TECHNICAL_SOURCE_UNAVAILABLE','technical_source',status='DATA_UNAVAILABLE')
        error.issue['technical_intake']=summary
        raise error
    facts=request['native_bundle']['stock_evidence']
    for key in ('exchange','currency'):
        require(meta.get(key)==facts[key],'TECHNICAL_INSTRUMENT_MISMATCH','technical_source.'+key)
    require(meta.get('data_provenance')==context['native_binding']['data_provenance'],
            'TECHNICAL_PROVENANCE_MISMATCH','technical_source.data_provenance')
    # Approved engineering fixture: explicit predicate inputs, never a new rule.
    fixture=source.get('synthetic_complete_predicates')
    if fixture is not None:
        require(meta.get('data_provenance')==context['native_binding']['data_provenance']=='SYNTHETIC',
                'SYNTHETIC_FIXTURE_SCOPE_REQUIRED','technical_source.synthetic_complete_predicates')
        require(set(fixture)==set(NAMES)|{'ma20_ok'},'SYNTHETIC_PREDICATE_SHAPE','technical_source.fixture')
        effective={}
        for group,names in NAMES.items():
            require(len(fixture[group])==len(names) and all(x in ('TRUE','FALSE','UNKNOWN') for x in fixture[group]),
                    'SYNTHETIC_PREDICATE_SHAPE','technical_source.fixture.'+group)
            effective[group]=[row['truth'] if row['truth']!='UNKNOWN' else value
                              for row,value in zip(summary['signals'][group],fixture[group])]
        require(fixture['ma20_ok'] in ('TRUE','FALSE','UNKNOWN'),'SYNTHETIC_PREDICATE_SHAPE','ma20_ok')
        summary['synthetic_complete_predicates']={**effective,'ma20_ok':fixture['ma20_ok']}
        summary['synthetic_fixture_scope']='ENGINEERING_ONLY_EXPLICIT_INPUTS_NOT_APPROVED_RULES'
    return summary


def apply_technical_source(bundle,technical):
    data=deepcopy(bundle)
    if technical is None:return data
    facts=data['stock_evidence']
    for group in NAMES:facts['core'][group]=[x['truth'] for x in technical['signals'][group]]
    facts['core']['ma20_ok']=technical['ma20_ok']
    if 'synthetic_complete_predicates' in technical:
        facts['core'].update(deepcopy(technical['synthetic_complete_predicates']))
    facts['sample_state']=technical['sample_state']
    facts['source_reference']=facts['source_reference']+' | TECHNICAL:'+technical['source_reference']
    facts['technical_source_digest']=technical['history_digest']
    data['producer_contract'].update(producer='W5_FULL_HISTORY_BRIDGE',version='1',parameters={'history_digest':technical['history_digest'],'scope':technical.get('synthetic_fixture_scope','PARTIAL_ORIGINAL_RULES')})
    facts.update(deepcopy(data['producer_contract']))
    facts['swings']=[{'asset_id':facts['asset_id'],**p} for k in ('lows','highs') for p in technical['swings'][k]]
    facts['technical_available_at']=technical.get('snapshot_available_at')
    if facts['technical_available_at']:
        facts['available_at']=max((facts['available_at'],facts['technical_available_at']),key=lambda x:timestamp(x,'available_at'))
    fields=data['stock_source_fields']
    for name in ('kd_state','macd_state','ma_state','emv_state','rsi_state','volume_price_state',
                 'daily_timeframe_state','weekly_timeframe_state','monthly_timeframe_state','atr_value'):
        fields[name]='UNKNOWN'
    for side in ('high','low'):
        fields['td9_'+side+'_state']={'count':technical['td9'][side+'_count'],
            'events':[e for e in technical['td9']['events'] if e['side']==side.upper()],
            'source':'ORIGINAL_TD9','data_provenance':technical['data_provenance']}
    lows=list(reversed(technical['swings']['lows']))
    for i in range(3):
        fields['previous_swing_low_'+str(i+1)]=({'amount':lows[i]['value'],
            'currency':facts['currency'],'source_reference':technical['source_reference'],
            'as_of':lows[i]['confirmed_at'],'status':'KNOWN'} if i<len(lows) else 'UNKNOWN')
    data['technical_intake']=deepcopy(technical)
    return data

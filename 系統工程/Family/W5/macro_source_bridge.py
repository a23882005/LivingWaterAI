"""Explicit W3 feed field mapping; no tactical-budget or missing-metric inference."""
from copy import deepcopy
from datetime import date
from decimal import Decimal,InvalidOperation
from family_boundary import require,timestamp
from family_input import digest


def project_macro(snapshot, evaluation_at):
    raw=snapshot['payload'];at=timestamp(evaluation_at,'evaluation_at')
    require(raw.get('schema')=='V70.3/family-macro-feed-v3','MACRO_SCHEMA','macro.schema','W3')
    require(raw.get('verification',{}).get('ready') is True,'MACRO_NOT_READY','macro.verification.ready','W3','DATA_UNAVAILABLE')
    require(snapshot.get('digest')==digest(raw),'MACRO_DIGEST_MISMATCH','macro.digest','W3')
    available=timestamp(raw.get('asOf'),'macro.asOf')
    require(available<=at,'FUTURE_MACRO','macro.asOf','W3')
    row=raw.get('indicators',{}).get('m12')
    require(isinstance(row,dict) and row.get('status')=='OK' and row.get('value') is not None,
            'MOVE_UNAVAILABLE','macro.indicators.m12','W3','DATA_UNAVAILABLE')
    require(row.get('source')=='https://finance.yahoo.com/quote/%5EMOVE/' and row.get('unit')=='',
            'MOVE_SOURCE_OR_UNIT_MISMATCH','macro.indicators.m12','W3')
    try:
        require(not isinstance(row['value'],bool),'MOVE_INVALID','macro.indicators.m12.value','W3')
        value=Decimal(str(row['value']))
        require(value.is_finite() and value>=0,'MOVE_INVALID','macro.indicators.m12.value','W3')
        observed=date.fromisoformat(row['dataDate'])
    except (InvalidOperation,ValueError,TypeError):
        require(False,'MOVE_INVALID','macro.indicators.m12','W3')
    require(observed<=available.date(),'FUTURE_MOVE_OBSERVATION','macro.indicators.m12.dataDate','W3')
    return {'producer':'Family.W5','schema_version':'Family.W5.MacroProjection.v1',
        'source_digest':snapshot['digest'],'source_as_of':raw['asOf'],
        'source_verification':deepcopy(raw['verification']),'source_snapshot':deepcopy(raw.get('sourceSnapshot')),
        'fields':{'PRED-005.move':{'value':str(value),'unit':'MOVE_INDEX_POINTS',
            'source_path':'/indicators/m12','source_row':deepcopy(row)}},
        'remaining_metrics':'Require separately identified existing producer; no zero fill',
        'tactical_budget_source':'SEPARATE_V70_RESULT_REQUIRED'}


def validate_macro_consumers(request):
    projected=project_macro(request['macro_snapshot'],request['evaluation_at'])
    expected=Decimal(projected['fields']['PRED-005.move']['value'])
    available=timestamp(projected['source_as_of'],'macro.asOf')
    for asset,facts in request['native_bundle']['bond_evidence'].items():
        value=facts.get('metrics',{}).get('PRED-005',{}).get('move')
        try:valid=not isinstance(value,bool) and value is not None and Decimal(str(value))==expected
        except InvalidOperation:valid=False
        require(valid,'MOVE_NATIVE_VALUE_MISMATCH','bond_evidence.'+asset+'.PRED-005.move','W5')
        require(available<=timestamp(facts['available_at'],'bond.available_at'),
                'MOVE_AVAILABLE_AFTER_EVIDENCE','bond_evidence.'+asset,'W5')
    return projected

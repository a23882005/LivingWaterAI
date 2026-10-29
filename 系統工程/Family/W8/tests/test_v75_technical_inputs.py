"""V75-specific named events reach the original technical evaluator."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import v75_technical_inputs as T
import formal_v75_parameters as P


def rows():
    return [{'Date':str(date(2026,1,1)+timedelta(days=i)),'Close':100+i,'Low':99+i,
        'High':101+i,'Open':100+i,'Volume':1000 if i<79 else 100} for i in range(80)]


def test_high_td_and_two_confirming_trim_factors_take_native_precedence():
    from bond_advisory import candidates
    from datetime import datetime,timezone
    candidates(ROOT)
    from v75_runtime.predicates import pred009
    base={'low_td9_setup':0,'high_td9_setup':9,'kd_k_9_3':90,'kd_d_9_3_3':95,
        'rsi14':72,'ma20':150,'ma50':140,'atr14':1,'macd_12_26':2,'macd_signal_9':1,'macd_histogram':'.1'}
    history=[deepcopy(base) for _ in range(4)];history[1].update(kd_k_9_3=96,kd_d_9_3_3=95,macd_histogram='.2')
    history[2].update(macd_histogram='.3')
    metrics=T.from_numeric(rows(),history)
    assert metrics['kd_death_cross_k_ge_80'] and metrics['rsi14_ge_70']
    assert metrics['macd_hist_shrinking_3d'] and metrics['price_up_volume_below_ma20']
    assert pred009(metrics,datetime.now(timezone.utc),['SYNTHETIC']).aggregate_state=='TRIM_WATCH'
    for h,value in zip(history,['-.1','-.2','-.3']):h['macd_histogram']=value
    metrics=T.from_numeric(rows(),history)
    assert metrics['macd_hist_improving_3d'] and not metrics['macd_hist_shrinking_3d']


def test_named_inputs_require_base_rule_proof_and_never_replace_missing_kd_with_zero():
    parameters={'parameter_version':P.VERSION,'parameter_sha256':P.PARAMETER_SHA256,
        'base_rule_source':{'source_sha256':P.BASE_RULE_SHA256}}
    result=T.produce(rows(),parameters)
    assert result['complete_named_inputs'] and not result['unprovided_inputs']
    parameters.pop('base_rule_source');result=T.produce(rows(),parameters)
    assert not result['complete_named_inputs'] and result['metrics']['macd_hist_shrinking_3d'] is None
    numeric=[{}]*4;metrics=T.from_numeric(rows(),numeric)
    assert metrics['low_td_count'] is None and metrics['k'] is None and metrics['kd_golden_cross_k_le_35'] is None

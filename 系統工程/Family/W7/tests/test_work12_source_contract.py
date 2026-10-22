"""Synthetic seam checks of exact accepted WORK12 code; no market/DB data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from datetime import date
from decimal import Decimal
import pytest

HOME=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,HOME/'vendor/work12'/f'{name}.py')
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj

def test_original_bytes():
    for row in json.loads((HOME/'work12_source_lock.json').read_text())['files']:
        assert hashlib.sha256((HOME/row['destination']).read_bytes()).hexdigest()==row['sha256']

def test_cagr_period_contract():
    p=module('pretax_performance_engine')
    result=p.calculate_cagr(Decimal(100),Decimal(110),date(2020,1,1),date(2021,1,1))
    assert abs(float(result)-0.0997830344948493)<0.000001
    with pytest.raises(p.PerformanceEngineError):p.calculate_cagr(Decimal(100),Decimal(110),date(2020,1,1),date(2020,12,31))

def test_bndw_remains_excluded():
    p=module('pretax_performance_engine')
    with pytest.raises(p.PerformanceEngineError,match='BNDW'):
        p.PreTaxPerformanceEngine([{'instrument':'BNDW'}],{}, {},[],[],[],[])

def test_risk_gap_and_invalid_data():
    p=module('risk_engine')
    assert p.max_drawdown_daily_wealth([100,120,90,110]).value == -0.25
    assert p.max_drawdown_daily_wealth([100,120],blocking_gap=True).status=='UNKNOWN'
    with pytest.raises(p.ContractViolation):p.max_drawdown_daily_wealth([100,float('nan')])

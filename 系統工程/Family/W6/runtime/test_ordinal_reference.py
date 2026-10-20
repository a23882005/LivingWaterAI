import json
from pathlib import Path
import pytest
from ordinal_reference import portfolio_grade

M=json.loads((Path(__file__).parent/'W6_17類六情境攻防評等_v1.0.json').read_text())
def h(code,w=1,tenor='none',key='a'):
    return {'asset_id':key,'class_id':code,'weight':w,'tenor':tenor}
def test_round_half_up_and_half_grid():
    x=portfolio_grade([h('S01',.5),h('B01',.5,key='b')],M,'牛市初期','attack')
    assert x['raw']==3.5 and x['level']==4 and x['grid']==2
def test_missing_keeps_weight_and_null():
    x=portfolio_grade([h('S01',.5),h(None,.5,key='b')],M,'牛市初期','attack')
    assert x['coverage']==.5 and x['known_contribution']==2.5 and x['level'] is None
def test_short_and_long_corporate():
    assert portfolio_grade([h('B05',tenor='short')],M,'牛市初期','attack')['level']==3
    assert portfolio_grade([h('B05',tenor='short')],M,'景氣衰退','defense')['level']==4
    assert portfolio_grade([h('B06',tenor='short')],M,'金融危機','defense')['level']==2
    assert portfolio_grade([h('B05',tenor='long')],M,'景氣衰退','attack')['level']==4
def test_invalid_input():
    for hs in [[h('S01',.5)], [h('S01',.5),h('B01',.5)], [h('S01',float('nan'))]]:
        with pytest.raises(ValueError):portfolio_grade(hs,M,'牛市初期','attack')
def test_204_matrix_values():
    values=[v for row in M['rows'] for pair in row['scenarios'].values() for v in pair.values()]
    assert len(values)==204 and all(isinstance(v,int) and 1<=v<=6 for v in values)

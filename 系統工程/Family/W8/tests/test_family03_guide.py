"""Family 03 source isolation and history semantics, independent of a real member."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class GuideTests(unittest.TestCase):
    def test_every_question_has_a_video_and_first_answer_is_optional(self):
        guide = module('family03_guide')
        for k in guide.QUESTIONS:
            self.assertTrue(guide.question(k)['影片']['網址'].startswith('https://www.youtube.com/watch?v='))
        with TemporaryDirectory() as d:
            question = guide.guide({}, {}, Path(d)/'absent', module('equity_sleeve'))
            self.assertEqual(question['key'],'goal')
            self.assertEqual(len(question['選項']),4)

    def test_mixed_currency_and_missing_values_are_visible(self):
        calc = module('equity_sleeve')
        self.assertEqual(calc.simulate({'A':50,'B':50},{'A':('USD',{}),'B':None})['標的'],['B'])
        self.assertIn('幣別',calc.simulate({'A':50,'B':50},{'A':('USD',{}),'B':('TWD',{})})['狀態'])

    def test_opposite_movements_cancel_in_actual_portfolio_wealth(self):
        calc = module('equity_sleeve')
        a,b={},{}
        for i in range(370):
            d=(date(2020,1,1)+timedelta(days=i)).isoformat()
            a[d]=100+i/10
            b[d]=100-i/10
        out=calc.simulate({'A':50,'B':50},{'A':('USD',a),'B':('USD',b)})
        self.assertAlmostEqual(out['最大回撤幅度'],0)
        self.assertAlmostEqual(out['年化報酬率'],0)

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

    def test_rank_follows_goal_and_discloses_unmet_ceiling(self):
        compare=module('family03_compare')
        answers={'core':'A','sat':'B','star':'C'}
        class Simulation:
            @staticmethod
            def simulate(weights, prices):
                risk=(110-weights['A'])/200
                return {'狀態':'歷史粗估','起日':'2020-01-01','迄日':'2025-01-01',
                        '最大回撤幅度':risk,'年化報酬率':risk/2,'Sharpe':1-risk}
            @staticmethod
            def exposure(*args):
                return {'共同曝險':[]}
        mixes=compare.VARIANTS[0]
        for goal,loss,best in ((0,4,(60,30,10)),(1,4,(40,40,20)),(1,1,None)):
            rows,selected,reason=compare.compare(answers,mixes,mixes[0],{},[],Simulation,goal,4,loss)
            self.assertEqual(selected,best)
            self.assertEqual(len(rows),3)
            self.assertEqual('三組都超過' in reason,loss==1)
        self.assertIsNone(compare.compare(answers,mixes,mixes[0],{},[],Simulation,2,4,4)[1])

    def test_trial_offered_within_each_band_and_uses_the_same_instruments(self):
        groups=module('family03_compare').VARIANTS
        limits=[((40,60),(30,40),(10,20)),((60,80),(15,30),(5,15)),((80,100),(0,20),(0,10))]
        for grp,bounds in zip(groups,limits):
            for mix in grp:
                self.assertEqual(sum(mix),100)
                self.assertEqual([x>0 for x in mix],[x>0 for x in grp[0]])
                self.assertTrue(all(lo<=v<=hi for v,(lo,hi) in zip(mix,bounds)))

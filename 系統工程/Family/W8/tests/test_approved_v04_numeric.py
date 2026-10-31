"""Independent stdlib checks of V82 candidate mathematics, not a trading engine.

Input vectors are synthetic and prevalidated. None represents a missing primitive
dependency. Decimal(50, HALF_EVEN) is the specified implementation arithmetic;
Fraction is an independent exact-math oracle. Oracle tolerance is solely a test
allowance for Decimal rounding, NEVER a signal-comparison epsilon.
"""
from decimal import Decimal, getcontext, ROUND_HALF_EVEN
from fractions import Fraction
import unittest

getcontext().prec = 50
getcontext().rounding = ROUND_HALF_EVEN
D = Decimal
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from approved_v04_numeric import sma,ema,kd,macd,atr,rsi,emv,td_count,td_first9,cross






















def first_known(xs):
    return next((i for i, x in enumerate(xs) if x is not None), None)


def exact_ema(xs, alpha):
    value, result = None, []
    for x in xs:
        value = x if value is None else alpha*x+(1-alpha)*value
        result.append(value)
    return result


class NumericSpecTests(unittest.TestCase):
    def assertExactOracle(self, actual, rational):
        expected = D(rational.numerator)/D(rational.denominator)
        self.assertLessEqual(abs(actual-expected), D('1e-45'))

    def test_kd_first_indices(self):
        c = [D(100)]*14
        r, k, d = kd(c, c, c)
        self.assertEqual([first_known(x) for x in (r, k, d)], [8, 10, 12])
        self.assertEqual((k[10], d[12]), (D(50), D(50)))

    def test_kd_flat9_not_d50_yet_T009(self):
        r, k, d = kd([D(100)]*9, [D(100)]*9, [D(100)]*9)
        self.assertEqual(r[-1], 50)
        self.assertIsNone(k[-1]); self.assertIsNone(d[-1])

    def test_kd_ramp_reference(self):
        c = [D(10+i) for i in range(20)]
        r, k, d = kd([x+1 for x in c], [x-1 for x in c], c)
        self.assertEqual((r[-1], k[-1], d[-1]), (D(90), D(90), D(90)))

    def test_kd_cross_equal_previous_T007(self):
        self.assertTrue(cross([D(20), D(21)], [D(20), D(20)]))
        self.assertFalse(D(20) < 20)

    def test_kd_equal_current_no_cross_T008(self):
        self.assertFalse(cross([None, D(80)], [None, D(80)]))
        self.assertFalse(D(80) > 80)

    def test_macd_warmup_T010(self):
        c = [D(100)]*35
        e12, e26, dif, dea, hist = macd(c)
        self.assertEqual([first_known(x) for x in (e12,e26,dif,dea,hist)], [11,25,25,33,33])
        self.assertIsNone(hist[32]); self.assertEqual(hist[33], 0)
        # Availability of the full previous/current pair, not whether Kleene
        # logic may already exclude a cross from one known FALSE conjunct.
        self.assertIsNone(dea[32]); self.assertIsNotNone(dea[33]); self.assertIsNotNone(dea[34])

    def test_T010_kleene_counterexample_current_equality_proves_no_cross(self):
        *_, dif, dea, hist = macd([D(100)]*34)
        self.assertIsNone(dea[-2])
        self.assertEqual(hist[-1],0)
        self.assertFalse(cross(dif,dea))
        self.assertFalse(cross(dea,dif))

    def test_macd_exact_rational_oracle(self):
        values = [100+(i*7 % 13)-5 for i in range(75)]
        c, f = list(map(D, values)), list(map(Fraction, values))
        e12, e26, dif, dea, hist = macd(c)
        f12, f26 = exact_ema(f, Fraction(2,13)), exact_ema(f, Fraction(2,27))
        fdif = [a-b for a,b in zip(f12,f26)]
        fdea = exact_ema(fdif[25:], Fraction(1,5))
        for i in range(33,len(c)):
            self.assertExactOracle(dif[i], fdif[i])
            self.assertExactOracle(dea[i], fdea[i-25])
            self.assertExactOracle(hist[i], fdif[i]-fdea[i-25])

    def test_macd_hist_is_not_doubled_T011_T012(self):
        self.assertTrue(cross([D(-1), D('.1')], [D(0), D(0)]))
        for now, shrink, expand in [(D('-.5'),True,False),(D(-1),False,False),(D('-1.1'),False,True)]:
            self.assertEqual(now < 0 and abs(now) < 1, shrink)
            self.assertEqual(now < 0 and abs(now) > 1, expand)
        *_, dif, dea, hist = macd([D(100+i) for i in range(35)])
        self.assertEqual(hist[-1], dif[-1]-dea[-1])

    def test_macd_prefix_invariance_and_seed_sensitivity(self):
        c = [D(100+(i*7%13)) for i in range(80)]
        full = macd(c)[-1]
        self.assertEqual(full[:50], macd(c[:50])[-1])
        self.assertNotEqual(full[-1], macd(c[20:])[-1][-1])

    def test_macd_missing_close_restarts(self):
        c = [D(100)]*40+[None]+[D(100)]*34
        hist = macd(c)[-1]
        self.assertTrue(all(x is None for x in hist[40:74]))
        self.assertEqual(hist[74], 0)

    def test_atr_warmup_and_constant(self):
        c = [D(100)]*15
        tr, out = atr([D(101)]*15, [D(99)]*15, c)
        self.assertEqual(first_known(out),13)
        self.assertEqual(tr,[D(2)]*15); self.assertEqual(out[13],2)

    def test_atr_gap_component_and_seed(self):
        tr, out = atr([D(101),D(111)]+[D(111)]*12, [D(99),D(109)]+[D(109)]*12, [D(100),D(110)]+[D(110)]*12)
        self.assertEqual(tr[0],2); self.assertEqual(tr[1],11)
        oracle = exact_ema([Fraction(x) for x in tr], Fraction(1,14))
        self.assertExactOracle(out[-1],oracle[-1])

    def test_atr_fast_threshold_T029(self):
        self.assertTrue(D('1.2')/D(1) >= D('1.20'))
        self.assertFalse(D('1.19999')/D(1) >= D('1.20'))
        self.assertEqual(ema([D(0)]*14,D(1)/14,14)[-1],0)
        # A6 expressly guards a zero base; no ratio is evaluated here.

    def test_atr_complete_HLC_gap_restarts(self):
        c=[D(100)]*20+[None]+[D(100)]*14
        h=[None if x is None else x+1 for x in c]
        l=[None if x is None else x-1 for x in c]
        tr,out=atr(h,l,c)
        self.assertIsNone(tr[20]); self.assertEqual(tr[21],2)
        self.assertTrue(all(x is None for x in out[20:34]))
        self.assertEqual(out[34],2)

    def test_rsi_first_index_T016(self):
        for c, expected in [([D(100)]*15,50),([D(100+i) for i in range(15)],100),([D(100-i) for i in range(15)],0)]:
            out = rsi(c)[-1]
            self.assertEqual(first_known(out),14)
            self.assertIsNone(out[13]); self.assertEqual(out[14],expected)

    def test_rsi_exact_oracle_not_sma_seeded_wilder(self):
        c = [D(100+i%2) for i in range(15)]
        out = rsi(c)[-1][-1]
        gains = [Fraction(1 if i%2 else 0) for i in range(1,15)]
        losses = [1-x for x in gains]
        g = exact_ema(gains,Fraction(1,14))[-1]
        d = exact_ema(losses,Fraction(1,14))[-1]
        self.assertExactOracle(out,100-100/(1+g/d))
        self.assertNotEqual(out,D(50))  # SMA-seeded Wilder would equal 50 here.

    def test_rsi_thresholds_T017_T018_T019(self):
        self.assertFalse(D(30)<30); self.assertFalse(D(70)>70)
        for r, expected in [('45',True),('55',True),('55.001',False),('52',True)]:
            self.assertEqual(D(45)<=D(r)<=D(55),expected)
        self.assertTrue(D(30)<D(35)<D(40)<D(45))
        self.assertFalse(D(30)<D(35)<D(35)<D(45))

    def test_rsi_missing_close_restarts_delta_seed(self):
        c = [D(100)]*20+[None]+[D(100)]*15
        out = rsi(c)[-1]
        self.assertTrue(all(x is None for x in out[20:35]))
        self.assertEqual(out[35],50)

    def test_emv_first_indices_and_ramp(self):
        mid = [D(100+i) for i in range(7)]
        raw, fast, e = emv([x+1 for x in mid],[x-1 for x in mid],[D(100000000)]*7)
        self.assertEqual([first_known(x) for x in (raw,fast,e)],[1,3,5])
        self.assertEqual((raw[-1],fast[-1],e[-1]),(D(2),D(2),D(2)))
        self.assertIsNotNone(e[5]); self.assertIsNotNone(e[6])

    def test_emv_range_zero_and_volume_zero_T015(self):
        raw,_,_ = emv([D(100),D(101),D(102)],[D(100),D(101),D(102)],[D(10),D(10),D(0)])
        self.assertEqual(raw[1],0); self.assertIsNone(raw[2])

    def test_emv_negative_midpoint_move(self):
        raw,_,_ = emv([D(101),D(100)],[D(99),D(98)],[D(100000000)]*2)
        self.assertEqual(raw[1],D(-2))

    def test_emv_two_sma_layers_not_renamed_emv14(self):
        # 3x3 cascaded SMA has triangular weights (1,2,3,2,1)/9.
        h=[D(100+i*i+1) for i in range(6)]
        l=[x-2 for x in h]
        raw,fast,e=emv(h,l,[D(100000000)]*6)
        expected=sum(w*x for w,x in zip(map(D,[1,2,3,2,1]),raw[1:]))/9
        self.assertEqual(e[5],expected)

    def test_td13_current9_first_unknown_T001(self):
        c=list(map(D,range(100,113)))
        self.assertEqual(td_count(c),(9,0)); self.assertIsNone(td_first9(c))

    def test_td14_current9_first_false_T002(self):
        c=list(map(D,range(100,114)))
        self.assertEqual(td_count(c),(9,0)); self.assertFalse(td_first9(c))

    def test_td_equal_reset_T003(self):
        c=list(map(D,range(100,113))); c[-1]=c[-5]
        self.assertEqual(td_count(c),(0,0)); self.assertFalse(td_first9(c))

    def test_td_fresh_first9_after_observed_reset(self):
        c=list(map(D,[100,101,102,103,99,104,105,106,107,108,109,110,111,112]))
        self.assertEqual(td_count(c[:-1]),(8,0))
        self.assertEqual(td_count(c),(9,0)); self.assertTrue(td_first9(c))

    def test_td_low_direction_and_missing_volume_independent_T004(self):
        c=list(map(D,range(113,100,-1)))
        self.assertEqual(td_count(c),(0,9)); self.assertIsNone(td_first9(c,1))
        h,l=[x+1 for x in c],[x-1 for x in c]
        self.assertIsNone(emv(h,l,[None]*len(c))[-1][-1])
        self.assertEqual(td_count(c),(0,9))

    def test_td_less13_and_missing_close_unknown(self):
        self.assertIsNone(td_count([D(100)]*12))
        self.assertIsNone(td_count([D(100)]*12+[None]))

    def test_post_high_search_23_close_bound(self):
        # At t=22, earliest live setup e=t-9=13 needs index e-13=0
        # to determine High_(e-1), not merely the current capped High_e.
        c=list(map(D,[100,101,102,103,99,104,105,106,107,108,109,110,111,112]+[113]*9))
        t=len(c)-1; e=t-9
        self.assertEqual((len(c),e),(23,13))
        self.assertTrue(td_first9(c[:e+1]))
        self.assertIsNone(td_first9(c[1:e+1]))

    def test_prior20_volume_T034(self):
        volumes=[D(100)]*19+[D(200)]
        inclusive=sma(volumes,20)[-1]
        self.assertEqual(inclusive,105)
        self.assertEqual(D(200)/inclusive,D(200)/D(105))
        self.assertIsNone(sma(volumes[:-1],20)[-1])
        volumes=[D(100)]+volumes
        self.assertEqual(volumes[-1]/sma(volumes[:-1],20)[-1],2)

    def test_decimal_boundary_returns_T030_T031(self):
        self.assertTrue(D('-.05')<=D('-.03')-D('.02'))
        self.assertFalse(D('-.0499')<=D('-.03')-D('.02'))
        self.assertTrue(D('.08')<D('.09')<D('.1') and D('.08')<=D('.8')*D('.1'))
        self.assertFalse(D('.0801')<=D('.8')*D('.1'))

    def test_declared_split_segmentation_does_not_carry_seed(self):
        before=[D(200)]*40; after=[D(100)]*34
        # The contract calls the primitive on separate segments. No implicit
        # corporate-action detector is implemented in this numeric microtest.
        joined=macd(before+after)[-1]
        reset=macd(after)[-1]
        self.assertLess(joined[len(before)],0) # Wrong unsplit carry creates artifact.
        self.assertIsNone(reset[0]); self.assertEqual(reset[33],0)
        self.assertIsNone(td_count(after[:12]))

    def test_cash_dividend_raw_return_not_total_return(self):
        raw_before,raw_after,total_before,total_after=map(D,[100,99,100,100])
        self.assertEqual(raw_after/raw_before-1,D('-.01'))
        self.assertEqual(total_after/total_before-1,0)
        self.assertNotEqual(raw_after/raw_before-1,total_after/total_before-1)

    def test_revised_S9_ma50_five_bar_slope_full_pair_at_55(self):
        ma=sma([D(200-i) for i in range(55)],50)
        self.assertEqual(first_known(ma),49)
        self.assertIsNone(ma[53-5])
        self.assertIsNotNone(ma[54-5])
        self.assertTrue(D(146)<ma[54]<ma[49])


if __name__ == '__main__':
    unittest.main(verbosity=2)

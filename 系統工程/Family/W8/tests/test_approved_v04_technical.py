"""Owner-approved source producer: boundaries, cold start, isolation and votes."""
from pathlib import Path
from decimal import Decimal
from datetime import date,datetime,timedelta
from unittest.mock import patch
from types import SimpleNamespace
import hashlib,json,sys,tempfile,unittest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import approved_v04_technical as A
import approved_v04_numeric as N
from technical_source_bridge import NAMES,predicate_votes,_aggregate


def history(count=100):
    start=date(2025,1,1)
    return [{'Date':(start+timedelta(days=i)).isoformat(),'Close':'100','High':'100','Low':'100','Open':'100','Volume':'1000'} for i in range(count)]


def slot(out,group,name):return next(r for r in out['signals'][group] if r['name']==name)


class ApprovedTechnicalTest(unittest.TestCase):
    def setUp(self):self.profile=A.load_profile(HERE/'owner_approved_v10.json')
    def produce(self,rows=None,**kwargs):return A.produce(rows or history(),profile=self.profile,**kwargs)
    def test_profile_rejects_unapproved_or_changed_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';receipt=json.loads((HERE/'owner_approved_v10.json').read_text())
            receipt['approval_status']='CANDIDATE';p.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'APPROVAL'):A.load_profile(p)
    def test_manifest_contains_all32_slots_and_no_fabricated_guidance(self):
        out=self.produce(is_etf=None)
        self.assertEqual({g:[r['name'] for r in rs] for g,rs in out['signals'].items()},NAMES)
        self.assertEqual(sum(len(rs) for rs in out['signals'].values()),32)
        self.assertEqual(slot(out,'up_confirm','eps_guidance_not_worse')['truth'],'UNKNOWN')
    def test_approved_etf_na_contributes_neither_true_nor_unknown_vote(self):
        out=self.produce(is_etf=True);row=slot(out,'up_confirm','eps_guidance_not_worse')
        self.assertEqual(row['truth'],'NOT_APPLICABLE');self.assertEqual(predicate_votes([row]),['FALSE'])
        self.assertEqual(out['deployment_status'],'NOT_RUN')
        row['name']='dif_up'
        with self.assertRaisesRegex(ValueError,'UNAUTHORIZED'):predicate_votes([row])
    def test_ma20_tolerance_boundary_and_not_above_ma_rule(self):
        # 19*100 + x gives MA20=100 exactly when x=100; isolate MA input to
        # exercise the actual approved predicate at the exact .99 boundary.
        original=N.sma
        def fixed(values,n):return [Decimal(100)]*len(values) if n==20 else original(values,n)
        with patch.object(N,'sma',side_effect=fixed):
            for close,expected in [('99','TRUE'),('98.999','FALSE')]:
                rows=history();rows[-1].update(Close=close,High='101',Low='98',Open='100')
                self.assertEqual(self.produce(rows)['ma20_ok'],expected)
    def test_flat_kd_zero_range_and_neutral_rsi_are_explicit_approved_results(self):
        out=self.produce()
        self.assertEqual(out['numeric_decimal']['kd_k'],'50')
        self.assertEqual(out['numeric_decimal']['kd_d'],'50')
        self.assertEqual(out['numeric_decimal']['rsi14'],'50')
        self.assertEqual(slot(out,'down_accel','kd_low_weak')['truth'],'FALSE')
    def test_zero_volume_does_not_erase_close_dependent_fields(self):
        rows=history()
        for r in rows:r['Volume']='0'
        out=self.produce(rows)
        self.assertIsNone(out['numeric_decimal']['emv_3_3'])
        self.assertEqual(slot(out,'up_confirm','emv_positive_or_improving')['truth'],'UNKNOWN')
        self.assertEqual(out['ma20_ok'],'TRUE')
    def test_close_only_never_manufactures_atr_kd_or_emv(self):
        out=self.produce(close_only=True)
        for key in ('kd_k','kd_d','atr14','emv_3_3'):self.assertIsNone(out['numeric_decimal'][key])
        self.assertEqual(out['ma20_ok'],'TRUE')
        self.assertEqual(slot(out,'up_confirm','rsi_high_no_divergence')['truth'],'FALSE')
    def test_cold_start_does_not_turn_empty_episode_search_into_false(self):
        out=self.produce(history(13))
        self.assertEqual(slot(out,'right_signals','breakout_retest_success')['truth'],'UNKNOWN')
        self.assertEqual(slot(out,'down_break','break_support_no_quick_reclaim')['truth'],'UNKNOWN')
        self.assertEqual(out['ma20_ok'],'UNKNOWN')
    def test_high_td9_event_does_not_keep_repeating(self):
        rows=history(40)
        for i,r in enumerate(rows):r.update(Close=str(100+i),High=str(101+i),Low=str(99+i),Open=str(100+i))
        # A first9 episode may be replaced or expire; no immortal TRUE after
        # the price has remained above the original reference for many bars.
        out=self.produce(rows)
        self.assertEqual(slot(out,'up_confirm','high_td9_then_new_high')['truth'],'FALSE')
    def test_retest_success_is_one_event_with_immutable_parent_level(self):
        rows=history(73)
        rows[69].update(Close='99',Low='98',High='100')
        rows[70].update(Close='101',Low='100',High='102')
        rows[71].update(Close='102',Low='100',High='103')
        rows[72].update(Close='103',Low='101',High='104')
        fake={'confirmed_swing_highs':lambda xs:[SimpleNamespace(index=50)],
              'confirmed_swing_lows':lambda xs:[]}
        with patch.object(A,'_originals',return_value=(fake,None)):
            first=self.produce(rows[:72]);later=self.produce(rows)
        self.assertEqual(slot(first,'right_signals','breakout_retest_success')['truth'],'TRUE')
        self.assertEqual(slot(later,'right_signals','breakout_retest_success')['truth'],'FALSE')
        self.assertTrue(any(e['immutable_level']=='100' and e['state']=='SUCCESS_EVENT' for e in first['episode_trace']))
    def test_no_quick_reclaim_waits_three_sessions_and_fires_only_once(self):
        rows=history(75)
        for r in rows[70:]:r.update(Close='98',Low='97',High='100')
        fake={'confirmed_swing_highs':lambda xs:[],
              'confirmed_swing_lows':lambda xs:[SimpleNamespace(index=60)]}
        with patch.object(A,'_originals',return_value=(fake,None)):
            outputs=[self.produce(rows[:end]) for end in (73,74,75)]
        self.assertEqual([slot(o,'down_break','break_support_no_quick_reclaim')['truth'] for o in outputs],
            ['UNKNOWN','TRUE','FALSE'])
    def test_native_aggregation_keeps_fixed_threshold_and_consumes_ma20(self):
        out=self.produce(is_etf=True)
        for rs in out['signals'].values():
            for r in rs:
                if r['truth']!='NOT_APPLICABLE':r['truth']='FALSE'
        out['signals']['up_price'][0]['truth']='TRUE'
        for r in out['signals']['up_confirm'][:3]:r['truth']='TRUE'
        self.assertEqual(_aggregate(ROOT,out['signals'],'FALSE')['runaway_up'],'FALSE')
        self.assertEqual(_aggregate(ROOT,out['signals'],'TRUE')['runaway_up'],'TRUE')
    def test_decimal_source_value_has_priority_over_float_display(self):
        rows=history();rows[-1]['Close']=100.0;rows[-1]['_source_decimal']={'Close':'100.0000000000000000001'}
        out=self.produce(rows)
        self.assertEqual(slot(out,'up_price','new_20d_close_high')['truth'],'TRUE')
    def test_timeframes_do_not_use_days_as_weeks_or_months(self):
        out=self.produce(history(100))
        self.assertEqual(out['timeframes']['monthly']['state'],'UNKNOWN')
        self.assertLess(out['timeframes']['weekly']['completed_periods'],34)
        self.assertFalse(out['timeframes']['weekly']['calendar_coverage_verified'])
    def test_macd_positive_state_is_not_a_new_flip_event(self):
        rows=history(100)
        for i,r in enumerate(rows):r['Close']=str(Decimal(100)+Decimal(i*i)/100)
        out=self.produce(rows)
        self.assertEqual(slot(out,'right_signals','macd_bear_hist_shrinking_or_positive')['truth'],'FALSE')
    def test_approved_method_never_changes_original_numeric_file(self):
        self.assertEqual(self.profile['reference_numeric_sha256'],'54e80709932753ac4f59344927095f65157f0aa8a46e00fff3b313ea6d5e3d2c')
        self.assertFalse(self.produce()['canonical_fields_modified'])
    def test_existing_bond_route_does_not_receive_stock_candidate_producer(self):
        import on_demand_market_observations as M
        from family_input import digest
        snapshot={'client_id':'SYNTHETIC','source_sha256':'a'*64,'tables':{
            'portfolio_position':[{'instrument_key':'SYNTHETIC_SGOV'}],
            'portfolio_instrument':[{'instrument_key':'SYNTHETIC_SGOV','ticker':'SGOV',
                'identity_state':'KNOWN','instrument_type':'ETF'}]}}
        raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-01T00:00:00Z','verification':{'ready':False}}
        receipt=json.loads((ROOT/'data/market_history/global/manifest.json').read_text())['items']['SGOV']['last_verified_utc']
        at=(datetime.fromisoformat(receipt.replace('Z','+00:00'))+timedelta(seconds=1)).isoformat()
        observed=M.build_member_market_observations(snapshot,[],{'payload':raw,'digest':digest(raw)},
            repo_root=ROOT,evaluation_at=at,approved_rule_profile=self.profile,
            verified_asset_types={'SGOV':'BOND_ETF'})
        self.assertEqual(len(observed['assets']),1)
        self.assertEqual(observed['assets'][0]['approved_technical'],{})
        self.assertTrue(observed['assets'][0]['v75_original_predicates'])
    def test_v10_authority_and_all_reduction_maturity_slots_are_present(self):
        out=self.produce()
        self.assertEqual(out['spec_version'],'1.0')
        self.assertEqual(out['source_commit'],'16318bb078f5d5328b7994fdd54001b4c0c94ced')
        self.assertEqual(out['approval_status'],'APPROVED_FOR_IMPLEMENTATION')
        self.assertEqual([x['id'] for x in out['technical_reduction_signals']],['S'+str(i) for i in range(1,10)])
        self.assertEqual([x['id'] for x in out['left_maturity_signals']],['M'+str(i) for i in range(1,9)])
        self.assertEqual(out['low_td9_score_times4'],'0')
    def test_failed_breakout_fires_once_and_does_not_grant_sell_permission(self):
        rows=history(73)
        rows[69].update(Close='99',Low='98',High='100')
        rows[70].update(Close='101',Low='100',High='102')
        rows[71].update(Close='99.4',Low='99',High='102')
        rows[72].update(Close='99.3',Low='99',High='100')
        fake={'confirmed_swing_highs':lambda xs:[SimpleNamespace(index=50)],
              'confirmed_swing_lows':lambda xs:[]}
        with patch.object(A,'_originals',return_value=(fake,None)):
            first=self.produce(rows[:72]);later=self.produce(rows)
        self.assertEqual(first['technical_reduction_signals'][7]['truth'],'TRUE')
        self.assertEqual(later['technical_reduction_signals'][7]['truth'],'FALSE')
        self.assertIn('CONDITIONS_ONLY',first['technical_reduction_scope'])

if __name__=='__main__':unittest.main()

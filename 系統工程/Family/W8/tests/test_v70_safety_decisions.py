"""Synthetic extension/provenance and original decision-consumer integration."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json,sys
from decimal import Decimal as D
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
import member_v82_analysis as M
import v70_safety_decisions as V
import test_v70_safety_intake as I
import test_member_v82_analysis as F
import test_v82_core_source as C


def extended():
    data=I.fixture();data['snapshot_timestamp']='2026-10-29T22:45:00Z'
    data['extension_approval']={'status':'APPROVED','approved_at':'2026-10-29T22:45:00Z',
        'approved_by':'SYNTHETIC_PM','record_url':'https://synthetic.invalid/extension',
        'scope':'SYNTHETIC_NINE_AUXILIARY_VALUES','candidate_sha256':'c'*64}
    for name in ('treasury_2y','treasury_10y','treasury_30y','pce','core_pce','gdp','sofr','srf','rrp'):
        data['signals'][name].update(value=1,as_of='2026-Q3' if name=='gdp' else '2026-10-28',
            published_at='2026-10-29T18:00:00Z',source='https://synthetic.invalid/official',
            method='SYNTHETIC_REPORTED_VALUE',unit='% SAAR' if name=='gdp' else '%',data_quality='OK',issue_codes=[])
    return data


class SafetyDecisionTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.at='2026-10-29T23:00:00Z';self.data=extended()

    def read(self,data=None,at=None):
        p=self.root/'source.json';p.write_text(json.dumps(self.data if data is None else data))
        self.desc={'local_path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),'source_reference':'SYNTHETIC_V70_APPROVED'}
        return M.read_v70_safety_snapshot(self.desc,at or self.at)

    def test_extension_preserves_original_approval_originals_and_all_seventeen_values(self):
        out=self.read()
        for k,v in self.data.items():self.assertEqual(out[k],v)
        self.assertEqual(len(out['unknown_signals']),11)
        self.assertEqual(sum(v['value'] is not None for v in out['signals'].values()),17)
        self.assertEqual(out['signals']['gdp']['as_of'],'2026-Q3')
        self.assertNotEqual(out['sha256'],out['extension_approval']['candidate_sha256'])

    def test_extension_missing_or_invalid_provenance_rejected(self):
        for key in ('status','approved_by','record_url','scope','candidate_sha256'):
            d=deepcopy(self.data);d['extension_approval'].pop(key)
            with self.subTest(key=key),self.assertRaisesRegex(PermissionError,'EXTENSION_APPROVAL_REQUIRED'):self.read(d)
        for value in ('f'*63,'F'*64,'z'*64,None):
            d=deepcopy(self.data);d['extension_approval']['candidate_sha256']=value
            with self.assertRaisesRegex(PermissionError,'EXTENSION_APPROVAL_REQUIRED'):self.read(d)

    def test_original_approval_and_each_timestamp_order_remain_required(self):
        d=deepcopy(self.data);d['approval']['status']='PENDING'
        with self.assertRaisesRegex(PermissionError,'APPROVAL_REQUIRED'):self.read(d)
        with self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):
            self.read(at='2026-10-29T22:44:59Z')
        d=deepcopy(self.data);d['extension_approval']['approved_at']='2026-10-29T22:44:59Z'
        with self.assertRaisesRegex(PermissionError,'AFTER_EVALUATION'):self.read(d)

    def test_quarter_is_observation_period_only_and_future_or_invalid_quarters_reject(self):
        for value in ('2026-Q4','2026-Q0','2026-Q5','Q3-2026'):
            d=deepcopy(self.data);d['signals']['gdp']['as_of']=value
            with self.subTest(value=value),self.assertRaises((ValueError,PermissionError)):self.read(d)
        d=deepcopy(self.data);d['signals']['gdp']['published_at']='2026-Q3'
        with self.assertRaises(ValueError):self.read(d)

    def test_missing_freshness_does_not_promote_snapshot_capture_to_fresh(self):
        out=V.produce(self.read(),self.at)
        self.assertEqual(out['observed']['gdp']['freshness'],'UNKNOWN')
        self.assertFalse(out['observed']['gdp']['decision_input_eligible'])
        self.assertIn('EXPECTED_RELEASE_COVERAGE_UNKNOWN',out['observed']['gdp']['qualification_issue_codes'])
        self.assertEqual(out['credit']['risk_level'],'UNKNOWN')
        self.assertFalse(out['score_used_as_safety'])

    def test_existing_calendar_contract_and_conservative_date_bound_are_kept_separate(self):
        row=self.data['signals']['treasury_2y'];row.update(published_at='2026-10-28',
            publication_time_precision='DATE_ONLY',publication_eligibility_bound='2026-10-29T04:59:59Z',
            freshness_contract={'release_calendar_reference':'SYNTHETIC_CALENDAR',
                'revision_rule_reference':'SYNTHETIC_VINTAGE','release_id':'SYNTHETIC_RELEASE',
                'expected_release_id':'SYNTHETIC_RELEASE','evaluated_at':self.at})
        out=V.produce(self.read(),self.at)['observed']['treasury_2y']
        self.assertTrue(out['decision_input_eligible']);self.assertEqual(out['freshness'],'FRESH')
        self.assertEqual(out['availability_precision'],'DATE_ONLY')
        self.assertFalse(out['exact_publication_time_verified'])
        row['freshness_contract']['release_id']='SYNTHETIC_OLD_RELEASE'
        out=V.produce(self.read(),self.at)['observed']['treasury_2y']
        self.assertEqual(out['freshness'],'STALE');self.assertFalse(out['decision_input_eligible'])

    def test_sofr_schedule_and_cpi_carry_keep_original_precision_and_policy(self):
        self.data['signals']['sofr']['publication_time_precision']='SCHEDULED_APPROXIMATE'
        self.data['signals']['sofr']['retrieved_at']='2026-10-29T22:59:00Z'
        self.data['signals']['sofr']['source_sha256']='d'*64
        self.data['signals']['core_cpi']['carry_forward']={'policy':'SYNTHETIC_CARRY','observationDate':'2026-09-01'}
        out=V.produce(self.read(),self.at)
        self.assertEqual(out['observed']['sofr']['availability_precision'],'SCHEDULED_APPROXIMATE')
        self.assertFalse(out['observed']['sofr']['exact_publication_time_verified'])
        self.assertEqual(out['observed']['sofr']['available_at_bound'],'2026-10-29T22:59:00Z')
        self.assertIn('KNOWN_BY_CAPTURE',out['observed']['sofr']['availability_basis'])
        self.assertEqual(out['observed']['sofr']['source_sha256'],'d'*64)
        self.assertEqual(out['observed']['sofr']['snapshot_sha256'],out['source_sha256'])
        self.assertEqual(out['observed']['core_cpi']['carry_forward_policy']['policy'],'SYNTHETIC_CARRY')

    def test_existing_credit_producer_short_circuits_and_irrelevant_unknown_does_not_spread(self):
        d={'hy_oas':D(323),'vix':D(23),'move':D(101)}
        out=V._credit_nodes(d)
        self.assertEqual((out['C1'],out['C2'],out['C3']),('TRUE','FALSE','UNKNOWN'))
        self.assertEqual(out['decision_relevant_unknown_ids'],['official_systemic_interruption'])
        self.assertNotIn('gdp',out['required_input_ids'])
        self.assertNotIn('repo_function_deterioration',out['decision_relevant_unknown_ids'])
        d['official_systemic_interruption']=True
        out=V._credit_nodes(d)
        self.assertEqual(out['risk_level'],3)
        self.assertEqual(out['required_input_ids'],['official_systemic_interruption'])

    def test_real_values_are_sent_to_existing_numeric_logic_but_not_used_as_safety_clearance(self):
        self.data['signals']['hy_oas'].update(value=3.23,unit='%')
        self.data['signals']['vix'].update(value=22.91,unit='index points')
        self.data['signals']['move'].update(value=101.28,unit='index points')
        out=V.produce(self.read(),self.at)
        self.assertEqual(out['observational_credit']['C1'],'TRUE')
        self.assertEqual(out['observational_credit']['proven_lower_bound'],1)
        self.assertEqual(out['credit']['risk_level'],'UNKNOWN')
        self.assertEqual(out['observed']['gdp']['json_pointer'],'/signals/gdp')
        self.assertIn('inflation_chain_accelerating',out['macro_pressure']['decision_relevant_unknown_ids'])
        self.assertNotIn('gdp',out['macro_pressure']['decision_relevant_unknown_ids'])

    def test_original_core_sufficiency_and_formal_consumers_receive_the_new_source(self):
        f=F.MemberV82Tests();f.setUp();self.addCleanup(f.doCleanups)
        f.config['market_sources']={s:f.market(s) for s in ('VT','QQQ')}
        f.config['run_binding']={'client_id':f.client,'evaluation_at':f.at,'run_id':'SYNTHETIC_V2_DECISION_BINDING'}
        self.data['signals']['hy_oas'].update(value=3.23,unit='%')
        self.read();f.config['v70_safety_snapshot_source']=self.desc
        before=deepcopy(f.snapshot)
        provider=F.OnDemandAnalysisProvider(F.MemberV82SourceProducer(**f.config),repo_root=ROOT)
        request,runner=provider(f.snapshot,{'question':'SYNTHETIC_ORIGINAL_DECISION_CONSUMER'})
        report=runner.analyze(request)
        for row in report['positions']:
            p=row['macro_observations'];self.assertIn('W8.v10_source_observations.credit_logic',row['call_trace'])
            self.assertEqual(p['source_sha256'],self.desc['sha256'])
            self.assertEqual(row['core_observation']['macro_safety_source_audit'],p)
            self.assertEqual(row['formal_conclusion']['macro_safety_source_audit']['credit'],p['credit'])
            facts={x['name']:x for x in row['core_observation']['actual_inputs']['safety_facts']}
            self.assertIn(self.desc['sha256'],facts['safety.macro']['source_reference'])
            self.assertIn('safety.credit_liquidity',facts)
            self.assertFalse(row['core_observation']['result']['permission']['new_buy_order_permission'])
            self.assertEqual(row['core_observation']['result']['permission']['hard_gate'],'UNKNOWN')
        self.assertEqual(f.snapshot,before);self.assertEqual(request['trade_authorization'],'NONE')

    def test_partial_shared_snapshot_does_not_erase_independent_qualified_core_assertions(self):
        f=C.CoreSourceTests();f.setUp();self.addCleanup(f.doCleanups);f.all_safety()
        from native_asset_source import native_core_observation
        qualified=f.source();before=deepcopy(qualified)
        baseline=native_core_observation(ROOT,f.observed,qualified_core_source=qualified)
        out=native_core_observation(ROOT,f.observed,qualified_core_source=qualified,
            macro_observations=V.produce(self.read(),self.at))
        self.assertEqual(out['result'],baseline['result'])
        self.assertEqual(qualified,before)
        self.assertTrue(out['result']['permission']['new_buy_order_permission'])


def test_source_session_differences_keep_holes_and_independent_short_windows():
    from datetime import date,timedelta
    from decimal import Decimal
    from v70_safety_decisions import _source_difference, _window_test
    end=date(2026,11,20)
    days=[end-timedelta(days=i) for i in reversed(range(36)) if (end-timedelta(days=i)).weekday()<5]
    data={d:Decimal('3') for d in days}
    data[end]=Decimal('3.50')
    data[days[-12]]=None
    five=_source_difference(data,end,5,set())
    twenty=_source_difference(data,end,20,set())
    assert five['difference_bp']=='50.00' and twenty is None
    window={'differences':{'HY':{'5':five,'20':twenty}}}
    from approved_v04_technical import either
    assert either(_window_test(window,'HY',5,50,'ge'), _window_test(window,'HY',20,100,'ge')) is True
    one=_source_difference(data,end,1,set())
    assert one['latest_day']=='2026-11-20' and one['prior_day']=='2026-11-19'


def test_publication_bound_and_current_snapshot_scope(tmp_path):
    import json
    from hashlib import sha256
    from v70_safety_decisions import read_source_window, _window_series, _time
    row={'unit':'percent','source_url':'https://fred.stlouisfed.org/data/T5YIE','published_as_displayed':'2026-11-20 4:03 PM CST',
         'observations':[['2026-11-20','2.18']]}
    assert not _window_series({'T5YIE':row},'T5YIE',row['source_url'],_time('2026-11-20T21:00:00Z'))[0]
    raw=json.dumps({'captured_at':'2026-11-21T11:30:00Z','series':{}}).encode()
    file=tmp_path/'window.json';file.write_bytes(raw)
    source={'local_path':str(file),'sha256':sha256(raw).hexdigest(),'client_id':'member','source_db_sha256':'db',
            'snapshot_sha256':'snapshot','evaluation_day':'2026-11-21'}
    snapshot={'sha256':'snapshot','data_cutoff':'2026-11-21T08:22:00Z'}
    request={'client_id':'member','client_snapshot':{'payload':{'source_sha256':'db'}},'evaluation_at':'2026-11-21T11:29:59Z'}
    assert read_source_window(source,snapshot,request) is None
    assert read_source_window(source,{**snapshot,'sha256':'previous'},request) is None


def test_live_window_uses_its_taipei_day_at_the_real_evaluation_cutoff(tmp_path):
    data={'captured_at':'2026-11-21T16:20:00Z','series':{}}
    file=tmp_path/'window.json';file.write_text(json.dumps(data))
    source={'local_path':str(file),'sha256':sha256(file.read_bytes()).hexdigest(),
        'client_id':'member','source_db_sha256':'db','snapshot_sha256':'pair'}
    snapshot={'sha256':'pair','data_cutoff':'2026-11-21T23:50:00+08:00',
        'signals':{'hy_oas':{},'real_yield':{}}}
    request={'client_id':'member','client_snapshot':{'payload':{'source_sha256':'db'}},
        'evaluation_at':'2026-11-21T16:30:00Z'}
    result=V.read_source_window(source,snapshot,request)
    assert result['execution_day_taipei']=='2026-11-22'
    assert result['economic_cutoff']==snapshot['data_cutoff']
    assert result['available_for_this_run_at']==data['captured_at']
    assert V.read_source_window({**source,'evaluation_day':'2026-11-21'},snapshot,request) is None
    assert V.read_source_window(source,snapshot,{**request,'evaluation_at':'2026-11-21T16:19:00Z'}) is None
    assert V.read_source_window(source,snapshot,{**request,'evaluation_at':'2026-11-22T16:00:00Z'}) is None


def test_decisive_pressure_and_only_fully_determined_credit_reach_original_core():
    from native_asset_source import native_core_observation

    test=SafetyDecisionTests()
    test.setUp()
    case=C.CoreSourceTests()
    case.setUp()
    try:
        snapshot=test.read()
        window={'snapshot_sha256':snapshot['sha256'],'captured_at':test.at,'hy_bp':'352.00',
            'differences':{'BAMLH0A0HYM2':{'1':{'difference_bp':'5'},'5':{'difference_bp':'32'},'20':{'difference_bp':'12'}},
                'TREASURY_REAL_10Y':{'20':{'difference_bp':'13'}},'T5YIE':{'20':{'difference_bp':'-27'}}}}
        p=V.produce(snapshot,test.at,window)
        assert p['macro_pressure']['truth']=='FALSE' and p['credit']['C1']=='TRUE'
        core=native_core_observation(ROOT,case.observed,macro_observations=p)
        facts={f['name']:f for f in core['actual_inputs']['safety_facts']}
        assert facts['safety.macro']['value']=='FALSE' and facts['safety.macro']['pit_status']=='VERIFIED'
        assert facts['safety.credit_liquidity']['value']=='UNKNOWN'
        assert facts['safety.material_events']['value']=='UNKNOWN'
        assert 'safety.macro' not in {g['field_path'] for g in core['input_gaps']}
        assert core['result']['permission']['hard_gate']=='UNKNOWN'

        exact=V._credit_nodes({'hy_oas':D('352'),'vix':D('24'),'move':D('105'),'hy_rapid_widening':False,
            'hy_direction_widening':True,'treasury_function_deterioration':False,
            'repo_function_deterioration':False,'official_systemic_interruption':False})
        p['core_safety_dependencies']['safety.credit_liquidity'].update(
            value=exact['risk_level'],decision_relevant_unknown_ids=exact['decision_relevant_unknown_ids'])
        core=native_core_observation(ROOT,case.observed,macro_observations=p)
        facts={f['name']:f for f in core['actual_inputs']['safety_facts']}
        assert facts['safety.credit_liquidity']['value']==1 and facts['safety.credit_liquidity']['data_quality']=='OK'
        assert 'safety.credit_liquidity' not in {g['field_path'] for g in core['input_gaps']}
        assert core['result']['permission']['hard_gate']=='UNKNOWN'
    finally:
        case.doCleanups()
        test.doCleanups()

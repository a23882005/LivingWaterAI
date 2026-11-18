"""Auxiliary JSON provenance, cutoff and private-writer failure regressions; synthetic only."""
import copy,csv,datetime as dt,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import v70_family_sources as sources
from v70_family_sources import stamp,canonical,sha
from v70_family_drive import checked_update,isolation_roundtrip,Drive,BASELINE_NAME
from v70_family_pipeline import validate_candidate,verify_formal_basis,project_publication_context,apply_formal_authorization

CUTOFF='2026-11-17T14:43:12+08:00'
RECORD={'sha256':'a'*64,'retrieved_at':'2026-11-17T12:00:00Z'}
URL='https://official.invalid/test'

def baseline():
    signals={k:{'signal_name':k,'value':None,'unit':None,'level':None,'direction':None,'speed':None,'data_quality':'UNKNOWN','issue_detail':'missing','coverage':{}} for k in sources.EXPECTED}
    for i in range(8):signals['legacy'+str(i)]={'value':i,'data_quality':'OK'}
    return {'schema_version':'V70.3/family-macro-safety-v2','data_cutoff':CUTOFF,'feed_asof_utc':'2026-11-17T06:43:12Z','feed_sha256':'x','source_commit':'a','health_score':60,'daily_record_id':'id','score_status':'FORMAL_VALID','upstream_verification':{'ready':True,'requiredScoringIndicatorsValidated':22},'upstream_publication':{'mode':'FORMAL','scoringAllowed':True},'signals':signals,'v70_indicators':{str(i):{'value':i} for i in range(29)},'v70_judgments':{'score':60}}

def intake(base):
    return {'baseline_sha256':sha(canonical(base)),'cutoff':CUTOFF,'created_at':'2026-11-17T12:00:00Z','registry_version':'synthetic','source_registry':[],'supplements':{k:{'value':None,'reason':'not qualified'} for k in sources.EXPECTED}}

class SourceParserTests(unittest.TestCase):
    def test_bea_yoy_and_saar_are_distinct(self):
        raw=b'EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Thursday, October 29, 2026. From the same month one year ago, the PCE price index for September increased 3.6 percent. Excluding food and energy, the PCE price index increased 3.1 percent from one year ago.'
        self.assertEqual(sources.parse_bea(raw,URL,RECORD,'pce',stamp(CUTOFF))['value'],3.6)
        self.assertEqual(sources.parse_bea(raw,URL,RECORD,'core_pce',stamp(CUTOFF))['value'],3.1)
        gdp=b'EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Thursday, October 29, 2026. GDP (Advance Estimate), 3rd Quarter 2026. Real gross domestic product (GDP) increased at an annual rate of 3.4 percent.'
        out=sources.parse_bea(gdp,URL,RECORD,'gdp',stamp(CUTOFF));self.assertEqual(out['growth_basis'],'QoQ_SAAR');self.assertEqual(out['estimate_vintage'],'advance')

    def test_bea_release_after_cutoff_is_rejected(self):
        raw=b'EMBARGOED UNTIL RELEASE AT 8:30 a.m. EST, Wednesday, November 18, 2026.'
        with self.assertRaisesRegex(ValueError,'RELEASE_AFTER_CUTOFF'):sources.parse_bea(raw,URL,RECORD,'pce',stamp(CUTOFF))

    def test_future_bea_discovery_checks_release_time_and_excludes_late_release(self):
        old='https://www.bea.gov/news/2026/personal-income-and-outlays-september-2026'
        new='https://www.bea.gov/news/2026/personal-income-and-outlays-october-2026'
        class Saved:
            def get(self,url):
                if url.endswith('current-releases'):raw=('<a href="'+new+'">new</a><a href="https://untrusted.invalid/news/2026/personal-income-and-outlays-x">ignore</a>').encode()
                else:raw=('EMBARGOED UNTIL RELEASE AT 8:30 a.m. EST, '+('November 25, 2026' if url==new else 'October 29, 2026')).encode()
                return 200,raw,RECORD
        source={'url':old}
        self.assertEqual(sources.discover_release(source,'pce',stamp('2026-11-25T13:29:59Z'),Saved()),old)
        self.assertEqual(sources.discover_release(source,'pce',stamp('2026-11-25T13:30:00Z'),Saved()),new)

    def test_frozen_first_round_does_not_discover_later_current_release(self):
        class NoFetch:
            def get(self,url):raise AssertionError('frozen snapshot must retain dated source')
        self.assertEqual(sources.discover_release({'url':URL},'cpi',stamp(CUTOFF),NoFetch()),URL)

    def test_backup_reasons_distinguish_http_error_and_basis_mismatch(self):
        self.assertIn('404',sources.backup_qualification({'website':'www.federalreserve.gov'},'treasury_2y',{'http_status':404}))
        self.assertIn('BASIS_MISMATCH',sources.backup_qualification({'website':'www.cmegroup.com'},'sofr',{'http_status':200}))

    def test_cpi_mom_does_not_replace_missing_yoy(self):
        raw=b'Transmission embargoed until 8:30 a.m. (ET) Tuesday, November 10, 2026. CONSUMER PRICE INDEX - OCTOBER 2026. CPI-U) increased 0.4 percent on a seasonally adjusted basis. BLS cannot publish 12-month percent changes. CPI-U) increased to an index level of 337.511.'
        out=sources.parse_cpi(raw,URL,RECORD,stamp(CUTOFF));self.assertIsNone(out['value']);self.assertEqual(out['supporting_observations']['published_mom_sa']['value'],.4)

    def test_treasury_same_snapshot_and_date_precision(self):
        raw=b'Date,2 Yr,10 Yr,30 Yr\n11/17/2026,9,10,11\n11/16/2026,2,2.3,3.1\n'
        base={'v70_indicators':{'m01':{'as_of':'2026-11-16','value':.3}}}
        out=sources.parse_treasury(raw,URL,RECORD,stamp(CUTOFF),'2 Yr',base)
        self.assertEqual(out['value'],2);self.assertEqual(out['as_of'],'2026-11-16');self.assertEqual(out['publication_time_precision'],'DATE_ONLY')
        base['v70_indicators']['m01']['value']=.9
        with self.assertRaisesRegex(ValueError,'CONFLICT'):sources.parse_treasury(raw,URL,RECORD,stamp(CUTOFF),'2 Yr',base)

    def test_sofr_next_business_publication_not_observation_date(self):
        raw=json.dumps({'refRates':[{'type':'SOFR','effectiveDate':'2026-11-16','percentRate':9},{'type':'SOFR','effectiveDate':'2026-11-13','percentRate':0}]}).encode()
        out=sources.parse_sofr(raw,URL,RECORD,stamp(CUTOFF));self.assertEqual(out['value'],0);self.assertEqual(out['as_of'],'2026-11-13');self.assertEqual(out['published_at'],'2026-11-16T13:00:00+00:00')

    def test_sofr_bank_holiday_does_not_publish_early(self):
        raw=json.dumps({'refRates':[{'type':'SOFR','effectiveDate':'2026-11-10','percentRate':1}]}).encode()
        with self.assertRaisesRegex(ValueError,'AFTER_CUTOFF'):sources.parse_sofr(raw,URL,RECORD,stamp('2026-11-12T12:59:59Z'))

    def operation(self,ident='A',amount=0,kind='Reverse Repo'):
        return {'operationId':ident,'operationType':kind,'operationMethod':'Full Allotment','term':'Overnight','auctionStatus':'Results','lastUpdated':'2026-11-16 13:45:22','operationDate':'2026-11-16','totalAmtAccepted':amount,'details':[{'securityType':'Treasury','amtAccepted':amount}]}

    def parse_ops(self,ops,kind='rrp',**extra):return sources.parse_operations(json.dumps({'repo':{'operations':ops,**extra}}).encode(),URL,RECORD,stamp(CUTOFF),kind)

    def test_operation_true_zero_and_identical_duplicates(self):
        x=self.operation();out=self.parse_ops([x,copy.deepcopy(x)]);self.assertEqual(out['value'],0);self.assertEqual(out['operation_ids'],['A'])

    def test_two_srf_operations_sum_principal_not_market_repo_rate(self):
        out=self.parse_ops([self.operation('A',1000000,'Repo'),self.operation('B',1000000,'Repo')],'srf');self.assertEqual(out['value'],.002);self.assertEqual(out['unit'],'USD bn');self.assertIn('flow',out['method'])

    def test_conflicting_duplicate_and_unreconciled_total_fail(self):
        x=self.operation('A',1);y=self.operation('A',2)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.parse_ops([x,y])
        x['totalAmtAccepted']=2
        with self.assertRaisesRegex(ValueError,'TOTAL_MISMATCH'):self.parse_ops([x])

    def test_future_operations_and_incomplete_query_do_not_become_zero(self):
        x=self.operation();x['lastUpdated']='2026-11-17 08:30:00'
        with self.assertRaisesRegex(ValueError,'NO_QUALIFIED'):self.parse_ops([x])
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):self.parse_ops([self.operation()],hasMore=True)

class CandidateTests(unittest.TestCase):
    def approved(self):
        base=baseline();base['approval']={'status':'APPROVED','role':'PM','approved_at':'2026-11-17T01:00:00Z','scope':'original snapshot'}
        base['extension_approval']={'status':'APPROVED','approved_by':'PM','approved_at':'2026-11-18T01:00:00Z','scope':'accepted first-round numeric fields and UNKNOWNs','record_url':'https://example.invalid/pm-record','candidate_sha256':'accepted-original'}
        base['signals']['sofr'].update(value=1,unit='%',as_of='2026-11-12',published_at='2026-11-13T13:00:00Z',source=URL,data_quality='OK')
        return base

    def test_formal_authorization_reuses_pm_scope_without_claiming_current_human_review(self):
        base=self.approved();pack=intake(base);out=sources.merge_candidate(base,pack);apply_formal_authorization(out,base)
        self.assertEqual(out['extension_approval']['status'],'APPROVED');self.assertEqual(out['extension_approval']['approved_at'],base['extension_approval']['approved_at']);self.assertFalse(out['extension_approval']['human_review_of_current_snapshot'])
        self.assertEqual(out['extension_approval']['original_round1_approval'],base['extension_approval']);self.assertEqual(out['approval']['original_snapshot_approval'],base['approval']);validate_candidate(out,base,pack,formal=True)

    def test_new_numeric_series_remains_unknown_until_pm_source_adoption(self):
        base=self.approved();pack=intake(base);pack['supplements']['cpi']={'value':2,'unit':'%','as_of':'2026-10-01','published_at':'2026-11-10T13:30:00Z','source':URL};out=sources.merge_candidate(base,pack);apply_formal_authorization(out,base)
        self.assertIsNone(out['signals']['cpi']['value']);self.assertEqual(out['signals']['cpi']['data_quality'],'UNKNOWN');self.assertIn('SOURCE_ADOPTION_PENDING_PM',out['signals']['cpi']['issue_codes']);validate_candidate(out,base,pack,formal=True)

    def test_formal_approval_does_not_accept_unapproved_baseline_or_forged_metadata(self):
        base=baseline();out=sources.merge_candidate(base,intake(base))
        with self.assertRaisesRegex(ValueError,'PM_APPROVED_EXTENSION_REQUIRED'):apply_formal_authorization(out,base)
        base=self.approved();pack=intake(base);out=sources.merge_candidate(base,pack);apply_formal_authorization(out,base);out['extension_approval']['approved_at']='2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'FORMAL_APPROVAL_SCOPE_MISMATCH'):validate_candidate(out,base,pack,formal=True)

    def test_repeated_formal_refresh_keeps_original_approval_and_pm_activation_acceptance(self):
        base=self.approved();out=sources.merge_candidate(base,intake(base));apply_formal_authorization(out,base);out['extension_approval']['activation_acceptance']='ACCEPTED_BY_PM'
        second=sources.merge_candidate(out,intake(out));apply_formal_authorization(second,out)
        self.assertEqual(second['extension_approval']['original_round1_approval'],base['extension_approval']);self.assertEqual(second['extension_approval']['activation_acceptance'],'ACCEPTED_BY_PM');self.assertEqual(second['approval']['original_snapshot_approval'],base['approval'])

    def test_nonfinite_json_is_rejected_before_private_write(self):
        base=baseline();pack=intake(base);out=sources.merge_candidate(base,pack);out['health_score']=float('nan')
        with self.assertRaises(ValueError):validate_candidate(out,base,pack)

    def test_next_formal_context_preserves_numeric_policy_bounds_and_refreshes_derived_date(self):
        base=baseline();base['v70_indicators']={'m06_rate':{},'m21':{'as_of':'2026-09-01'}};base['v70_judgments']={'score':60};base['signals']={'fed_policy':{'v70_indicator_id':'m06_rate'},**{k:{} for k in sources.EXPECTED}}
        feed={'asOf':'2026-12-01T03:00:00Z','publication':{},'verification':{},'sourceSnapshot':{},'indicators':{'m06_rate':{'value':3.875,'dataDate':'2026-09-17','lowerBound':{'value':3.75},'upperBound':{'value':4},'publicationDate':'2026-09-16'}},'derived':{'m21':{'value':0}},'leiHistory':[{'observation_date':'2026-10-01','retrieved_at':'2026-12-01T01:00:00Z'}]}
        row={'health_score':60,'daily_record_id':'new','source_commit':'new','v70_version':'V70','run_timestamp_utc':'2026-12-01T03:01:00Z'};state={'judgments':{'score':60},'risk':{}}
        out=project_publication_context(base,feed,row,state,'hash')
        self.assertEqual(out['signals']['fed_policy']['target_range'],{'lower':3.75,'upper':4,'unit':'%'})
        self.assertEqual(out['signals']['fed_policy']['statement_date'],'2026-09-16');self.assertEqual(out['v70_indicators']['m21']['as_of'],'2026-10-01');self.assertEqual(base['v70_indicators']['m21']['as_of'],'2026-09-01')

    def test_preserve_original_29_judgments_8_signals_and_unknown_reasons(self):
        base=baseline();pack=intake(base);out=sources.merge_candidate(base,pack)
        self.assertEqual(out['v70_indicators'],base['v70_indicators']);self.assertEqual(out['v70_judgments'],base['v70_judgments'])
        for i in range(8):self.assertEqual(out['signals']['legacy'+str(i)],base['signals']['legacy'+str(i)])
        self.assertTrue(all(out['signals'][k]['issue_detail'] for k in sources.EXPECTED));self.assertEqual(base,baseline())

    def test_zero_value_is_filled_without_inventing_judgment_or_pm_approval(self):
        base=baseline();pack=intake(base);pack['supplements']['sofr']={'value':0,'unit':'%','as_of':'2026-11-13','published_at':'2026-11-16T13:00:00Z','source':URL}
        out=sources.merge_candidate(base,pack);self.assertEqual(out['signals']['sofr']['value'],0);self.assertEqual(out['signals']['sofr']['data_quality'],'OK');self.assertIsNone(out['signals']['sofr']['level']);self.assertEqual(out['extension_approval']['status'],'PENDING_HIGHEST_PM_ACCEPTANCE');validate_candidate(out,base,pack)

    def test_changed_baseline_or_cutoff_is_not_merged(self):
        base=baseline();pack=intake(base);pack['baseline_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'HASH'):sources.merge_candidate(base,pack)
        pack=intake(base);pack['cutoff']='2026-11-18T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'CUTOFF'):sources.merge_candidate(base,pack)

    def test_existing_qualified_value_survives_missing_refresh(self):
        base=baseline();base['signals']['sofr'].update(value=1,unit='%',as_of='2026-11-13',data_quality='OK');pack=intake(base);out=sources.merge_candidate(base,pack)
        self.assertEqual(out['signals']['sofr'],base['signals']['sofr'])

    def test_newer_comparable_value_can_refresh_previous_value(self):
        base=baseline();base['signals']['sofr'].update(value=1,unit='%',as_of='2026-11-12',data_quality='OK');pack=intake(base);pack['supplements']['sofr']={'value':2,'unit':'%','as_of':'2026-11-13','published_at':'2026-11-16T13:00:00Z','source':URL};out=sources.merge_candidate(base,pack);self.assertEqual(out['signals']['sofr']['value'],2)

    def test_publisher_rejects_future_release_even_if_intake_is_tampered(self):
        base=baseline();pack=intake(base);pack['supplements']['sofr']={'value':1,'unit':'%','as_of':'2026-11-16','published_at':'2026-11-17T13:00:00Z','source':URL};out=sources.merge_candidate(base,pack)
        with self.assertRaisesRegex(ValueError,'AFTER_CUTOFF'):validate_candidate(out,base,pack)

    def test_registry_covers_exact_twenty_with_three_different_sites(self):
        config=json.loads(sources.CONFIG.read_text());self.assertEqual({r['signal'] for r in config['signals']},sources.EXPECTED)
        for r in config['signals']:
            sites={'.'.join(s['website'].split('.')[-2:]) for s in r['sources']};self.assertEqual(len(sites),3)
            self.assertEqual([s['rank'] for s in r['sources']],['primary','backup_1','backup_2'])

class FakeDrive:
    private=staticmethod(Drive.private)
    def __init__(self):self.objects={};self.counter=0;self.fail_replace=False;self.conflict=False
    def find(self,name,parent=None,required=False):
        return next((copy.deepcopy(v['meta']) for v in self.objects.values() if v['meta']['name']==name),None)
    def create(self,name,parent,data,mime_type='application/json'):
        self.counter+=1;ident=str(self.counter);m={'id':ident,'name':name,'parents':[parent],'shared':False,'ownedByMe':True,'mimeType':mime_type};self.objects[ident]={'meta':m,'data':data};return copy.deepcopy(m)
    def read(self,ident):return self.objects[ident]['data']
    def backup(self,meta,parent):
        m=self.create(meta['name']+'.backup',parent,self.read(meta['id']))
        if self.conflict:self.objects[meta['id']]['data']=json.dumps({'cutoff':'2026-11-19T00:00:00Z'}).encode()
        return m
    def replace(self,ident,data):
        if self.fail_replace:raise RuntimeError('NETWORK_FAILURE')
        self.objects[ident]['data']=data

def document(day='2026-11-17T06:43:12Z',value=1):return {'cutoff':day,'value':value}

class PrivateWriterTests(unittest.TestCase):
    def setUp(self):self.drive=FakeDrive();self.parent='private';self.name='candidate.json'
    def test_create_and_idempotent_retry_have_one_target(self):
        a=checked_update(self.drive,self.name,self.parent,document());b=checked_update(self.drive,self.name,self.parent,document());self.assertEqual(a['file_id'],b['file_id']);self.assertEqual(b['status'],'UNCHANGED_IDEMPOTENT');self.assertEqual(len(self.drive.objects),1)
    def test_older_snapshot_cannot_replace_newer(self):
        a=checked_update(self.drive,self.name,self.parent,document());before=self.drive.read(a['file_id'])
        with self.assertRaisesRegex(RuntimeError,'OLDER'):checked_update(self.drive,self.name,self.parent,document('2026-11-16T00:00:00Z'))
        self.assertEqual(self.drive.read(a['file_id']),before)
    def test_failed_verification_restores_exact_previous_bytes(self):
        a=checked_update(self.drive,self.name,self.parent,document());before=self.drive.read(a['file_id'])
        def fail(_):raise RuntimeError('verification failure')
        with self.assertRaisesRegex(RuntimeError,'verification failure'):checked_update(self.drive,self.name,self.parent,document(value=2),verify=fail)
        self.assertEqual(self.drive.read(a['file_id']),before);self.assertEqual(len(self.drive.objects),2)
    def test_network_failure_keeps_previous_target(self):
        a=checked_update(self.drive,self.name,self.parent,document());before=self.drive.read(a['file_id']);self.drive.fail_replace=True
        with self.assertRaisesRegex(RuntimeError,'NETWORK'):checked_update(self.drive,self.name,self.parent,document(value=2))
        self.assertEqual(self.drive.read(a['file_id']),before)
    def test_changed_target_during_backup_is_not_overwritten(self):
        a=checked_update(self.drive,self.name,self.parent,document());self.drive.conflict=True
        with self.assertRaisesRegex(RuntimeError,'CONFLICT'):checked_update(self.drive,self.name,self.parent,document(value=2))
        self.assertEqual(json.loads(self.drive.read(a['file_id']))['cutoff'],'2026-11-19T00:00:00Z')
    def test_formal_target_is_disabled_by_default(self):
        with self.assertRaisesRegex(RuntimeError,'PM_ENABLEMENT'):checked_update(self.drive,BASELINE_NAME,self.parent,document())
        self.assertEqual(self.drive.objects,{})
    def test_real_isolation_protocol_includes_failure_and_recovery(self):
        result=isolation_roundtrip(self.drive,self.parent,document());self.assertEqual(result['status'],'WRITE_READBACK_FAILURE_RECOVERY_PASS')

class FormalBasisTests(unittest.TestCase):
    def test_hash_gate_and_daily_record_must_all_match(self):
        base=baseline();feed={'asOf':base['feed_asof_utc'],'verification':{'ready':True,'requiredScoringIndicatorsValidated':22},'publication':{'mode':'FORMAL'}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);raw=json.dumps(feed).encode();(p/'feed.json').write_bytes(raw);base['feed_sha256']=sha(raw)
            fields=['daily_record_id','feed_sha256','score_status','health_score']
            with (p/'daily.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow(dict(zip(fields,['id',base['feed_sha256'],'FORMAL_VALID','60'])))
            self.assertIn('PASS',verify_formal_basis(base,p/'daily.csv',p/'feed.json')['status'])
            base['upstream_publication']['mode']='DATA_ONLY'
            with self.assertRaisesRegex(ValueError,'FORMAL_22'):verify_formal_basis(base,p/'daily.csv',p/'feed.json')

if __name__=='__main__':unittest.main()

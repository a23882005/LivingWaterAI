"""Synthetic source/approval seam; original Family tests own financial maths."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json,sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from member_financial_chain import read,calculate
from family_input import digest


class FinancialSourceTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'source.json'
        client='fam_'+'a'*32;at='2026-10-29T00:00:00Z'
        snapshot={'schema_version':'Family.W5.W1Snapshot.v1','client_id':client,'source_sha256':'a'*64,'tables':{}}
        target={'target_version':2,'payload':{'draft':{'target_lines':[{'instrument_id':'SYNTHETIC_ASSET',
            'ticker':'SYNTHETIC_ASSET','weight':{'value':'1'},'target_amount':{'value_state':'KNOWN','amount':'1000','currency':'USD'}}]}}}
        self.parent={'client_id':client,'run_id':'SYNTHETIC_RUN','evaluation_at':at,'question':'SYNTHETIC_QUESTION',
            'confirmed_target':target,'client_snapshot':{'payload':snapshot}}
        child=deepcopy(self.parent);child.update(trade_authorization='NONE',owner={'client_id':client,
            'account':'SYNTHETIC_ACCOUNT','broker':'SYNTHETIC_BROKER','currency':'USD','funding_domain':'SYNTHETIC_DOMAIN'})
        child['native_bundle']={'stock_request':{'asset_context':{'asset':{'asset_id':'SYNTHETIC_ASSET'}}}}
        self.pack={'request':child,'trusted_context':{'client_id':client,'trade_authorization':'NONE',
            'native_binding':{'schema_version':'Family.W5.NativeBinding.v1','data_provenance':'SOURCE_BACKED',
                'source_reference':'SYNTHETIC_TEST_SOURCE'}},'source_metadata':{'client_id':client,'run_id':'SYNTHETIC_RUN',
            'source_db_sha256':'a'*64,'market_data_provenance':'SOURCE_BACKED','market_verification':True,'market_as_of':at}}
        self.data={'schema_version':'Family.W8.MemberV82FinancialSource.v1','client_id':client,
            'run_id':'SYNTHETIC_RUN','evaluation_at':at,'asset_id':'SYNTHETIC_ASSET','source_db_sha256':'a'*64,
            'available_at':at,'source_reference':'SYNTHETIC_SOURCE_ONLY','pack':self.pack}

    def descriptor(self):
        self.path.write_text(json.dumps(self.data))
        return {'local_path':str(self.path),'sha256':sha256(self.path.read_bytes()).hexdigest()}

    def test_exact_bound_pack_is_retained_without_source_mutation(self):
        before=deepcopy(self.data);result=read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')
        self.assertEqual(result,self.pack);self.assertEqual(self.data,before)

    def test_owner_run_snapshot_and_native_asset_cannot_be_swapped(self):
        for key,value in [('run_id','OTHER'),('evaluation_at','2026-10-30T00:00:00Z')]:
            old=self.pack['request'][key];self.pack['request'][key]=value
            with self.subTest(key=key),self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')
            self.pack['request'][key]=old
        self.pack['request']['native_bundle']['stock_request']['asset_context']['asset']['asset_id']='OTHER'
        with self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')

    def test_absent_money_base_and_changed_approval_cannot_be_filled_by_bundle(self):
        for change in [{'amount':'2000'},{'currency':'TWD'},{'value_state':'UNKNOWN','amount':None}]:
            money=self.pack['request']['confirmed_target']['payload']['draft']['target_lines'][0]['target_amount']
            old=deepcopy(money);money.update(change)
            with self.subTest(change=change),self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')
            money.clear();money.update(old)
        self.parent['confirmed_target']['payload']['draft']['target_lines'][0]['target_amount']['value_state']='UNKNOWN'
        with self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')

    def test_source_hash_cutoff_and_recursive_analysis_are_rejected(self):
        descriptor=self.descriptor();descriptor['sha256']='f'*64
        with self.assertRaises(PermissionError):read(descriptor,self.parent,'SYNTHETIC_ASSET')
        self.data['available_at']='2026-10-31T00:00:00Z'
        with self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')
        self.data['available_at']=self.parent['evaluation_at'];self.pack['member_v82_report']={}
        with self.assertRaises(PermissionError):read(self.descriptor(),self.parent,'SYNTHETIC_ASSET')

    def calculate(self,result):
        seen=[]
        def factory(root,context_provider):
            class Runner:
                def analyze(_,request):seen.append(request);return deepcopy(result)
            return Runner()
        value=calculate(ROOT,self.descriptor(),self.parent,'SYNTHETIC_ASSET',runner_factory=factory)
        self.assertEqual(seen,[self.pack['request']]);return value

    def test_original_c7_error_is_retained_not_promoted_to_mentor(self):
        value=self.calculate({'status':'DATA_UNAVAILABLE','issue_codes':[
            {'code':'C7_RETURN_TO_V70','field_path':'asset_framework.STOCK'}]})
        self.assertEqual(value['issue_codes'][0]['code'],'C7_RETURN_TO_V70')
        self.assertFalse(value['full_native_pipeline_complete']);self.assertIsNone(value['mentor'])

    def test_positive_local_result_requires_drive_readback_even_with_native_mentor(self):
        value=self.calculate({'status':'OK','mentor':{'schema_version':'SYNTHETIC_NATIVE_MENTOR'},
            'native_result':{'status':'NATIVE_PIPELINE_COMPLETE','formal_deployment_ready':True,
                'stock_result':{'canonical_v82_output':{'canonical_analysis':{
                    'execution_amount':{'value':{'amount':'10','currency':'USD'}}}}}}})
        self.assertTrue(value['full_native_pipeline_complete']);self.assertIsNotNone(value['mentor'])
        self.assertFalse(value['formal_deployment_ready'])
        self.assertEqual(value['drive_persistence_status'],'PENDING_DRIVE_BACKUP_UPDATE_READBACK')

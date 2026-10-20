"""Authorized staging dispatcher. W7 supplies production authority/persistence.

The provider must come from the operator, never from the incoming request.
It supplies current identity/versions and the digest of a reviewed native
input mapping. This module does not fabricate missing source mappings.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
from family_boundary import BoundaryError,prepare_input,require
from family_input import digest
from native_pipeline import run_native_pipeline
from mentor_bridge import explain_native
from recovery_bridge import StagingAnalysisStore,RecoveryError,input_digest
from verify_dependencies import verify
from stock_source_bridge import bind_stock_source


class FamilyRunner:
    def __init__(self,repo_path,*,context_provider):
        self.repo_path=Path(repo_path).resolve()
        self.context_provider=context_provider
        verify(self.repo_path)
        path=Path(__file__).parent/'vendor/w2/runtime/c_configuration_core/work21/recovery.py'
        spec=importlib.util.spec_from_file_location('w5_runner_w2_recovery',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.store=StagingAnalysisStore(module)

    def _validate(self,request):
        ctx=deepcopy(self.context_provider())
        prepared=prepare_input(request,trusted_context=ctx)
        bundle=request.get('native_bundle')
        require(isinstance(bundle,dict),'NATIVE_INPUT_MAPPING_REQUIRED','native_bundle',status='DATA_UNAVAILABLE')
        binding=ctx.get('native_binding',{})
        require(binding.get('schema_version')=='Family.W5.NativeBinding.v1','NATIVE_BINDING_REQUIRED','trusted_context.native_binding',status='DATA_UNAVAILABLE')
        require(binding.get('request_digest')==prepared.input_digest,'NATIVE_REQUEST_BINDING_MISMATCH','native_binding.request_digest')
        require(binding.get('bundle_digest')==digest(bundle),'NATIVE_BUNDLE_DIGEST_MISMATCH','native_binding.bundle_digest')
        require(binding.get('target_binding_digest')==prepared.payload['target_binding']['binding_digest'],'NATIVE_TARGET_BINDING_MISMATCH','native_binding.target_binding_digest')
        require(binding.get('family_owner')==request['owner'],'NATIVE_FAMILY_OWNER_MISMATCH','native_binding.family_owner')
        require(binding.get('data_provenance') in ('SYNTHETIC','SOURCE_BACKED') and bool(binding.get('source_reference')),'NATIVE_MAPPING_PROVENANCE_REQUIRED','native_binding')
        for branch in ('stock_request','bond_request'):
            w3=bundle[branch]['work3_handoff']
            require(w3['run_id']==request['run_id']==bundle[branch]['run_id'],'NATIVE_RUN_MISMATCH',branch)
            require(w3['client_state_context']['payload']['client_id']==request['client_id'],'NATIVE_CLIENT_MISMATCH',branch)
            require(w3['owner']==binding.get('native_owner') and w3['currency']==request['owner']['currency'],'NATIVE_OWNER_MISMATCH',branch)
            require(w3['final_target']['allocation_id']==prepared.payload['target_binding']['allocation_id'],'NATIVE_ALLOCATION_MISMATCH',branch)
            evidence=request['confirmed_target']['payload']['confirmation_evidence']
            proof=w3['final_target']['confirmation_proof']
            require(all(proof.get(k)==evidence.get(k) for k in ('confirmed_at','confirmed_by')),
                    'NATIVE_CONFIRMATION_PROOF_MISMATCH',branch)
        require(bundle['stock_evidence']['evaluated_at']==request['evaluation_at'],'NATIVE_EVALUATION_TIME_MISMATCH','stock_evidence.evaluated_at')
        prepared.payload['stock_source']=bind_stock_source(request,prepared,binding)
        return prepared,ctx

    def _compute(self,request):
        prepared,ctx=self._validate(request)
        native=run_native_pipeline(self.repo_path,deepcopy(request['native_bundle']),prepared.payload['stock_source'])
        require(native.get('status')=='NATIVE_PIPELINE_COMPLETE','NATIVE_RESULT_INCOMPLETE','native.status',status='DATA_UNAVAILABLE')
        u=native['unified_result']
        mentor=explain_native(self.repo_path,native['work9_request'],u,trusted_context={
            'client_id':request['client_id'],'run_id':request['run_id'],'owner':u['owner'],'currency':u['currency'],
            'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','runtime_mode':'REAL_DETERMINISTIC',
            'data_provenance':ctx['native_binding']['data_provenance'],'expected_result_digest':digest(u)})
        return {'schema_version':'Family.W5.result.v1','status':'OK','client_id':request['client_id'],
            'request_id':request['request_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
            'input_digest':input_digest(request),'target_binding':deepcopy(prepared.payload['target_binding']),
            'expected_versions':deepcopy(request['expected_versions']),'evaluation_at':request['evaluation_at'],
            'runtime_mode':'REAL_DETERMINISTIC','data_provenance':ctx['native_binding']['data_provenance'],
            'native_result':native,'mentor':mentor,'call_trace':native['call_trace'],
            'storage_scope':'ISOLATED_TEST_STAGING','production':'HOLD','trade_action':'NO_TRADE'}

    def analyze(self,request,*,timeout_seconds=30):
        frozen=deepcopy(request)
        try:
            response=self.store.analyze(frozen,validate=self._validate,compute=self._compute,timeout_seconds=timeout_seconds)
            return {**response['result'],'replay_status':response['status']}
        except BoundaryError as error:
            return self._error(frozen,error.status,error.issue)
        except RecoveryError as error:
            return self._error(frozen,'BLOCKED',{'code':str(error),'producer':'W5','field_path':'recovery'})
        except (KeyError,TypeError,ValueError) as error:
            # Preserve native error code without echoing possibly private data.
            code=getattr(error,'code','CONTRACT_ERROR')
            return self._error(frozen,'ERROR',{'code':code,'producer':'NATIVE_OR_W5','field_path':'dispatch'})

    @staticmethod
    def _error(request,status,issue):
        return {'schema_version':'Family.W5.result.v1','status':status,
            'request_id':request.get('request_id'),'run_id':request.get('run_id'),
            'issue_codes':[issue],'canonical_result':None,'mentor':None,
            'storage_scope':'ISOLATED_TEST_STAGING','production':'HOLD','trade_action':'NO_TRADE'}

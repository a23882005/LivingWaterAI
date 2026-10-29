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
from bond_source_bridge import bind_bond_sources
from macro_source_bridge import validate_macro_consumers
from funding_bridge import bind_funding_source
from position_source_bridge import bind_position_values,bind_stock_protection
from target_source_bridge import bind_target_source
from bond_target_bridge import bind_bond_targets
from v70_source_bridge import bind_v70_source
from c7_engine import bind_c7_source
from family_technical_bridge import bind_technical_source,apply_technical_source


class FamilyRunner:
    def __init__(self,repo_path,*,context_provider,native_source_report=None):
        self.repo_path=Path(repo_path).resolve()
        self.context_provider=context_provider
        self.native_source_report=deepcopy(native_source_report)
        verify(self.repo_path)
        path=Path(__file__).parent/'vendor/w2/runtime/c_configuration_core/work21/recovery.py'
        spec=importlib.util.spec_from_file_location('w5_runner_w2_recovery',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.store=StagingAnalysisStore(module)

    def _validate(self,request):
        ctx=deepcopy(self.context_provider())
        prepared=prepare_input(request,trusted_context=ctx)
        from v75_pred007_source import bind as bind_pred007
        amendment=bind_pred007(request,ctx)
        from native_target_source import bind as bind_native_targets
        native_targets=bind_native_targets(request,ctx)
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
        # Protection and target/drift consumers require a ready C7 framework.
        # Report the original C7 refusal before accessing absent target rows.
        prepared.payload['c7_computation']=bind_c7_source(self.repo_path,request,ctx)
        require(bundle['stock_evidence']['evaluated_at']==request['evaluation_at'],'NATIVE_EVALUATION_TIME_MISMATCH','stock_evidence.evaluated_at')
        prepared.payload['technical_intake']=bind_technical_source(self.repo_path,request,ctx) if ctx.get('technical_source') is not None else None
        prepared.payload['stock_source']=bind_stock_source(request,prepared,binding)
        prepared.payload['family_sources']={'funding':bind_funding_source(request,ctx),
            'macro':validate_macro_consumers(request),'bond':bind_bond_sources(request,prepared,binding)}
        if amendment is not None:prepared.payload['family_sources']['pred007_amendment']=amendment
        values=bind_position_values(request,prepared,ctx)
        prepared.payload['family_sources']['valuation']=values
        prepared.payload['family_sources']['protection']=bind_stock_protection(request,prepared,ctx,values)
        prepared.payload['family_sources']['target']=bind_target_source(request,projection=native_targets)
        prepared.payload['family_sources']['bond_targets']=bind_bond_targets(request,prepared,binding,projection=native_targets)
        prepared.payload['family_sources']['v70']=bind_v70_source(request,ctx)
        prepared.payload['family_sources']['c7']=prepared.payload['c7_computation']
        if ctx.get('technical_source') is None:bind_technical_source(self.repo_path,request,ctx)
        return prepared,ctx

    def _compute(self,request):
        prepared,ctx=self._validate(request)
        native=run_native_pipeline(self.repo_path,apply_technical_source(request['native_bundle'],prepared.payload['technical_intake']),
            prepared.payload['stock_source'],prepared.payload['family_sources'])
        amendment=prepared.payload['family_sources'].get('pred007_amendment')
        if native.get('status')!='NATIVE_PIPELINE_COMPLETE' and amendment is not None:
            error=BoundaryError('NATIVE_RESULT_INCOMPLETE','native.status',status='DATA_UNAVAILABLE')
            error.issue.update(native_status=native.get('status'),pred007_amendment=deepcopy(amendment))
            raise error
        require(native.get('status')=='NATIVE_PIPELINE_COMPLETE','NATIVE_RESULT_INCOMPLETE','native.status',status='DATA_UNAVAILABLE')
        u=native['unified_result']
        mentor=explain_native(self.repo_path,native['work9_request'],u,trusted_context={
            'client_id':request['client_id'],'run_id':request['run_id'],'owner':u['owner'],'currency':u['currency'],
            'analysis_permission':'ANALYZE_ONLY','trade_authorization':'NONE','runtime_mode':'REAL_DETERMINISTIC',
            'data_provenance':ctx['native_binding']['data_provenance'],'expected_result_digest':digest(u),
            'expected_bond_context_digest':digest(prepared.payload['family_sources']['bond_targets'])},
            bond_context=prepared.payload['family_sources']['bond_targets'])
        amendment=prepared.payload['family_sources'].get('pred007_amendment')
        if amendment is not None:
            from v75_pred007_source import describe
            mentor['liquidity_amendment']={'assessment':deepcopy(amendment),'explanation':describe(amendment)}
        return {'schema_version':'Family.W5.result.v1','status':'OK','client_id':request['client_id'],
            'request_id':request['request_id'],'run_id':request['run_id'],'owner':deepcopy(request['owner']),
            'input_digest':input_digest(request),'target_binding':deepcopy(prepared.payload['target_binding']),
            'expected_versions':deepcopy(request['expected_versions']),'evaluation_at':request['evaluation_at'],
            'runtime_mode':'REAL_DETERMINISTIC','data_provenance':ctx['native_binding']['data_provenance'],
            'technical_intake':prepared.payload['technical_intake'],'native_result':native,'mentor':mentor,'call_trace':native['call_trace'],
            'formal_deployment_ready':native.get('formal_deployment_ready',False),
            'read_only_native_wait_review':native.get('read_only_native_wait_review',False),
            'storage_scope':'ISOLATED_TEST_STAGING','production':'HOLD','trade_action':'NO_TRADE'}

    def analyze(self,request,*,timeout_seconds=30):
        frozen=deepcopy(request)
        try:
            if self.native_source_report is not None:
                ctx=deepcopy(self.context_provider())
                prepare_input(frozen,trusted_context=ctx)
                from v75_pred007_source import bind as bind_pred007
                bind_pred007(frozen,ctx)
                report=deepcopy(self.native_source_report)
                require(report.get('schema_version')=='Family.W8.NativeSourceProduction.v1'
                    and report.get('status') in ('BLOCKED_BY_ORIGINAL_ADAPTER','SOURCE_STAGE_INCOMPLETE')
                    and report.get('complete_native_bundle') is False
                    and report.get('mentor') is None,
                    'INVALID_NATIVE_SOURCE_FAILURE','source_production')
                require(report.get('report_digest')==digest({k:v for k,v in report.items() if k!='report_digest'})
                    and report.get('request_digest')==digest(frozen)
                    and report.get('client_id')==frozen['client_id']
                    and report.get('run_id')==frozen['run_id']
                    and report.get('owner')==frozen['owner']
                    and report.get('source_db_sha256')==frozen['client_snapshot']['payload']['source_sha256'],
                    'NATIVE_SOURCE_FAILURE_BINDING_MISMATCH','source_production')
                failure=report['first_failure']
                result=self._error(frozen,'DATA_UNAVAILABLE',{
                    'code':failure['code'],'field_path':failure.get('field_path'),
                    'producer':failure['function'],'message':failure['raw_error']})
                return {**result,'source_production':report,
                    'call_trace':['W5.FamilyRunner.analyze:validate_source_failure',*report['call_trace']],
                    'data_provenance':report.get('effective_input_provenance','SOURCE_BACKED'),
                    'source_data_provenance':'SOURCE_BACKED',
                    'mode':report.get('mode'),'runtime_mode':'REAL_DETERMINISTIC'}
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
        detail=deepcopy(issue)
        review=detail.pop('configuration_review',None)
        result={'schema_version':'Family.W5.result.v1','status':status,
            'request_id':request.get('request_id'),'run_id':request.get('run_id'),
            'issue_codes':[detail],'canonical_result':None,'mentor':None,
            'storage_scope':'ISOLATED_TEST_STAGING','production':'HOLD','trade_action':'NO_TRADE'}
        if review is not None:
            result['configuration_review']=review
            if review.get('mentor_review') is not None:
                result['mentor_review']=deepcopy(review['mentor_review'])
                result['formal_deployment_ready']=False
        return result

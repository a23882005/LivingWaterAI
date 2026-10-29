"""Execute the approved C Work7 engine; retain its schemas, math and routing."""
from copy import deepcopy
import importlib
from pathlib import Path
import sys
from threading import RLock
from family_input import digest
from family_boundary import require
from verify_dependencies import verify

C_ROOT = Path('系統工程/C-配置決策引擎＋Mentor整合/正式Runtime')
_LOCK = RLock()


def load_original_configuration_module(repo_path, module_name):
    root = Path(repo_path).resolve()
    verify(root)
    base = root / C_ROOT
    # The original modules use absolute work2..work7 imports. Refuse an already
    # loaded different implementation rather than silently reusing it.
    with _LOCK:
        for name, module in tuple(sys.modules.items()):
            if name.split('.')[0] in {'work2','work3','work4','work5','work6','work7'}:
                origin = getattr(module, '__file__', None)
                if origin is None or not Path(origin).resolve().is_relative_to(base):
                    raise ValueError('C7_MODULE_ORIGIN_CONFLICT:' + name)
        sys.path.insert(0, str(base))
        try:
            module = importlib.import_module(module_name)
        finally:
            sys.path.remove(str(base))
    return module


def run_c7_engine(repo_path, source):
    root = Path(repo_path).resolve()
    base = root / C_ROOT
    module = load_original_configuration_module(root, 'work7.asset_framework')
    schemas = base / 'contracts_c7'
    data = deepcopy(source)
    if data.get('work6_source') is not None:
        from configuration_source import run_work6_engine
        replay = run_work6_engine(root, data['work6_source'])
        require(data['work6_source']['canonical_input'] == data['canonical_input']
                and data['work6_source']['evaluated_at'] == data['evaluated_at'],
                'C7_WORK6_SOURCE_IDENTITY_MISMATCH', 'c7_source.work6_source')
        require(replay['result'] == data['work6_result'],
                'C7_WORK6_REPLAY_MISMATCH', 'c7_source.work6_result')
    result = module.run_asset_framework_integration(
        data['canonical_input'], work6_result=data['work6_result'],
        funding_context=data['funding_context'], evaluated_at=data['evaluated_at'],
        canonical_input_schema_path=schemas/'05_C_Canonical_Input.schema.json',
        work6_output_schema_path=schemas/'57_C_Work6_Mentor_Adjustment_Result.schema.json',
        work7_output_schema_path=schemas/'68_C_Work7_V70_Asset_Framework_Result.schema.json',
        funding_context_schema_path=schemas/'80_C_Work7_Funding_Context.schema.json')
    return {'source_digest':digest(source), 'original_source':deepcopy(source), 'result':result,
            'call_trace':['C.Work7.run_asset_framework_integration'],
            'production':'HOLD', 'trade_action':'NO_TRADE'}


def bind_c7_source(repo_path, request, context):
    source = context.get('c7_source')
    # Legacy synthetic adapter fixtures remain explicitly construction-only.
    if source is None and context['native_binding']['data_provenance'] == 'SYNTHETIC':
        return None
    require(isinstance(source, dict), 'C7_SOURCE_REQUIRED', 'trusted_context.c7_source', status='DATA_UNAVAILABLE')
    require(request.get('c7_source_digest') == digest(source), 'C7_SOURCE_DIGEST_MISMATCH', 'c7_source_digest')
    require(source.get('schema_version') == 'Family.W5.C7Source.v1' and
            all(source.get(k) for k in ('producer','version','source_reference')),
            'C7_SOURCE_PROVENANCE_REQUIRED', 'c7_source')
    require(source.get('family_owner') == request['owner'], 'C7_SOURCE_OWNER_MISMATCH', 'c7_source.family_owner')
    identity = source['canonical_input']['identity']
    require(identity['client_id'] == request['client_id'] and identity['run_id'] == request['run_id'],
            'C7_SOURCE_IDENTITY_MISMATCH', 'canonical_input.identity')
    require(source['evaluated_at'] == request['evaluation_at'], 'C7_EVALUATION_MISMATCH', 'c7_source.evaluated_at')
    if context['native_binding']['data_provenance'] == 'SOURCE_BACKED':
        require(isinstance(source.get('work6_source'), dict), 'C7_WORK6_SOURCE_REQUIRED',
                'c7_source.work6_source', status='DATA_UNAVAILABLE')
    computed = run_c7_engine(repo_path, source)
    result = computed['result']
    if result['status'] != 'READY_FOR_PM_GATE':
        from family_boundary import BoundaryError
        error = BoundaryError('C7_FRAMEWORK_NOT_READY', 'c7.status', status='DATA_UNAVAILABLE')
        error.issue.update(native_status=result['status'], native_issues=deepcopy(result['issues']),
                           work6_status=source['work6_result']['loop_status'])
        raise error
    require(digest(result) == digest(request['native_bundle']['asset_framework']),
            'C7_COMPUTED_FRAMEWORK_MISMATCH', 'native_bundle.asset_framework')
    return computed

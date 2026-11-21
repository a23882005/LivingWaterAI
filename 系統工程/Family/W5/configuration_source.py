"""Read the pinned B source and replay original C Work6 without fixtures."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from c7_engine import C_ROOT, load_original_configuration_module
from family_input import digest


def benchmark_source(root, descriptor, evaluated_at):
    reader = load_original_configuration_module(root, 'work2.benchmark_reader')
    core = load_original_configuration_module(root, 'work5.core_engine')
    xlsx = load_original_configuration_module(root, 'work2.xlsx_minimal_reader')
    path = Path(descriptor['local_path']).resolve(strict=True)
    actual = sha256(path.read_bytes()).hexdigest()
    if (descriptor.get('drive_file_id') != reader.FORMAL_DRIVE_FILE_ID
            or path.name != reader.FORMAL_WORKBOOK_NAME
            or actual != descriptor.get('sha256') or actual != reader.CURRENT_CLOSEOUT_SHA256):
        raise PermissionError('CONFIGURATION_BENCHMARK_SOURCE_MISMATCH')
    # The immutable, engine-pinned workbook establishes the header contract;
    # a different workbook cannot authorize its own headers here.
    workbook = xlsx.read_xlsx(path)
    headers = {k: v.headers for k, v in workbook.sheets.items()}
    binding = {'drive_file_id': descriptor['drive_file_id'], 'expected_sha256': actual,
        'drive_modified_utc': descriptor['drive_modified_utc'],
        'retrieved_at': descriptor['retrieved_at'], 'expected_headers': headers,
        'workbook_name': reader.FORMAL_WORKBOOK_NAME}
    snapshot = reader.read_benchmark(path, reader.SourceBinding(**binding),
        evaluation_date=datetime.fromisoformat(evaluated_at.replace('Z', '+00:00')).date())
    return {'descriptor': deepcopy(descriptor), 'binding': binding,
            'reference': core._benchmark_reference_for_output(snapshot),
            'source_references': [core._normalize_work2_source_reference(s)
                                  for s in snapshot['source_references']],
            'reader_status': snapshot.get('formal_output_eligibility')}


def run_work6_engine(root, source):
    module = load_original_configuration_module(root, 'work6.adjustment_loop')
    benchmark = benchmark_source(root, source['benchmark_source'], source['evaluated_at'])
    base = Path(root) / C_ROOT / 'contracts_c7'
    with TemporaryDirectory(prefix='family-work6-') as directory:
        binding = Path(directory) / 'binding.json'
        binding.write_text(json.dumps(benchmark['binding'], ensure_ascii=False), encoding='utf-8')
        options={}
        if source.get('family_scope') is not None:
            if source.get('schema_version')!='Family.W5.Work6Source.v2':
                raise PermissionError('C7_VERSIONED_WORK6_SCOPE_REQUIRED')
            module=load_original_configuration_module(root,'work6.family_long_term_read')
            run=module.run_existing_long_term
            options['family_scope']=deepcopy(source['family_scope'])
            result_schema=base/'84_Family_Existing_LongTerm_Work6_Result.schema.json'
        else:
            if source.get('schema_version')=='Family.W5.Work6Source.v2':
                raise PermissionError('C7_WORK6_SCOPE_SOURCE_REQUIRED')
            run=module.run_mentor_adjustment_loop
            result_schema=base/'57_C_Work6_Mentor_Adjustment_Result.schema.json'
        result = run(
            deepcopy(source['canonical_input']), adjustment_request=deepcopy(source['adjustment_request']),
            benchmark_path=source['benchmark_source']['local_path'], binding_path=binding,
            input_schema_path=base/'05_C_Canonical_Input.schema.json',
            output_schema_path=base/'06_C_Canonical_Output.schema.json',
            work6_request_schema_path=base/'56_C_Work6_Adjustment_Request.schema.json',
            work6_output_schema_path=result_schema,
            evaluated_at=source['evaluated_at'],**options)
    return {'result': result, 'source_digest': digest(source),
            'call_trace': ['C.Work6.run_existing_long_term' if options else 'C.Work6.run_mentor_adjustment_loop'], 'trade_action': 'NO_TRADE'}

"""Read W2 target records through the approved W5 validator.

The caller supplies the existing validator, a trusted client/run context and
source metadata. This module neither confirms a target nor allocates funds.
"""
from copy import deepcopy
from report_receiver import require, digest
from source_views import canonical_section


def receive_target(target, *, client_id, report_run_id, evaluation_at,
                   source_id, rules_sha, validator):
    require(bool(client_id) and bool(report_run_id), 'TARGET_REPORT_IDENTITY_REQUIRED')
    require(evaluation_at.tzinfo is not None, 'TARGET_REPORT_TIMEZONE_REQUIRED')
    require(bool(source_id) and bool(rules_sha), 'TARGET_REPORT_LINEAGE_REQUIRED')
    if target is None:
        return canonical_section(None, client_id=client_id, run_id=report_run_id, section='target')
    validated = validator(deepcopy(target), client_id, evaluation_at)
    require(validated == target, 'TARGET_VALIDATOR_CHANGED_SOURCE')
    # A historical confirmation run stays in the payload; the envelope identifies
    # the current reporting run. W5 owns confirmation validity and expiry rules.
    envelope = {'client_id': client_id, 'run_id': report_run_id, 'section': 'target',
                'value_state': 'KNOWN', 'payload': deepcopy(validated),
                'payload_sha256': digest(validated), 'source_id': source_id,
                'rules_sha': rules_sha, 'as_of': evaluation_at.isoformat()}
    return canonical_section(envelope, client_id=client_id, run_id=report_run_id, section='target')

"""Bind the recovered Work1 v1.0.3 contract without editing frozen runtime.

The attachment remains private. Only the exact, verified composition is
accepted; a version label or an older parameter table is not a substitute.
This module supplies provenance, not a second predicate evaluator.
"""
from hashlib import sha256
from pathlib import Path
from v75_remaining_inputs import time

VERSION='V75_PREDICATE_PARAMS_v1.0.3'
PARAMETER_SHA256='9aea7bca82fa0f9b3835136a87afcdb08682b226ed4162213e083186beb5f54e'
WORK6_SHA256='5d8eed1638a76f63b9bff9ed822f5f53e09a0b481cb236c7ae4ba3b1c60f8b3c'
WORK1_SHA256='ac23e11197f167be00c5e4c303462373eeced67f353ba26d26bfb4c739b50a71'


def read(source,evaluation_at):
    if source is None:return None
    if (source.get('schema_version')!='Family.W8.FormalV75ParameterSource.v1'
        or source.get('parameter_version')!=VERSION):
        raise PermissionError('V75_FORMAL_PARAMETER_VERSION_MISMATCH')
    if (source.get('sha256')!=PARAMETER_SHA256
        or sha256(Path(source['local_path']).read_bytes()).hexdigest()!=PARAMETER_SHA256):
        raise PermissionError('V75_FORMAL_PARAMETER_BYTES_CHANGED')
    if time(source['source_available_at'])>time(evaluation_at):
        raise PermissionError('V75_FORMAL_PARAMETER_NOT_YET_AVAILABLE')
    if (source.get('outer_sha256')!=WORK6_SHA256 or source.get('inner_sha256')!=WORK1_SHA256
        or source.get('outer_crc_passed') is not True or source.get('inner_crc_passed') is not True):
        raise PermissionError('V75_FORMAL_PARAMETER_CHECKPOINT_PROVENANCE')
    return {'parameter_version':VERSION,'parameter_sha256':PARAMETER_SHA256,
        'work6_sha256':WORK6_SHA256,'work1_sha256':WORK1_SHA256,
        'available_at':source['source_available_at'],'threshold_owner':'ORIGINAL_V75_WORK1',
        'runtime_evaluator':'UNCHANGED_V75_RUNTIME_EVALUATORS',
        'sofr_ois_tenor_defined':False,'fra_ois_tenor_defined':False,
        'yield_basis':'OFFICIAL_PORTFOLIO_YTM_THEN_30_DAY_SEC_YIELD',
        'yield_history_frequency':'WEEKLY','yield_history_years':5,
        'minimum_since_inception_years':3,
        'sgov_treasury_branch_reference':'1 Yr',
        'ttm_cash_yield_is_canonical_yield':False}

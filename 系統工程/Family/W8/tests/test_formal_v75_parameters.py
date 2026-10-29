"""Reject substituted parameter tables and retrospective source availability."""
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import formal_v75_parameters as M


def test_exact_bytes_and_availability_are_required_even_with_correct_version(tmp_path):
    path=tmp_path/'synthetic-contract.md';path.write_bytes(b'SYNTHETIC fixture, never production parameters')
    source={'schema_version':'Family.W8.FormalV75ParameterSource.v1','parameter_version':M.VERSION,
        'local_path':str(path),'sha256':M.PARAMETER_SHA256,'source_available_at':'2026-10-29T06:00:00Z',
        'outer_sha256':M.WORK6_SHA256,'inner_sha256':M.WORK1_SHA256,
        'outer_crc_passed':True,'inner_crc_passed':True}
    with pytest.raises(PermissionError,match='BYTES_CHANGED'):M.read(source,'2026-10-29T07:00:00Z')
    # Synthetic bytes are accepted only under this explicit test patch.
    with patch.object(M,'PARAMETER_SHA256',sha256(path.read_bytes()).hexdigest()):
        source['sha256']=M.PARAMETER_SHA256
        with pytest.raises(PermissionError,match='NOT_YET_AVAILABLE'):M.read(source,'2026-10-29T05:00:00Z')
        result=M.read(source,'2026-10-29T07:00:00Z')
        assert result['sgov_treasury_branch_reference']=='1 Yr'
        assert not result['ttm_cash_yield_is_canonical_yield']
        assert not result['sofr_ois_tenor_defined'] and not result['fra_ois_tenor_defined']
        source['parameter_version']='V75_PREDICATE_PARAMS_v1.0.1'
        with pytest.raises(PermissionError,match='VERSION_MISMATCH'):M.read(source,'2026-10-29T07:00:00Z')

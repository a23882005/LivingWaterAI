"""Synthetic raw-source qualification for the explicit PM scope, no orders."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from deployment_c7_sources import family_scope_source,bind_family_approval,extend,FAMILY_PROFILE


def test_new_scope_missing_facts_never_falls_back_to_legacy_confirm(monkeypatch):
    import deployment_c7_sources as producer
    def forbidden(*args,**kwargs):pytest.fail('No legacy or tactical CONFIRM is authorized')
    monkeypatch.setattr(producer,'run_work6_engine',forbidden)
    out=extend(ROOT,{}, {},None,{'family_c7_profile':FAMILY_PROFILE},{'source_validation_issues':[]})
    assert out['source_validation_issues'][0]['code']=='FAMILY_C7_ORIGINAL_SCOPE_FACTS_REQUIRED'


def test_member_deployment_preflight_names_assembly_without_asserting_all_facts_missing():
    from deployment_c7_sources import member_scope_preflight
    assert member_scope_preflight({}, {}) is None  # Legacy entry remains unchanged.
    issue=member_scope_preflight({}, {'family_c7_profile':FAMILY_PROFILE})
    assert issue['kind']=='SOURCE_ASSEMBLY_REQUIRED'
    assert issue['external_fact_completeness_not_inferred'] is True
    assert 'family_scope.exposure_coverage' in issue['required_contract_fields']


def test_source_bytes_owner_run_db_approval_and_originals_are_bound(tmp_path):
    raw=tmp_path/'SYNTHETIC_ORIGINAL.json';raw.write_text('{"synthetic":true}')
    hashed=sha256(raw.read_bytes()).hexdigest();at='2026-10-30T00:00:00Z'
    request={'client_id':'SYNTHETIC_CLIENT','run_id':'SYNTHETIC_RUN','owner':{'client_id':'SYNTHETIC_CLIENT','account':'SYNTHETIC_ACCOUNT'},
        'evaluation_at':at,'client_snapshot':{'payload':{'source_sha256':'a'*64}},'confirmed_target':{'target_version':1}}
    data={'schema_version':'Family.W8.C7FamilyScopeSource.v1',**{k:request[k] for k in ('client_id','run_id','owner','evaluation_at')},
        'source_db_sha256':'a'*64,'confirmed_target_digest':digest(request['confirmed_target']),
        'family_scope':{'family_owner':request['owner'],'source_db_sha256':'a'*64,'target_version':1,'profile':FAMILY_PROFILE},
        'raw_sources':[{'source_id':'SYNTHETIC_RAW','local_path':str(raw),'sha256':hashed}],
        'source_references':[{'source_id':'SYNTHETIC_RAW','source_fingerprint':hashed}]}
    file=tmp_path/'SYNTHETIC_SCOPE.json'
    def context():
        file.write_text(json.dumps(data));return {'family_c7_profile':FAMILY_PROFILE,
            'family_c7_scope_source':{'local_path':str(file),'sha256':sha256(file.read_bytes()).hexdigest()}}
    assert family_scope_source(request,context())==data
    for key,value in [('run_id','FOREIGN'),('source_db_sha256','b'*64),('confirmed_target_digest','c'*64),('asset_framework',{})]:
        before=deepcopy(data);data[key]=value
        with pytest.raises(PermissionError):family_scope_source(request,context())
        data.clear();data.update(before)
    ctx=context();raw.write_text('{"changed":true}')
    with pytest.raises(PermissionError,match='ORIGINAL_SOURCE_BYTES_CHANGED'):family_scope_source(request,ctx)


def test_approved_money_base_is_bound_to_w2_and_never_current_nav():
    row={'instrument_id':'SYNTHETIC_ASSET','ticker':'SYNTHETIC_ASSET','weight':{'value':'.8'}}
    request={'confirmed_target':{'payload':{'draft':{'target_lines':[row]},
        'confirmation_evidence':{'action':'READ_EXISTING_APPROVAL','confirmed_at':'2026-01-01T00:00:00Z','confirmed_by':'SYNTHETIC_OWNER'}}}}
    projected={'denominator':{'amount':'1000','currency':'USD'},'source_to_native':{'SYNTHETIC_ASSET':'SYNTHETIC_ASSET'},
        'targets':{'SYNTHETIC_ASSET':{'target_amount':{'amount':'800','currency':'USD'}}}}
    approved={'denominator':{'amount':'1000','currency':'USD'},'confirmed_at':'2026-01-01T00:00:00Z','confirmed_by':'SYNTHETIC_OWNER',
        'positions':[{'instrument_id':'SYNTHETIC_ASSET','weight':{'value':'.8'},'portfolio_amount':{'amount':'800','currency':'USD'}}]}
    scope={'approved_long_term_target':approved}
    assert bind_family_approval(request,{'native_target_source':projected},scope)==approved
    approved['denominator']['amount']='2000'
    with pytest.raises(PermissionError,match='INVESTMENT_POOL_CHANGED'):bind_family_approval(request,{'native_target_source':projected},scope)


def test_native_path_reports_structured_c7_failure_without_losing_the_field():
    from native_asset_source import native_error_path
    class Error(ValueError):issues=[{'field_path':'family_scope.exposure_coverage','code':'SYNTHETIC_MISSING_SOURCE'}]
    assert native_error_path(Error())=='family_scope.exposure_coverage'

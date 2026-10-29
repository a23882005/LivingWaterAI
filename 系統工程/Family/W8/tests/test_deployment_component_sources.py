"""Full-entry assembly reuses actual adapters without inventing missing data."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import test_holdings_analysis as holdings_fixture
import native_funding_advice as F
import native_bond_source as B
from family_input import digest
from deployment_component_sources import collect
from on_demand_analysis import assemble_native_input,NativeSourceAssemblyError


def case():
    p,request,report,trial,investment,tactical=holdings_fixture.NativeFundingAdviceTest().case()
    report.update(client_id=request['client_id'],run_id=request['run_id'],owner=deepcopy(request['owner']),
        source_db_sha256=request['client_snapshot']['payload']['source_sha256'])
    row=deepcopy(report['analysis_result']['positions'][0])
    row.update(symbol='SGOV',instrument_id='SYNTHETIC_SGOV',core_observation=None,
        native_product_identity={'engine_route':'V75_PREDICATES','asset_type':None,'asset_grade':'UNKNOWN'})
    row['market'].update(symbol='SGOV',provider_verified_at='2026-10-27T22:00:00Z',source_sha256='c'*64,
        observed_date='2026-10-26',v75_original_predicates={})
    row['current_analysis']['recommendation']['position_currency']='USD'
    report['analysis_result']['positions'].append(row)
    request['confirmed_target']['payload']['draft']['target_lines'] += [
        {'instrument_id':symbol,'ticker':symbol,'target_amount':{
            'value_state':'KNOWN','amount':amount,'currency':'USD'}} for symbol,amount in [('SGOV','700'),('SPSB','300')]]
    roles={k:deepcopy(report[k]) for k in ('client_id','run_id','owner','source_db_sha256')}
    roles.update(status='SOURCE_DERIVED_ACCOUNTING',roles={
        'sgov_bond_bucket_amount':{'amount':'0','currency':'USD'},
        'sgov_dry_powder_bucket_amount':{'amount':'500','currency':'USD'}},
        physical={'quantity':'5','valuation':{'amount':'500','currency':'USD'},
            'valuation_as_of':request['evaluation_at'],'source_reference':'SYNTHETIC_CURRENT_SGOV'})
    roles['digest']=digest(roles);report['sgov_role_source']=roles
    shared=F.build_shared_inputs(p,request,report,trial=trial,investment=investment,tactical=tactical)
    report['native_funding_advice']=F.build(p,request,report,trial=trial,investment=investment,
        tactical=tactical,shared_inputs=shared)
    report['native_bond_source']=B.build(ROOT,request,report,shared_inputs=shared,fx_observation=None,
        strategic_policy={'client_id':request['client_id'],'stock_percent':80,'bond_percent':20,
            'life_stage_code':'L7','source_reference':'SYNTHETIC_STRATEGY'})
    report['report_digest']=digest(report)
    return request,report


def test_actual_stock_bond_adapters_and_physical_roles_are_reused_without_new_defaults():
    request,report=case();before=deepcopy((request,report));sources=collect(ROOT,request,report,'QQQ')
    bundle=sources['native_bundle']
    assert bundle['stock_request']==report['native_funding_advice']['items']['SYNTHETIC_QQQ']['stock_request']
    assert bundle['bond_request']==report['native_bond_source']['adapter_request']
    assert bundle['stock_request']['work3_handoff']==bundle['bond_request']['work3_handoff']
    assert bundle['physical_sgov']['physical_market_value']=='500'
    assert set(bundle)=={'stock_request','bond_request','physical_sgov'}
    assert (request,report)==before
    with pytest.raises(NativeSourceAssemblyError) as error:assemble_native_input(request,{},sources)
    missing=error.value.missing
    assert 'native_bundle.stock_evidence' in missing and 'trusted_context.c7_source' in missing
    assert 'native_bundle.stock_request' not in missing and 'native_bundle.bond_request' not in missing
    assert 'native_bundle.physical_sgov' not in missing


@pytest.mark.parametrize('kind',['owner','shared','stock_output','sgov'])
def test_cross_owner_changed_shared_inputs_or_component_output_is_rejected(kind):
    request,report=case()
    if kind=='owner':report['owner']['account']='OTHER'
    elif kind=='shared':report['native_bond_source']['adapter_request']['work3_handoff']['run_id']='OTHER'
    elif kind=='stock_output':report['native_funding_advice']['items']['SYNTHETIC_QQQ']['work4_result']['integration_binding']['asset_id']='OTHER'
    else:report['sgov_role_source']['roles']['sgov_dry_powder_bucket_amount']['amount']='600'
    with pytest.raises(PermissionError,match='DEPLOYMENT_'):collect(ROOT,request,report,'QQQ')


def test_unavailable_focus_or_bond_request_cannot_be_replaced_by_a_fixture():
    request,report=case()
    assert collect(ROOT,request,report,'ABSENT') is None
    report['native_bond_source'].pop('adapter_request')
    assert collect(ROOT,request,report,'QQQ') is None


def test_funding_replay_loads_and_checks_the_original_runtime_in_a_fresh_process(tmp_path):
    request,report=case()
    for row in report['analysis_result']['positions']:
        row['current_analysis']['native_funding_advice']=F.delivery(
            report['native_funding_advice']['items'][row['instrument_id']])
    assert report['native_funding_advice']['items']['SYNTHETIC_QQQ']['status']=='CASH_TRIAL_ADVICE_COMPUTED'
    source=tmp_path/'synthetic-funding-replay.json'
    source.write_text(json.dumps({'request':request,'report':report}))
    code="""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'系統工程/Family/W8'),str(root/'系統工程/Family/W5')]
from native_funding_advice import validate
assert 'livingwater_v82_runtime' not in sys.modules
data=json.loads(Path(sys.argv[2]).read_text())
validate(root,data['report'],data['request'])
"""
    completed=subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(source)],
        text=True,capture_output=True,timeout=30)
    assert completed.returncode==0,completed.stderr


def test_bond_supplement_replay_loads_the_original_runtime_in_a_fresh_process(tmp_path):
    from test_v75_market_supplement import MarketSupplementTest
    source,_=MarketSupplementTest().fixture(tmp_path)
    path=tmp_path/'synthetic-source.json';path.write_text(json.dumps(source))
    code="""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'系統工程/Family/W8'),str(root/'系統工程/Family/W5')]
from v75_market_supplement import read,validate
from family_input import digest
assert 'v75_runtime' not in sys.modules
source=json.loads(Path(sys.argv[2]).read_text());at='2026-10-29T02:00:00Z'
macro={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-10-27T01:00:00Z',
    'verification':{'ready':True},'indicators':{}}
request={'evaluation_at':at,'macro_snapshot':{'payload':macro,'digest':digest(macro)}}
report={'bond_market_supplement':read(source,at),'analysis_result':{'positions':[]}}
validate(request,{'bond_market_supplement_source':source},report,root)
"""
    completed=subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(path)],
        text=True,capture_output=True,timeout=30)
    assert completed.returncode==0,completed.stderr

"""Independent contract, full session proof and native V75 source replay."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
import test_v75_macro_inputs as macro_fixture
from test_v75_remaining_inputs import history,repo
from family_input import digest
import v75_macro_inputs as M
import v75_market_contract as Q
import native_source_freshness as F


def fixture(tmp_path):
    source,_=macro_fixture.MacroInputsTest().fixture(tmp_path)
    manifest=json.loads(Path(source['local_path']).read_text())
    p=tmp_path/'NYFED_REPO.raw';p.write_text(json.dumps(repo()));h=sha256(p.read_bytes()).hexdigest()
    receipt=tmp_path/'NYFED_REPO.receipt.json';receipt.write_text(json.dumps({
        'url':'https://markets.newyorkfed.org/api/rp/repo/all/results/lastTwoWeeks.json',
        'http_status':200,'sha256':h,'requested_at':'2026-10-29T00:59:00Z','available_at':'2026-10-29T01:00:00Z'}))
    manifest['sources']['NYFED_REPO']={'local_path':str(p),'sha256':h,'receipt_path':str(receipt),
        'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}
    ids={}
    for symbol in ('SGOV','SPSB'):
        key='YAHOO_'+symbol;p=tmp_path/(key+'.raw');p.write_text(json.dumps(history(symbol)))
        h=sha256(p.read_bytes()).hexdigest();receipt=tmp_path/(key+'.receipt.json')
        receipt.write_text(json.dumps({'url':'https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?range=5y&interval=1d&events=div%2Csplits',
            'http_status':200,'sha256':h,'requested_at':'2026-10-29T00:59:00Z','available_at':'2026-10-29T01:00:00Z'}))
        manifest['sources'][key]={'local_path':str(p),'sha256':h,'receipt_path':str(receipt),
            'receipt_sha256':sha256(receipt.read_bytes()).hexdigest()}
        contract=tmp_path/(symbol+'.contract.json')
        contract.write_text(json.dumps({'status':'fulfilled','value':{'isError':False,
            'structuredContent':{'results':[{'symbol':symbol,'country_code':'US','exchange':'ARCA',
                'underlying_contract_id':123 if symbol=='SGOV' else 456,'sections':[{'security_type':'STK'}]},
                {'symbol':symbol,'country_code':'MX','exchange':'MEXI','underlying_contract_id':789,
                    'sections':[{'security_type':'STK'}]}]}}}))
        ids[symbol]={'local_path':str(contract),'sha256':sha256(contract.read_bytes()).hexdigest(),
            'tool_name':'search_contracts','arguments':{'query':symbol},'available_at':'2026-10-29T01:00:00Z'}
    manifest['bond_market_identity_sources']=ids
    path=Path(source['local_path']);path.write_text(json.dumps(manifest));source['sha256']=sha256(path.read_bytes()).hexdigest()
    return source,manifest


def save_manifest(source,manifest):
    path=Path(source['local_path']);path.write_text(json.dumps(manifest));source['sha256']=sha256(path.read_bytes()).hexdigest()


def macro():
    path=ROOT/'系統工程/總經V70/V70_macro_latest.json';raw=path.read_bytes();value=json.loads(raw)
    return {'payload':value,'digest':digest(value),'source_sha256':sha256(raw).hexdigest()}


def test_full_source_replay_qualifies_only_completed_bond_prices(tmp_path):
    source,_=fixture(tmp_path);at='2026-10-29T02:00:00Z';pool=M.read(source,at)
    raw={'assets':[{'symbol':'SGOV','instrument_key':'SYNTHETIC','call_trace':[]}]}
    out=M.apply(raw,pool,evaluation_at=at,repo_root=ROOT,macro=macro());row=out['assets'][0]
    assert row['qualified_bond_market']['contract_id']==123 and row['qualified_bond_market']['eligible']
    assert row['formal_identity_verified'] and not row['formal_deployment_eligible']
    assert not row['v75_original_predicates']['PRED-009']['deployment_input_eligible']
    assert row['v75_original_predicates']['PRED-009']['raw_price_freshness_verified']
    assert not row['v75_original_predicates']['PRED-008']['input_freshness_verified']
    assert row['v75_original_predicates']['PRED-008']['original_result']['assessment_status']=='INSUFFICIENT_DATA'
    assert pool['income_observations']['SGOV']['calculation']['latest_ttm_cash_per_share']
    assert row['v75_original_predicates']['PRED-007']['input_freshness_verified']
    assert not row['v75_original_predicates']['PRED-007']['deployment_input_eligible']
    request={'evaluation_at':at,'macro_snapshot':macro()};context={'v75_macro_source_manifest':source}
    report={'v75_macro_inputs':pool,'analysis_result':{'positions':[{'market':row}]}}
    M.validate(request,context,report,ROOT);Q.validate(request,context,report,ROOT)
    row['numeric']['rsi14']=99
    with pytest.raises(PermissionError,match='MARKET_REPLAY'):Q.validate(request,context,report,ROOT)


def test_contract_collision_changed_bytes_and_bad_ohlcv_fail_closed(tmp_path):
    source,manifest=fixture(tmp_path);entry=manifest['bond_market_identity_sources']['SGOV']
    path=Path(entry['local_path']);path.write_text('{}')
    with pytest.raises(PermissionError,match='IDENTITY_BYTES'):M.read(source,'2026-10-29T02:00:00Z')
    source,manifest=fixture(tmp_path);entry=manifest['bond_market_identity_sources']['SGOV'];path=Path(entry['local_path'])
    raw=json.loads(path.read_text());raw['value']['structuredContent']['results'][0]['country_code']='MX'
    path.write_text(json.dumps(raw));entry['sha256']=sha256(path.read_bytes()).hexdigest();save_manifest(source,manifest)
    with pytest.raises(ValueError,match='CONTRACT_AMBIGUOUS'):M.read(source,'2026-10-29T02:00:00Z')
    source,manifest=fixture(tmp_path);entry=manifest['sources']['YAHOO_SGOV'];path=Path(entry['local_path'])
    raw=json.loads(path.read_text());raw['chart']['result'][0]['indicators']['quote'][0]['high'][0]='1'
    path.write_text(json.dumps(raw));entry['sha256']=sha256(path.read_bytes()).hexdigest()
    receipt=Path(entry['receipt_path']);value=json.loads(receipt.read_text());value['sha256']=entry['sha256'];receipt.write_text(json.dumps(value));entry['receipt_sha256']=sha256(receipt.read_bytes()).hexdigest();save_manifest(source,manifest)
    with pytest.raises(ValueError,match='INVALID_OHLCV'):M.read(source,'2026-10-29T02:00:00Z')


def test_old_close_is_stale_when_another_session_has_completed(tmp_path):
    source,_=fixture(tmp_path);pool=M.read(source,'2026-10-30T02:00:00Z')
    assert all(c['status']=='STALE' and not c['eligible'] for c in pool['qualified_bond_markets'].values())


def test_advisory_candidates_do_not_override_primary_market_scope(tmp_path):
    source,_=fixture(tmp_path);at='2026-10-29T02:00:00Z';pool=M.read(source,at)
    row=M.apply({'assets':[{'symbol':'SGOV','call_trace':[]}]},pool,evaluation_at=at,repo_root=ROOT,macro=macro())['assets'][0]
    request={'evaluation_at':at,'macro_snapshot':macro(),'confirmed_target':{'payload':{'draft':{'target_lines':[{'ticker':'SGOV'}]}}}}
    report={'v75_macro_inputs':pool,'analysis_result':{'positions':[{'symbol':'SGOV',
        'native_product_identity':{'engine_route':'V75_PREDICATES'},'market':row}]},
        'bond_target_market_observations':{'IEF':{'symbol':'IEF','observed_date':'2026-10-27','source_sha256':'a'*64}}}
    assert F.build(ROOT,request,report)['market']['state']=='FRESH'
    row.pop('qualified_bond_market');row['formal_deployment_eligible']=True
    assert F.build(ROOT,request,report)['market']['state']=='UNKNOWN'


def test_qualified_history_does_not_erase_the_existing_move_supplement(tmp_path):
    import test_v75_market_supplement as supplement_fixture
    import v75_market_supplement as S
    source,_=fixture(tmp_path);supplement_source,_=supplement_fixture.MarketSupplementTest().fixture(tmp_path)
    at='2026-10-29T02:00:00Z';pool=M.read(source,at);supplement=S.read(supplement_source,at)
    out=M.apply({'assets':[{'symbol':'SGOV','call_trace':[]}]},pool,evaluation_at=at,repo_root=ROOT,macro=macro())
    out=S.apply(out,supplement,evaluation_at=at,repo_root=ROOT)
    report={'v75_macro_inputs':pool,'bond_market_supplement':supplement,
        'analysis_result':{'positions':[{'market':out['assets'][0]}]}}
    request={'evaluation_at':at,'macro_snapshot':macro()}
    context={'v75_macro_source_manifest':source,'bond_market_supplement_source':supplement_source}
    Q.validate(request,context,report,ROOT);M.validate(request,context,report,ROOT);S.validate(request,context,report,ROOT)
    assert out['assets'][0]['v75_original_predicates']['PRED-005']['metrics']['move_pct_change_5bd']=='10.0'

"""Current QQQ labels and the existing shared financial dispatch boundary."""
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from native_asset_source import AssetSourceProducer
from v10_source_observations import forward_observations
from test_member_financial_producer import case,ROOT
from member_financial_producer import produce


def snapshot(label='QQQ未來12個月Forward P/E'):
    row={'value':'18.82','dataDate':'2026-11-18','source':'https://stockanalysis.com/etf/qqq/',
        'unit':'倍 Forward','status':'OK','lastVerifiedAt':'2026-11-19T19:08:26+08:00',
        'sourceEvidence':{'label':label,'value':'18.82','source_url':'https://stockanalysis.com/etf/qqq/'}}
    raw={'schema':'V70.3/family-macro-feed-v3','asOf':'2026-11-19T11:08:41.792735Z',
        'verification':{'ready':True},'indicators':{'m03_qqq':row}}
    return {'payload':raw,'digest':digest(raw),'source_sha256':'a'*64}


@pytest.mark.parametrize('label',['QQQ未來12個月Forward P/E','Forward PE'])
def test_both_qqq_labels_preserve_current_and_strict_qualification(label):
    source=snapshot(label);before=deepcopy(source)
    current=forward_observations(source,'QQQ','2026-11-19T22:19:37Z',purpose='CURRENT_HOLDINGS_ANALYSIS')[0]
    strict=forward_observations(source,'QQQ','2026-11-19T22:19:37Z')[0]
    assert current['current']==strict['current']=='18.82'
    assert current['valuation_level']==strict['valuation_level']=='NORMAL'
    assert current['current_source_accepted'] and not current['execution_input_eligible']
    assert current['strict_contract_validity']['pit_status']==strict['pit_status']=='UNVERIFIABLE'
    assert strict['freshness']=='UNKNOWN' and not strict['current_source_accepted']
    assert source==before


@pytest.mark.parametrize('purpose',['CURRENT_HOLDINGS_ANALYSIS','STRICT_NATIVE_INPUT'])
@pytest.mark.parametrize('change',['wrong_asset','trailing','generic_pe','number','url','nan','bool'])
def test_qqq_alias_does_not_accept_other_assets_or_inconsistent_evidence(purpose,change):
    s=snapshot();e=s['payload']['indicators']['m03_qqq']['sourceEvidence']
    if change=='wrong_asset':e['label']='VT未來12個月Forward P/E'
    elif change=='trailing':e['label']='Trailing PE'
    elif change=='generic_pe':e['label']='P/E Ratio'
    elif change=='number':e['value']='18.83'
    elif change=='url':e['source_url']='https://stockanalysis.com/etf/vt/'
    elif change=='nan':e['value']='NaN'
    else:e['value']=True
    s['digest']=digest(s['payload'])
    with pytest.raises(ValueError,match='V10_FORWARD_PE_DEFINITION_OR_SOURCE_MISMATCH'):
        forward_observations(s,'QQQ','2026-11-19T22:19:37Z',purpose=purpose)


def test_qqq_named_label_cannot_be_used_as_vt():
    s=snapshot();s['payload']['indicators']['m03_vt']=s['payload']['indicators'].pop('m03_qqq')
    s['digest']=digest(s['payload'])
    with pytest.raises(ValueError,match='DEFINITION_OR_SOURCE'):
        forward_observations(s,'VT','2026-11-19T22:19:37Z')


def test_menu_stock_producer_selects_financial_continuation(tmp_path):
    request,_,descriptor=case(tmp_path);seen=[]
    def factory(**cfg):
        seen.append(cfg)
        return lambda *args:{'request':deepcopy(cfg['request_seed']),'source_production':{
            'status':'SOURCE_STAGE_INCOMPLETE','financial_continuation':{'status':'ORIGINAL_C7_SOURCE_REQUIRED'},
            'source_validation_issues':[{'code':'SYNTHETIC_SAME_RUN_SHARED_FUNDING_REQUIRED'}]}}
    attempt,result=produce(ROOT,request,'SYNTHETIC_ASSET',descriptor(),equity_only=True,producer_factory=factory)
    assert seen[0]['flow']=='V82_FINANCIAL' and result is None
    assert attempt['financial_continuation']['status']=='ORIGINAL_C7_SOURCE_REQUIRED'
    assert not attempt['qualified_financial_pack']


def test_incomplete_shared_sources_keep_analysis_without_bond_or_ledger_dispatch():
    producer=object.__new__(AssetSourceProducer)
    analysis={'call_trace':['V82.evaluate_core_rule_state'],'original_synthetic_analysis':'retained'}
    assembly={'issues':[{'code':'SYNTHETIC_SHARED_SETTLED_SOURCE_REQUIRED'}],'call_trace':['ORIGINAL_C7']}
    with patch.object(AssetSourceProducer,'__call__',side_effect=AssertionError('Unqualified financial dispatch')):
        pack=producer.continue_financial({}, {}, {'run_id':'SYNTHETIC'}, {},analysis,assembly,[])
    result=pack['source_production']
    assert result['analysis_report']==analysis and result['family_scope_assembly']==assembly
    assert result['status']=='SOURCE_STAGE_INCOMPLETE'
    assert result['source_validation_issues']==assembly['issues']
    assert not result['financial_continuation']['native_financial_dispatch_attempted']
    assert 'native_sources' not in pack


def test_qualified_scope_resumes_original_joint_financial_route_with_same_sources():
    producer=object.__new__(AssetSourceProducer)
    producer.flow='V82_FINANCIAL';producer.req={'before':'original'};producer.ctx={'before':'original'}
    producer.v75_macro_source_manifest={'sha256':'b'*64}
    producer.bond_market_supplement_source={'sha256':'c'*64}
    producer.cash_policy={'synthetic_original_cash_policy':'retained'}
    request={'run_id':'SYNTHETIC_SAME_RUN','evaluation_at':'2026-11-19T22:19:37Z'}
    context={'equity_analysis_symbol':'QQQ','other':'unchanged'}
    assembly={'source_descriptor':{'local_path':'SYNTHETIC_ORIGINAL_SCOPE','sha256':'d'*64},'digest':'e'*64}
    seen=[]
    def dispatch(child,snapshot,payload):
        seen.append(child)
        assert child.flow=='DEPLOYMENT' and child.req==request
        assert 'equity_analysis_symbol' not in child.ctx
        assert child.ctx['family_c7_scope_source']==assembly['source_descriptor']
        assert child.v75_macro_source_manifest==producer.v75_macro_source_manifest
        assert child.bond_market_supplement_source==producer.bond_market_supplement_source
        assert child.cash_policy==producer.cash_policy
        return {'original_financial_pack':'SYNTHETIC_DISPATCH_SENTINEL'}
    with patch.object(AssetSourceProducer,'__call__',dispatch):
        result=producer.continue_financial({}, {},request,context,{},assembly,[])
    assert result=={'original_financial_pack':'SYNTHETIC_DISPATCH_SENTINEL'} and len(seen)==1
    assert producer.flow=='V82_FINANCIAL' and producer.req=={'before':'original'}
    assert context['equity_analysis_symbol']=='QQQ'


def test_joint_bond_source_refusal_preserves_stock_analysis_and_original_failure():
    producer=object.__new__(AssetSourceProducer)
    assembly={'source_descriptor':{'local_path':'SYNTHETIC_SCOPE','sha256':'a'*64},
        'digest':'b'*64,'call_trace':['ORIGINAL_C7']}
    analysis={'call_trace':['V82.evaluate_core_rule_state'],'synthetic_stock_result':'retained'}
    with patch.object(AssetSourceProducer,'__call__',side_effect=ValueError('V75_MACRO_FUTURES_HORIZON')):
        pack=producer.continue_financial({}, {}, {}, {},analysis,assembly,[])
    result=pack['source_production'];continuation=result['financial_continuation']
    assert continuation['native_financial_dispatch_attempted']
    assert continuation['original_source_issue']['code']=='V75_MACRO_FUTURES_HORIZON'
    assert result['analysis_report']==analysis and result['family_scope_assembly']==assembly
    assert result['source_validation_issues'][0]['code']=='V75_MACRO_FUTURES_HORIZON'
    assert 'native_sources' not in pack and result['no_financial_engine_or_ledger_claimed']

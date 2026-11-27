"""Synthetic original money sources: known intention never becomes cash."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json, sys
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from family_input import digest
from member_financial_facts import reported_money, broker_observations, produce


def case():
    client='SYNTHETIC_CLIENT';at='2026-11-04T02:00:00Z'
    run=dict(client_id=client,run_id='SYNTHETIC_SOURCE',as_of_utc='2026-10-26T05:50:00Z',
             created_at_utc='2026-10-26T05:50:00Z',sealed_at_utc='2026-10-26T05:50:00Z',
             version_no=1,run_state='SEALED',source_kind='OWNER_VERIFIED')
    item=dict(client_id=client,run_id=run['run_id'],domain_code='CASH',entity_key='SYNTHETIC_ACCOUNT',
              field_key='owner_confirmed_investable_minor',value_state='KNOWN',value_type='INTEGER_MINOR',
              value_integer_minor=1234500,value_text=None,unit='MINOR',currency_code='TWD',
              source_kind='OWNER_VERIFIED',source_reference='SYNTHETIC_ORIGINAL',
              source_observed_at_utc=run['as_of_utc'],recorded_at_utc=run['as_of_utc'])
    tables=dict(portfolio_snapshot_run=[run],portfolio_snapshot_item=[item])
    req=dict(client_id=client,run_id='SYNTHETIC_RUN',evaluation_at=at,trade_authorization='NONE',
             confirmed_target={'target_version':1},client_snapshot={'payload':dict(
                client_id=client,source_sha256='a'*64,tables=tables,payload_digest=digest(tables))})
    return req,run,item


def rehash(req):
    s=req['client_snapshot']['payload'];s['payload_digest']=digest(s['tables'])


def save(path,obj):
    path.write_text(json.dumps(obj));return dict(local_path=str(path),sha256=sha256(path.read_bytes()).hexdigest())


def test_owner_integer_minor_intent_and_cash_report_are_distinct_and_read_only():
    req,run,item=case();req['client_snapshot']['payload']['tables']['portfolio_snapshot_item'].append(
        {**item,'field_key':'reported_amount_minor'});rehash(req);before=deepcopy(req)
    out=reported_money(req);facts={r['fact_kind']:r for r in out['facts']}
    assert set(facts)=={'REPORTED_CASH','OWNER_INVESTMENT_INTENT'}
    assert facts['OWNER_INVESTMENT_INTENT']['amount']=='12345'
    assert facts['OWNER_INVESTMENT_INTENT']['qualification']=='OWNER_CONFIRMED_INTENT'
    assert all(not f['settlement_qualified'] and f['available_cash'] is None
               and f['authorized_incremental_amount'] is None for f in facts.values())
    assert out['aggregate_reported_cash'] is None and req==before


def test_screenshot_cash_aliases_are_one_fact_and_unknown_observation_time_stays_unknown():
    req,run,item=case();tables=req['client_snapshot']['payload']['tables']
    row={**item,'domain_code':'OWNER_SCREENSHOT_SOURCE','field_key':'cash_balance','value_type':'TEXT',
         'value_text':'321.10','value_integer_minor':None,'unit':'USD','currency_code':'USD',
         'source_observed_at_utc':None,'source_kind':'USER_PROVIDED'}
    tables['portfolio_snapshot_item']=[row,{**row,'field_key':'total_cash_same_balance_not_additive'}]
    rehash(req);out=reported_money(req)
    assert len(out['facts'])==1 and len(out['facts'][0]['source_rows'])==2
    assert out['facts'][0]['amount']=='321.10' and out['facts'][0]['as_of'] is None
    assert out['facts'][0]['qualification']=='REPORTED_UNQUALIFIED'


@pytest.mark.parametrize('field',['reported_amount','reported_cash','owner_reported_amount'])
def test_existing_major_unit_cash_field_variants_are_retained(field):
    req,_,item=case();item.update(field_key=field,value_type='TEXT',value_text='125.50',unit='TWD')
    rehash(req);assert reported_money(req)['facts'][0]['amount']=='125.50'


def test_accepted_report_cash_is_preserved_as_a_reported_observation():
    req,_,item=case();item.update(domain_code='W6_ACCEPTED_SOURCE',field_key='cash_usd_display',
        value_type='TEXT',value_text='25.50',unit='USD',currency_code='USD')
    rehash(req);out=reported_money(req)
    assert out['facts'][0]['amount']=='25.50' and out['facts'][0]['qualification']=='REPORTED_UNQUALIFIED'


@pytest.mark.parametrize('change',['hypothetical','draft','future_run','future_seal','future_item','no_currency','no_reference','unknown'])
def test_unqualified_or_future_sources_do_not_become_usable_money(change):
    req,run,item=case()
    if change=='hypothetical':run['source_kind']='USER_HYPOTHETICAL'
    elif change=='draft':run['run_state']='DRAFT'
    elif change=='future_run':run['as_of_utc']='2099-01-01T00:00:00Z'
    elif change=='future_seal':run['sealed_at_utc']='2099-01-01T00:00:00Z'
    elif change=='future_item':item['recorded_at_utc']='2099-01-01T00:00:00Z'
    elif change=='no_currency':item['currency_code']=None
    elif change=='no_reference':item['source_reference']=None
    else:item['value_state']='UNKNOWN'
    rehash(req);assert reported_money(req)['facts']==[]


def test_new_run_replaces_same_source_entity_without_summing_cash_or_other_alias_accounts():
    req,run,item=case();tables=req['client_snapshot']['payload']['tables'];old=deepcopy(item)
    newer={**run,'run_id':'NEW','as_of_utc':'2026-10-27T00:00:00Z'}
    tables['portfolio_snapshot_run'].append(newer)
    tables['portfolio_snapshot_item'] += [{**old,'run_id':'NEW','value_integer_minor':2000000},
                                        {**old,'entity_key':'OTHER_ALIAS'}]
    rehash(req);out=reported_money(req)
    assert sorted(f['amount'] for f in out['facts'])==['12345','20000']
    assert out['aggregate_reported_cash'] is None and not out['cash_sources_proven_nonoverlapping']


@pytest.mark.parametrize('change',['client','row_client','digest','trade'])
def test_member_snapshot_and_trade_scope_are_enforced(change):
    req,_,item=case()
    if change=='client':req['client_id']='OTHER'
    elif change=='row_client':item['client_id']='OTHER';rehash(req)
    elif change=='digest':req['client_snapshot']['payload']['payload_digest']='wrong'
    else:req['trade_authorization']='YES'
    with pytest.raises(PermissionError):reported_money(req)


def candidate(tmp_path, req):
    at='2026-11-04T01:00:00+00:00';calls={}
    for name,method,result,args in [
        ('balances','get_account_balances',{'balances':[{'currency':'BASE','cash_balance':50,'settled_cash':50},
          {'currency':'USD','cash_balance':50,'settled_cash':50}]},{}),
        ('positions','get_account_positions',{'positions':[]},{}),
        ('orders','get_account_orders',{'orders':[{'order_id':1,'order_status':'REPLACED'}]},{'show_completed':False}),
        ('trades','get_account_trades',{'trades':[]},{'period':'DAYS_7'}),
        ('summary','get_account_summary',{'buying_power':10000,'available_funds':5000},{})]:
        body=dict(status='fulfilled',method=method,arguments=args,retrieved_at=at,
                  value=dict(isError=False,structuredContent=result))
        calls[name]={**save(tmp_path/(name+'.json'),body),'tool_name':method,'retrieved_at':at,'arguments':args}
    manifest=dict(schema_version='Family.W8.MemberBrokerObservations.v1',
                  **{k:req[k] for k in ('client_id','run_id','evaluation_at')},
                  source_db_sha256=req['client_snapshot']['payload']['source_sha256'],
                  snapshot_digest=req['client_snapshot']['payload']['payload_digest'],
                  target_version=1,source_reference='SYNTHETIC_RPC_CAPTURE',available_at=at,calls=calls)
    return manifest


def test_broker_base_alias_settlement_margin_replacement_and_empty_trade_window_stay_distinct(tmp_path):
    req,_,_=case();manifest=candidate(tmp_path,req)
    out=broker_observations(req,save(tmp_path/'manifest.json',manifest))
    assert len(out['cash_observations'])==1 and out['cash_observations'][0]['broker_settled_observation']=='50'
    assert out['qualified_available_cash'] is None and out['pending_exposure'] is None
    assert out['summary_observations']['buying_power']==10000 and not out['margin_funds_used_as_cash']
    assert len(out['replaced_orders_requiring_successor_or_release'])==1
    assert out['trade_query']=={'period':'DAYS_7'} and out['trades']==[] and not out['orders_complete']


@pytest.mark.parametrize('change',['client','run','db','snapshot','version','cutoff','method','arguments','bytes'])
def test_broker_candidate_wrong_scope_or_lineage_is_rejected(tmp_path,change):
    req,_,_=case();m=candidate(tmp_path,req)
    if change in ('client','run'):m[change+'_id']='OTHER'
    elif change=='db':m['source_db_sha256']='b'*64
    elif change=='snapshot':m['snapshot_digest']='b'*64
    elif change=='version':m['target_version']=2
    elif change=='cutoff':m['available_at']='2099-01-01T00:00:00Z'
    elif change=='method':m['calls']['balances']['tool_name']='get_account_positions'
    elif change=='arguments':m['calls']['orders']['arguments']={'show_completed':True}
    else:Path(m['calls']['balances']['local_path']).write_text('{}')
    with pytest.raises(PermissionError):broker_observations(req,save(tmp_path/'manifest.json',m))


def test_failed_provider_call_is_named_and_does_not_turn_into_empty_or_zero(tmp_path):
    req,_,_=case();m=candidate(tmp_path,req);p=Path(m['calls']['orders']['local_path']);body=json.loads(p.read_text())
    body['value']={'isError':True,'content':[{'type':'text','text':'SYNTHETIC_FAILURE'}]}
    m['calls']['orders'].update(save(p,body));out=broker_observations(req,save(tmp_path/'manifest.json',m))
    assert out['orders'] is None and out['pending_exposure'] is None and out['provider_failures']


def test_local_empty_ledger_and_pending_target_do_not_initialize_cycle_or_broker_state():
    req,_,_=case();req['confirmed_target'].update(complete_allocation=False,source_kind='PARTIAL_TARGET_CHANGE_PENDING_WEIGHTS')
    normalized={**{k:req[k] for k in ('client_id','run_id','evaluation_at')},'source_db_sha256':'a'*64,
                'planning_ledger':{'cycle_count':0},'account_cash_observations':[]}
    before=deepcopy((req,normalized));out=produce(req,normalized)
    assert out['local_planning_ledger']['cycle_count']==0 and not out['broker_orders_inferred_empty_from_local_ledger']
    assert out['target_selection']['complete_allocation'] is False and not out['financial_cycle_initialized']
    assert (req,normalized)==before and out['qualified_incremental_authorization'] is None

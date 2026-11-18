"""Synthetic current quotes, reporting values and bounded PM interface scope."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json,sys
import pytest
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5'),str(HERE/'tests')]
from family_input import digest
from current_market_contract import read,new_buy_scope,portfolio_reference
from test_owner_current_business import current_case


def contract_case(tmp_path):
 req,_,_,_=current_case(tmp_path);name='SYN_C'
 html='牌價最新掛牌時間：<span class="time">2026/10/29 12:00</span>\r\n<table><tr><td>美金 (USD)</td><td data-table="本行即期買入">32</td></tr></table>\r\n'
 bank=tmp_path/'SYN_BANK.html';bank.write_bytes(html.encode())
 bank_source={'local_path':str(bank),'sha256':sha256(bank.read_bytes()).hexdigest(),
  'retrieved_at':'2026-10-29T05:00:00Z','source_reference':'https://rate.bot.com.tw/xrt?Lang=zh-TW'}
 from member_position_valuation import read_fx
 fx=read_fx(bank_source,req['evaluation_at']);raw='{"SYNTHETIC":"QUOTE"}'
 quote={'asset':'SYN_ASSET','bytes':len(raw.encode()),'raw_original_utf8':raw,
  'raw_sha256':sha256(raw.encode()).hexdigest(),'validation_issues':[],
  'retrieved_at':'2026-10-29T20:00:00Z','selected_observation':{'price':'50','session_date':'2026-10-29'}}
 data={'schema':'Family.PM.CurrentPriceSupplement.v1','trade':'NONE',
  'member_revaluations':{name:{'source_db_sha256':req['client_snapshot']['payload']['source_sha256']}},
  'sources':{'SYN_ASSET':quote},'official_BOT_FX_original_reader':{'source':bank_source,'original_reader_result':fx},
  'official_BOT_FX_original_utf8':html.replace('\r\n','\n'),'PM_integration_decisions':{}}
 path=tmp_path/'SYN_PM_CURRENT.json'
 def desc():
  path.write_text(json.dumps(data));return {'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
   'member':name,'target_version':1,'source_reference':'SYN_PM_AUTHORITY','available_at':'2026-10-29T22:00:00Z',
   'official_bank_source':deepcopy(bank_source)}
 return req,data,desc,fx


def test_pinned_contract_preserves_exact_bank_bytes_and_old_cutoff_stays_unavailable(tmp_path):
 req,data,desc,fx=contract_case(tmp_path);out=read(desc(),req)
 assert out['official_bank_original_result']==fx and not out['formal_NAV_or_buy_permission_created']
 earlier=deepcopy(req);earlier['evaluation_at']='2026-10-29T21:59:59Z';assert read(desc(),earlier) is None


@pytest.mark.parametrize('change',['member','client','db','snapshot','target','trade','bytes','quote','bank'])
def test_contract_cannot_cross_member_cutoff_approval_or_changed_originals(tmp_path,change):
 req,data,desc,_=contract_case(tmp_path)
 if change=='quote':data['sources']['SYN_ASSET']['raw_original_utf8']='changed'
 source=desc()
 if change=='member':source['member']='OTHER'
 elif change=='client':req['client_id']='OTHER'
 elif change=='db':req['client_snapshot']['payload']['source_sha256']='b'*64
 elif change=='snapshot':req['client_snapshot']['payload']['tables']['injected']=[]
 elif change=='target':source['target_version']=2
 elif change=='trade':req['trade_authorization']='YES'
 elif change=='bytes':Path(source['local_path']).write_text('{}')
 elif change=='bank':Path(source['official_bank_source']['local_path']).write_text('changed')
 with pytest.raises(PermissionError):read(source,req)


def test_reference_cash_counts_once_and_new_buy_absence_is_not_a_zero_target(tmp_path):
 req,data,desc,fx=contract_case(tmp_path)
 data['PM_integration_decisions']['SYN_C']={'status':'NO_ADDITIONAL_BUY_TARGET_AUTHORIZED__PRESERVE_EXISTING_HOLDINGS','symbols':['SYN_ASSET']}
 contract=read(desc(),req);scope=new_buy_scope(contract,'SYN_ASSET')
 assert not scope['zero_target_invented'] and not scope['sell_instruction_created']
 assert new_buy_scope(contract,'OTHER') is None
 common={k:req[k] for k in ('client_id','run_id','evaluation_at')};common['source_db_sha256']='a'*64
 accepted={**common,'accepted_net_available_by_currency':{'TWD':'23','USD':'2.5'}}
 values={**common,'fx_observation':fx,'positions':[{'symbol':'SYN_ASSET','quantity':'2','amount':'100','currency':'USD',
  'observed_close':'50','observed_market_date':'2026-10-29','market_source_sha256':contract['original_quote_hashes']['SYN_ASSET'],'issue':None}]}
 coverage={'holding_and_target_rows':[{'symbol':'SYN_ASSET','route':'V82','target_lines':[]}]}
 before=deepcopy((accepted,values,coverage));out=portfolio_reference(req,coverage,values,accepted,common,contract)
 assert out['positions_plus_accepted_cash_TWD']=='3303.0' and out['current_stock_exposure_TWD']=='3200'
 assert out['additional_cash_target_reserve_deducted']=='0' and not out['SGOV_roles_added_to_cash']
 gap=out['allocation_reference_gaps'][0];assert gap['status']==scope['status'] and gap['approved_target_amount_TWD'] is None
 assert out['issues']==[] and not out['formal_NAV_or_buy_permission_created']
 assert (accepted,values,coverage)==before
 accepted['client_id']='OTHER'
 with pytest.raises(PermissionError):portfolio_reference(req,coverage,values,accepted,common,contract)


@pytest.fixture
def market_case():
 from test_member_v82_analysis import MemberV82Tests
 case=MemberV82Tests();case.setUp()
 try:yield case
 finally:case.doCleanups()


def append_source(case):
 source=case.market();base=json.loads(Path(source['local_path']).read_bytes());raw=deepcopy(base)
 result=raw['chart']['result'][0];old=result['timestamp'][-1];result['timestamp']=[old,old+86400,old+172800]
 result['indicators']['quote']=[{'open':[999,500,600],'high':[1000,501,601],'low':[998,499,599],
  'close':[999,500,600],'volume':[100,100,100]}]
 calendar=Path(source['calendar_source']['local_path']);schedule=json.loads(calendar.read_bytes())
 for stamp in result['timestamp'][1:]:
  day=datetime.fromtimestamp(stamp,timezone.utc)
  schedule['sessions'].append({'session_id':day.date().isoformat(),'open_at':day.replace(hour=13).isoformat(),'close_at':day.replace(hour=20).isoformat()})
 calendar.write_text(json.dumps(schedule));source['calendar_source']['sha256']=sha256(calendar.read_bytes()).hexdigest()
 path=case.folder/'SYN_CURRENT.json';path.write_text(json.dumps(raw))
 source['current_observation_source']={'provider':'YAHOO_CHART','local_path':str(path),
  'sha256':sha256(path.read_bytes()).hexdigest(),'retrieved_at':source['retrieved_at'],'source_reference':'SYN_CURRENT_QUOTE'}
 return source,base


def test_new_closes_extend_history_without_replacing_overlap_and_drive_actual_current_price(market_case):
 from member_market_source import read_market
 case=market_case;source,base=append_source(case);original=deepcopy(source);original.pop('current_observation_source')
 before=read_market(original,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 out=read_market(source,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 assert out['completed_rows'][:len(before['completed_rows'])]==before['completed_rows']
 assert len(out['completed_rows'])==len(before['completed_rows'])+2
 assert out['observed_close']=='600' and out['observed_date']==out['current_quote_append']['appended_completed_dates'][-1]
 assert out['source_sha256']==source['current_observation_source']['sha256']
 assert not out['current_quote_append']['history_replaced'] and not out['history_quality']['formal_deployment_eligible']
 assert json.loads(Path(source['local_path']).read_bytes())==base


@pytest.mark.parametrize('field,value',[('currency','TWD'),('instrumentType','EQUITY'),('symbol','OTHER')])
def test_current_quote_cannot_relabel_currency_listing_or_product(market_case,field,value):
 from member_market_source import read_market
 case=market_case;source,_=append_source(case);path=Path(source['current_observation_source']['local_path'])
 raw=json.loads(path.read_bytes());raw['chart']['result'][0]['meta'][field]=value;path.write_text(json.dumps(raw))
 source['current_observation_source']['sha256']=sha256(path.read_bytes()).hexdigest()
 with pytest.raises(PermissionError):read_market(source,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')


def test_uncompleted_new_session_cannot_supply_a_close(market_case):
 from member_market_source import read_market
 case=market_case;source,_=append_source(case);calendar=Path(source['calendar_source']['local_path'])
 data=json.loads(calendar.read_bytes());data['sessions'][-1]['close_at']='2026-11-01T20:00:00Z';calendar.write_text(json.dumps(data))
 source['calendar_source']['sha256']=sha256(calendar.read_bytes()).hexdigest()
 out=read_market(source,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 assert out['observed_close']=='500' and len(out['current_quote_append']['appended_completed_dates'])==1


def test_stock_ceiling_only_calls_original_math_without_reclassifying_cash_or_bond_targets():
 from v70_tactical_input import calculate,calculate_stock_ceiling
 req={'client_id':'SYNTHETIC','evaluation_at':'2026-10-30T17:14:15Z','owner':{'currency':'TWD'},
  'confirmed_target':{'target_version':1,'payload':{'draft':{'denominator':{'value_state':'KNOWN','amount':'1000000','currency':'TWD'}}}}}
 weights={'stock':'0.60','bond':'0.30','cash':'0.10'}
 contract={'client_id':req['client_id'],'target_version':1,'source_reference':'SYN_PM_STOCK_ONLY',
  'source_descriptor':{'sha256':'a'*64},'decision':{'status':'APPROVED_PM_STOCK_CEILING_ONLY_INTERFACE_CONTRACT',
   'approved_original_weights':weights,'approved_full_portfolio_base_unchanged':True,
   'source_HTML_sha256':sha256((ROOT/'系統工程/總經V70/V70-3-27.html').read_bytes()).hexdigest()}}
 before=deepcopy((req,contract));out=calculate_stock_ceiling(ROOT,req,contract)
 original=calculate(ROOT,req,{'client_id':req['client_id'],'stock_percent':60,'bond_percent':40,'source_reference':contract['source_reference']})
 assert out['native_currency_amounts']=={'stock':original['native_currency_amounts']['stock']}
 assert out['approved_original_weights']==weights and out['consumed_output_keys']==['stock']
 assert out['internal_inputs']['INTERNAL_NON_STOCK_COMPLEMENT']==40
 assert out['allocation_base']==req['confirmed_target']['payload']['draft']['denominator']
 assert not out['bond_and_cash_targets_changed'] and not out['cash_target_deducted_from_available_cash']
 assert (req,contract)==before
 contract['target_version']=2
 with pytest.raises(PermissionError):calculate_stock_ceiling(ROOT,req,contract)


def test_unlisted_new_buy_path_does_not_block_or_receive_other_assets_funding():
 from test_member_funding_summary import REQUEST,financial_row
 from member_funding_summary import reconcile
 excluded={'symbol':'SYN_EXCLUDED','new_buy_scope':{'client_id':REQUEST['client_id'],'run_id':REQUEST['run_id'],
  'symbol':'SYN_EXCLUDED','status':'NOT_APPLICABLE_NO_ADDITIONAL_BUY_AUTHORIZATION','additional_buy_authorized':False}}
 out=reconcile(REQUEST,[financial_row(),excluded])
 assert out['conserved'] and out['unresolved_assets']==[] and out['new_buy_not_applicable_assets']==['SYN_EXCLUDED']
 assert out['accounts'][0]['aggregate']['equity_used']=='20'
 excluded['new_buy_scope']['client_id']='OTHER'
 with pytest.raises(PermissionError):reconcile(REQUEST,[financial_row(),excluded])


def test_reference_quote_preserves_conservative_final_close_gate(market_case):
 from member_market_source import read_market
 case=market_case;source,_=append_source(case);p=Path(source['current_observation_source']['local_path'])
 raw=json.loads(p.read_bytes());last=datetime.fromtimestamp(raw['chart']['result'][0]['timestamp'][-1],timezone.utc)
 raw['chart']['result'][0]['meta']['regularMarketTime']=int(last.replace(hour=20,minute=0,second=2).timestamp())
 p.write_text(json.dumps(raw));source['current_observation_source']['sha256']=sha256(p.read_bytes()).hexdigest()
 source['current_observation_source']['retrieved_at']=last.replace(hour=23).isoformat()
 source['retrieved_at']=(last-timedelta(days=1)).replace(hour=23).isoformat()
 calendar=Path(source['calendar_source']['local_path']);cal=json.loads(calendar.read_bytes());cal['sessions'][-1]['close_at']=last.replace(hour=20,minute=3).isoformat()
 calendar.write_text(json.dumps(cal));source['calendar_source']['sha256']=sha256(calendar.read_bytes()).hexdigest()
 out=read_market(source,symbol='VT',evaluation_at=last.replace(hour=23).isoformat(),repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 assert out['observed_close']=='500'
 assert out['current_reference_quote']['observed_close']=='600'
 assert not out['current_reference_quote']['original_final_close_verified']
 assert out['current_reference_quote']['final_close_qualification_issues']
 assert not out['history_quality']['formal_deployment_eligible']


def test_distinct_reported_broker_source_rows_are_not_real_account_bindings():
 from member_position_valuation import _reported_source_category_keys
 original=[{'symbol':'SYN_BOND','broker_label':'SYN_SOURCE_A','quantity':3},
  {'symbol':'SYN_BOND','broker_label':'SYN_SOURCE_B','quantity':4}]
 facts=[{**r,'quantity':str(r['quantity']),'source_kind':'SEALED_W6','source_run_id':'SYN_BOOK',
  'source_row':{'field_key':'accepted_W6_broker_holdings_json','value_text':json.dumps(original)}} for r in original]
 assert len(_reported_source_category_keys(facts))==2
 duplicate=deepcopy(facts);duplicate[1]=deepcopy(duplicate[0]);assert _reported_source_category_keys(duplicate) is None
 changed=deepcopy(facts);changed[1]['quantity']='99';assert _reported_source_category_keys(changed) is None
 assert all('account_key' not in f for f in facts)


def test_c7_current_round_fx_replaces_only_derived_currency_projection(tmp_path,monkeypatch):
 from test_family_c7_source_assembly import original_case
 from family_c7_source_assembly import SourceAssembler
 import member_reconciliation_source
 _,_,req,ctx,_,_,_,_=original_case(tmp_path)
 current={'base_currency':'USD','quote_currency':'TWD','quote_per_base':'32',
  'as_of':req['evaluation_at'][:10],'source_url':'https://rate.bot.com.tw/xrt?Lang=zh-TW'}
 ctx['family_c7_reporting_fx']={**current,'quote_per_base':'30'}
 normalized={'owner_current_portfolio':{'logical_accounts':[{'owner':req['owner']}]},
  'current_market_contract':{'decision':{}},'position_values':{'fx_observation':current}}
 monkeypatch.setattr(member_reconciliation_source,'read',lambda *a:deepcopy(normalized))
 ctx['member_reconciliation_source']={'local_path':'SYNTHETIC','sha256':'a'*64};before=deepcopy(req)
 assembler=SourceAssembler(ROOT,req,ctx,tmp_path/'private')
 assert assembler.context['family_c7_reporting_fx']==current
 assert assembler.context['native_target_source']['fx_observation']==current
 assert req==before and assembler.request['confirmed_target']==req['confirmed_target']


def test_incomplete_bridge_keeps_long_history_and_reports_latest_quote_separately(market_case):
 from member_market_source import read_market
 case=market_case;source,_=append_source(case);original=deepcopy(source);original.pop('current_observation_source')
 p=Path(source['current_observation_source']['local_path']);raw=json.loads(p.read_bytes());result=raw['chart']['result'][0]
 missing=datetime.fromtimestamp(result['timestamp'][1],timezone.utc).date().isoformat()
 result['timestamp']=[result['timestamp'][i] for i in (0,2)]
 for key,values in result['indicators']['quote'][0].items():result['indicators']['quote'][0][key]=[values[i] for i in (0,2)]
 p.write_text(json.dumps(raw));source['current_observation_source']['sha256']=sha256(p.read_bytes()).hexdigest()
 before=read_market(original,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 out=read_market(source,symbol='VT',evaluation_at=case.at,repo_root=ROOT,profile=None,is_etf=True,observation_route='V75')
 assert out['completed_rows']==before['completed_rows'] and out['source_sha256']==original['sha256']
 assert out['current_reference_quote']['observed_close']=='600'
 assert out['current_quote_append']['missing_bridge_sessions']==[missing]
 assert out['current_quote_append']['appended_completed_dates']==[]

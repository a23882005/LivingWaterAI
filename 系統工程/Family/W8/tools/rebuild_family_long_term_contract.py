"""Explicit engineering schema/lock regeneration for the PM-authorized profile."""
from pathlib import Path
from hashlib import sha256
import json
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'系統工程/C-配置決策引擎＋Mentor整合/正式Runtime';D=BASE/'contracts_c7'
def obj(properties,required=None):return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties) if required is None else required}
text={'type':'string','minLength':1};amount={'type':['number','string','null']}
owner=obj({k:text for k in ('client_id','broker','account','currency','funding_domain')})
receipt=obj({'source_reference_id':text,'source_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},
 'as_of':text,'available_at':text,'qualification':{'const':'VERIFIED_AT_CUTOFF'},
 'complete':{'type':'boolean'},'empty_portfolio_asserted':{'type':'boolean'},
 'confirmed_effects_already_applied':{'type':'array','items':text,'uniqueItems':True}},
 ['source_reference_id','source_sha256','as_of','available_at','qualification'])
base=obj({'base_id':text,'amount':amount,'currency':text,'source_reference_id':text})
ceiling=obj({'amount':amount,'currency':text,'cap_scope':{'const':'TOTAL_PORTFOLIO_STOCK'},
 'accounting_base':{'$ref':'#/$defs/base'},'receipt':{'$ref':'#/$defs/receipt'}})
cap=obj({'cap_id':text,'applicability':{'enum':['REQUIRED','NOT_APPLICABLE']},
 'value_state':{'enum':['KNOWN','UNKNOWN','NONE']},'amount':amount,'currency':text,
 'accounting_base':{'$ref':'#/$defs/base'},'receipt':{'$ref':'#/$defs/receipt'}},['cap_id','applicability','value_state'])
exposure=obj({'event_id':text,'economic_effect_ids':{'type':'array','items':text,'minItems':1,'uniqueItems':True},
 'kind':{'enum':['CONFIRMED_POSITION','ACTIVE_BUY_RESERVATION','OTHER_COMMITMENT','RELEASE']},
 'owner':{'$ref':'#/$defs/owner'},'asset_id':text,'amount':amount,'currency':text,
 'intent_id':{'type':['string','null']},'side':{'enum':['BUY','SELL',None]},'amount_basis':text,
 'lifecycle_state':text,'release_confirmed':{'type':'boolean'},'releases_event_id':text,'release_state':text,
 'receipt':{'$ref':'#/$defs/receipt'}},['event_id','economic_effect_ids','kind','owner','asset_id','amount','currency','receipt'])
funding=obj({'bucket_id':text,'owner':{'$ref':'#/$defs/owner'},'currency':text,'value_state':{'enum':['KNOWN','UNKNOWN']},
 'settled':{'type':['boolean','null']},'cash_amount':amount,'reserved_amount':amount,
 'cash_basis':{'enum':['NET_AVAILABLE','GROSS_SETTLED_CASH']},'authorized_incremental_amount':amount,
 'receipt':{'$ref':'#/$defs/receipt'}})
fx=obj({'owner':{'$ref':'#/$defs/owner'},'from_currency':text,'to_currency':text,'quote_per_base':amount,
 'accounting_base_id':text,'purpose':{'const':'REPORTING_BUDGET_NORMALIZATION_NOT_EXECUTION'},'receipt':{'$ref':'#/$defs/receipt'}})
schema=obj({'schema_version':{'const':'C.FamilyLongTermV70CeilingInput.v1'},
 'profile':{'const':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'},
 'approval_contract_sha256':{'const':'112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0'},
 'identity':{'type':'object','required':['client_id','run_id','portfolio_id']},'family_owner':{'$ref':'#/$defs/owner'},'budget_currency':text,
 'account_owners':{'type':'array','items':{'$ref':'#/$defs/owner'},'minItems':1},
 'source_db_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},'target_version':{'type':['string','integer']},
 'approved_long_term_target':{'type':'object'},'approved_target_digest':{'type':'string','pattern':'^[a-f0-9]{64}$'},
 'approval_receipt':{'$ref':'#/$defs/receipt'},'protection_coverage':{'$ref':'#/$defs/coverage'},'preference_locks':json.loads((D/'57_C_Work6_Mentor_Adjustment_Result.schema.json').read_text())['properties']['preference_locks'],'current_nav':{'type':'object'},
 'total_stock_ceiling':{'$ref':'#/$defs/ceiling'},'portfolio_caps':{'type':'array','items':{'$ref':'#/$defs/cap'}},
 'exposure_coverage':{'$ref':'#/$defs/coverage'},'exposures':{'type':'array','items':{'$ref':'#/$defs/exposure'}},
 'funding_buckets':{'type':'array','items':{'$ref':'#/$defs/funding'},'minItems':1},
 'budget_normalizations':{'type':'array','items':{'$ref':'#/$defs/fx'}},
 'upstream_net_capacity':obj({'producer_contract':text,'gross_input_digest':text,'amount':amount,'receipt':{'$ref':'#/$defs/receipt'}})},
 ['schema_version','profile','approval_contract_sha256','identity','family_owner','account_owners','budget_currency','source_db_sha256',
 'target_version','approved_long_term_target','approved_target_digest','approval_receipt','protection_coverage','preference_locks','current_nav','total_stock_ceiling',
 'portfolio_caps','exposure_coverage','exposures','funding_buckets'])
schema.update({'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:livingwater:c7:family-long-term-input:v1',
 '$defs':{'owner':owner,'receipt':receipt,'coverage':dict(receipt,required=receipt['required']+['complete','empty_portfolio_asserted','confirmed_effects_already_applied']),'base':base,'ceiling':ceiling,'cap':cap,'exposure':exposure,'funding':funding,'fx':fx}})
w6=json.loads((D/'57_C_Work6_Mentor_Adjustment_Result.schema.json').read_text())
w6['$id']='urn:livingwater:c7:family-work6-existing-long-term:v1'
w6['properties']['contract_version']={'const':'C-W6-FAMILY-LT-v1.0.0'}
w6['properties']['loop_status']={'enum':['BLOCKED','V70_REROUTE_REQUIRED','EXISTING_LONG_TERM_TARGET_READ']}
w6['properties']['mentor_result_contract']['properties']['display_status']={'enum':['BLOCKED','V70_REROUTE_REQUIRED','EXISTING_LONG_TERM_TARGET_READ']}
w6['properties']['family_scope_evidence']={'type':'object','required':['profile','approval_contract_sha256','input_scope_digest','approved_long_term_target','current_engine_result','project_target_money_base','current_weight_and_drift_base','new_confirmation_created'],
 'properties':{'profile':{'const':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'},'approval_contract_sha256':{'const':'112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0'},'new_confirmation_created':{'const':False},'tactical_target_approved':{'const':False},'project_target_money_rebased_to_NAV':{'const':False}}}
w6['required'].append('family_scope_evidence')
(D/'84_Family_Existing_LongTerm_Work6_Result.schema.json').write_text(json.dumps(w6,ensure_ascii=False,indent=2)+'\n')

w7=json.loads((D/'68_C_Work7_V70_Asset_Framework_Result.schema.json').read_text())
w7['$id']='urn:livingwater:c7:family-long-term-work7-result:v1'
w7['properties']['contract_version']={'const':'C-W7-FAMILY-LT-v1.0.0'}
w7['properties']['family_scope_evidence']={'type':'object','required':['profile','approval_contract_sha256','input_scope','canonical_input','input_scope_digest','source_db_sha256','target_version','family_owner','approved_long_term_target','project_target_money_base','current_weight_and_drift_base','same_run_v70_total_ceiling','occupancy_and_capacity','new_confirmation_created','production_released'],
 'properties':{'profile':{'const':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'},'approval_contract_sha256':{'const':'112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0'},'new_confirmation_created':{'const':False},'tactical_target_approved':{'const':False},'production_released':{'const':False}}}
w7['required'].append('family_scope_evidence')
w7['$defs']['ResidualAllocation']=obj({'method':{'const':'PRESERVE_LONG_TERM_NO_V70_RESIDUAL_SCALING'},'buckets':{'type':'array','minItems':0,'items':{'type':'object'}}})
w7['$defs']['ResidualItem']['properties']['allocation_rule']={'const':'PRESERVE_EXISTING_LONG_TERM_EFFECTIVE_VIEW'}
(D/'85_Family_LongTerm_Work7_Result.schema.json').write_text(json.dumps(w7,ensure_ascii=False,indent=2)+'\n')

(D/'83_Family_LongTerm_V70Ceiling_Input.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
files=['work7/family_long_term.py','work7/asset_framework.py','C8C9_RUNTIME/C8C9_Work8_Protected_Holding_Client_Action_Protection.py',
 'contracts_c7/69_C_Work7_V70_資產框架整合_LockedResidual_RadarSnapshot.md','contracts_c7/83_Family_LongTerm_V70Ceiling_Input.schema.json',
 '../../Family/W5/family_ceiling_bridge.py','../../Family/W5/c7_engine.py','../../Family/W5/configuration_source.py',
 '../../Family/W5/target_units.py','../../Family/W5/target_source_bridge.py','../../Family/W5/stock_engine.py','../../Family/W5/native_pipeline.py',
 '../../Family/W5/v82_slice_bridge.py','../../Family/W5/family_runner.py','../../Family/W8/deployment_c7_sources.py',
 '../../Family/W8/member_financial_chain.py','../../Family/W8/member_funding_summary.py','../../Family/W8/native_asset_source.py','../../Family/W8/member_financial_producer.py','../../Family/W8/family_c7_source_assembly.py','../../Family/W8/w1_portfolio_observations.py','../../Family/W8/same_run_market_cache.py',
 '../../Family/W8/approved_v04_technical.py','../../Family/W5/technical_source_bridge.py','../../Family/W8/tools/rebuild_family_long_term_contract.py',
 '../../Family/W8/v70_tactical_input.py','../../Family/W8/v70_component_runtime.cjs']
files += [p for p in ['work6/family_long_term_read.py','contracts_c7/84_Family_Existing_LongTerm_Work6_Result.schema.json','contracts_c7/85_Family_LongTerm_Work7_Result.schema.json'] if (BASE/p).exists()]
manifest={'profile':'FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1','approval_sha256':'112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0',
 'status':'APPROVED_FOR_IMPLEMENTATION__PM_GATE_NOT_RELEASED','files':[{'path':p,'sha256':sha256((BASE/p).read_bytes()).hexdigest()} for p in files]}
(D/'Family_LongTerm_V70Ceiling_v1.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
lock=ROOT/'系統工程/Family/W5/dependency_lock.json';data=json.loads(lock.read_text());rows=data['files'] if isinstance(data,dict) else data
new=[str((BASE/p).resolve().relative_to(ROOT)) for p in files]+[str((D/'Family_LongTerm_V70Ceiling_v1.manifest.json').relative_to(ROOT))]
for path in new:
 if not any(r['path']==path for r in rows):rows.append({'path':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()})
for r in rows:r['sha256']=sha256((ROOT/r['path']).read_bytes()).hexdigest()
lock.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
source_lock=ROOT/'系統工程/Family/W5/source_lock.json';data=json.loads(source_lock.read_text())
for row in data['files']:
 if row['path'].endswith('/C8C9_Work8_Protected_Holding_Client_Action_Protection.py'):
  row['sha256']=sha256((ROOT/row['path']).read_bytes()).hexdigest()
  raw=(ROOT/row['path']).read_bytes()
  from hashlib import sha1
  row['size']=len(raw);row['git_blob_sha']=sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  row['commit_scope']='UPSTREAM_ANCHOR_ONLY__FAMILY_EXTENSION_LOCKED_BY_SHA256'
  row['family_revision']='PM_20261030_FAMILY_LT_PROFILE_V1_READONLY'
  row['family_profile_extension']={'approval_contract_sha256':manifest['approval_sha256'],
    'scope':manifest['profile'],'legacy_schema_and_guard_preserved':True,'pm_gate_released':False}
source_lock.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print('Family profile schemas/source locks updated:',len(files))

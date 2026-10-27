"""Produce a source-bound first-asset handoff through the original adapters.

No fixture is used. Original adapter failures stop production with their code,
field and detail. A partial result is not a native bundle or a Mentor result.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import importlib.util
import json
import hashlib
import sqlite3
import re
import sys
import uuid

HERE=Path(__file__).resolve().parent
W5=HERE.parent/'W5'
if str(W5) not in sys.path:sys.path.insert(0,str(W5))
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
from family_input import digest
from family_boundary import prepare_input
from runtime_loader import load_c_module
from official_holdings_source import project_official_holdings
from loop2_cash_scenario import build_cash_overlay, validate_cash_overlay

# V82.md §32.2 lists these eleven classes. Only its explicit examples are
# resolved here. Company classes require their original per-company sources.
FORMAL_CLASSES=('全球股票ETF','美國大型核心ETF','科技／AI／高成長ETF',
    '台灣大型權值ETF','製藥／醫療ETF','美國中小型ETF','半導體ETF',
    '國防／軍工ETF','產業／主題ETF','大型成熟／高品質個股','高Beta／事件型個股')
EXAMPLES={'VT':0,'VWRA':0,'VOO':1,'SPY':1,'QQQ':2,'VGT':2,'0050':3,
          'PPH':4,'XLV':4,'IWM':5,'SOXX':6,'SMH':6,'NATO':7,'ITA':7}


def native_error_path(error):
    schema=re.search(r'schema rejection at ([^:]+):',str(error))
    if schema:return schema.group(1)
    money=re.search(r'c7\.contexts\[(\d+)\]\.([a-z_]+)',str(error))
    if money:return '/c7_funding_context/contexts/'+money.group(1)+'/'+money.group(2)
    return 'c7_funding_context.contexts' if getattr(error,'code',None)=='C8C9.W4.C7_DOMAIN_SET' else None


def classification(symbol, source, product_source=None):
    text=Path(source['local_path']).read_text(encoding='utf-8-sig')
    from hashlib import sha256
    if sha256(Path(source['local_path']).read_bytes()).hexdigest()!=source['sha256']:
        raise ValueError('CLASSIFICATION_SOURCE_CHANGED')
    if not all(name in text for name in FORMAL_CLASSES):
        raise ValueError('FORMAL_ELEVEN_CLASSES_NOT_IN_SOURCE')
    index=EXAMPLES.get(symbol)
    name=FORMAL_CLASSES[index] if index is not None else 'UNKNOWN'
    framework='第四十九章｜VT／VWRA型' if index==0 else None
    if framework and '# '+framework not in text:
        raise ValueError('FORMAL_FRAMEWORK_NOT_IN_SOURCE')
    result={'primary_class':name,'primary_framework':framework,
        'formal_class_count':len(FORMAL_CLASSES),'source_reference':source['source_reference'],
        'source_sha256':source['sha256'],'sot_section':'V82.md §32.2 / chapter 49' if index==0 else 'V82.md §32.2',
        'asset_type':None,'asset_grade':'UNKNOWN','grade_evidence':None}
    if symbol=='VT' and product_source is not None:
        raw=Path(product_source['local_path']).read_bytes()
        if sha256(raw).hexdigest()!=product_source['sha256']:
            raise ValueError('PRODUCT_STRUCTURE_SOURCE_CHANGED')
        product=json.loads(raw)
        facts=product.get('excerpts',[])
        if (product.get('symbol')!='VT' or product.get('source_url')!=
                'https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf'
                or not all(x in facts for x in ('FTSE Global All Cap Index','Passively managed',
                    'developed and emerging','large-, mid-, and small-capitalization'))):
            raise ValueError('VT_OFFICIAL_STRUCTURE_EVIDENCE_REQUIRED')
        if '廣泛分散核心市場結構 → `A`' not in text:
            raise ValueError('FORMAL_BROAD_DIVERSIFIED_GRADE_RULE_REQUIRED')
        result.update(asset_type='BROAD_ETF',asset_grade='A',grade_evidence={
            'rule':'V82.md Canonical Asset Grade §2.1.1',
            'source_url':product['source_url'],'source_sha256':product_source['sha256'],
            'facts':deepcopy(facts),'basis':'GLOBAL_PASSIVE_DIVERSIFIED_STRUCTURE__NOT_TICKER_DEFAULT'})
    return result


def cash_trial(snapshot, owner, policy, *, db_path=None, run_id='UNBOUND_DIAGNOSTIC'):
    """Apply the explicit cash-only assumption, without changing any source row."""
    if (policy.get('schema_version')!='Family.W8.CashTrialPolicy.v1' or
        policy.get('missing_cash_value')!='0' or not policy.get('source_reference')):
        raise ValueError('EXPLICIT_CASH_TRIAL_POLICY_REQUIRED')
    if owner.get('client_id')!=snapshot['client_id']:
        raise PermissionError('CASH_TRIAL_CLIENT_MISMATCH')
    view=project_official_holdings(snapshot)
    total=[]
    for row in view['cash_sources']:
        if (owner.get('broker')=='IBKR' and owner.get('currency')=='USD'
                and row.get('symbol')=='USD_CASH' and row.get('broker_label')=='IB'):
            total.append((row['quantity'],row))
        elif (owner.get('broker')=='IBKR' and row.get('field')=='cash_balance' and row.get('value_state')=='KNOWN'
              and row['source_row'].get('entity_key')=='IB_SCREEN'
              and row.get('currency')==owner['currency']):
            total.append((row['value'],row))
    if len(total)>1:raise ValueError('CASH_TOTAL_SOURCE_AMBIGUOUS')
    values={'total':None,'available':None,'unsettled':None,'reserved':None};facts={}
    if total:
        values['total']=str(total[0][0]);facts['total']=deepcopy(total[0][1])
    # Read the existing W1 view rather than inventing an available-cash formula.
    if db_path is not None:
        path=Path(db_path).resolve(strict=True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=snapshot['source_sha256']:
            raise PermissionError('CASH_TRIAL_DB_MISMATCH')
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            cash_rows=[dict(r) for r in db.execute('SELECT * FROM cash_available_view WHERE client_id=? '
                'AND account_key=? AND currency_code=? ORDER BY as_of_utc DESC,version DESC',
                (snapshot['client_id'],owner['account'],owner['currency']))]
        if cash_rows and cash_rows[0]['available_state']=='VERIFIED':
            row=cash_rows[0]
            # W1's currency minor units are source data, never assumed here.
            currency=next(r for r in snapshot['tables']['currency_registry'] if r['currency_code']==owner['currency'])
            exponent=currency.get('minor_digits')
            if exponent is None:raise ValueError('CASH_MINOR_UNIT_SOURCE_REQUIRED')
            scale=Decimal(10)**int(exponent)
            values['available']=str(Decimal(row['available_minor'])/scale);facts['available']=row
            if row.get('reserved_minor') is not None:
                values['reserved']=str(Decimal(row['reserved_minor'])/scale);facts['reserved']=row
        if hashlib.sha256(path.read_bytes()).hexdigest()!=snapshot['source_sha256']:
            raise PermissionError('CASH_TRIAL_DB_CHANGED')
    # Verified W1 cash rows retain their original account/currency and precision.
    rows=[r for r in snapshot['tables'].get('cash_balance_snapshot',[])
          if r.get('account_key')==owner['account'] and r.get('currency_code')==owner['currency']]
    if rows:
        latest=max(rows,key=lambda r:(r['as_of_utc'],r['version']))
        if latest.get('data_state')=='VERIFIED':
            currencies=[r for r in snapshot['tables']['currency_registry'] if r['currency_code']==owner['currency']]
            if len(currencies)!=1:raise ValueError('CASH_CURRENCY_SOURCE_REQUIRED')
            exponent=currencies[0].get('minor_digits')
            if exponent is None:raise ValueError('CASH_MINOR_UNIT_SOURCE_REQUIRED')
            scale=Decimal(10)**int(exponent)
            for field,col in [('total','reported_cash_minor'),('reserved','reserved_minor')]:
                if latest.get(col) is not None:
                    candidate=str(Decimal(latest[col])/scale)
                    if values[field] is not None and Decimal(values[field])!=Decimal(candidate):
                        raise ValueError('CASH_SOURCE_CONFLICT:cash_state.'+field)
                    values[field]=candidate;facts[field]=deepcopy(latest)
    scenario=build_cash_overlay(values,snapshot=snapshot,owner=owner,
        authorization=policy,run_id=run_id)
    validated=validate_cash_overlay(values,scenario,snapshot=snapshot,owner=owner,
        authorization=policy,run_id=run_id)
    # Conflicting or malformed cash remains in the isolated diagnostic context;
    # it cannot become effective native cash or be masked with another zero.
    values=validated['effective_cash']
    return {'owner':deepcopy(owner),'currency':owner['currency'],
        'cash_state':{k:float(Decimal(v)) for k,v in values.items()} if values else None,
        'decimal_values':values,'formal_sources':facts,'assumptions':scenario['assumptions'],
        'scenario':scenario,'issues':validated['issues'],
        'label':'缺漏現金按 0 試算','official_cash_records_changed':False}


class AssetSourceProducer:
    """Trusted raw snapshot/approval -> original Work3 -> original Work4.

    The bootstrap contains existing approval/account proofs, never a native
    bundle. The member snapshot is freshly supplied by the official menu.
    """
    def __init__(self, *, repo_root, request_seed, context_seed, cash_policy,
                 classification_source, source_commit, focus_symbol='VT',db_path=None,product_source=None,
                 flow='HOLDINGS_ANALYSIS', analyze_all=True):
        self.root=Path(repo_root);self.req=deepcopy(request_seed);self.ctx=deepcopy(context_seed)
        self.policy=deepcopy(cash_policy);self.class_source=deepcopy(classification_source)
        self.source_commit=source_commit;self.symbol=focus_symbol
        self.db_path=db_path
        self.product_source=deepcopy(product_source)
        if flow not in ('HOLDINGS_ANALYSIS','DEPLOYMENT'):
            raise ValueError('INVALID_MENU04_INTERNAL_FLOW')
        self.flow=flow;self.analyze_all=analyze_all

    def __call__(self,snapshot,payload):
        if snapshot!=self.req['client_snapshot']['payload']:
            raise PermissionError('PRODUCER_APPROVAL_SNAPSHOT_CHANGED')
        req=deepcopy(self.req);ctx=deepcopy(self.ctx)
        when=datetime.now(timezone.utc).isoformat();run='family-04-'+uuid.uuid4().hex
        req.update(run_id=run,request_id=run+'-request',evaluation_at=when)
        req['client_snapshot']['as_of']=when
        # Refresh the actual W3 feed independently; no old result is re-labelled.
        from market_bridge import read_macro_snapshot
        macro=read_macro_snapshot(self.root,source_commit=self.source_commit)
        req['macro_snapshot']=macro
        req['expected_versions']['market']=ctx['expected_versions']['market']=macro['digest']
        prepared=prepare_input(req,trusted_context=ctx)
        found=[r for r in prepared.payload['positions'] if r['source_instrument'].get('ticker')==self.symbol]
        if len(found)!=1:raise ValueError('FOCUS_ASSET_SOURCE_MISSING_OR_AMBIGUOUS')
        held=found[0];asset_class=classification(self.symbol,self.class_source,self.product_source)
        if self.flow=='DEPLOYMENT' and asset_class['primary_class']!=FORMAL_CLASSES[0]:
            raise ValueError('CLASS_SPECIFIC_NATIVE_PRODUCER_REQUIRED')
        trial=cash_trial(snapshot,req['owner'],self.policy,db_path=self.db_path,run_id=run)
        if self.flow=='DEPLOYMENT' and trial['issues']:
            raise ValueError(trial['issues'][0]['code']+':'+trial['issues'][0]['field_path'])
        spec=importlib.util.spec_from_file_location('asset_source_market',HERE/'on_demand_market_observations.py')
        market=importlib.util.module_from_spec(spec);spec.loader.exec_module(market)
        holdings=project_official_holdings(snapshot,evaluation_at=when)
        observations=market.build_member_market_observations(snapshot,[],macro,repo_root=self.root,
            evaluation_at=when,official_holdings=holdings)
        # A branches before constructing or loading any deployment adapter.
        # It retains original source/owner checks but needs no new-money plan.
        if self.flow=='HOLDINGS_ANALYSIS':
            from holdings_analysis import build_analysis_report
            report=build_analysis_report(self,req,ctx,prepared,holdings,observations,trial)
            return {'request':req,'trusted_context':ctx,'analysis_report':report,
                'source_metadata':{'client_id':req['client_id'],'run_id':run,
                    'source_db_sha256':snapshot['source_sha256']}}
        observed=next((r for r in observations['assets'] if r['symbol']==self.symbol),None)
        report={'schema_version':'Family.W8.NativeSourceProduction.v1','client_id':req['client_id'],
            'run_id':run,'owner':deepcopy(req['owner']),'source_db_sha256':snapshot['source_sha256'],
            'request_digest':digest(req),'focus_symbol':self.symbol,'classification':asset_class,
            'prepared_account_positions':deepcopy(prepared.payload['positions']),
            'full_household_sources':holdings,'cash_trial':trial,'market_observations':observations,
            'call_trace':['W8.menu04.source_producer','W5.prepare_input','W5.project_official_holdings'],
            'native_inputs':{},'native_outputs':{},'mentor':None,'complete_native_bundle':False,
            'full_native_mentor_reached':False,'trade_authorization':'NONE'}
        report['analysis_mode']='CASH_ZERO_SIMULATION'
        if observed:
            report['native_outputs']['v82_core_observation']=self.core_observation(observed)
            report['call_trace'].append('V82.evaluate_core_rule_state:observations_only')
        owner={'funding_domain':'US_BROKER','broker':req['owner']['broker'],'account':req['owner']['account']}
        ref='DB:'+snapshot['source_sha256'];target=req['confirmed_target']['payload'];draft=target['draft']
        v70_id='V70-SOURCE-INPUT-'+macro['digest'][:24]
        v70={'run_id':run,'source_namespace':'V70.RUNTIME_CONTEXT','upstream_v70_snapshot_id':v70_id,
            'snapshot_as_of':macro['asOf'],'data_as_of':{'macro':macro['asOf']},'source_reference_ids':[ref],
            'payload':{'run_id':run,'stock_tactical_amount':None,'bond_tactical_amount':None,
                'v70_original_dry_powder_amount':None,'value_state':'UNKNOWN','data_quality':'UNKNOWN',
                'issue_codes':['V70_MONETARY_SOURCE_NOT_PRODUCED']}}
        # Available cash is zero in this run when it was absent. No positive
        # budget is inferred from a total balance or an unverified settlement.
        available=Decimal(trial['decimal_values']['available'])
        budget='0' if available==0 else None
        legs={leg:{'amount':budget,'currency':req['owner']['currency'],'cash_basis':'AVAILABLE',
                   'owner':deepcopy(owner)} for leg in ('equity','bond')}
        final={'allocation_id':draft['allocation_id'],'authorization_reference':draft['allocation_id'],
            'confirmation_proof':{k:target['confirmation_evidence'][k] for k in ('confirmed_at','confirmed_by')},
            'payload':{'instrument_targets':{r['instrument_id']:{'project_target_position':
                r['target_amount']['amount'] if r['target_amount']['value_state']=='KNOWN' else None}
                for r in draft['target_lines']}}}
        if self.symbol not in final['payload']['instrument_targets']:
            # Target absence is not changed into a guessed monetary zero.
            final['payload']['instrument_targets'][self.symbol]={'project_target_position':None}
        w3=load_c_module(self.root,3);w4=load_c_module(self.root,4)
        envelope={'contract_name':w3.WORK2_ENVELOPE_NAME,'contract_version':w3.WORK2_ENVELOPE_VERSION,
            'baseline_id':w3.BASELINE_ID,'run_id':run,'owner':owner,'currency':req['owner']['currency'],
            'settlement':{'cash_basis':'AVAILABLE','cash_state':trial['cash_state'],
                'source_status':'TRIAL_MISSING_CASH_ZERO'},'final_target':final,
            'remaining_target_gap':{'v82':{'mode':'V82_EXISTING_RUNTIME_DERIVED','payload':{'source_owned':True,'asset':self.symbol}},
                'v75':{'mode':'V75_EXISTING_EXPLICIT_GAP','payload':{'remaining_target_gap_amount':None}}},
            'executable_budget':legs,'temporal':{'as_of':when,'data_as_of':{'W1':req['client_snapshot']['as_of'],'V70':macro['asOf']}},
            'versions':{'rule':req['expected_versions'],'data':{'W1':snapshot['source_sha256']},'schema':{'Family':'W5.request.v1'}},
            'lineage':{'source_reference_ids':[ref],'upstream_snapshot_ids':{'v70':v70_id,'c7':None}},
            'reason_status':{'source_reason_codes':{'C7':['C7_SOURCE_NOT_PRODUCED']},
                'source_status_codes':{'C7':'UNKNOWN'},'integration_diagnostics':[]},
            'sgov_boundary':{'v70_original_dry_powder':{'amount':None,'weight':None,'source_status':'UNKNOWN'},
                'sgov_bond_bucket_amount':None,'sgov_dry_powder_bucket_amount':None,
                'v75_undeployed_to_sgov':None,'v82_undeployed_to_sgov':None,'roles_kept_separate':True,
                'v82_access_forbidden':True,'v82_raw_equity_budget_auto_route_forbidden':True,
                'final_aggregate_computed_in_work2':False,'physical_subledger_out_of_scope':True}}
        shared={'run_id':run,'source_namespace':'LOOP2.SHARED_DECISION_CONTEXT','context_id':'CTX-'+run,
            'context_version':'Family.W8.RawSource.v1','as_of':when,'data_as_of':{'macro':macro['asOf']},
            'payload':{'macro':deepcopy(macro['payload']),'full_client_snapshot':deepcopy(snapshot),
                       'cash_trial':deepcopy(trial),'market_observations':observations},
            'source_reference_ids':[ref],'versions':{'source_db':snapshot['source_sha256']}}
        native_request={'contract_name':w3.INPUT_CONTRACT_NAME,'contract_version':w3.INPUT_CONTRACT_VERSION,
            'baseline_id':w3.BASELINE_ID,'run_id':run,'work2_envelope':envelope,
            'client_state_context':{'run_id':run,'source_namespace':'C.CLIENT_STATE',
                'payload':{'client_id':req['client_id'],'portfolio_id':req['owner']['account'],
                           'full_client_snapshot':deepcopy(snapshot)},'data_as_of':req['client_snapshot']['as_of'],
                'source_reference_ids':[ref]},'v70_runtime_context':v70,'shared_decision_context':shared}
        report['native_inputs']['work3']=deepcopy(native_request)
        function='C8C9.Work3.build_context_handoff'
        contexts=[]
        try:
            report['call_trace'].append(function)
            handoff=w3.build_context_handoff(native_request)
            report['native_outputs']['work3']=handoff
            contexts,cash_sources=self.funding_contexts(snapshot,owner,trial,run,ref)
            report['cash_by_domain']=cash_sources
            c7={'contract_name':'LivingWaterAI.C.Work7.FundingContext','contract_version':'C-W7-FUND-v1.0.0',
                'run_id':run,'base_currency':req['owner']['currency'],'bank_cash_scope':'OUT_OF_SCOPE',
                # A cash balance is not an authorized new-investment pool.
                'total_new_investment_amount':None,
                'contexts':contexts,'source_reference_ids':[ref]}
            stock={'contract_name':w4.INPUT_CONTRACT_NAME,'contract_version':w4.INPUT_CONTRACT_VERSION,
                'baseline_id':w4.BASELINE_ID,'run_id':run,'work3_handoff':handoff,'c7_funding_context':c7,
                'asset_context':{'asset':{'asset_id':self.symbol,'asset_type':asset_class['asset_type'],
                    'asset_grade':asset_class['asset_grade'],'portfolio_role':'UNKNOWN'},
                    'client_project_version':str(draft.get('original_allocation_version',req['expected_versions']['target'])),
                    'project_target_pointer':'/instrument_targets/'+self.symbol+'/project_target_position',
                    'confirmed_position_snapshot':{'quantity':held['quantity'],'source':'BROKER'}}}
            report['native_inputs']['stock_request']=stock
            function='C8C9.Work4.build_v82_runtime_input';report['call_trace'].append(function)
            report['native_outputs']['work4']=w4.build_v82_runtime_input(stock)
        except ValueError as error:
            report['status']='BLOCKED_BY_ORIGINAL_ADAPTER'
            report['first_failure']={'function':function,'code':getattr(error,'code',type(error).__name__),
                'raw_error':str(error),'detail':getattr(error,'detail',str(error)),
                'field_path':native_error_path(error)}
        else:
            report['status']='SOURCE_STAGE_INCOMPLETE'
            report['first_failure']={'function':'W8.AssetSourceProducer','code':'DOWNSTREAM_NATIVE_SOURCES_REQUIRED',
                'field_path':'native_bundle','raw_error':'Remaining native source contracts have not been produced'}
        report['source_inventory']={
            'holdings':'MAPPED_FROM_ACCEPTED_SEALED_SOURCE',
            'classification':'MAPPED_FROM_FORMAL_ELEVEN_CLASSES',
            'cash':'FORMAL_VALUES_PLUS_EXPLICIT_CASH_ONLY_ZERO_TRIAL',
            'work3_handoff':'ORIGINAL_BUILDER_EXECUTED' if 'work3' in report['native_outputs'] else 'NATIVE_BUILDER_REJECTED',
            'stock_request':'PRODUCED_AND_PASSED_TO_ORIGINAL_WORK4' if 'stock_request' in report['native_inputs'] else 'UPSTREAM_REJECTED',
            'bond_request':'NOT_PRODUCED_IN_FIRST_ASSET_SOURCE_STAGE',
            'stock_evidence':'ORIGINAL_CORE_OBSERVATIONS_ONLY__FORMAL_METADATA_AND_FUNDAMENTALS_UNRESOLVED',
            'producer_contract':'FORMAL_DEPLOYMENT_ATTESTATION_NOT_PRODUCED',
            'stock_source_fields':'FORMAL_49_FIELD_ASSEMBLY_NOT_REACHED',
            'bond_evidence':'OBSERVATIONS_AVAILABLE__COMPLETE_NATIVE_BOND_EVIDENCE_NOT_PRODUCED',
            'asset_framework':'C7_NATIVE_FUNDING_CONTEXT_NOT_READY',
            'physical_sgov':'SOURCE_QUANTITY_PRESERVED__NATIVE_ROLE_RECONCILIATION_NOT_REACHED'}
        if 'stock_request' in report['native_inputs']:
            report['funding_domain_diagnosis']={
                'native_required_domains':['TW_LOCAL_BROKER','TW_SUB_BROKERAGE','US_BROKER'],
                'native_context_count':len(c7['contexts']),
                'verified_context_domains':[r['domain'] for r in c7['contexts']],
                'original_member_accounts':deepcopy(snapshot['tables']['portfolio_account']),
                'original_broker_links':deepcopy(snapshot['tables'].get('account_broker_link',[])),
                'original_funding_domains':deepcopy(snapshot['tables'].get('funding_domain',[])),
                'unused_domain_representation_in_original_schema':None,
                'invented_accounts':False,'native_contract_modified':False}
        missing_identity=[f'/c7_funding_context/contexts/{i}/{field}'
            for i,row in enumerate(contexts) for field in ('broker','account') if row.get(field) is None]
        report['issues']=[{'code':'CONTRACT_SCOPE_UNSUPPORTED','stage':'NATIVE_INPUT_READY',
            'field_path':path,'source_id':ref,'producer':'W8.AssetSourceProducer.funding_contexts',
            'missing_reason':'Required native domain identity is absent; original schema has no unused-domain representation',
            'remediation':'Provide an approved identity mapping or a versioned unused-domain contract; do not invent an account',
            'retryable':False,'evidence_ref':'funding_domain_diagnosis'} for path in missing_identity]
        report['issues'] += [{'code':'NATIVE_INPUT_MAPPING_REQUIRED','stage':'NATIVE_INPUT_READY',
            'field_path':path,'source_id':ref,'producer':'W8.AssetSourceProducer.funding_contexts',
            'missing_reason':'Cash authorization does not establish an investment pool',
            'remediation':'Map the existing approved funding evaluation and assignment; retain unknown if absent',
            'retryable':False,'evidence_ref':'native_inputs.stock_request.c7_funding_context'}
            for path in ['/c7_funding_context/total_new_investment_amount']+
            [f'/c7_funding_context/contexts/{i}/bucket_new_investment_amount' for i in range(len(contexts))]]
        report['mode']='CASH_ZERO_SIMULATION'
        report['source_data_provenance']='SOURCE_BACKED'
        report['effective_input_provenance']='CASH_ZERO_SIMULATION'
        report['stage_status']={'SOURCE_LOADING':'COMPLETED','SOURCE_READY':'COMPLETED',
            'MAPPING_READY':'PARTIAL','NATIVE_INPUT_READY':'BLOCKED',
            'NATIVE_COMPLETE':'NOT_REACHED','MENTOR_READY':'NOT_REACHED'}
        report['coverage']=[{'position_identity':deepcopy(row['owner']) if 'owner' in row else deepcopy(req['owner']),
            'instrument_id':row['instrument_key'],'source_instrument':deepcopy(row['source_instrument']),
            'status':'BLOCKED','native_complete':False,'mentor_ready':False,
            'reason':'TRACED_NATIVE_CONTRACT_REJECTION' if row['source_instrument'].get('ticker')==self.symbol
                else 'NOT_RUN__SHARED_REQUIRED_FUNDING_CONTEXT_UNRESOLVED'}
            for row in prepared.payload['positions']]
        report['coverage_scope']='ACCEPTED_SELECTED_IB_ACCOUNT__NOT_ALL_HOUSEHOLD_ASSETS'
        report['manifest']=self.source_manifest(report,req,held,ref)
        report['manifest_digest']=digest(report['manifest'])
        report['readable_analysis']={'symbol':self.symbol,'classification':asset_class['primary_class'],
            'framework':asset_class['primary_framework'],'source_quantity':held['quantity'],
            'asset_type':asset_class['asset_type'],'asset_grade':asset_class['asset_grade'],
            'observed_close':observed['observed_close'] if observed else None,
            'price_observation_date':observed['observed_date'] if observed else None,
            'price_scope':'CACHED_CLOSE_OBSERVATION__NOT_FULL_FORMAL_MARKET_ATTESTATION',
            'original_core_state':report['native_outputs'].get('v82_core_observation',{}).get('result'),
            'cash_assumption':trial['label'],'native_deployment_completed':False,
            'native_work9_mentor_completed':False,'first_blocker':report['first_failure']}
        core=report['readable_analysis']['original_core_state'] or {}
        permission=core.get('permission',{})
        report['analysis_summary']=(f"{self.symbol}｜{asset_class['primary_class']}；主框架：{asset_class['primary_framework']}。"
            f"本人帳戶來源持倉 {held['quantity']} 股。"
            +(f"快取收盤觀測 {observed['observed_close']}（{observed['observed_date']}）；正式行情證明未齊。" if observed else '尚無可用的同標的價格觀測。')
            +f"原 V82 Core：估值 {core.get('valuation',{}).get('level','UNKNOWN')}，"
            f"基本面 {core.get('fundamentals',{}).get('context','UNKNOWN')}，"
            f"新增買單允許={permission.get('new_buy_order_permission','UNKNOWN')}，"
            f"原因={','.join(permission.get('reason_codes',[]))}。"
            f"{trial['label']}；正式現金紀錄未變更。"
            f"原生部署與 Work9 Mentor 尚未完成；第一阻塞為 {report['first_failure']['function']}："
            f"{report['first_failure']['raw_error']}。")
        report['report_digest']=digest(report)
        return {'request':req,'trusted_context':ctx,'source_production':report,
            'source_metadata':{'client_id':req['client_id'],'run_id':run,'source_db_sha256':snapshot['source_sha256']}}

    def source_manifest(self, report, request, held, source_id):
        """Field-level source records and honest gaps for the first slice."""
        records=[]
        def add(path,field,reader,transform,value,status='SOURCE_BACKED',source=source_id,
                source_hash=None,observed_at=None):
            records.append({'field_path':path,'source_id':source,'source_field':field,
                'reader':reader,'producer':'W8.AssetSourceProducer','builder':
                    'C8C9.Work4.build_v82_runtime_input' if path.startswith('stock_request') else None,
                'transform':transform,'source_hash':source_hash or report['source_db_sha256'],
                'observed_at':observed_at,'available_at':None,
                'evidence_status':status,'output_digest':digest(value)})
        add('stock_request.asset_context.confirmed_position_snapshot.quantity',
            'prepared.positions[source_instrument.ticker='+self.symbol+'].quantity',
            'W5.prepare_input','PRESERVE_ORIGINAL_PRECISION',held['quantity'])
        for name in ('asset_type','asset_grade'):
            add('stock_request.asset_context.asset.'+name,'V82 Canonical Asset Grade §2.1.1 + issuer structure',
                'W8.classification','FORMAL_MAPPING_WITH_ISSUER_EVIDENCE',report['classification'][name],
                'DERIVED',self.class_source['source_reference'],self.class_source['sha256'])
        for domain,trial in report.get('cash_by_domain',{}).items():
            for name in ('total','available','unsettled','reserved'):
                assumption=next((a for a in trial['assumptions'] if a['field_path']=='cash_state.'+name),None)
                add('c7_funding_context.'+domain+'.brokerage_cash_state.'+name,
                    trial['formal_sources'].get(name,assumption),'W8.cash_trial',
                    'AUTHORIZED_MISSING_CASH_ZERO' if assumption else 'PRESERVE_SOURCE_CASH',
                    trial['decimal_values'][name], 'AUTHORIZED_ASSUMPTION' if assumption else 'SOURCE_BACKED')
        for issue in report['issues']:
            add(issue['field_path'],None,'W5 snapshot / original C7 schema',
                'NO_VALUE_INVENTED',None,'UNAVAILABLE')
        for section,state in report['source_inventory'].items():
            if section in ('bond_request','stock_evidence','producer_contract','stock_source_fields',
                           'bond_evidence','asset_framework','physical_sgov'):
                add('native_sources.native_bundle.'+section,None,'W8.AssetSourceProducer',state,None,'UNAVAILABLE')
        return records

    def funding_contexts(self, snapshot, selected_owner, selected_trial, run, ref):
        """Map all three required domains, retaining missing identity as null.

        The extra slots are schema domains, not fabricated broker accounts.
        Missing cash uses the explicit trial policy; missing broker/account never
        becomes a made-up identifier. Original validation remains authoritative.
        """
        contexts=[];cash_sources={}
        accounts=snapshot['tables']['portfolio_account']
        for domain in ('TW_LOCAL_BROKER','TW_SUB_BROKERAGE','US_BROKER'):
            if domain==selected_owner['funding_domain']:
                owner=selected_owner;trial=selected_trial
            else:
                candidates=[]
                if domain=='TW_LOCAL_BROKER':
                    candidates=[r for r in accounts if r['account_key']!=selected_owner['account']
                        and ('Taiwan broker' in r.get('account_label','') or 'Cathay Securities' in r.get('account_label',''))]
                if len(candidates)>1:raise ValueError('FUNDING_DOMAIN_ACCOUNT_AMBIGUOUS')
                account=candidates[0]['account_key'] if candidates else None
                links=[r for r in snapshot['tables'].get('account_broker_link',[]) if r.get('account_key')==account]
                # The already-recorded broker *category label* is retained for
                # analysis when an external broker identifier was not supplied.
                # It is not represented as a newly discovered brokerage name.
                broker=(links[0]['broker_key'] if len(links)==1 else
                    candidates[0].get('account_label') if candidates else None)
                owner={'funding_domain':domain,'broker':broker,'account':account}
                # No nonzero currency conversion is introduced for another
                # account. Its currently missing cash is zero in this trial.
                family_owner={'client_id':snapshot['client_id'],'account':account,'broker':broker,
                    'currency':'TWD' if domain=='TW_LOCAL_BROKER' else selected_trial['currency']}
                trial=cash_trial(snapshot,family_owner,self.policy,db_path=self.db_path,run_id=run)
                if trial['issues']:
                    raise ValueError(trial['issues'][0]['code']+':'+trial['issues'][0]['field_path'])
                if family_owner['currency']!=selected_trial['currency'] and any(
                        Decimal(v)!=0 for v in trial['decimal_values'].values()):
                    raise ValueError('NONZERO_OTHER_ACCOUNT_CASH_FX_SOURCE_REQUIRED')
            available=Decimal(trial['decimal_values']['available'])
            amount=0.0 if available==0 else None
            contexts.append({'domain':domain,'broker':owner['broker'],'account':owner['account'],
                'bucket_new_investment_amount':None,'brokerage_cash_state':trial['cash_state'],
                'executable_budget':{leg:{'amount':amount,'cash_basis':'AVAILABLE','source_domain':domain,
                    'source_broker':owner['broker'],'source_account':owner['account']} for leg in ('equity','bond')},
                'source_reference_ids':[ref]})
            cash_sources[domain]=trial
        return contexts,cash_sources

    def core_observation(self, observed, *, valuation_metrics=None, broad_etf=True):
        path=self.root/'系統工程/股票V80/正式Runtime/v82_runtime_greenfield/src'
        if str(path) not in sys.path:sys.path.insert(0,str(path))
        from livingwater_v82_runtime.core_rules import evaluate_core_rule_state,EvidenceFact
        from livingwater_v82_runtime.enums import PredicateTruth,RequirementLevel,DataQuality,Freshness,PitStatus
        groups={k:[PredicateTruth(r['truth']) for r in values]
                for k,values in observed['observed_named_signals'].items()}
        result=evaluate_core_rule_state(valuation_metrics=valuation_metrics or [],
            valuation_waterfall=['FORWARD_PE','TRAILING_PE','CAPE','PB','FCF_YIELD'],
            fundamental_fields=[],safety_facts=[EvidenceFact(name='formal_source_coverage',value='UNKNOWN',
                requirement=RequirementLevel.SAFETY_REQUIRED,data_quality=DataQuality.UNKNOWN,
                freshness=Freshness.UNKNOWN,pit_status=PitStatus.UNVERIFIABLE,source_reference=observed['source_path'])],
            **groups,hard_gate_predicates=[PredicateTruth.UNKNOWN],
            theses=[] if broad_etf else [{'state':'UNKNOWN'}],
            structural_confirmation=PredicateTruth.UNKNOWN,ma20_ok=PredicateTruth.UNKNOWN)
        return {'function':'V82.evaluate_core_rule_state','result':json.loads(json.dumps(asdict(result),
                default=lambda x:str(x) if isinstance(x,Decimal) else x.value)),
            'scope':'ORIGINAL_CORE_OBSERVATION__NOT_DEPLOYMENT_OR_MENTOR','source_sha256':observed['source_sha256'],
            'company_thesis_scope':'INAPPLICABLE_TO_BROAD_ETF_PER_FORMAL_RULE_APPLICABILITY_MATRIX' if broad_etf else 'UNKNOWN',
            'etf_structure_safety':'UNKNOWN__RETAINED_IN_SAFETY_SUFFICIENCY'}

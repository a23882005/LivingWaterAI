"""Assemble schema83 from original approvals, V70 and reconciled business facts.

The source is never a Work6/C7/native result. Partial business facts remain
available by field; only a complete source envelope can enter the C engines.
No cash, empty order book, protection clearance or cap exemption is inferred.
"""
from copy import deepcopy
from decimal import Decimal,localcontext
from hashlib import sha256
from pathlib import Path
import json
from family_input import digest
from member_market_source import time

PROFILE='FAMILY_LONG_TERM_TARGET_WITH_V70_CEILING_V1'
APPROVAL_SHA='112b4ffad8d900971879f5502702bbf1252214edd709d22398a604ec070ed2e0'
DIRECT='EXISTING_BOUND_SOURCE'
ADAPTER='EXISTING_SOURCE_NEEDS_QUALIFICATION'
MISSING='ORIGINAL_FACT_NOT_PROVIDED'


def asset_kind(identity):
    route=identity.get('engine_route','');typ=identity.get('asset_type')
    if route=='V75_PREDICATES' or typ in ('BOND_ETF','BOND','bond ETF'):return 'bond ETF'
    if typ in ('STOCK','INDIVIDUAL_STOCK'):return 'equity individual stock'
    if route.startswith('V82_') or isinstance(typ,str) and 'ETF' in typ:return 'equity ETF'
    if typ in ('CASH','cash'):return 'cash'
    return None


def number(value):
    if value is None or isinstance(value,bool):raise ValueError('C7_ASSEMBLY_EXACT_AMOUNT_REQUIRED')
    n=Decimal(str(value))
    if not n.is_finite() or n<0:raise ValueError('C7_ASSEMBLY_NONNEGATIVE_AMOUNT_REQUIRED')
    return n


def metric(value,at,refs):
    return {'value_state':'KNOWN' if value is not None else 'UNKNOWN','value':float(value) if value is not None else None,
        'unit':'portfolio_weight','as_of':at,'data_quality':'OK' if value is not None else 'UNKNOWN',
        'freshness':'UNKNOWN','issue_codes':[],'source_reference_ids':list(refs),'source_native_status':None}


def money(value,currency,at,refs):
    return {'value_state':'KNOWN' if value is not None else 'UNKNOWN','amount':float(value) if value is not None else None,
        'currency':currency,'as_of':at,'data_quality':'OK' if value is not None else 'UNKNOWN',
        'freshness':'UNKNOWN','issue_codes':[],'source_reference_ids':list(refs)}


def read_facts(source,request):
    if source is None:return None
    raw=Path(source['local_path']).read_bytes()
    if sha256(raw).hexdigest()!=source['sha256']:raise PermissionError('C7_ASSEMBLY_ORIGINAL_FACT_BYTES_CHANGED')
    data=json.loads(raw)
    if (data.get('schema_version')!='Family.W8.PortfolioReconciliationFacts.v1'
        or data.get('client_id')!=request['client_id']
        or data.get('source_db_sha256')!=request['client_snapshot']['payload']['source_sha256']
        or str(data.get('target_version'))!=str(request['confirmed_target']['target_version'])
        or data.get('data_provenance')!='SOURCE_BACKED' or not data.get('source_reference')
        or any(k in data for k in ('family_scope','canonical_input','work6_result','asset_framework','native_result'))):
        raise PermissionError('C7_ASSEMBLY_ORIGINAL_FACT_IDENTITY_OR_KIND_MISMATCH')
    if not time(data['as_of'])<=time(data['available_at'])<=time(request['evaluation_at']):
        raise PermissionError('C7_ASSEMBLY_ORIGINAL_FACT_FUTURE_SOURCE')
    # Reconciliation covers one explicitly named portfolio, never another
    # member's account or an unenumerated implicit zero account.
    accounts=data.get('accounts')
    if not isinstance(accounts,list):raise ValueError('C7_ASSEMBLY_ACCOUNT_RECORDS_REQUIRED')
    expected={r['account_key'] for r in request['client_snapshot']['payload']['tables'].get('portfolio_account',[])}
    actual=[r['owner']['account'] for r in accounts]
    if (len(actual)!=len(set(actual)) or set(actual)!=expected
        or any(r['owner']['client_id']!=request['client_id'] for r in accounts)):
        raise PermissionError('C7_ASSEMBLY_PORTFOLIO_ACCOUNT_COVERAGE_MISMATCH')
    for row in accounts:
        if any(not isinstance(row['owner'].get(k),str) or not row['owner'][k] for k in
            ('client_id','account','broker','funding_domain','currency')):
            raise PermissionError('C7_ASSEMBLY_ACCOUNT_OWNER_BINDING_REQUIRED')
        if row.get('binding_evidence_state')!='VERIFIED' or not row.get('binding_source_reference'):
            raise PermissionError('C7_ASSEMBLY_ACCOUNT_OWNER_PROOF_REQUIRED')
    return data


class SourceAssembler:
    def __init__(self,root,request,context,artifact_directory):
        self.root=Path(root).resolve();self.request=request;self.context=context
        self.at=request['evaluation_at'];self.owner=request.get('owner') or {}
        self.currency=self.owner.get('currency');self.inventory={};self.references=[];self.raw=[];self.issues=[]
        self.folder=Path(artifact_directory).resolve()
        if self.folder.is_relative_to(self.root):raise PermissionError('C7_ASSEMBLY_PRIVATE_ARTIFACT_OUTSIDE_REPO_REQUIRED')
        self.folder.mkdir(parents=True,exist_ok=True)
        self.prefix=digest({'client':request['client_id'],'run':request['run_id'],'owner':self.owner})[:24]

    def field(self,path,value,*,state=None,code=None,sources=(),producer='ORIGINAL_FAMILY_SOURCE',responsibility=None,blocking=True):
        state=state or (DIRECT if value is not None else MISSING)
        locators=deepcopy(list(sources))
        if not locators:locators=[{'location':'same_run_request.'+path,'source_db_sha256':self.request['client_snapshot']['payload']['source_sha256'],
            'binding_sha256':digest(value),'as_of':self.at,'available_at':self.at}]
        for locator in locators:
            ref=next((r for r in self.references if r['source_id']==locator.get('source_id')),None)
            if ref:locator.update(as_of=ref['as_of'],available_at=ref['retrieved_at'])
            locator.setdefault('source_db_sha256',self.request['client_snapshot']['payload']['source_sha256'])
            locator.setdefault('as_of',None);locator.setdefault('available_at',None)
            locator['observation_time_state']='KNOWN' if locator['as_of'] else 'NOT_PROVIDED'
            locator['binding_checked_at']=self.at
        self.inventory[path]={'field_path':'family_scope.'+path,'classification':state,
            'value_state':'KNOWN' if value is not None else 'UNKNOWN','source_locators':locators,
            'producer':producer,'consumer':'schema83 -> C.Work6 -> C.Work7',
            'next_responsibility':responsibility or ('CODEX_SOURCE_ADAPTER' if state==ADAPTER else
                'OWNER_OR_ORIGINAL_SOURCE_VIA_PM' if state==MISSING else 'ORIGINAL_C_CONTRACT_VALIDATION'),
            'reason_code':code}
        if state!=DIRECT:
            self.issues.append({'code':code or 'C7_ASSEMBLY_'+path.upper().replace('.','_')+'_REQUIRED',
                'field_path':'family_scope.'+path,'kind':state,'source_locators':locators,
                'next_responsibility':self.inventory[path]['next_responsibility'],'blocking':blocking})
        return value

    def derived(self,key,payload,as_of=None,available_at=None,*,kind='SYSTEM_DERIVED',original=None):
        at=as_of or self.at;available=available_at or self.at
        if not time(at)<=time(available)<=time(self.at):raise PermissionError('C7_ASSEMBLY_DERIVED_SOURCE_FUTURE')
        path=self.folder/(self.prefix+'.'+key+'.json')
        path.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
        return self.reference(key,{'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()},at,available,kind=kind,original=original)

    def reference(self,key,descriptor,at,available,*,kind='SYSTEM_DERIVED',original=None):
        sid='SRC_FAMILY_ASSEMBLY_'+key.upper()
        self.raw.append({'source_id':sid,**deepcopy(descriptor)})
        self.references.append({'source_id':sid,'source_kind':kind,'owner':'C_INTEGRATION',
            'source_reference':(original or {}).get('source_reference') or 'ORIGINAL-SOURCE:'+descriptor['sha256'],
            'source_fingerprint':descriptor['sha256'],'source_fingerprint_algorithm':'SHA256','source_version':'1.0',
            'as_of':at,'retrieved_at':available,'data_quality':'OK','freshness':'UNKNOWN','issue_codes':[],
            'source_native_status':None,'notes':None})
        return {'source_reference_id':sid,'source_sha256':descriptor['sha256'],
            'as_of':at,'available_at':available,'qualification':'VERIFIED_AT_CUTOFF'}

    def approved(self,identities):
        req=self.request;target=req['confirmed_target'];draft=target['payload']['draft']
        evidence=target['payload'].get('confirmation_evidence',{});projection=self.context.get('native_target_source')
        if projection is None and self.currency:
            from native_target_source import produce
            projection=produce(req,self.context.get('family_c7_reporting_fx'))
        if projection is None:
            return self.field('approved_long_term_target',None,state=ADAPTER,code='C7_APPROVED_TARGET_OWNER_FX_PROJECTION_REQUIRED',
                sources=[{'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],'target_version':target['target_version']}])
        from native_target_source import produce
        if projection!=produce(req,projection.get('fx_observation')):
            raise PermissionError('C7_ASSEMBLY_APPROVED_NATIVE_TARGET_REPLAY_MISMATCH')
        self.approved_projection=deepcopy(projection)
        base=projection['denominator']
        if base.get('value_state')!='KNOWN':
            return self.field('approved_long_term_target',None,code='C7_CURRENT_APPROVED_INVESTMENT_POOL_REQUIRED',
                sources=[{'target_version':target['target_version'],'original_denominator':deepcopy(draft.get('denominator'))}])
        if evidence.get('action')!='READ_EXISTING_APPROVAL' or not evidence.get('confirmed_at') or not evidence.get('confirmed_by'):
            return self.field('approved_long_term_target',None,state=ADAPTER,code='C7_READ_EXISTING_APPROVAL_CONFIRMATION_PROOF_REQUIRED')
        proof=self.derived('approval',{'confirmed_target':target,'native_target_source':projection,
            'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
            'original_product_classification_sources':deepcopy(identities)},
            as_of=evidence['confirmed_at'],kind='CLIENT_PROJECT')
        sid=proof['source_reference_id'];positions=[]
        for row in draft['target_lines']:
            iid=projection['source_to_native'][row['instrument_id']];item=projection['targets'][iid]
            p=identities.get(row.get('ticker'),{})
            kind=asset_kind(p) or ('cash' if row.get('asset_type') in ('CASH','cash') else None)
            if kind is None:
                self.field('approved_long_term_target.positions.'+iid+'.asset_type',None,state=ADAPTER,
                    code='C7_ORIGINAL_ASSET_BUCKET_CLASSIFICATION_REQUIRED',sources=[{'original_target_row':deepcopy(row)}])
                kind='UNKNOWN'
            m=item['target_amount']
            if m.get('value_state')!='KNOWN':
                self.field('approved_long_term_target.positions.'+iid+'.portfolio_amount',None,code='C7_APPROVED_TARGET_MONEY_OR_FX_REQUIRED')
            positions.append({'instrument_id':iid,'ticker':row.get('ticker'),'display_name':None,'asset_type':kind,
                'market':None,'base_currency':p.get('quote_currency'),'value_state':'KNOWN',
                'weight':metric(number(row['weight']['value']),self.at,[sid]),
                'portfolio_amount':money(number(m['amount']) if m.get('value_state')=='KNOWN' else None,self.currency,self.at,[sid]),
                'source_reference_ids':[sid]})
        approved={'allocation_id':draft['allocation_id'],'stage':'FINAL_TARGET','as_of':evidence['confirmed_at'],
            'denominator':money(number(base['amount']),self.currency,self.at,[sid]),'positions':positions,
            'declared_total_weight':metric(sum((number(r['weight']['value']) for r in positions),Decimal(0)),self.at,[sid]),
            'confirmation_status':'CONFIRMED','confirmed_at':evidence['confirmed_at'],
            'confirmed_by':evidence['confirmed_by'],'source_reference_ids':[sid]}
        self.field('approval_receipt',proof,sources=[self.raw[-1]],producer='ORIGINAL_W1_OR_DOCUMENT_APPROVAL_AND_NATIVE_TARGET_SOURCE')
        return self.field('approved_long_term_target',approved,sources=[self.raw[-1]],producer='ORIGINAL_W1_OR_DOCUMENT_APPROVAL_AND_NATIVE_TARGET_SOURCE')

    def tactical(self,tactical,scope):
        req=self.request
        if tactical is None or not tactical.get('native_currency_amounts'):
            return self.field('total_stock_ceiling',None,state=ADAPTER,code='C7_ORIGINAL_V70_TOTAL_AMOUNT_OR_ACCOUNTING_BASE_REQUIRED')
        base=tactical['allocation_base'];original=req['confirmed_target']['payload']['draft']['denominator']
        if base!=original or tactical.get('native_execution_currency')!=self.currency:
            raise PermissionError('C7_ASSEMBLY_V70_APPROVED_BASE_OR_CURRENCY_CHANGED')
        macro=req['macro_snapshot']
        if tactical.get('source_feed_sha256')!=macro['source_sha256'] or tactical.get('feed_as_of')!=macro['asOf']:
            raise PermissionError('C7_ASSEMBLY_V70_MACRO_SOURCE_MISMATCH')
        original_html=self.root/'系統工程/總經V70/V70-3-27.html'
        if tactical.get('source_html_sha256')!=sha256(original_html.read_bytes()).hexdigest():
            raise PermissionError('C7_ASSEMBLY_V70_ORIGINAL_PRODUCER_BYTES_CHANGED')
        proof=self.derived('v70',{'original_tactical':tactical,'macro_snapshot':macro,
            'source_target_digest':digest(req['confirmed_target'])},as_of=macro['asOf'])
        amount=tactical['native_currency_amounts']['stock']
        approved=scope['approved_long_term_target']
        if approved is None:return self.field('total_stock_ceiling',None,state=ADAPTER,code='C7_V70_NORMALIZED_APPROVED_BASE_UNAVAILABLE')
        value={'amount':str(number(amount)),'currency':self.currency,'cap_scope':'TOTAL_PORTFOLIO_STOCK',
            'accounting_base':{'base_id':'ORIGINAL_APPROVED_BASE:'+digest(original),
                'amount':str(number(self.approved_projection['denominator']['amount'])),'currency':self.currency,
                'source_reference_id':proof['source_reference_id']},'receipt':proof}
        return self.field('total_stock_ceiling',value,sources=[self.raw[-1]],producer='ORIGINAL_V70_TACTICAL_INPUT_CALCULATE')

    def portfolio(self,facts,descriptor,scope):
        snapshot=self.request['client_snapshot']['payload'];tables=snapshot['tables']
        if facts is None:
            from w1_portfolio_observations import normalize
            review=normalize(self.request)
            counts={k:len(tables.get(k,[])) for k in ('portfolio_account','account_broker_link','account_ownership',
                'funding_account_domain_link','cash_balance_snapshot','holding_policy_proposal','holding_policy_confirmation')}
            locator={'source_db_sha256':snapshot['source_sha256'],'table_row_counts':counts}
            for path,code in [('account_owners','C7_FULL_PORTFOLIO_ACCOUNT_OWNER_BINDINGS_REQUIRED'),
                ('current_nav','C7_COMPLETE_CURRENT_NAV_RECONCILIATION_REQUIRED'),
                ('exposure_coverage','C7_COMPLETE_POSITION_ORDER_COMMITMENT_COVERAGE_REQUIRED'),
                ('exposures','C7_SOURCE_BOUND_EXPOSURE_BOOK_REQUIRED'),
                ('protection_coverage','C7_COMPLETE_PROTECTION_COVERAGE_REQUIRED'),
                ('preference_locks','C7_CONFIRMED_HOLDING_DIRECTIVES_REQUIRED'),
                ('portfolio_caps','C7_CLIENT_GLOBAL_CAP_APPLICABILITY_REQUIRED'),
                ('funding_buckets','C7_SETTLED_AVAILABLE_RESERVED_AND_AUTHORIZATION_REQUIRED')]:
                scope[path]=self.field(path,None,state=ADAPTER if path in ('account_owners','current_nav','exposures') else MISSING,
                    code=code,sources=[locator])
            # Exact original observations are retained, never promoted to net
            # available cash or to a complete book by table absence.
            self.observations={'cash_balance_snapshot':deepcopy(tables.get('cash_balance_snapshot',[])),
                'portfolio_positions':deepcopy(tables.get('portfolio_position',[])),
                'holding_policies':deepcopy(tables.get('holding_policy_proposal',[])),
                'account_bindings':deepcopy(tables.get('account_broker_link',[])),
                'w1_portfolio_review':review}
            self.inventory['account_owners']['qualification_review']={
                'producer':'W8.w1_portfolio_observations.normalize -> W5.family_boundary.bind_owner',
                'qualified_account_count':review['qualified_account_count'],
                'accounts':[{'account_key':r['account_key'],'missing_original_fields':r['missing_binding_fields']}
                    for r in review['accounts']]}
            return None
        proof=self.reference('reconciliation',descriptor,facts['as_of'],facts['available_at'],original=facts)
        sid=proof['source_reference_id'];accounts=facts['accounts'];owners=[deepcopy(r['owner']) for r in accounts]
        scope['account_owners']=self.field('account_owners',owners,sources=[self.raw[-1]])
        if self.owner not in owners:raise PermissionError('C7_ASSEMBLY_SELECTED_ACCOUNT_NOT_IN_VERIFIED_PORTFOLIO')
        coverage=facts.get('coverage') or {}
        complete=all(coverage.get(k) is True for k in ('positions_complete','orders_complete','other_commitments_complete','fills_reconciled'))
        complete=complete and all(isinstance(facts.get(k),list) for k in ('orders','fills','other_commitments','confirmed_releases'))
        scope['exposure_coverage']=self.field('exposure_coverage',dict(proof,complete=True,
            empty_portfolio_asserted=coverage.get('empty_portfolio_asserted') is True,
            confirmed_effects_already_applied=deepcopy(coverage.get('confirmed_effects_already_applied',[]))) if complete else None,
            code='C7_COMPLETE_POSITION_ORDER_COMMITMENT_COVERAGE_REQUIRED',sources=[self.raw[-1]])
        protection=facts.get('protection_confirmation') or {}
        protected=(coverage.get('protection_complete') is True and isinstance(facts.get('holding_directives'),list)
            and protection.get('evidence_state')=='VERIFIED' and bool(protection.get('source_reference'))
            and bool(protection.get('confirmed_by')) and bool(protection.get('confirmed_at')))
        if protected and time(protection['confirmed_at'])>time(facts['available_at']):
            raise PermissionError('C7_ASSEMBLY_PROTECTION_CONFIRMATION_FUTURE_SOURCE')
        scope['protection_coverage']=self.field('protection_coverage',dict(proof,complete=True,
            empty_portfolio_asserted=coverage.get('empty_portfolio_asserted') is True,
            confirmed_effects_already_applied=[]) if protected else None,
            code='C7_COMPLETE_PROTECTION_COVERAGE_REQUIRED',sources=[self.raw[-1]])
        if not isinstance(facts.get('portfolio_caps'),list) or not facts['portfolio_caps'] or scope['total_stock_ceiling'] is None:caps=None
        else:
            caps=[]
            for c in facts['portfolio_caps']:
                if not c.get('source_reference') or c.get('evidence_state')!='VERIFIED':raise ValueError('C7_ASSEMBLY_CAP_SOURCE_REQUIRED')
                if c['applicability']=='NOT_APPLICABLE':
                    if not c.get('applicability_reason'):raise ValueError('C7_ASSEMBLY_CAP_EXEMPTION_SOURCE_REQUIRED')
                    caps.append({'cap_id':c['cap_id'],'applicability':'NOT_APPLICABLE','value_state':'NONE'});continue
                if c['value_state']=='KNOWN' and (c.get('currency')!=self.currency
                    or c.get('accounting_base_id')!=scope['total_stock_ceiling']['accounting_base']['base_id']):
                    raise ValueError('C7_ASSEMBLY_CAP_ACCOUNTING_BASE_REQUIRED')
                caps.append({'cap_id':c['cap_id'],'applicability':'REQUIRED','value_state':c['value_state'],
                    'amount':str(number(c['amount'])) if c.get('amount') is not None else None,'currency':self.currency,
                    'accounting_base':deepcopy(scope['total_stock_ceiling']['accounting_base']),'receipt':deepcopy(proof)})
        if coverage.get('cap_applicability_complete') is not True:caps=None
        scope['portfolio_caps']=self.field('portfolio_caps',caps,code='C7_CLIENT_GLOBAL_CAP_APPLICABILITY_REQUIRED',sources=[self.raw[-1]])
        fx=facts.get('reporting_fx',[]);scope['budget_normalizations']=[]
        def rate(owner):
            if owner['currency']==self.currency:return Decimal(1)
            matches=[r for r in fx if r['owner']==owner and r['from_currency']==owner['currency'] and r['to_currency']==self.currency]
            if len(matches)!=1:raise ValueError('C7_ASSEMBLY_EXPLICIT_REPORTING_FX_REQUIRED')
            value=number(matches[0]['quote_per_base'])
            if value<=0:raise ValueError('C7_ASSEMBLY_POSITIVE_REPORTING_FX_REQUIRED')
            record={'owner':deepcopy(owner),'from_currency':owner['currency'],'to_currency':self.currency,'quote_per_base':str(value),
                'accounting_base_id':scope['total_stock_ceiling']['accounting_base']['base_id'],
                'purpose':'REPORTING_BUDGET_NORMALIZATION_NOT_EXECUTION','receipt':deepcopy(proof)}
            if record not in scope['budget_normalizations']:scope['budget_normalizations'].append(record)
            return value
        positions=[];exposures=[];funding=[];nav=Decimal(0);cash_known=True
        aggregate={};nav_refs={};position_effects={};cash_reserved={};broker_orders={}
        with localcontext() as numeric:
            numeric.prec=50
            for account in accounts:
                owner=account['owner'];factor=rate(owner);subtotal=Decimal(0)
                if not isinstance(account.get('positions'),list):raise ValueError('C7_ASSEMBLY_ACCOUNT_POSITIONS_REQUIRED')
                for p in account['positions']:
                    iid=p['asset_id']
                    if p['position_id'] in position_effects:raise ValueError('C7_ASSEMBLY_POSITION_IDENTITY_CONFLICT')
                    quantity=number(p['quantity']);price=number(p['price']);value=quantity*price
                    if (p.get('price_basis')!='REPORTED_MARKET_PRICE' or not p.get('price_source_reference')
                        or time(p['price_as_of'])>time(facts['as_of'])):
                        raise ValueError('C7_ASSEMBLY_CURRENT_MARKET_PRICE_SOURCE_REQUIRED')
                    if p['currency']!=owner['currency']:raise ValueError('C7_ASSEMBLY_POSITION_QUOTE_FX_REQUIRED')
                    subtotal+=value;kind=p['asset_class']
                    if kind not in ('STOCK','BOND','CASH'):raise ValueError('C7_ASSEMBLY_POSITION_ASSET_CLASS_REQUIRED')
                    known_kind=self.asset_kinds.get(iid) or asset_kind(self.identities.get(p.get('ticker',iid),{}))
                    known_bucket=('STOCK' if known_kind and known_kind.startswith('equity') else
                        'BOND' if known_kind=='bond ETF' else 'CASH' if known_kind=='cash' else None)
                    if known_bucket is not None and known_bucket!=kind:raise ValueError('C7_ASSEMBLY_POSITION_ASSET_CLASS_CONFLICT')
                    canonical_kind='cash' if kind=='CASH' else known_kind
                    if canonical_kind is None:
                        self.field('current_positions.'+iid+'.asset_type',None,state=ADAPTER,code='C7_CURRENT_PRODUCT_BUCKET_SOURCE_REQUIRED')
                    canonical={'instrument_id':iid,'ticker':p.get('ticker',iid),'display_name':None,
                        'asset_type':canonical_kind or 'UNKNOWN',
                        'market':None,'base_currency':owner['currency'],'value_state':'KNOWN','weight':None,
                        'portfolio_amount':None,'source_reference_ids':[sid]}
                    if iid in aggregate:
                        if aggregate[iid]['canonical']!=canonical:
                            raise ValueError('C7_ASSEMBLY_CROSS_ACCOUNT_ASSET_UNIT_MAPPING_REQUIRED')
                        aggregate[iid]['amount']+=value*factor
                    else:aggregate[iid]={'canonical':canonical,'amount':value*factor}
                    if kind=='STOCK':exposures.append({'event_id':p['position_id'],'economic_effect_ids':deepcopy(p['economic_effect_ids']),
                        'kind':'CONFIRMED_POSITION','owner':deepcopy(owner),'asset_id':iid,'amount':str(value),'currency':owner['currency'],
                        'intent_id':None,'side':None,'amount_basis':'CONFIRMED_NOTIONAL','receipt':deepcopy(proof)})
                    position_effects[p['position_id']]={'owner':owner,'asset_id':iid,'quantity':quantity,'effects':set(p['economic_effect_ids'])}
                cash=account.get('cash') or {};authorization=account.get('authorized_incremental_amount')
                auth=(account.get('authorization_evidence_state')=='VERIFIED'
                    and bool(account.get('authorization_source_reference')) and bool(account.get('authorization_confirmed_at')))
                if auth and time(account['authorization_confirmed_at'])>time(facts['available_at']):
                    raise PermissionError('C7_ASSEMBLY_FUNDING_AUTHORIZATION_FUTURE_SOURCE')
                if not auth or authorization is None:
                    authorization=None
                    self.field('funding_buckets.'+owner['account']+'.authorization',None,
                        code='C7_ACCOUNT_FUNDING_AUTHORIZATION_SOURCE_REQUIRED',sources=[self.raw[-1]])
                total_cash=number(cash['total_cash']) if cash.get('total_cash') is not None and cash.get('source_reference') else None
                if total_cash is None:cash_known=False
                else:
                    native_nav=subtotal+total_cash
                    if account.get('net_asset_value') is None or native_nav!=number(account['net_asset_value']):
                        raise ValueError('C7_ASSEMBLY_ACCOUNT_NAV_RECONCILIATION_REQUIRED')
                    nav+=native_nav*factor;nav_refs[owner['account']]=str(native_nav)
                    positions.append({'instrument_id':'ACCOUNT_CASH:'+owner['account'],'ticker':None,'display_name':None,'asset_type':'cash',
                        'market':None,'base_currency':owner['currency'],'value_state':'KNOWN','weight':None,
                        'portfolio_amount':money(total_cash*factor,self.currency,facts['as_of'],[sid]),'source_reference_ids':[sid]})
                required=('total_cash','settled_cash','unsettled_cash','reserved_cash','available_cash')
                settled=cash.get('settlement_evidence_state')=='VERIFIED' and all(cash.get(k) is not None for k in required)
                values={k:number(cash[k]) for k in required} if settled else None
                if settled and (not cash.get('source_reference') or values['total_cash']-values['unsettled_cash']!=values['settled_cash']
                    or values['settled_cash']-values['reserved_cash']!=values['available_cash']):
                    raise ValueError('C7_ASSEMBLY_CASH_RECONCILIATION_REQUIRED')
                basis=account.get('cash_basis')
                if basis not in ('NET_AVAILABLE','GROSS_SETTLED_CASH'):raise ValueError('C7_ASSEMBLY_CASH_BASIS_REQUIRED')
                if settled:cash_reserved[owner['account']]=values['reserved_cash']
                else:self.field('funding_buckets.'+owner['account']+'.settled_cash',None,
                    code='C7_ACCOUNT_SETTLEMENT_AVAILABLE_RESERVED_SOURCE_REQUIRED',sources=[self.raw[-1]],
                    blocking=authorization is None or number(authorization)!=0)
                funding.append({'bucket_id':account['bucket_id'],'owner':deepcopy(owner),'currency':owner['currency'],
                    'value_state':'KNOWN' if settled else 'UNKNOWN','settled':True if settled else None,
                    'cash_amount':str(values['available_cash'] if basis=='NET_AVAILABLE' else values['settled_cash']) if settled else None,
                    'reserved_amount':str(values['reserved_cash']) if settled else None,'cash_basis':basis,
                    'authorized_incremental_amount':str(number(authorization)) if authorization is not None else None,'receipt':deepcopy(proof)})
            filled_by_position={};seen_fills={}
            for fill in facts.get('fills',[]):
                fill_id=fill.get('fill_id')
                if not fill_id:raise ValueError('C7_ASSEMBLY_FILL_IDENTITY_REQUIRED')
                if fill_id in seen_fills:
                    if seen_fills[fill_id]!=fill:raise ValueError('C7_ASSEMBLY_FILL_IDENTITY_CONFLICT')
                    continue
                seen_fills[fill_id]=deepcopy(fill)
                target=position_effects.get(fill.get('applied_to_position_id'))
                if (target is None or target['owner']['account']!=fill['account'] or target['asset_id']!=fill['asset_id']
                    or fill.get('economic_effect_id') not in target['effects']):
                    raise ValueError('C7_ASSEMBLY_FILL_POSITION_RECONCILIATION_REQUIRED')
                key=fill['applied_to_position_id'];filled_by_position[key]=filled_by_position.get(key,Decimal(0))+number(fill['quantity'])
                if filled_by_position[key]>target['quantity']:raise ValueError('C7_ASSEMBLY_FILLS_EXCEED_CURRENT_POSITION')
            for order in facts.get('orders',[]):
                owner=next((o for o in owners if o['account']==order['account']),None)
                if owner is None:raise PermissionError('C7_ASSEMBLY_ORDER_OWNER_MISMATCH')
                total=number(order['order_quantity']);filled=number(order['filled_quantity']);remaining=number(order['remaining_quantity'])
                if total-filled!=remaining:raise ValueError('C7_ASSEMBLY_ORDER_QUANTITY_RECONCILIATION_REQUIRED')
                if order['side']=='SELL':continue  # A working sell is never a release.
                if order['side']!='BUY':raise ValueError('C7_ASSEMBLY_ORDER_SIDE_REQUIRED')
                if order['state'] in ('FILLED','CANCELLED','REJECTED','EXPIRED'):
                    if remaining!=0:raise ValueError('C7_ASSEMBLY_TERMINAL_ORDER_REMAINING_CONFLICT')
                    continue
                if order['state'] not in ('PLANNED','SUBMITTED','OPEN','PARTIAL_FILL','CANCEL_PENDING','REPLACE_PENDING'):
                    raise ValueError('C7_ASSEMBLY_ORDER_LIFECYCLE_REQUIRED')
                price=number(order['commitment_price'])
                if order['state'] in ('CANCEL_PENDING','REPLACE_PENDING'):
                    acknowledged=order.get('last_acknowledged_commitment') or {}
                    if (not acknowledged.get('source_reference') or not acknowledged.get('as_of')
                        or time(acknowledged['as_of'])>time(facts['available_at'])
                        or number(acknowledged.get('order_quantity'))!=total
                        or number(acknowledged.get('commitment_price'))!=price):
                        raise ValueError('C7_ASSEMBLY_PENDING_COMMITMENT_REDUCTION_UNCONFIRMED')
                if remaining>0 and (price<=0 or order.get('price_basis') not in ('ORIGINAL_LIMIT_PRICE','BROKER_COMMITMENT_PRICE')):
                    raise ValueError('C7_ASSEMBLY_BUY_COMMITMENT_NOTIONAL_SOURCE_REQUIRED')
                if order['state']!='PLANNED':broker_orders[owner['account']]=broker_orders.get(owner['account'],Decimal(0))+remaining*price
                exposures.append({'event_id':order['event_id'],'economic_effect_ids':deepcopy(order['remaining_economic_effect_ids']),
                    'kind':'ACTIVE_BUY_RESERVATION','owner':deepcopy(owner),'asset_id':order['asset_id'],
                    'amount':str(remaining*price),'currency':owner['currency'],
                    'intent_id':order['intent_id'],'side':'BUY','amount_basis':'REMAINING_UNFILLED_NOTIONAL',
                    'lifecycle_state':order['state'],'receipt':deepcopy(proof)})
            for kind,key in [('OTHER_COMMITMENT','other_commitments'),('RELEASE','confirmed_releases')]:
                for event in facts.get(key,[]):
                    owner=next((o for o in owners if o['account']==event['account']),None)
                    if owner is None:raise PermissionError('C7_ASSEMBLY_COMMITMENT_OWNER_MISMATCH')
                    row={'event_id':event['event_id'],'economic_effect_ids':deepcopy(event['economic_effect_ids']),
                        'kind':kind,'owner':deepcopy(owner),'asset_id':event['asset_id'],'amount':str(number(event['amount'])),
                        'currency':owner['currency'],'intent_id':event.get('intent_id'),'receipt':deepcopy(proof)}
                    if kind=='RELEASE':row.update(release_confirmed=event['confirmation_state']=='CONFIRMED',
                        releases_event_id=event['releases_event_id'],release_state=event['release_state'])
                    exposures.append(row)
            for account,held in broker_orders.items():
                if account in cash_reserved and held>cash_reserved[account]:
                    raise ValueError('C7_ASSEMBLY_WORKING_BUY_CASH_RESERVATION_RECONCILIATION_REQUIRED')
        scope['exposures']=self.field('exposures',exposures if complete else None,
            state=DIRECT if complete else ADAPTER,code='C7_EXPOSURE_BOOK_COVERAGE_NOT_COMPLETE',sources=[self.raw[-1]])
        scope['funding_buckets']=self.field('funding_buckets',funding,sources=[self.raw[-1]])
        for entry in aggregate.values():
            p=entry['canonical'];p['portfolio_amount']=money(entry['amount'],self.currency,facts['as_of'],[sid]);positions.append(p)
        nav_money=money(nav,self.currency,facts['as_of'],[sid]) if cash_known and nav>0 and coverage.get('positions_complete') is True else None
        scope['current_nav']=self.field('current_nav',nav_money,code='C7_COMPLETE_CURRENT_NAV_RECONCILIATION_REQUIRED',sources=[self.raw[-1]])
        current=None
        if nav_money is not None:
            for p in positions:p['weight']=metric(number(p['portfolio_amount']['amount'])/nav,facts['as_of'],[sid])
            current={'allocation_id':'CURRENT-RECONCILED:'+digest(facts),'stage':'CURRENT','as_of':facts['as_of'],
                'denominator':deepcopy(nav_money),'positions':positions,'declared_total_weight':metric(1,facts['as_of'],[sid]),
                'confirmation_status':'NOT_APPLICABLE','confirmed_at':None,'confirmed_by':None,'source_reference_ids':[sid]}
        locks=[]
        if protected and current is not None:
            by={p['instrument_id']:p for p in positions}
            for directive in facts.get('holding_directives',[]):
                p=by.get(directive['asset_id'])
                if p is None or directive.get('evidence_state')!='VERIFIED' or not directive.get('source_reference'):
                    raise ValueError('C7_ASSEMBLY_CONFIRMED_HOLDING_DIRECTIVE_REQUIRED')
                if time(directive['confirmed_at'])>time(self.at):raise ValueError('C7_ASSEMBLY_FUTURE_HOLDING_DIRECTIVE')
                if directive['policy'] not in ('HOLD_AS_IS','UNLOCKED'):raise ValueError('C7_ASSEMBLY_HOLDING_POLICY_REQUIRED')
                locked=directive['policy']=='HOLD_AS_IS'
                locks.append({'instrument_id':p['instrument_id'],'ticker':p['ticker'],'protected_existing_holding':locked,
                    'client_preference_locked':locked,'final_target_locked_to_current':locked,'current_weight':p['weight']['value'],
                    'preference_confirmed_at':directive['confirmed_at'] if locked else None,'preference_source_ids':[sid] if locked else [],
                    'unlock_confirmed_at':None if locked else directive['confirmed_at'],'unlock_source_ids':[] if locked else [sid]})
        scope['preference_locks']=self.field('preference_locks',locks if protected and current is not None else None,
            code='C7_CONFIRMED_HOLDING_DIRECTIVES_REQUIRED',sources=[self.raw[-1]])
        self.observations={'account_nav_reconciliation':nav_refs,'original_coverage':deepcopy(coverage)}
        return current

    def build(self,*,tactical=None,identities=None,portfolio_facts_source=None):
        req=self.request;target=req['confirmed_target'];owner=self.owner;self.identities=deepcopy(identities or {})
        scope={'schema_version':'C.FamilyLongTermV70CeilingInput.v1','profile':PROFILE,'approval_contract_sha256':APPROVAL_SHA,
            'identity':{'client_id':req['client_id'],'run_id':req['run_id'],'request_id':req.get('request_id') or req['run_id']+'-request',
                'portfolio_id':'GLOBAL-PORTFOLIO:'+req['client_id']},
            'family_owner':deepcopy(owner) if all(owner.get(k) for k in ('client_id','broker','account','currency','funding_domain')) else None,
            'budget_currency':self.currency,'source_db_sha256':req['client_snapshot']['payload']['source_sha256'],
            'target_version':target['target_version']}
        for k,v in list(scope.items()):self.field(k,v,code='C7_SELECTED_OWNER_SOURCE_REQUIRED' if k=='family_owner' else None)
        scope['approved_long_term_target']=self.approved(identities or {})
        self.asset_kinds={r['instrument_id']:r['asset_type'] for r in (scope['approved_long_term_target'] or {}).get('positions',[])}
        scope['approved_target_digest']=self.field('approved_target_digest',digest(scope['approved_long_term_target']) if scope['approved_long_term_target'] else None,
            state=DIRECT if scope['approved_long_term_target'] else ADAPTER,code='C7_APPROVED_TARGET_SNAPSHOT_UNAVAILABLE')
        scope['approval_receipt']=next(({'source_reference_id':r['source_id'],'source_sha256':r['source_fingerprint'],
            'as_of':r['as_of'],'available_at':r['retrieved_at'],'qualification':'VERIFIED_AT_CUTOFF'} for r in self.references if r['source_id'].endswith('_APPROVAL')),None)
        scope['total_stock_ceiling']=self.tactical(tactical,scope)
        facts=read_facts(portfolio_facts_source,req)
        current=self.portfolio(facts,portfolio_facts_source,scope)
        for key in ('approval_receipt','account_owners','current_nav','protection_coverage','preference_locks','portfolio_caps','exposure_coverage','exposures','funding_buckets'):
            if key not in self.inventory:self.field(key,scope.get(key),state=ADAPTER,code='C7_ORIGINAL_DEPENDENCY_NOT_QUALIFIED')
        out={'schema_version':'Family.W8.C7SourceAssembly.v1','client_id':req['client_id'],'run_id':req['run_id'],
            'evaluation_at':self.at,'owner':deepcopy(owner),'source_db_sha256':scope['source_db_sha256'],
            'target_version':target['target_version'],'status':'PARTIAL_ORIGINAL_SOURCES',
            'scope_candidate':scope,'current_allocation':current,'field_inventory':list(self.inventory.values()),
            'issues':self.issues,'original_observations':deepcopy(getattr(self,'observations',{})),
            'raw_sources':deepcopy(self.raw),'source_references':deepcopy(self.references),
            'new_confirmation_created':False,'unknown_values_defaulted_to_zero':False,'trade_action':'NO_TRADE'}
        if not any(i['blocking'] for i in self.issues) and all(scope.get(k) is not None for k in ('approved_long_term_target','current_nav','total_stock_ceiling')):
            from jsonschema import Draft202012Validator
            schema=json.loads((self.root/'系統工程/C-配置決策引擎＋Mentor整合/正式Runtime/contracts_c7/83_Family_LongTerm_V70Ceiling_Input.schema.json').read_text())
            errors=list(Draft202012Validator(schema).iter_errors(scope))
            if errors:raise ValueError('C7_ASSEMBLY_SCHEMA83_INVALID:'+str(list(errors[0].path)))
            data={'schema_version':'Family.W8.C7FamilyScopeSource.v1',
                **{k:deepcopy(req[k]) for k in ('client_id','run_id','owner','evaluation_at')},
                'source_db_sha256':scope['source_db_sha256'],'confirmed_target_digest':digest(target),
                'family_scope':scope,'current_allocation':current,'raw_sources':self.raw,'source_references':self.references}
            path=self.folder/(self.prefix+'.scope-source.json')
            path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            out.update(status='SOURCE_ASSEMBLED__ORIGINAL_C7_VALIDATION_PENDING',
                source_descriptor={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()})
        out['digest']=digest(out)
        return out


def assemble(root,request,context,*,artifact_directory,tactical=None,identities=None,portfolio_facts_source=None):
    return SourceAssembler(root,request,context,artifact_directory).build(tactical=tactical,
        identities=identities,portfolio_facts_source=portfolio_facts_source)


def assemble_original_producers(producer,request,context,prepared,trial):
    """Build original sources before expensive product deployment analysis.

    Independent Member stock components have already executed. V70 is called
    here with its real approved base and feed; cash-trial assumptions are kept
    only as observations and cannot populate qualified funding buckets.
    """
    options=producer.family_c7_assembly_inputs
    if not isinstance(options,dict) or options.get('schema_version')!='Family.W8.C7AssemblyInputs.v1':
        raise PermissionError('C7_ASSEMBLY_VERSIONED_ORIGINAL_INPUTS_REQUIRED')
    from native_asset_source import classification
    identities={};tables=request['client_snapshot']['payload']['tables']
    symbols={r.get('ticker') for r in request['confirmed_target']['payload']['draft']['target_lines']}
    symbols.update(r.get('ticker') for r in tables.get('portfolio_instrument',[]))
    from bond_advisory import candidates
    bond_symbols=set(candidates(producer.root))
    for symbol in sorted(s for s in symbols if s):
        identities[symbol]=classification(symbol,producer.class_source,producer.product_sources.get(symbol))
        units={r.get('quote_currency') for r in tables.get('portfolio_instrument',[]) if r.get('ticker')==symbol and r.get('quote_currency')}
        if len(units)==1:identities[symbol]['quote_currency']=next(iter(units))
        if symbol in bond_symbols:
            identities[symbol].update(engine_route='V75_PREDICATES',asset_type='BOND_ETF',
                product_bucket_source='ORIGINAL_V75_WORK3_US_LISTED_ASSETS__NO_QUALITY_OR_BUY_CLEARANCE')
    from v70_tactical_input import calculate
    arguments={'feed_source':producer.verified_macro_feed_source} if producer.verified_macro_feed_source is not None else {}
    tactical=calculate(producer.root,request,producer.v70_strategic_policy,producer.fx_observation,**arguments)
    ctx=deepcopy(context);ctx['family_c7_reporting_fx']=deepcopy(producer.fx_observation)
    assembler=SourceAssembler(producer.root,request,ctx,options['artifact_directory'])
    out=assembler.build(tactical=tactical,identities=identities,portfolio_facts_source=options.get('portfolio_reconciliation_source'))
    out['original_observations'].update(selected_account_cash_trial={
        'formal_sources':deepcopy(trial.get('formal_sources',{})),'assumptions':deepcopy(trial.get('assumptions',[])),
        'trial_values_used_as_qualified_funding':False},
        accepted_position_source_count=len(prepared.payload['positions']),
        original_broker_view=deepcopy(prepared.payload.get('broker_snapshot_source')),
        approved_account_scope=deepcopy(context.get('approved_document_account_scope')))
    if options.get('portfolio_reconciliation_source') is None:
        db_locator={'local_path':str(producer.db_path),'sha256':request['client_snapshot']['payload']['source_sha256'],
            'as_of':request['client_snapshot'].get('as_of'),'available_at':request['client_snapshot'].get('available_at')}
        for position in prepared.payload['positions']:
            source=position.get('source_position') or {};iid=position['instrument_key']
            locator={**db_locator,'table':'portfolio_position','instrument_key':iid,
                'source_reference':source.get('source_reference') or source.get('source_row'),
                'as_of':source.get('as_of_utc') or source.get('observed_at_utc') or db_locator['as_of']}
            assembler.field('current_nav.positions.'+iid+'.quantity',position.get('quantity') if position.get('quantity_state')=='KNOWN' else None,
                code='C7_CURRENT_POSITION_QUANTITY_REQUIRED',sources=[locator],producer='W5.prepare_input:accepted_original_position')
        review=out['original_observations']['w1_portfolio_review']
        from w1_portfolio_observations import MINOR_COLUMNS
        for account in review['accounts']:
            aid=account['account_key'];observations=account['cash_observations']
            selected=observations[0] if len(observations)==1 else None
            row=selected['original_row'] if selected is not None else None
            locator={**db_locator,'table':'cash_balance_snapshot','account_key':aid,
                'selected_snapshot':deepcopy(selected),'snapshot_currency_ambiguous':len(observations)>1}
            for name,column in {**MINOR_COLUMNS,'unsettled_cash':None}.items():
                original=selected['amounts'].get(name) if selected is not None else None
                assembler.field('funding_buckets.'+aid+'.'+name,original,
                    state=ADAPTER if original is not None else MISSING,
                    code='C7_ACCOUNT_ORIGINAL_'+name.upper()+'_QUALIFICATION_REQUIRED',
                    sources=[dict(locator,as_of=row.get('as_of_utc') if row else None,
                        available_at=selected['available_at'] if selected is not None else None,
                        currency=selected['currency'] if selected is not None else None,
                        unit='currency_major',original_minor_column=column,
                        original_minor_value=row.get(column) if row is not None and column else None,
                        normalized_amount=original)],
                    producer='ORIGINAL_W1_COHERENT_CASH_SNAPSHOT__OBSERVATION_NOT_EXECUTABLE_CASH')
            assembler.field('funding_buckets.'+aid+'.available_and_authorization',None,
                code='C7_ACCOUNT_AVAILABLE_CASH_AND_INCREMENTAL_AUTHORIZATION_REQUIRED',sources=[locator])
        order=prepared.payload.get('broker_snapshot_source')
        locator={'location':'prepared.broker_snapshot_source.order_source' if order else 'original_owner_order_confirmation',
            'source':deepcopy(order['order_source'] if order else producer.order_confirmation),
            'source_sha256':digest(order['order_source'] if order else producer.order_confirmation),
            'as_of':order.get('captured_at') if order else None,'available_at':order.get('captured_at') if order else None}
        assembler.field('exposure_coverage.original_order_snapshot',None,
            state=ADAPTER if order or producer.order_confirmation else MISSING,
            code='C7_ORIGINAL_ORDER_ASOF_LIFECYCLE_AND_PORTFOLIO_COVERAGE_REQUIRED',sources=[locator],
            producer='ORIGINAL_READONLY_BROKER_OR_OWNER_ORDER_OBSERVATION')
        out['field_inventory']=list(assembler.inventory.values());out['issues']=assembler.issues
    out['call_trace']=['W8.family_c7_source_assembly.assemble_original_producers','W8.v70_tactical_input.calculate',
        'W8.family_c7_source_assembly:original_approval_and_portfolio_business_records']
    out['digest']=digest({k:v for k,v in out.items() if k!='digest'})
    return out

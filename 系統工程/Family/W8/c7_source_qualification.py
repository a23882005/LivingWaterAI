"""Resolve engineering dependencies against named original business facts.

This is a source/ownership work queue. It does not validate a C7 decision,
authorize funding or replace the original financial consumer.
"""
from copy import deepcopy
from family_input import digest
from member_market_source import time

AVAILABLE='AVAILABLE_FOR_ORIGINAL_CONSUMER'
MISSING='ORIGINAL_FACT_NOT_PROVIDED'
UNQUALIFIED='EXISTING_ORIGINAL_REQUIRES_QUALIFICATION'
ENGINEERING='CODEX_NORMALIZATION_OR_WIRING'
WAITING='BLOCKED_BY_NAMED_ORIGINAL_FACTS'


def known_before_cutoff(records,evaluation_at):
    cutoff=time(evaluation_at)
    if not records:return False
    for row in records:
        stamps=[row[k] for k in ('as_of_utc','created_at_utc','recorded_at_utc','reconciled_at_utc') if row.get(k)]
        if not stamps:return False
        try:
            if any(time(stamp)>cutoff for stamp in stamps):return False
        except (ValueError,TypeError,AttributeError):
            return False
    return True


def w1_binding_at_cutoff(request,owner):
    tables=request['client_snapshot']['payload']['tables'];aid=owner['account']
    parts=[[r for r in tables.get(name,[]) if r.get('account_key')==aid]
        for name in ('portfolio_account','account_ownership','account_broker_link')]
    parts.append([r for r in tables.get('funding_account_domain_link',[]) if r.get('account_key')==aid
        and r.get('currency_code')==owner['currency'] and r.get('funding_domain_key')==owner['funding_domain']])
    parts.append([r for r in tables.get('funding_domain',[]) if r.get('funding_domain_key')==owner['funding_domain']])
    return all(known_before_cutoff(records,request['evaluation_at']) for records in parts)


def annotate(assembly,request):
    scope=assembly['scope_candidate'];observations=assembly['original_observations']
    snapshot=request['client_snapshot']['payload'];tables=snapshot['tables']
    review=observations.get('w1_portfolio_review') or {}
    checks={}
    def check(key,available,fields,*,existing=False,locators=(),account=None):
        state=AVAILABLE if available else UNQUALIFIED if existing else MISSING
        checks[key]={'requirement_id':key,'state':state,'account_key':account,
            'business_fields':list(fields),'source_locators':deepcopy(list(locators)),
            'source_db_sha256':snapshot['source_sha256'],
            'next_responsibility':'ORIGINAL_CONSUMER' if available else 'PM_CONSOLIDATES_ORIGINAL_BUSINESS_FACTS',
            'owner_json_required':False}
    def rows(table,account):return [r for r in tables.get(table,[]) if r.get('account_key')==account]
    def refs(table,records):return [{'table':table,'row_digest':digest(r),
        'as_of':r.get('as_of_utc'),'available_at':r.get('created_at_utc') or r.get('recorded_at_utc'),
        'source_reference':r.get('source_reference')} for r in records]
    owner_requirements=[];funding_requirements=[]
    for account in tables.get('portfolio_account',[]):
        aid=account['account_key'];prefix='account:'+aid+':'
        owners=rows('account_ownership',aid);brokers=rows('account_broker_link',aid)
        domains=rows('funding_account_domain_link',aid)
        qualified=next((r for r in review.get('accounts',[]) if r['account_key']==aid),{})
        bound=(qualified.get('binding_qualification')=='ORIGINAL_W5_OWNER_BINDING_PASSED'
            and w1_binding_at_cutoff(request,qualified['owner_candidate']))
        # A reconciled facts descriptor has already passed read_facts' complete
        # all-account proof checks. Do not re-require a particular W1 encoding.
        bound=bound or any(o['account']==aid for o in (scope.get('account_owners') or []))
        owner_parts=[('account_record',bound or account.get('account_state')=='KNOWN' and bool(account.get('account_currency'))
                and known_before_cutoff([account],request['evaluation_at']),
            ['actual account identity/state','native currency'],[account],'portfolio_account'),
            ('owner_proof',bound or len(owners)==1 and owners[0].get('ownership_state')=='VERIFIED'
                and owners[0].get('owner_client_id')==request['client_id']
                and known_before_cutoff(owners,request['evaluation_at']),
                ['owner/client confirmation'],owners,'account_ownership'),
            ('broker_currency_domain',bound,
                ['actual broker','native currency','investment funding domain','original binding reference/time'],
                brokers+domains,'account_broker_link/funding_account_domain_link')]
        for suffix,ready,fields,records,table in owner_parts:
            key=prefix+suffix;owner_requirements.append(key)
            check(key,ready,fields,existing=bool(records),locators=refs(table,records),account=aid)
        cash=rows('cash_balance_snapshot',aid)
        ready=scope.get('funding_buckets') is not None
        for suffix,fields in [('cash_eligibility',['same-cutoff total/settled/unsettled/reserved/available cash',
                'cash basis','payable/netting/nonoverlap evidence']),
            ('incremental_authorization',['allowed incremental amount/currency','original confirmation reference/time'])]:
            key=prefix+suffix;funding_requirements.append(key)
            check(key,ready,fields,existing=bool(cash) if suffix=='cash_eligibility' else False,
                locators=refs('cash_balance_snapshot',cash),account=aid)
    draft=request['confirmed_target']['payload']['draft'];base=draft.get('denominator') or {}
    approval=request['confirmed_target']['payload'].get('confirmation_evidence') or request['confirmed_target'].get('original_confirmation')
    approved=scope.get('approved_long_term_target') is not None
    check('approved_pool',approved or base.get('value_state')=='KNOWN' and base.get('amount') is not None
        and bool(base.get('currency')),['current approved investment pool amount/currency/confirmation'],
        existing=base.get('amount') is not None,locators=[{'location':'request.confirmed_target.payload.draft.denominator',
            'original':deepcopy(base),'target_version':request['confirmed_target']['target_version']}])
    check('approval_record',approved or bool(approval),['existing original target confirmation/version'],
        existing=bool(approval),locators=[{'location':'request.confirmed_target','target_version':request['confirmed_target']['target_version']}])
    check('current_nav',scope.get('current_nav') is not None,
        ['all-account complete positions at reconciled cutoff','same-cutoff market prices/currencies',
         'total/net cash/debt/payables and NAV reconciliation'],
        existing=bool(tables.get('portfolio_position') or tables.get('cash_balance_snapshot')),
        locators=[{'location':'original_observations.w1_portfolio_review',
            'historical_position_rows':sum(len(a['positions']) for a in review.get('accounts',[])),
            'cash_observations':sum(len(a['cash_observations']) for a in review.get('accounts',[]))}])
    order_fields=[f for f in assembly['field_inventory'] if f['field_path'].endswith('exposure_coverage.original_order_snapshot')]
    order_locators=[loc for f in order_fields for loc in f['source_locators']]
    check('complete_exposure_book',scope.get('exposure_coverage') is not None and scope.get('exposures') is not None,
        ['all-account orders/fills/other commitments/confirmed releases at cutoff',
         'original event/intent/economic IDs','last acknowledged pending quantities/prices'],
        existing=any(bool(loc.get('source')) for loc in order_locators) or bool(observations.get('original_coverage')),
        locators=order_locators)
    check('protection',scope.get('protection_coverage') is not None and scope.get('preference_locks') is not None,
        ['complete holding protection/unlock coverage','original Owner confirmation reference/time'],
        existing=bool(tables.get('holding_policy_proposal') or tables.get('holding_policy_confirmation')))
    check('caps',scope.get('portfolio_caps') is not None,
        ['client/global cap applicability','amount/currency/accounting base or confirmed exemption'])
    dependencies={
        'family_owner':owner_requirements,'budget_currency':owner_requirements,
        'account_owners':owner_requirements,
        'approved_long_term_target':['approved_pool','approval_record']+owner_requirements,
        'approved_target_digest':['approved_pool','approval_record']+owner_requirements,
        'approval_receipt':['approved_pool','approval_record']+owner_requirements,
        'total_stock_ceiling':['approved_pool','approval_record']+owner_requirements,
        'current_nav':['current_nav']+owner_requirements,
        'exposure_coverage':['complete_exposure_book']+owner_requirements,
        'exposures':['complete_exposure_book']+owner_requirements,
        'funding_buckets':funding_requirements+owner_requirements,
        'protection_coverage':['protection'],'preference_locks':['protection','current_nav'],
        'portfolio_caps':['caps'],
    }
    for field in assembly['field_inventory']:
        root=field['field_path'].removeprefix('family_scope.').split('.')[0]
        # A known independent leaf does not become unknown because another
        # portfolio field is missing. Derived digests are never Owner JSON tasks.
        available=field['classification']=='EXISTING_BOUND_SOURCE' and field['value_state']=='KNOWN'
        ids=[] if available else dependencies.get(root,[])
        unresolved=[key for key in ids if checks[key]['state']!=AVAILABLE]
        state=AVAILABLE if available else WAITING if unresolved else ENGINEERING
        field['dependency_resolution']={'state':state,'original_requirement_ids':unresolved,
            'next_responsibility':'ORIGINAL_CONSUMER' if available else
                'PM_ORIGINALS_THEN_CODEX_NORMALIZATION' if unresolved else 'CODEX_SOURCE_ADAPTER',
            'owner_json_required':False}
    assembly['source_qualification']={'schema_version':'Family.W8.C7SourceQualification.v1',
        'client_id':request['client_id'],'run_id':request['run_id'],
        'source_db_sha256':snapshot['source_sha256'],
        'original_fact_checks':list(checks.values()),
        'required_original_facts':[deepcopy(v) for v in checks.values() if v['state']!=AVAILABLE],
        'engineering_only_fields':[f['field_path'] for f in assembly['field_inventory']
            if f['dependency_resolution']['state']==ENGINEERING],
        'financial_pass_claimed':False,'trade_action':'NO_TRADE'}
    return assembly

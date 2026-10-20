"""Non-computing report helpers for source inventories and canonical sections."""
from copy import deepcopy
from datetime import datetime
from report_receiver import require, digest


def select_inventory(records, current_id):
    ids=set()
    for row in records:
        require(row['source_id'] not in ids, 'DUPLICATE_SOURCE_ID');ids.add(row['source_id'])
        require(row['sha256']==row['observed_sha256'], 'SOURCE_HASH_MISMATCH')
    selected=[r for r in records if r['source_id']==current_id]
    require(len(selected)==1 and selected[0]['role']=='CURRENT', 'CURRENT_TEMPLATE_REQUIRED')
    require(sum(r['role']=='CURRENT' for r in records)==1,'AMBIGUOUS_CURRENT_TEMPLATE')
    return deepcopy(selected[0])


def history_view(events, client_id):
    seen=set();rows=[]
    for e in events:
        require(e['client_id']==client_id,'HISTORY_CLIENT')
        require(e['event_id'] not in seen,'HISTORY_DUPLICATE');seen.add(e['event_id'])
        when=datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00'))
        require(when.tzinfo is not None,'HISTORY_TIMEZONE')
        require(e.get('source_id') and e.get('confirmed_by') and e.get('confirmed') is True,'HISTORY_EVIDENCE')
        require(all(k in e for k in ('before','after','impact','sequence')),'HISTORY_FIELDS')
        rows.append((when,e['sequence'],e['event_id'],deepcopy(e)))
    return [r[-1] for r in sorted(rows,key=lambda x:x[:3])]


def canonical_section(envelope, *, client_id, run_id, section):
    """Preserve upstream values; missing sections are not calculated locally."""
    if envelope is None:
        return {'section':section,'value_state':'UNKNOWN','payload':None,'issue_codes':['SOURCE_NOT_PROVIDED']}
    require(envelope.get('client_id')==client_id,'SECTION_CLIENT')
    require(envelope.get('run_id')==run_id,'SECTION_RUN')
    require(envelope.get('section')==section,'SECTION_KIND')
    require(envelope.get('value_state') in ('KNOWN','UNKNOWN','STALE','PARTIAL'),'SECTION_STATE')
    require(envelope.get('source_id') and envelope.get('rules_sha') and envelope.get('as_of'),'SECTION_LINEAGE')
    require(envelope.get('payload_sha256')==digest(envelope.get('payload')),'SECTION_HASH')
    if envelope['value_state']=='KNOWN':
        require(envelope.get('payload') is not None,'KNOWN_SECTION_EMPTY')
    return deepcopy(envelope)


def cash_history_view(snapshot):
    """Keep date, funding domains, protected and available states distinct."""
    tables=snapshot['tables'];client=snapshot['client_id']
    result={}
    for name in ('cash_balance_snapshot','funding_domain','funding_account_domain_link',
                 'funding_evaluation','funding_assignment','protected_funding_claim',
                 'protected_funding_confirmation','sgov_role_proposal','sgov_role_confirmation'):
        rows=tables.get(name,[])
        require(all(r.get('client_id')==client for r in rows),'FUNDING_CLIENT')
        result[name]=deepcopy(rows)
    return {'value_state':'SOURCE_VALUES_ONLY','snapshot_aggregation':'NONE','tables':result}

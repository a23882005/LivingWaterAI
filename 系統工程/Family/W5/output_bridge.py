"""Branch projections reuse the frozen Work9 mappings without dummy branches."""
from copy import deepcopy
from runtime_loader import load_c_module


def normalize_stock(repo_path, integrated, protected=False):
    native=load_c_module(repo_path,9)
    raw=deepcopy(integrated['canonical_v82_output'])
    fields=raw['canonical_analysis']
    action,reasons=native._normalize_v82_action(fields['execution_action']['value'],protected)
    return {'canonical_action':action,'source_action':fields['execution_action']['value'],
        'reason_codes':reasons,'trade_action':'NO_TRADE','raw_output':raw,
        'execution_amount':deepcopy(fields['execution_amount']['value']),
        'execution_quantity':deepcopy(fields['execution_quantity']['value']),
        'execution_price':deepcopy(fields['execution_price']['value'])}


def normalize_bond(repo_path, integrated):
    native=load_c_module(repo_path,9)
    ready=deepcopy(integrated['canonical_v75_runtime_ready_snapshot'])
    raw=deepcopy(integrated['canonical_v75_output'])
    account,reasons=native._normalize_v75_envelope_action(raw,ready)
    rows=[]
    for decision in raw['per_asset_decisions']:
        action,codes=native._normalize_v75_action(decision)
        rows.append({'asset_id':decision['asset_id'],'canonical_action':action,
            'reason_codes':codes,'source_decision':deepcopy(decision),'trade_action':'NO_TRADE'})
    return {'account_action':account,'account_reason_codes':reasons,'per_asset':rows,
        'raw_output':raw,'raw_runtime_ready':ready,'trade_action':'NO_TRADE'}

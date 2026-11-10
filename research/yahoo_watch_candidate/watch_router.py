"""Operational monitor routing over formal V82 evidence, never a strategy change.
This adapter does not compute or certify the upstream V82 predicates.
Monitor exit is manual; unknown data never silently stops an active watch.
"""
import math


def route(snapshot, now, expected_rule_sha256, previously_active=False, manual_stop=False):
    out = {'monitor_active': previously_active, 'new_buy_permission': False,
           'reason': 'INPUT_UNKNOWN', 'auto_exit_defined': False}
    if manual_stop:
        return {**out, 'monitor_active':False, 'reason':'MANUAL_STOP'}
    if not isinstance(snapshot, dict):
        return out
    if not expected_rule_sha256 or snapshot.get('rule_sha256') != expected_rule_sha256:
        return {**out, 'reason':'RULE_VERSION_MISMATCH'}
    if snapshot.get('qualified_formal_daily_input') is not True:
        return {**out, 'reason':'NOT_QUALIFIED_FORMAL_DAILY_INPUT'}
    if not snapshot.get('snapshot_id') or not snapshot.get('producer_id'):
        return {**out, 'reason':'MISSING_PROVENANCE'}
    start, end = snapshot.get('as_of'), snapshot.get('valid_until')
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (start,end)) or not start <= now < end:
        return {**out, 'reason':'SNAPSHOT_NOT_CURRENT'}
    price, down = snapshot.get('L_price'), snapshot.get('RunawayDown')
    if price is True or down is True:
        return {**out, 'monitor_active': True,
                'reason':'V82_DOWN_RISK_OBSERVATION' if down is True else 'V82_LEFT_PRICE_OBSERVATION'}
    if price is False and down is False:
        return {**out, 'reason':'ACTIVE_UNTIL_MANUAL_STOP' if previously_active else 'NO_DOWN_OBSERVATION'}
    return {**out, 'reason':'PREDICATE_UNKNOWN_RETAIN_PRIOR_MONITOR_STATE'}

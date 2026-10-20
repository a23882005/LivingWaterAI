"""Read-only W6 boundary for W5 receipts. No trading or strategy computation.

The allowlist is operator-supplied. W1 historical tables remain historical;
the current allocation workbook is a separate, explicitly dated input.
"""
import hashlib
import html
import json
import math
from decimal import Decimal
from copy import deepcopy
from datetime import datetime


class ReportError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise ReportError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def encode(value):
    """Tagged v1 encoding: preserve Decimal, numeric types and array order."""
    if value is None:return ['null']
    if isinstance(value,bool):return ['bool',value]
    if isinstance(value,str):return ['str',value]
    if isinstance(value,int):return ['int',str(value)]
    if isinstance(value,Decimal):
        if not value.is_finite():raise ReportError('NONFINITE_INPUT')
        return ['decimal',str(value)]
    if isinstance(value,float):
        if not math.isfinite(value):raise ReportError('NONFINITE_INPUT')
        return ['float',value.hex()]
    if isinstance(value,list):return ['list',[encode(x) for x in value]]
    if isinstance(value,dict) and all(isinstance(k,str) for k in value):
        return ['dict',[[k,encode(value[k])] for k in sorted(value)]]
    raise ReportError('UNSUPPORTED_INPUT_TYPE')


def input_digest(request):
    wire=['Family.W5.digest.v1',encode(request)]
    return hashlib.sha256(json.dumps(wire,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def assemble(snapshot, request, result, *, client_id, members, sections=None, events=None, target_validator=None):
    require(client_id in members, 'MEMBER_NOT_ALLOWED')
    require(snapshot.get('schema_version') == 'Family.W5.W1Snapshot.v1', 'SNAPSHOT_SCHEMA')
    require(request.get('schema_version') == 'Family.W5.request.v1', 'REQUEST_SCHEMA')
    require(result.get('schema_version') == 'Family.W5.result.v1', 'RESULT_SCHEMA')
    require(snapshot.get('client_id') == request.get('client_id') == client_id, 'CLIENT_MISMATCH')
    require(snapshot.get('identity', {}).get('client_id') == client_id, 'IDENTITY_MISMATCH')
    require(snapshot['identity'].get('family_alias') == members[client_id], 'ALIAS_MISMATCH')
    require(request.get('client_snapshot', {}).get('payload') == snapshot, 'SNAPSHOT_BINDING')
    require(bool(request.get('run_id')) and request['run_id'] == result.get('run_id'), 'RUN_MISMATCH')
    require(bool(request.get('request_id')) and request['request_id'] == result.get('request_id'), 'REQUEST_MISMATCH')
    when = datetime.fromisoformat(request['evaluation_at'].replace('Z', '+00:00'))
    require(when.tzinfo is not None, 'TIMEZONE_REQUIRED')
    require(request.get('trade_authorization') == 'NONE', 'TRADE_SCOPE')
    # Reject any identity in nested source content before constructing output.
    def check_identity(obj):
        if isinstance(obj, dict):
            if 'client_id' in obj:
                require(obj['client_id'] == client_id, 'NESTED_CLIENT_MISMATCH')
            for value in obj.values():
                check_identity(value)
        elif isinstance(obj, list):
            for value in obj:
                check_identity(value)
    # W5 retains upstream demonstration identities inside native_result as
    # provenance. It is not a Family envelope and is never copied into the view.
    # The Family result/mentor are checked here; receive_action verifies the
    # request digest, canonical digest and native account owner separately.
    family_result = {k: v for k, v in result.items() if k != 'native_result'}
    for source in (snapshot, request, family_result):
        check_identity(source)
    tables = snapshot['tables']
    accounts = {r['account_key']: r for r in tables.get('portfolio_account', [])}
    require(len(accounts) == len(tables.get('portfolio_account', [])), 'DUPLICATE_ACCOUNT')
    instruments = {r['instrument_key']: r for r in tables.get('portfolio_instrument', [])}
    require(len(instruments) == len(tables.get('portfolio_instrument', [])), 'DUPLICATE_INSTRUMENT')
    seen = set()
    holdings = []
    for p in tables.get('portfolio_position', []):
        require(p['account_key'] in accounts, 'POSITION_ACCOUNT_MISSING')
        require(p['instrument_key'] in instruments, 'POSITION_INSTRUMENT_MISSING')
        key = (p['account_key'], p['instrument_key'], p.get('as_of_utc'))
        require(key not in seen, 'DUPLICATE_POSITION')
        seen.add(key)
        holdings.append({'account': deepcopy(accounts[p['account_key']]),
                         'instrument': deepcopy(instruments[p['instrument_key']]),
                         'position': deepcopy(p)})
    cash_seen = set()
    for row in tables.get('cash_balance_snapshot', []):
        require(row['account_key'] in accounts, 'CASH_ACCOUNT_MISSING')
        key = row['cash_snapshot_id']
        require(key not in cash_seen, 'DUPLICATE_CASH_SNAPSHOT')
        cash_seen.add(key)
    action = receive_action(result, request)
    from source_views import canonical_section, cash_history_view, history_view
    sections = sections or {}
    canonical = {name: canonical_section(sections.get(name), client_id=client_id, run_id=request['run_id'], section=name) for name in ('target','drift','performance','risk','look_through','valuation','funding')}
    if request.get('confirmed_target') is not None:
        require(callable(target_validator), 'TARGET_VALIDATOR_REQUIRED')
        from target_receipt import receive_target
        from inspect import getsource
        target_view = receive_target(request['confirmed_target'], client_id=client_id,
            report_run_id=request['run_id'], evaluation_at=when,
            source_id='W5_REQUEST:' + request['request_id'] + ':confirmed_target',
            rules_sha=hashlib.sha256(getsource(target_validator).encode()).hexdigest(),
            validator=target_validator)
        if sections.get('target') is not None:
            require(canonical['target']['payload'] == target_view['payload'], 'TARGET_SECTION_CONFLICT')
        canonical['target'] = target_view
    history = history_view(events or [], client_id)
    cash = cash_history_view(snapshot)
    return {'schema_version': 'Family.W6.ReportView.v1', 'client_id': client_id,
            'member_alias': members[client_id], 'run_id': request['run_id'],
            'evaluation_at': request['evaluation_at'], 'mode': 'HISTORICAL_SOURCE_REVIEW',
            'holdings': sorted(holdings, key=lambda x: (x['position']['account_key'], x['position']['instrument_key'])),
            'source_tables': deepcopy(tables), 'engine': action,
            'canonical_sections': canonical, 'history': history, 'history_state': 'UNKNOWN' if events is None else 'PROVIDED', 'cash_history': cash,
            'source_hashes': {k: digest(v) for k, v in [('snapshot', snapshot), ('request', request), ('result', result)]},
            'formal_output_eligible': False, 'production': 'HOLD', 'trade_authorization': 'NONE'}


def receive_action(result, request):
    require(result.get('schema_version') == 'Family.W5.result.v1', 'RESULT_SCHEMA')
    require(bool(request.get('run_id')) and result.get('run_id') == request['run_id'], 'RUN_MISMATCH')
    require(bool(request.get('request_id')) and result.get('request_id') == request['request_id'], 'REQUEST_MISMATCH')
    # Failure receipts may omit client_id; every supplied nested identity must match.
    def check_client(value):
        if isinstance(value, dict):
            if 'client_id' in value:
                require(value['client_id'] == request.get('client_id'), 'RESULT_CLIENT')
            for child in value.values():
                check_client(child)
        elif isinstance(value, list):
            for child in value:
                check_client(child)
    if result.get("status") != "OK":
        check_client(result)
    require(result.get('production') == 'HOLD' and result.get('trade_action') == 'NO_TRADE', 'ENGINE_EXECUTION_SCOPE')
    status = result.get('status')
    require(status in ('OK', 'DATA_UNAVAILABLE', 'REJECTED', 'BLOCKED', 'INVALID_INPUT', 'ERROR'), 'RESULT_STATUS_UNKNOWN')
    if status != 'OK':
        require(result.get('canonical_result') is None and result.get('mentor') is None, 'FAILED_RESULT_HAS_ADVICE')
        return {'status': status, 'items': [], 'issue_codes': deepcopy(result.get('issue_codes', [])),
                'display': '本次引擎未產生可採用的部署建議。', 'execution_advice_allowed': False,
                'source_run_id': result['run_id']}
    require(result.get('client_id') == request['client_id'], 'RESULT_CLIENT')
    require(result.get('input_digest') == input_digest(request), 'RESULT_INPUT_DIGEST')
    mentor = result.get('mentor') or {}
    require(mentor.get('client_id') == request['client_id'] and mentor.get('run_id') == request['run_id'], 'MENTOR_BINDING')
    require(result.get('data_provenance') in ('SOURCE_BACKED', 'SYNTHETIC'), 'PROVENANCE_REQUIRED')
    canonical = mentor.get('canonical_deployment_result')
    require(isinstance(canonical, dict) and isinstance(canonical.get('items'), list), 'CANONICAL_REQUIRED')
    require(mentor.get('canonical_deployment_result_sha256') == digest(canonical), 'CANONICAL_DIGEST')
    require(mentor.get('execution_advice_allowed') is False, 'MENTOR_EXECUTION_SCOPE')
    ids = [x['item_id'] for x in canonical['items']]
    require(len(ids) == len(set(ids)), 'DUPLICATE_ACTION_ITEM')
    for item in canonical['items']:
        require(item.get('account_owner') == mentor.get('owner') == request.get('native_bundle', {}).get('stock_request', {}).get('work3_handoff', {}).get('owner'), 'ACTION_OWNER')
        require(bool(item.get('data_lineage')) and bool(item.get('rule_lineage')), 'ACTION_LINEAGE')
    return {'status': status, 'items': deepcopy(canonical['items']),
            'issue_codes': deepcopy(mentor.get('unknown_reason_codes', [])),
            'data_provenance': result['data_provenance'], 'execution_advice_allowed': False,
            'display': '工程合成測試，非家人建議。' if result['data_provenance'] == 'SYNTHETIC' else '引擎分析原值；未授權執行交易。',
            'source_run_id': result['run_id'], 'canonical_digest': digest(canonical)}


def render_review(view):
    """Escaped standalone diagnostic report; no cross-member aggregate context."""
    e = lambda v: html.escape(str(v if v is not None else '未提供'))
    rows = ''.join('<tr>' + ''.join('<td>' + e(v) + '</td>' for v in [
        x['account']['account_label'], x['instrument']['ticker'],
        x['position'].get('quantity_decimal'), x['position'].get('cost_state'),
        x['position'].get('as_of_utc')]) + '</tr>' for x in view['holdings'])
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font:18px sans-serif;background:#fbfaf5;color:#245c50;margin:24px} '
        'table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #bbb;overflow-wrap:anywhere}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}.scroll{overflow:auto}</style>'
        '<h1>' + e(view['member_alias']) + ' 歷史來源接收核對</h1><p>' + e(view['evaluation_at']) +
        '；歷史資料，非目前持股或交易建議。</p><div class="scroll"><table><tr><th>來源帳戶</th><th>標的</th><th>股數</th>'
        '<th>成本狀態</th><th>持股日期</th></tr>' + rows + '</table></div><h2>引擎結果</h2><p>' +
        e(view['engine']['display']) + '</p><h2>來源與資金狀態</h2><p>未提供的成本、績效、穿透、確認目標及可用資金，以UNKNOWN保留。</p><details><summary>檢視原始來源狀態</summary><pre>' + e(json.dumps({'canonical_sections':view['canonical_sections'],'cash_history':view['cash_history'],'history':view['history'],'history_state':view['history_state']},ensure_ascii=False,indent=2)) + '</pre></details><h2>引擎原始回覆</h2><pre>' + e(json.dumps(view['engine'],ensure_ascii=False,indent=2)) +
        '</pre><p>現金各日期快照分別保存，未相加；缺值不是0。Production HOLD；交易NONE。</p></html>')

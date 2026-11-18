"""Human-readable V82 reference-notice email; preserve original JSON for tasks.

Formatting only: never infer a buy signal, real-time market status or a new data event.
"""
from datetime import datetime, timedelta, timezone
import math

TW = timezone(timedelta(hours=8))
JSON_MARKER = '--- LW_MARKET_JSON_V1 ---'


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _tw(value):
    dt = _date(value)
    return dt.astimezone(TW).strftime('%m/%d %H:%M') if dt else '時間未知'


def _price(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return format(value, '.8g')


def _label(symbol):
    return '0050' if symbol == '0050.TW' else str(symbol or '未知標的')


def _rows(report):
    return report['items'] if report['schema'] == 'LW_MARKET_BATCH_V1' else [report]


def _row_status(row, at):
    """Return (has_reference_price, concise status) as known at mail creation time."""
    if row.get('notice_kind') == 'TEST' or row.get('data_status') == 'TEST_ONLY' or row.get('source') == 'SYNTHETIC_NO_MARKET_DATA':
        return False, '測試資料，已排除'
    status = row.get('data_status')
    if status == 'OLD_OBSERVATION_NOT_CURRENT':
        prior = _price(row.get('market_price'))
        detail = ('；舊報價 ' + prior + '，時間 ' + _tw(row.get('quote_time'))) if prior else ''
        return False, '舊行情，已排除' + detail
    if status in ('NOT_EVALUATED', 'UNKNOWN'):
        detail = '缺價格／行情時間' if _price(row.get('market_price')) is None or _date(row.get('quote_time')) is None else '來源尚未核實'
        return False, detail + '（' + status + '）'
    value = _price(row.get('market_price'))
    quote = _date(row.get('quote_time'))
    until = _date(row.get('valid_until'))
    if value is None or quote is None:
        return False, '缺價格或行情時間'
    if at is None or until is None:
        return False, '有效時間未確認'
    if quote > at or until <= at:
        return False, '報價時間異常或通知發出時已過期'
    if status != 'OBSERVED_NOT_REALTIME_CERTIFIED':
        return False, '資料狀態未合格（' + str(status or 'UNKNOWN') + '）'
    delay = row.get('delay_seconds')
    delay = delay if isinstance(delay, (int, float)) and not isinstance(delay, bool) and delay >= 0 else 0
    if (at - quote).total_seconds() > delay + 900:
        return False, '舊行情，超過觀測時效'
    session = row.get('session')
    if session not in ('RTH', 'PRE', 'POST'):
        return False, '盤別未確認'
    unit = '元' if row.get('symbol') in ('0050.TW', '0050') else '（原幣別）'
    label = {'RTH': '交易時段', 'PRE': '盤前', 'POST': '盤後'}[session]
    return True, f'{label}參考價 {value}{unit}；報價 {_tw(row.get("quote_time"))}；有效至 {_tw(row.get("valid_until"))}（未認證即時）'


def compose(report, json_body):
    """Return (subject, body); append unmodified canonical JSON after a stable marker."""
    rows = _rows(report)
    stamp = report.get('generated_at') or report.get('observed_at')
    at = _date(stamp)
    statuses = [(_label(r.get('symbol')), *_row_status(r, at)) for r in rows]
    usable = sum(1 for _, valid, _ in statuses if valid)
    label = '／'.join(symbol for symbol, _, _ in statuses[:3])
    if len(statuses) > 3:
        label += '等' + str(len(statuses)) + '檔'
    is_test = all(r.get('notice_kind') == 'TEST' or r.get('data_status') == 'TEST_ONLY' for r in rows)
    summary = '測試通知' if is_test else (f'參考報價{usable}/{len(statuses)}' if usable else f'無可用行情0/{len(statuses)}')
    subject = f'[V82-WATCH] {label}｜{summary}｜{_tw(stamp)}｜非買進訊號'
    lines = [
        '🌿 V82 行情監控（非買進指令）',
        f'台灣時間：{_tw(stamp)}｜寄出時有時效參考價 {usable}/{len(statuses)} 檔',
    ]
    for symbol, _, note in statuses[:8]:
        lines.append(f'• {symbol}：{note}')
    if len(statuses) > 8:
        lines.append(f'• 其餘{len(statuses)-8}檔：詳見下方原始JSON。')
    lines.extend([
        '閱讀時請重新查價；此信未執行正式V82判斷或交易授權。',
        'GitHub執行：' + str(report.get('run_id') or '未提供'),
        '紀錄：' + str(report.get('run_url') or '未提供'),
        '',
        JSON_MARKER,
        json_body,
    ])
    return subject, '\n'.join(lines)

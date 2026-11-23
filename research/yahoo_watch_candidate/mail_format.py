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


RD_LABELS = {
    'D1': '連續3日創20日收盤新低',
    'D2': '收盤跌破已確認的波段低點',
    'D3': '跌破支撐後未迅速收回',
    'A1': 'MACD空方動能擴大',
    'A2': 'KD低檔持續走弱',
    'A3': 'EMV持續惡化',
    'A4': 'RSI連續走低',
    'A5': '價跌且成交量高於20日均量',
    'A6': '波動幅度快速擴張',
    'A7': '近期5日跌勢較前5日加速',
    'A8': '最近3段反彈逐步變弱',
}


def _codes(value, prefix, max_number):
    if not isinstance(value, str):
        return []
    valid = {f'{prefix}{i}' for i in range(1, max_number + 1)}
    return list(dict.fromkeys(code for code in value.split('|') if code in valid))


def _daily_risk_lines(report, day):
    """Show provenance-bound completed-day evidence; never substitute intraday."""
    lines = []
    close = _price(report.get('daily_close'))
    previous = _price(report.get('daily_previous_close'))
    low = _price(report.get('daily_low'))
    unit = '元' if report.get('symbol') in ('0050', '0050.TW') else '美元'
    pct = report.get('daily_change_percent')
    pct_ok = (isinstance(pct, (int, float)) and not isinstance(pct, bool)
              and math.isfinite(pct))
    if close and previous and pct_ok:
        diff = float(close) - float(previous)
        detail = f'；盤中最低{low}{unit}' if low else ''
        lines.append(
            f'收盤數字：{day} 前收{previous}→收{close}{unit}'
            f'（{diff:+.2f}{unit}，{pct:+.2f}%）{detail}。')
    elif close:
        lines.append(f'收盤數字：{day} 觀測收盤{close}{unit}；前收／跌幅尚缺。')
    else:
        lines.append('收盤數字：本次警戒JSON未附日線價與跌幅，需由正式日K補證。')
    breaks = _codes(report.get('rd_break_true_codes'), 'D', 3)
    accelerations = _codes(report.get('rd_accel_true_codes'), 'A', 8)
    if breaks or accelerations:
        summary = '、'.join(f'{code}{RD_LABELS[code]}' for code in breaks) or '尚缺分項'
        accel = '、'.join(f'{code}{RD_LABELS[code]}' for code in accelerations) or '尚缺分項'
        lines.append(f'急跌證據：價格結構【{summary}】；跌勢加速已確認{len(accelerations)}項【{accel}】。')
    else:
        lines.append('急跌證據：上游僅提供公式TRUE，尚缺D1～D3／A1～A8逐票明細。')
    pivot = _price(report.get('daily_confirmed_swing_low'))
    pivot_day = report.get('daily_confirmed_swing_session')
    if pivot and close and isinstance(pivot_day, str) and float(close) < float(pivot):
        lines.append(
            f'確認前低：{pivot_day} {pivot}{unit}；'
            f'本次收盤低於前低{float(pivot)-float(close):.2f}{unit}。')
    return lines


def compose(report, json_body):
    """Return (subject, body); append unmodified canonical JSON after a stable marker."""
    rows = _rows(report)
    stamp = report.get('generated_at') or report.get('observed_at')
    at = _date(stamp)
    # Production sends only qualified original daily-risk observations. Keep
    # the generic formatter for historical/tests/legacy recipients.
    if report.get('schema') == 'LW_MARKET_NOTICE_V1' and (
            str(report.get('event_id','')).startswith('rd-daily-action-v1:')
            and report.get('rd_observation') == 'TRUE'
            and report.get('monitor_status') == 'ACTIVE_OBSERVATION_NOT_BUY'
            and isinstance(report.get('daily_session'), str)):
        symbol = _label(report.get('symbol'))
        day = report['daily_session']
        subject = f'[V82-WATCH] {symbol}｜日線急跌警戒已觸發｜請檢查買單｜{_tw(stamp)}'
        lines = [
            f'⚠️ {symbol}：{day} 已完成日線觸發急跌警戒（觀察級）',
            f'已完成：{day} 收盤日線的原核准急跌公式檢查，結果成立。',
            *_daily_risk_lines(report, day),
            f'現在請做：核對{symbol}未成交買單的限價、股數、GTC效期及預留資金，優先檢查可能自動成交的長效單。',
            f'新單建議：先暫緩新增{symbol}買單；原單撤改與加碼時機，依最新版V82完整安全／估值／資金報告決定。',
            '已有部位：先依原持有策略觀察；本郵件不單獨產生賣出或下單授權。',
        ]
        valid, reference_note = _row_status(report, at)
        if valid:
            lines.append('獨立盤中行情：' + reference_note + '；與上述正式日線日期分開。')
        elif report.get('data_status') == 'OLD_OBSERVATION_NOT_CURRENT':
            lines.append('額外報價：' + reference_note + '；這是舊值，請勿拿來設定現在的限價。')
        lines.extend([
            f'檢查時間：{_tw(stamp)}（台灣時間）；日線資料日期：{day}',
            '原始證據：' + str(report.get('run_url') or 'GitHub執行紀錄'),
            '本通知是原核准日線的來源觀測；正式V82與券商委託另行核對。',
            '',
            JSON_MARKER,
            json_body,
        ])
        return subject, '\n'.join(lines)
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

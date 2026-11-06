"""Quote validated financial outputs into the existing eight report chapters.

No market access, strategy, valuation, funding, order or ledger computation.
Every displayed value carries its original JSON pointer/value alongside the
readable text. The original result and explicitly supplied chapter envelopes
remain separate from these display-only, partial source-review quotations.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

SECTIONS = ("bond", "market", "radar", "valuation", "actions", "risks", "education", "institutions")
MISSING = object()


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(ok, code):
    if not ok:
        raise ValueError(code)


def _time(value):
    require(isinstance(value, str), "W6_FINANCIAL_SOURCE_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("W6_FINANCIAL_SOURCE_TIME") from None
    # Source observation dates may be date-only; availability must carry time.
    if len(value) == 10:
        parsed = parsed.replace(tzinfo=timezone.utc)
    require(parsed.tzinfo is not None, "W6_FINANCIAL_SOURCE_TIME")
    return parsed


def _check_dates(value, cutoff):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("available_at", "provider_verified_at", "source_as_of", "lastVerifiedAt",
                       "observed_date", "completed_session_close_at", "dataDate", "as_of") and child:
                if key in ("available_at", "provider_verified_at", "source_as_of", "lastVerifiedAt"):
                    require(isinstance(child, str) and len(child) > 10, "W6_FINANCIAL_SOURCE_TIME")
                require(_time(child) <= cutoff, "W6_FINANCIAL_FUTURE_SOURCE")
            _check_dates(child, cutoff)
    elif isinstance(value, list):
        for child in value:
            _check_dates(child, cutoff)


def validate_coverage(result, source, request):
    """Validate identities/counts/digests, never financial eligibility."""
    coverage = result.get("all_asset_coverage")
    if coverage is None:
        return  # Older accepted member receipts have no all-asset sidecar.
    require(isinstance(coverage, dict)
            and coverage.get("schema_version") == "Family.W8.AllAssetCoverage.v1", "W6_ALL_ASSET_SCHEMA")
    require(coverage.get("client_id") == source["client_id"]
            and coverage.get("source_db_sha256") == source["source_db_sha256"]
            and coverage.get("evaluation_at") == request["evaluation_at"], "W6_ALL_ASSET_BINDING")
    require(coverage.get("coverage_digest") == digest(
        {k: v for k, v in coverage.items() if k != "coverage_digest"}), "W6_ALL_ASSET_DIGEST")
    require(coverage.get("financial_completeness_asserted") is False
            and coverage.get("database_written") is False
            and coverage.get("trade_action") == "NO_TRADE"
            and type(coverage.get("coverage_complete")) is bool, "W6_ALL_ASSET_REVIEW_SCOPE")
    def clients(value):
        if isinstance(value, dict):
            if "client_id" in value:
                require(value["client_id"] == source["client_id"], "W6_ALL_ASSET_NESTED_CLIENT")
            for child in value.values():
                clients(child)
        elif isinstance(value, list):
            for child in value:
                clients(child)
    clients(coverage)
    for key in ("expected", "observed", "missing", "excluded", "equity_symbols", "bonds", "cash_accounts"):
        require(isinstance(coverage.get(key), list), "W6_ALL_ASSET_COVERAGE")
    for key in ("expected", "observed", "missing", "equity_symbols"):
        items = coverage[key]
        require(all(isinstance(x, str) and x for x in items)
                and len(set(items)) == len(items), "W6_ALL_ASSET_COVERAGE")
    expected, observed = set(coverage["expected"]), set(coverage["observed"])
    require(observed <= expected and set(coverage["missing"]) == expected - observed,
            "W6_ALL_ASSET_COVERAGE")
    bonds = coverage["bonds"]
    require(all(isinstance(b, dict) and b.get("route") == "V75"
                and b.get("trade_action") == "NO_TRADE"
                and b.get("full_financial_complete") is False
                and b.get("result_digest") == digest({k: v for k, v in b.items() if k != "result_digest"})
                for b in bonds), "W6_ALL_ASSET_BOND_DIGEST")
    bond_symbols = [b.get("symbol") for b in bonds]
    equity = set(coverage["equity_symbols"])
    require(len(set(bond_symbols)) == len(bond_symbols) and not equity.intersection(bond_symbols)
            and set(coverage["observed"]) == equity.union(bond_symbols)
            and equity == {x["symbol"] for x in result["positions"]}, "W6_ALL_ASSET_ROUTES")
    denominators = coverage.get("denominators", {})
    for key, count in (("securities", len(expected)), ("equity", len(equity)),
                       ("bonds", len(bonds)), ("cash_accounts", len(coverage["cash_accounts"]))):
        require(type(denominators.get(key)) is int and denominators[key] == count,
                "W6_ALL_ASSET_DENOMINATOR")
    require(not coverage["coverage_complete"] or (not coverage["missing"] and not coverage["excluded"]),
            "W6_ALL_ASSET_COVERAGE")
    accounts = [x.get("account_key") for x in coverage["cash_accounts"]]
    require(len(set(accounts)) == len(accounts) and all(a in source["source_account_keys"] for a in accounts),
            "W6_ALL_ASSET_ACCOUNT")
    _check_dates(coverage, _time(request["evaluation_at"]))


def _get(value, pointer):
    for part in pointer.strip("/").split("/"):
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return MISSING
    return value


def _text(value):
    if value is MISSING or value is None:
        return "UNKNOWN"
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


REASON_TEXT = {
    "OWN_RAW_PRICE_CALENDAR_AND_EVENT_COVERAGE_SOURCE_UNAVAILABLE": "缺已核實原價、交易日曆與事件覆蓋來源",
    "OWN_METRIC_COMPARABLE_PIT_HISTORY_SOURCE_UNAVAILABLE": "缺可比較的自身估值歷史及時點來源",
    "DATA_INSUFFICIENCY": "來源尚未齊全",
}
FIELD_TEXT = {
    "canonical_target_rate": "原正式目標比例", "approved_project_target_amount": "核准投資池金額",
    "canonical_valuation_price_identity_and_validity": "價格身分與有效性",
    "active_orders_and_fill_reconciliation": "委託及成交核對",
}


def _fact_text(fact):
    value = fact["value"] if fact["present"] else MISSING
    if fact["pointer"].endswith("/reason_codes") and isinstance(value, list):
        return "、".join(REASON_TEXT.get(code, str(code)) for code in value) or "[]"
    if fact["pointer"].endswith(("/missing_fields", "/stage_required_unknown_fields")) and isinstance(value, list):
        return "、".join(FIELD_TEXT.get(code, str(code)) for code in value) or "[]"
    if value == "NOT_RUN_REQUIRED_INPUTS_UNRESOLVED":
        return "待相依輸入，原計算未執行"
    return _text(value)


def _holding_fields(base, holdings):
    fields = []
    for index, holding in enumerate(holdings):
        pointer = base + f"/{index}"
        fields.extend([(f"來源{index + 1}帳戶／券商", pointer + ("/account_key" if holding.get("account_key") else "/broker_label")),
                       (f"來源{index + 1}數量", pointer + "/quantity"),
                       (f"來源{index + 1}幣別", pointer + "/currency")])
        if holding.get("observed_at"):
            fields.append((f"來源{index + 1}觀察日期", pointer + "/observed_at"))
        elif holding.get("received_at"):
            fields.append((f"來源{index + 1}可得日期（非觀察日）", pointer + "/received_at"))
    return fields


class _Quotes:
    def __init__(self, result, request, producer):
        self.data = {"result": result, "request": request}
        self.producer = producer
        self.rows = {name: [] for name in SECTIONS}
        self.field_map = {name: [] for name in SECTIONS}

    def add(self, section, heading, fields=(), *, note="", reference=None):
        # Split long lists into independent cards; no data/source truncation.
        facts = []
        for label, pointer in fields:
            value = _get(self.data, pointer)
            facts.append({"label": label, "pointer": pointer, "present": value is not MISSING,
                          "value": None if value is MISSING else deepcopy(value)})
        groups, group, size = [], [], 0
        for fact in facts:
            length = len(fact["label"]) + len(_fact_text(fact))
            if group and size + length > 440:
                groups.append(group); group, size = [], 0
            group.append(fact); size += length
        groups.append(group)
        for index, part in enumerate(groups):
            body = "；".join(x["label"] + "：" + _fact_text(x) for x in part)
            if note:
                body += ("。" if body else "") + note
            ref = reference or self.producer["source_id"]
            self.rows[section].append({"heading": heading + (f"（續{index + 1}）" if index else ""),
                "body": body, "source_reference": ref, "quoted_fields": deepcopy(part),
                "source_result_sha256": digest(self.data["result"])})
            self.field_map[section].extend(deepcopy(part))

    def compact_rows(self, section, rows, *, note):
        """Group labelled rows; preserve order/values, never total amounts."""
        batch, body_parts, size = [], [], 0
        def save():
            if not batch:
                return
            facts = []
            for symbol, fields in batch:
                for label, pointer in fields:
                    value = _get(self.data, pointer)
                    facts.append({"label": label, "pointer": pointer, "present": value is not MISSING,
                                  "value": None if value is MISSING else deepcopy(value)})
            self.rows[section].append({"heading": "原逐檔資料｜" + "、".join(x[0] for x in batch),
                "body": "。".join(body_parts) + "。" + note,
                "source_reference": self.producer["source_id"], "quoted_fields": deepcopy(facts),
                "source_result_sha256": digest(self.data["result"])})
            self.field_map[section].extend(deepcopy(facts))
        for symbol, fields in rows:
            parts = []
            for label, pointer in fields:
                value = _get(self.data, pointer)
                fact = {"pointer": pointer, "value": None if value is MISSING else value, "present": value is not MISSING}
                short_label = label[len(symbol):] if label.startswith(symbol) else label
                parts.append(short_label + "：" + _fact_text(fact))
            text = symbol + "｜" + "；".join(parts)
            if batch and (len(batch) == 3 or size + len(text) > 580):
                save();batch, body_parts, size = [], [], 0
            batch.append((symbol, fields));body_parts.append(text);size += len(text)
        save()


def member_sections(source, request, original, producer):
    """Display projections of a previously validated, unchanged member result."""
    validate_coverage(original, source, request)
    q = _Quotes(original, request, producer)
    coverage = original.get("all_asset_coverage")
    cutoff = _time(request["evaluation_at"])
    for row in original["positions"]:
        _check_dates({k: row.get(k) for k in ("market", "macro_observations", "valuation_observations")}, cutoff)
    _check_dates(request.get("macro_snapshot", {}), cutoff)
    action_fields = []
    risk_fields = []
    for index, row in enumerate(original["positions"]):
        base = f"/result/positions/{index}"
        formal = base + "/formal_conclusion"
        approved = formal + "/approved_v10_analysis"
        label = row["symbol"]
        classification = (row.get("formal_conclusion") or {}).get("classification", {}).get("primary_class")
        price_fields = [
            ("持倉／目標範圍", base + "/coverage_basis"),
            ("原逐檔分析狀態", formal + "/status"), ("行情日期", base + "/market/observed_date"),
            ("來源預期已完成交易日", base + "/market/latest_expected_completed_session"),
            ("報價幣別", base + "/market/market_identity/currency"),
            ("來源收盤價", base + "/market/observed_close"), ("價格資格", base + "/market/formal_deployment_eligible"),
            ("MA20", base + "/market/numeric/ma20"), ("MA50", base + "/market/numeric/ma50"),
            ("KD K", base + "/market/numeric/kd_k_9_3"), ("KD D", base + "/market/numeric/kd_d_9_3_3"),
            ("RSI14", base + "/market/numeric/rsi14"),
            ("Right", formal + "/market_predicates/right"), ("Up", formal + "/market_predicates/runaway_up"),
            ("Left", formal + "/market_predicates/left"),
            ("底二條件原值", approved + "/left_stage_profile/eligible/2"),
            ("成熟度", base + "/daily_slice/maturity/state")]
        price_fields.extend(_holding_fields(base + "/holding/source_facts", row.get("holding", {}).get("source_facts", [])))
        q.add("valuation", label + "｜" + str(classification or "原分類未提供"), price_fields,
            note="價格與技術值為原日期觀察，保留來源資格；不代替合格投資池市值。",
            reference=row.get("market", {}).get("source_reference"))
        value_fields = [
            ("估值原結論", formal + "/valuation_validity/native_result/level"),
            ("qP", approved + "/qP/value"), ("qP狀態", approved + "/qP/status"),
            ("qP來源缺項", approved + "/qP/reason_codes"),
            ("qV", approved + "/qV/value"), ("qV狀態", approved + "/qV/status"),
            ("qV來源缺項", approved + "/qV/reason_codes"),
            ("depth", approved + "/qP/depth"), ("原選定模式", formal + "/selected_mode"),
            ("原正式階段", formal + "/formal_stage"), ("階段所缺欄位", formal + "/stage_required_unknown_fields")]
        value_references = [producer["source_id"]]
        for vi, metric in enumerate(row.get("valuation_observations") or []):
            pointer = base + f"/valuation_observations/{vi}"
            metric_label = str(metric.get("metric_name", "原估值觀察"))
            value_fields.extend([(metric_label + "來源數值", pointer + "/current"),
                (metric_label + "單位", pointer + "/unit"),
                (metric_label + "日期", pointer + "/source_row/dataDate"),
                (metric_label + "原分類", pointer + "/valuation_level")])
            if metric.get("source_reference") not in value_references and metric.get("source_reference"):
                value_references.append(metric["source_reference"])
        q.add("valuation", label + "｜估值位置與原階段", value_fields,
            note="當期估值觀察與歷史qV／價格qP分開；原階段未選定仍為UNKNOWN，估值有效性沿原資格。",
            reference="；".join(value_references))
        action_fields.append((label, [(label + "原新增金額", base + "/proposed_amount"),
            (label + "原目標比例", formal + "/canonical_target_rate"),
            (label + "原cap（非金額）", base + "/daily_slice/cap"),
            (label + "原買進資格", formal + "/buy_permission/value"),
            (label + "原資格原因", formal + "/buy_permission/reason_codes"),
            (label + "原缺口狀態", formal + "/deployment_gap/status"),
            (label + "缺口所缺欄位", formal + "/deployment_gap/missing_fields")]))
        risk_fields.append((label, [
            ("HardGate", base + "/core_observation/result/permission/hard_gate"),
            ("Down", base + "/core_observation/result/technical/runaway_down"),
            ("結構風險原等級", base + "/core_observation/result/structural_risk/risk_grade"),
            ("事件來源狀態", formal + "/event_coverage/status"),
            ("委託來源狀態", formal + "/order_source/status"),
            ("原分析完整度", base + "/data_complete")]))

    q.compact_rows("actions", action_fields,
        note="各標的原值分列，無金額加總；未有本人完整Work9／Mentor金額，UNKNOWN不填0，交易NONE。")
    q.compact_rows("risks", risk_fields,
        note="缺委託／資金只限制相依輸出；正式檢視頻率待原來源，未以缺值判安全。")

    if coverage is not None:
        q.add("radar", "全資產來源範圍與金融完整度", [
            ("證券", "/result/all_asset_coverage/denominators/securities"),
            ("股票／股票ETF", "/result/all_asset_coverage/denominators/equity"),
            ("V75債券", "/result/all_asset_coverage/denominators/bonds"),
            ("現金帳戶", "/result/all_asset_coverage/denominators/cash_accounts"),
            ("來源覆蓋完整", "/result/all_asset_coverage/coverage_complete"),
            ("完整金融已成立", "/result/all_asset_coverage/financial_completeness_asserted")],
            note="來源覆蓋與金融計算資格分列。未提供合格C四雷達，六軸分數維持UNKNOWN；沒有以股票筆數替代全資產分母。")
        for index, bond in enumerate(coverage["bonds"]):
            base = f"/result/all_asset_coverage/bonds/{index}"
            bond_fields = [
                ("持倉／目標範圍", base + "/coverage_basis"), ("行情日期", base + "/market/observed_date"),
                ("原收盤價", base + "/market/observed_close"),
                ("PRED-009原狀態", base + "/original_pred009/aggregate_state"),
                ("原評估資格", base + "/original_pred009/assessment_status"),
                ("技術日期", base + "/original_pred009/as_of"),
                ("原新鮮度", base + "/original_pred009/input_freshness_state"),
                ("完整V75金融資格", base + "/full_financial_complete")]
            bond_fields.extend(_holding_fields(base + "/holdings", bond.get("holdings", [])))
            q.add("bond", bond["symbol"] + "｜原V75技術條件", bond_fields,
                note="債券沿原V75條件，不套股票九階；技術可讀與完整買額資格分列。",
                reference=bond.get("market", {}).get("source_reference"))
            if bond.get("sgov_roles") is not None:
                q.add("bond", bond["symbol"] + "｜原SGOV角色紀錄", [
                    ("角色提案", base + "/sgov_roles/sgov_role_proposal"),
                    ("角色確認", base + "/sgov_roles/sgov_role_confirmation")],
                    note="實體持有、債券桶與子彈桶各按原角色紀錄顯示，沒有重分配。")
            for gi, gap in enumerate(bond.get("missing_inputs") or []):
                q.add("bond", bond["symbol"] + "｜相依缺項", [
                    ("欄位", base + f"/missing_inputs/{gi}/field"),
                    ("原因", base + f"/missing_inputs/{gi}/reason"),
                    ("影響", base + f"/missing_inputs/{gi}/affects")])
        for index, cash in enumerate(coverage["cash_accounts"]):
            base = f"/result/all_asset_coverage/cash_accounts/{index}"
            q.add("actions", "現金帳戶｜" + cash["account_key"], [
                ("帳戶原幣別", base + "/owner_candidate/currency"),
                ("原可用現金", base + "/available_cash"),
                ("缺綁定欄位", base + "/missing_binding_fields"),
                ("所需來源", base + "/missing_inputs")],
                note="逐帳戶原值，不把buying power或歷史現金改作已結算可部署資金。")
            for oi, observation in enumerate(cash.get("cash_observations") or []):
                pointer = base + f"/cash_observations/{oi}"
                q.add("actions", "現金原件｜" + cash["account_key"], [
                    ("資料日期", pointer + "/as_of"), ("幣別", pointer + "/currency"),
                    ("原申報現金", pointer + "/amounts/reported_cash"),
                    ("原已結算現金", pointer + "/amounts/settled_cash"),
                    ("可用現金", pointer + "/available_cash"),
                    ("資金資格", pointer + "/qualified_funding")], reference=observation.get("source_reference"))

    macro = request.get("macro_snapshot", {}).get("payload", {})
    macro_groups = {}
    for key, indicator in macro.get("indicators", {}).items():
        if not isinstance(indicator, dict) or "value" not in indicator:
            continue
        macro_groups.setdefault(indicator.get("source") or producer["source_id"], []).append(key)
    for reference, keys in macro_groups.items():
        for start in range(0, len(keys), 3):
            batch = keys[start:start + 3]
            fields = []
            for key in batch:
                pointer = "/request/macro_snapshot/payload/indicators/" + key
                fields.extend([(key + "原值", pointer + "/value"), (key + "單位", pointer + "/unit"),
                    (key + "日期", pointer + "/dataDate"), (key + "查核狀態", pointer + "/status")])
                if macro["indicators"][key].get("detail"):
                    fields.append((key + "口徑", pointer + "/detail"))
            q.add("institutions", "原總經資料｜" + "、".join(batch), fields,
                note="原件觀察，未新增機構預測。", reference=reference)
    if original["positions"]:
        base = "/result/positions/0/macro_observations"
        for key, label in (("hy_oas", "HY OAS"), ("vix", "VIX"), ("move", "MOVE")):
            q.add("market", label + "｜當次原觀察", [
                ("原值", base + "/observed/" + key + "/value"),
                ("單位", base + "/observed/" + key + "/unit"),
                ("觀察日期", base + "/observed/" + key + "/as_of"),
                ("原方向", base + "/observed/" + key + "/direction"),
                ("原速度", base + "/observed/" + key + "/speed"),
                ("原新鮮度", base + "/observed/" + key + "/freshness")])
        q.add("market", "原信用狀態與市場情境範圍", [
            ("C1", base + "/credit/C1"), ("C2", base + "/credit/C2"),
            ("C3", base + "/credit/C3"), ("原風險級別", base + "/credit/risk_level"),
            ("完整安全來源", base + "/full_safety_contract_complete"),
            ("原待補輸入", base + "/remaining_inputs")],
            note="半年／三年正式情境結果尚未提供，沒有用新聞或單點指標補機率。")
    q.add("education", "讀取本次指標的範圍", note=
          "原價格／技術、當期估值、歷史qV與價格qP分欄；來源未提供時標UNKNOWN。條件TRUE與原正式選定模式／階段分開，未將單一條件當作已選定階段。這是本次原欄位閱讀說明，正式教材來源另待提供。")
    q.add("education", "資料缺項如何影響結果", note=
          "各章保留已取得的原觀察；現金、同輪C與Work9／Mentor缺項只限制相依的金額、漂移或雷達，不抹去既有技術／估值。N/A、UNKNOWN與原資料日期依來源分列；沒有新增買進門檻。")
    gaps = {
        "bond": "缺原V75金融輸入，完整買額待原來源；已知債券技術條件照列。",
        "market": "缺正式半年／三年情境結果；原總經觀察與來源日期仍可查閱。",
        "radar": "缺本人同輪C canonical_snapshot，四雷達六軸分數UNKNOWN；未以其他分數替代。",
        "valuation": "缺已綁定逐檔估值結果；既有來源與目標保留，未補qP／qV／價格。",
        "actions": "缺本人同輪原Work9／Mentor，新增金額與順序待原結果；交易授權NONE。",
        "risks": "缺正式風險結果與檢視頻率來源；不把缺資料當作安全。",
        "institutions": "缺正式機構研究／總經章節原件，沒有代擬預測。"}
    for section in SECTIONS:
        if not q.rows[section]:
            q.add(section, "本章來源與相依缺項", note=gaps.get(section, "正式教材來源待提供。"))
    rules_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    envelopes = {name: {"client_id": source["client_id"], "run_id": request["run_id"],
        "section": name, "value_state": "PARTIAL", "scope": "原結果節錄；逐欄原日期見內文",
        "source_id": producer["source_id"] + ":DISPLAY:" + name, "rules_sha": rules_sha,
        "upstream_rules_sha": producer["rules_sha"], "as_of": request["evaluation_at"],
        "payload": q.rows[name], "payload_sha256": digest(q.rows[name])} for name in SECTIONS}
    summary = None if coverage is None else {key: deepcopy(coverage[key]) for key in (
        "expected", "observed", "missing", "excluded", "denominators", "coverage_complete",
        "financial_completeness_asserted", "coverage_digest")}
    return {"envelopes": envelopes, "coverage_summary": summary,
            "projection": {"schema_version": "Family.W8.FinancialSectionDisplay.v1", "rules_sha": rules_sha,
                "upstream_rules_sha": producer["rules_sha"], "source_result_sha256": digest(original),
                "quoted_fields": q.field_map, "financial_completeness_asserted": False}}

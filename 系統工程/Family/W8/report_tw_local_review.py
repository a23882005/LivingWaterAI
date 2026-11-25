"""Quote the original same-run TW account outputs without running V75."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

spec = importlib.util.spec_from_file_location("tw_report_common", Path(__file__).with_name("report_canonical_adapter.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def validate(source, request, result):
    t = result.get("tw_local_bond_analysis")
    if t is None:
        return None
    owner = t.get("owner", {}) if isinstance(t, dict) else {}
    A.require(isinstance(t, dict) and t.get("schema_version") == "Family.W8.TWLocalBondAnalysis.v1"
              and t.get("run_id") == request["run_id"] and t.get("evaluation_at") == request["evaluation_at"]
              and t.get("source_db_sha256") == source["source_db_sha256"]
              and owner.get("client_id") == source["client_id"] and owner.get("currency") == "TWD"
              and owner.get("funding_domain") == "TW_LOCAL_BROKER"
              and owner.get("account") in source["source_account_keys"], "W6_TW_LOCAL_SOURCE_BINDING")
    tables = request["client_snapshot"]["payload"]["tables"]
    accounts = [x for x in tables["portfolio_account"] if x["account_key"] == owner["account"]]
    binding = t.get("account_binding", {})
    scope = binding.get("approved_document_category_scope", {})
    A.require(len(accounts) == 1 and binding.get("owner") == scope.get("owner") == owner
              and binding.get("source_rows") == accounts and scope.get("original_account_row") == accounts[0]
              and scope.get("source_snapshot_digest") == source["snapshot_payload_sha256"]
              and scope.get("trade_authorization") == t.get("trade_authorization") == "NONE"
              and t.get("trade_action") == "NO_TRADE"
              and any(x.get("client_id") == source["client_id"] and x.get("account_key") == owner["account"]
                      and x.get("broker_key") == owner.get("broker") for x in tables.get("account_broker_link", [])),
              "W6_TW_LOCAL_ACCOUNT_BINDING")
    A.require(t.get("native_validation", {}).get("state") == "ACCEPT"
              and t["native_validation"].get("accepted") is True, "W6_TW_LOCAL_NATIVE_VALIDATION")
    native = t.get("native_input", {})
    A.require(all(native.get(k) == value for k, value in (
        ("client_ref", source["client_id"]), ("run_id", request["run_id"]),
        ("analysis_timestamp", request["evaluation_at"]), ("broker_account_id", owner["account"]),
        ("broker_domain_type", owner["funding_domain"]), ("currency", owner["currency"]))),
        "W6_TW_LOCAL_NATIVE_INPUT_BINDING")
    positions, market = t.get("registered_positions"), t.get("market")
    A.require(isinstance(positions, dict) and bool(positions) and isinstance(market, dict)
              and set(positions) == set(market), "W6_TW_LOCAL_POSITION_COVERAGE")
    instruments = {x["instrument_key"]: x for x in tables["portfolio_instrument"]}
    for symbol, row in positions.items():
        raw = row.get("source_row", {})
        A.require(raw in tables["portfolio_position"] and raw.get("client_id") == source["client_id"]
                  and raw.get("account_key") == row.get("account_key") == owner["account"]
                  and raw.get("instrument_key") == row.get("instrument_key")
                  and instruments.get(row["instrument_key"], {}).get("ticker") == row.get("symbol") == symbol
                  and raw.get("quantity_decimal") == row.get("quantity")
                  and raw.get("as_of_utc") == row.get("observed_at")
                  and row.get("currency") == instruments[row["instrument_key"]].get("quote_currency") == "TWD",
                  "W6_TW_LOCAL_REGISTERED_POSITION_BINDING")
        quote = market[symbol]
        A.require(quote.get("currency") == "TWD" and quote.get("exchange") == "TPEX"
                  and quote.get("observed_session") == quote.get("expected_last_completed_session")
                  and quote.get("completed_price_is_current") is True
                  and type(quote.get("sessions")) is int and quote["sessions"] > 0
                  and A._number(quote.get("completed_close")) > 0
                  and quote.get("missing_calendar_sessions") == quote.get("extra_calendar_sessions") == []
                  and re.fullmatch(r"[0-9a-f]{64}", str(quote.get("calendar_sha256", "")))
                  and A._time(quote.get("market_available_at")) <= A._time(request["evaluation_at"])
                  and quote["observed_session"] <= request["evaluation_at"][:10], "W6_TW_LOCAL_MARKET_BINDING")
    w3 = t.get("work3", {})
    w5 = t.get("work5", {}).get("snapshot", {})
    output = w5.get("output", {})
    for value in (w3, w5, output):
        A.require(all(value.get(k) == expected for k, expected in (
            ("run_id", request["run_id"]), ("broker_account_id", owner["account"]), ("currency", "TWD"))),
            "W6_TW_LOCAL_WORK_BINDING")
    account_scope = output.get("bond_allocation_final", {}).get("account_scope", {})
    A.require(account_scope == {"broker_account_id": owner["account"],
              "broker_domain_type": owner["funding_domain"], "currency": "TWD"}, "W6_TW_LOCAL_WORK_BINDING")
    holdings = native.get("existing_bond_holdings", [])
    A.require(len(holdings) == len(positions) and {x.get("asset_id") for x in holdings} == set(positions)
              and all(x.get("broker_account_id") == owner["account"] and x.get("amount", {}).get("currency") == "TWD"
                      for x in holdings), "W6_TW_LOCAL_NATIVE_HOLDINGS_BINDING")
    for row in t.get("original_broker_rows", []):
        raw = row.get("source_row", {})
        originals = [x for values in tables.values() if isinstance(values, list) for x in values if x == raw]
        A.require(bool(originals) and raw.get("client_id") == source["client_id"]
                  and row.get("currency") == "TWD" and row.get("symbol") in positions,
                  "W6_TW_LOCAL_ORIGINAL_BROKER_SOURCE")
        try:
            original_rows = json.loads(raw.get("value_text", "null"))
        except (TypeError, ValueError):
            raise ValueError("W6_TW_LOCAL_ORIGINAL_BROKER_SOURCE") from None
        A.require(isinstance(original_rows, list) and any(isinstance(x, dict)
                  and x.get("symbol") == row.get("symbol") and x.get("broker_label") == row.get("broker_label")
                  and x.get("currency") == row.get("currency")
                  and A._number(x.get("quantity")) == A._number(row.get("quantity")) for x in original_rows),
                  "W6_TW_LOCAL_ORIGINAL_BROKER_QUANTITY")
        A.require(row.get("account_key") is None and row.get("account_mapping_state") == "UNKNOWN",
                  "W6_TW_LOCAL_UNMAPPED_BROKER_ROW")
    A.require(t.get("canonical_result") is None and t.get("formal_deployment_eligible") is False
              and output.get("formal_output_eligible") is False, "W6_TW_LOCAL_REVIEW_SCOPE_ONLY")
    return t


def quote_sections(q, t):
    if t is None:
        return
    root = "/result/tw_local_bond_analysis"
    q.add("bond", "當輪原生臺幣帳戶與原Work3／4／5", [
        ("當輪輪號", root + "/run_id"), ("當輪查核時間", root + "/evaluation_at"),
        ("原生帳戶", root + "/owner/account"), ("幣別", root + "/owner/currency"),
        ("原生驗證", root + "/native_validation/state"), ("原Work3狀態", root + "/work3/evaluation_state"),
        ("原Work4狀態", root + "/work4/status"), ("原Work5分類", root + "/work5/snapshot/final_classification"),
        ("原Work5閘門", root + "/work5/snapshot/gate_state"), ("本輪V70來源資格", root + "/v70_freshness/state")],
        note="這是本人原04同輪原生臺幣結果；各步驟資格依原值分列。僅涵蓋本人已登記券商類別，不宣稱帳戶現金或全倉已完整核實。")
    for symbol in t["registered_positions"]:
        p = root + "/registered_positions/" + symbol
        m = root + "/market/" + symbol
        gaps = t["work3"].get("gap_calculations", [])
        index = next((i for i, row in enumerate(gaps) if row.get("asset_id") == symbol), None)
        fields = [("已登記持股", p + "/quantity"), ("持股原日期", p + "/observed_at"),
            ("幣別", p + "/currency"), ("行情原日期", m + "/observed_session"),
            ("原收盤價", m + "/completed_close"), ("完成交易日數", m + "/sessions"),
            ("原成交量單位", m + "/volume_unit"),
            ("原技術分類", m + "/predicate_observations/PRED-009/original_result/aggregate_state"),
            ("原技術資格", m + "/predicate_observations/PRED-009/original_result/assessment_status"),
            ("原技術數值", m + "/predicate_observations/PRED-009/metrics"),
            ("個別判定輸入已驗新鮮度", m + "/predicate_observations/PRED-009/input_freshness_verified")]
        if index is not None:
            base = root + f"/work3/gap_calculations/{index}"
            fields += [("原Work3結構資格", base + "/eligibility_state"),
                ("原Work3目標金額", base + "/target_amount"), ("原Work3已計既有金額", base + "/eligible_existing_amount"),
                ("原Work3目標缺口", base + "/remaining_target_gap_amount")]
        q.add("bond", symbol + "｜當輪原生臺幣逐檔結果", fields,
            note="原Work3缺口0保留其結構範圍；它不是本檔核定新增金額或股數，後者仍待原Work5。")
        q.add("bond", symbol + "｜當輪原Work4判定與缺項", [
            ("原判定與各項缺資料", root + "/work4/predicate_source_gaps/" + symbol)],
            note="只引用原生判定，不重跑、補算或替換V75輸入。")
    for index, row in enumerate(t.get("original_broker_rows", [])):
        base = root + f"/original_broker_rows/{index}"
        q.add("bond", row["symbol"] + "｜另一來源券商原列（歷史參考）", [
            ("原券商標籤", base + "/broker_label"), ("原列數量", base + "/quantity"),
            ("幣別", base + "/currency"), ("原資料可得日期", base + "/received_at"),
            ("帳戶映射資格", base + "/account_mapping_state"), ("原來源輪號", base + "/source_run_id")],
            note="此列帳戶綁定仍待核；原券商各列保留，不併入本輪已登記帳戶或跨帳戶資金。")
    q.add("actions", "臺幣原Work5：待核金額與股數", [
        ("原逐檔決策", root + "/work5/snapshot/output/per_asset_decisions"),
        ("唯讀執行上限", root + "/native_input/bond_executable_budget"),
        ("帳戶實際現金", root + "/native_input/broker_cash_total"),
        ("可用現金", root + "/native_input/broker_cash_available"),
        ("原缺項", root + "/work4/missing"), ("正式金融輸出資格", root + "/formal_deployment_eligible")],
        note="原Work5尚無逐檔下單金額、股數，均UNKNOWN。唯讀上限0不表示實際現金為0，也不填成各檔建議買額0。")


def current_position_display(source, request, result, producer):
    """Prefer exact original04 holdings; retain DB rows separately as history."""
    rows = []
    for index, item in enumerate(result["analysis_result"]["positions"]):
        base = f"/result/analysis_result/positions/{index}"
        recommendation = item["current_analysis"].get("recommendation", {})
        fields = {"quantity": base + "/holding/quantity", "quantity_as_of": base + "/holding/observed_at",
            "currency": base + "/owner/currency", "reference_amount": base + "/current_analysis/recommendation/confirmed_position_amount",
            "reference_price_as_of": base + "/current_analysis/recommendation/price_date"}
        rows.append({"ticker": item["symbol"], "account": item["owner"]["account"],
            "quantity": item["holding"].get("quantity"), "quantity_as_of": item["holding"].get("observed_at"),
            "currency": item["owner"]["currency"], "reference_amount": recommendation.get("confirmed_position_amount"),
            "reference_price_as_of": recommendation.get("price_date"),
            "valuation_scope": recommendation.get("valuation_scope"), "source_pointers": fields,
            "source_reference": producer["source_id"] + "#" + base})
    t = result.get("tw_local_bond_analysis")
    if t is not None:
        holdings = t["native_input"]["existing_bond_holdings"]
        for symbol, item in t["registered_positions"].items():
            index = next(i for i, row in enumerate(holdings) if row["asset_id"] == symbol)
            base = "/result/tw_local_bond_analysis/registered_positions/" + symbol
            price = "/result/tw_local_bond_analysis/market/" + symbol
            amount = f"/result/tw_local_bond_analysis/native_input/existing_bond_holdings/{index}/amount/amount"
            rows.append({"ticker": symbol, "account": t["owner"]["account"], "quantity": item["quantity"],
                "quantity_as_of": item.get("observed_at"), "currency": item["currency"],
                "reference_amount": holdings[index]["amount"]["amount"], "reference_price_as_of": t["market"][symbol]["observed_session"],
                "valuation_scope": "ORIGINAL_TW_ACCOUNT_WORK3_REFERENCE__NOT_HOUSEHOLD_NAV",
                "source_pointers": {"quantity": base + "/quantity", "quantity_as_of": base + "/observed_at",
                    "currency": base + "/currency", "reference_amount": amount, "reference_price_as_of": price + "/observed_session"},
                "source_reference": producer["source_id"] + "#" + base})
    A.require(len({(r["account"], r["ticker"]) for r in rows}) == len(rows), "W6_CURRENT_HOLDINGS_DUPLICATE")
    return {"schema_version": "Family.W8.CurrentHoldingsDisplay.v1", "client_id": source["client_id"],
        "run_id": request["run_id"], "evaluation_at": request["evaluation_at"], "source_db_sha256": source["source_db_sha256"],
        "source_result_sha256": producer["result_sha256"], "positions": deepcopy(rows),
        "unknown_positions_omitted_as_current_zero": False, "household_NAV_asserted": False}

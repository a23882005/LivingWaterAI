"""Read-only quotations of the original account-scoped holdings report.

This receiver checks immutable source bindings, not financial calculations.
Earlier multi-account V75 observations remain separately labelled references.
The complete W5/C/Work9 canonical report route remains in the original adapter.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("report_canonical_adapter.py", "holdings_review_common_adapter")
Q = _load("report_financial_sections.py", "holdings_review_quotations")
TW = _load("report_tw_local_review.py", "holdings_review_tw")
STATES = ("ANALYSIS_COMPLETE", "ANALYSIS_PARTIAL", "ANALYSIS_BLOCKED")


class _ReviewQuotes(Q._Quotes):
    """Readable leaf quotations; raw facts and pointers remain lossless."""
    LABELS = {"account": "帳戶", "qty": "股數", "amount": "金額", "currency": "幣別",
        "status": "狀態", "value": "原值", "state": "原分類", "scope": "範圍",
        "ma20": "20日均線", "ma50": "50日均線", "ma200": "200日均線", "rsi14": "RSI14",
        "high_td9_setup": "TD高點計數", "low_td9_setup": "TD低點計數",
        "kd_k_9_3": "KD K", "kd_d_9_3_3": "KD D", "atr14": "ATR14",
        "macd_12_26": "MACD", "macd_signal_9": "MACD訊號", "macd_histogram": "MACD柱值"}

    def add(self, section, heading, fields=(), *, note="", reference=None):
        flat = []
        def leaves(label, pointer, value):
            if isinstance(value, dict) and value:
                for key, child in value.items():
                    leaves(label + "／" + self.LABELS.get(key, key), pointer + "/" + key, child)
            elif isinstance(value, list) and value:
                for index, child in enumerate(value):
                    leaves(label + "／原列" + str(index + 1), pointer + "/" + str(index), child)
            else:
                flat.append((label, pointer))
        for label, pointer in fields:
            leaves(label, pointer, Q._get(self.data, pointer))
        start = len(self.rows[section])
        super().add(section, heading, flat, note=note, reference=reference)
        # Latin identifiers may otherwise exceed the approved paragraph width.
        # Only display whitespace is inserted; quoted original types/values stay exact.
        for card in self.rows[section][start:]:
            card["body"] = re.sub(r"[A-Za-z0-9_./:-]{50,}",
                lambda m: " ".join(m[0][i:i + 40] for i in range(0, len(m[0]), 40)), card["body"])


def _bound(value, source, request):
    A.require(isinstance(value, dict) and all(value.get(k) == expected for k, expected in (
        ("client_id", source["client_id"]), ("run_id", request["run_id"]),
        ("owner", request["owner"]), ("source_db_sha256", source["source_db_sha256"]))),
        "W6_HOLDINGS_NESTED_BINDING")


def validate(source, request, result, producer):
    A.require(isinstance(request, dict) and request.get("schema_version") == "Family.W5.request.v1"
              and request.get("analysis_permission") == "ANALYZE_ONLY"
              and request.get("trade_authorization") == "NONE"
              and request.get("client_id") == source["client_id"]
              and isinstance(request.get("run_id"), str) and bool(request["run_id"]),
              "W6_HOLDINGS_REQUEST_REQUIRED")
    A._time(request.get("evaluation_at"))
    snap = request.get("client_snapshot", {}).get("payload", {})
    A.require(snap.get("client_id") == source["client_id"]
              and snap.get("source_sha256") == source["source_db_sha256"]
              and snap.get("payload_digest") == source["snapshot_payload_sha256"]
              and isinstance(snap.get("tables"), dict)
              and A.digest(snap["tables"]) == source["snapshot_payload_sha256"]
              and request["client_snapshot"].get("digest") == A.digest(snap),
              "W6_HOLDINGS_SNAPSHOT_BINDING")
    owner = request.get("owner", {})
    A.require(owner.get("client_id") == source["client_id"]
              and owner.get("account") in source["source_account_keys"]
              and all(isinstance(owner.get(k), str) and owner[k] for k in
                      ("broker", "currency", "funding_domain")), "W6_HOLDINGS_OWNER_ACCOUNT")
    accounts = snap["tables"].get("portfolio_account", [])
    A.require(any(x.get("account_key") == owner["account"] and x.get("client_id") == source["client_id"]
                  and x.get("account_currency") in (None, owner["currency"]) for x in accounts),
              "W6_HOLDINGS_OWNER_ACCOUNT")
    A.require(isinstance(result, dict) and result.get("schema_version") == "Family.W8.HoldingsAnalysisReport.v1"
              and result.get("status") in STATES, "W6_HOLDINGS_ANALYSIS_REQUIRED")
    _bound(result, source, request)
    A.require(result.get("request_digest") == A.digest(request)
              and result.get("snapshot_digest") == A.digest(snap)
              and result.get("source_sha256", source["source_db_sha256"]) == source["source_db_sha256"]
              and result.get("report_digest") == A.digest({k: v for k, v in result.items()
                        if k not in ("report_digest", "source_sha256")}), "W6_HOLDINGS_RESULT_DIGEST")
    A.require(isinstance(producer, dict) and isinstance(producer.get("source_id"), str)
              and bool(producer["source_id"].strip())
              and re.fullmatch(r"[0-9a-f]{64}", str(producer.get("rules_sha", "")))
              and producer.get("result_sha256") == A.digest(result), "W6_HOLDINGS_PRODUCER_RECEIPT")
    deployment = result.get("deployment_status", {})
    A.require(result.get("source_data_provenance") == "SOURCE_BACKED"
              and result.get("canonical_result") is None
              and deployment.get("full_native_canonical_complete") is False
              and result.get("trade_authorization") == "NONE" and result.get("trade_action") == "NO_TRADE",
              "W6_HOLDINGS_REVIEW_SCOPE_ONLY")
    analysis = result.get("analysis_result", {})
    rows = analysis.get("positions")
    A.require(isinstance(rows, list) and bool(rows)
              and isinstance(analysis.get("scope"), str) and bool(analysis["scope"])
              and analysis.get("coverage", {}).get("requested") == len(rows)
              == analysis["coverage"].get("returned")
              and len({x.get("instrument_id") for x in rows}) == len(rows), "W6_HOLDINGS_COVERAGE")
    for row in rows:
        delivery = row.get("current_analysis", {})
        A.require(isinstance(row.get("symbol"), str) and bool(row["symbol"])
                  and row.get("owner") == owner and row.get("status") in STATES
                  and delivery.get("owner") == owner and delivery.get("symbol") == row["symbol"]
                  and delivery.get("holding") == row.get("holding")
                  and delivery.get("delivery_digest") == A.digest({k: v for k, v in delivery.items()
                                                                   if k != "delivery_digest"}),
                  "W6_HOLDINGS_ITEM_BINDING")
        Q._check_dates(row.get("holding", {}), A._time(request["evaluation_at"]))
        for key in ("observed_at", "received_at"):
            value = row.get("holding", {}).get(key)
            if value is not None:
                A.require(A._time(value) <= A._time(request["evaluation_at"]), "W6_HOLDINGS_FUTURE_SOURCE")
        Q._check_dates(row.get("market", {}), A._time(request["evaluation_at"]))
    wreq, work9, mentor = (result.get(k) for k in ("work9_request", "work9_result", "mentor"))
    for value in (wreq, work9, mentor):
        _bound(value, source, request)
    A.require(wreq.get("request_digest") == result["request_digest"]
              and wreq.get("positions") == [{"instrument_id": x["instrument_id"],
                    "native_component_delivery": x["current_analysis"]} for x in rows]
              and work9.get("source_request_digest") == A.digest(wreq)
              and work9.get("request_digest") == result["request_digest"]
              and work9.get("result_digest") == A.digest({k: v for k, v in work9.items() if k != "result_digest"})
              and work9.get("full_canonical_deployment_complete") is False
              and work9.get("trade_action") == "NO_TRADE"
              and mentor.get("source_result_digest") == A.digest(work9)
              and mentor.get("full_native_deployment_mentor") is False
              and mentor.get("broker_execution_allowed") is False
              and mentor.get("production") == "HOLD" and mentor.get("trade_action") == "NO_TRADE",
              "W6_HOLDINGS_WORK9_MENTOR_BINDING")
    items = work9.get("items", [])
    A.require(len(items) == len(rows) and all(item.get("item_id") == row["instrument_id"]
              and item.get("asset_id") == row["symbol"]
              and item.get("native_component_delivery") == row["current_analysis"]
              for item, row in zip(items, rows)), "W6_HOLDINGS_WORK9_ITEM_BINDING")
    mentor_items = mentor.get("items", [])
    A.require(len(mentor_items) == len(items) and all(x.get("item_id") == y.get("item_id")
              and x.get("asset_id") == y.get("asset_id") and x.get("source_result_digest") == work9["result_digest"]
              for x, y in zip(mentor_items, items)), "W6_HOLDINGS_MENTOR_ITEM_BINDING")
    broker = result.get("broker_readonly_source")
    if broker is not None:
        _bound(broker, source, request)
        A.require(broker.get("source_descriptor_digest") == request.get("broker_snapshot_source_digest")
                  and broker.get("database_written") is False and broker.get("trade_action") == "NO_TRADE",
                  "W6_HOLDINGS_BROKER_BINDING")
        A.require(A._time(broker.get("captured_at")) <= A._time(request["evaluation_at"]),
                  "W6_HOLDINGS_FUTURE_SOURCE")
    recommendation = result.get("recommendation_report", {})
    A.require(recommendation.get("client_id") == source["client_id"]
              and recommendation.get("run_id") == request["run_id"]
              and recommendation.get("positions_returned") == len(rows)
              and recommendation.get("full_native_deployment_complete") is False
              and recommendation.get("trade_action") == "NO_TRADE"
              and recommendation.get("digest") == A.digest({k: v for k, v in recommendation.items() if k != "digest"})
              and len(recommendation.get("rows", [])) == len(rows)
              and all(x.get("instrument_id") == y["instrument_id"] and x.get("symbol") == y["symbol"]
                      and x.get("quantity") == y["holding"].get("quantity")
                      for x, y in zip(recommendation["rows"], rows)), "W6_HOLDINGS_RECOMMENDATION_BINDING")
    A.require(result.get("manifest_digest") == A.digest(result.get("manifest")), "W6_HOLDINGS_MANIFEST_DIGEST")
    bond = result.get("native_bond_source")
    if bond is not None:
        _bound(bond, source, request)
        A.require(bond.get("canonical_result") is None and bond.get("full_native_canonical_complete") is False
                  and bond.get("trade_action") == "NO_TRADE", "W6_HOLDINGS_BOND_SCOPE")
        state = bond.get("structural_state", {})
        A.require(state.get("run_id") == request["run_id"]
                  and state.get("broker_account_id") == owner["account"]
                  and state.get("currency") == owner["currency"], "W6_HOLDINGS_BOND_BINDING")
    TW.validate(source, request, result)


def supplement_documents(sources, source, request):
    if sources is None:
        return {}
    A.require(isinstance(sources, dict) and set(sources) == {"raw", "structural"}, "W6_HOLDINGS_REVIEW_DOCUMENTS")
    docs = {}
    for name, receipt in sources.items():
        A.require(isinstance(receipt, dict) and isinstance(receipt.get("original_text"), str)
                  and sha256(receipt["original_text"].encode("utf-8")).hexdigest() == receipt.get("sha256")
                  and isinstance(receipt.get("source_id"), str) and bool(receipt["source_id"]),
                  "W6_HOLDINGS_REVIEW_DOCUMENT_SHA")
        try:
            docs[name] = json.loads(receipt["original_text"])
        except (ValueError, TypeError):
            raise ValueError("W6_HOLDINGS_REVIEW_DOCUMENT_JSON") from None
        A.require(isinstance(docs[name], dict), "W6_HOLDINGS_REVIEW_DOCUMENT_JSON")
    raw, structural = docs["raw"], docs["structural"]
    A.require(raw.get("client_id") == structural.get("member_client_id") == source["client_id"]
              and structural.get("source_db_sha256") == source["source_db_sha256"]
              and structural.get("parent_raw_run_id") == raw.get("run_id")
              and isinstance(raw.get("run_id"), str) and bool(raw["run_id"])
              and structural.get("source_sha256") == raw.get("source_pack_sha256")
              and re.fullmatch(r"[0-9a-f]{64}", str(raw.get("source_pack_sha256", "")))
              and raw.get("trade_authorization") == structural.get("trade_authorization") == "NONE"
              and raw.get("has_formal_buying_permission") is False
              and structural.get("formal_ledger_writable") is False,
              "W6_HOLDINGS_REVIEW_DOCUMENT_BINDING")
    A.require(A._time(raw.get("evaluation_at")) <= A._time(structural.get("actual_evaluation_at"))
              <= A._time(request["evaluation_at"]), "W6_HOLDINGS_REVIEW_DOCUMENT_TIME")
    positions, assets = raw.get("bond_positions"), structural.get("assets")
    A.require(isinstance(positions, dict) and bool(positions) and isinstance(assets, dict)
              and set(positions) == set(assets), "W6_HOLDINGS_REVIEW_DOCUMENT_COVERAGE")
    for symbol, observation in positions.items():
        asset = assets[symbol]
        A.require(isinstance(observation, dict) and isinstance(asset, dict)
                  and observation.get("symbol") == symbol
                  and observation.get("source_zip_sha256") == raw["source_pack_sha256"]
                  and observation.get("currency") == asset.get("valuation_currency")
                  and type(observation.get("rows")) is int and observation["rows"] > 0
                  and A._number(observation.get("last_close")) == A._number(asset.get("provider_close"))
                  and A._number(asset.get("total_quantity")) >= 0
                  and isinstance(asset.get("positions"), list)
                  and asset.get("normal_increment_amount") is None and asset.get("normal_increment_quantity") is None,
                  "W6_HOLDINGS_REVIEW_DOCUMENT_ITEM")
        holdings = asset["positions"]
        A.require(all(isinstance(x, dict) and isinstance(x.get("account"), str) and bool(x["account"])
                      and A._number(x.get("qty")) >= 0 for x in holdings)
                  and len({x["account"] for x in holdings}) == len(holdings)
                  and sum((A._number(x["qty"]) for x in holdings), A._number("0"))
                  == A._number(asset["total_quantity"]), "W6_HOLDINGS_REVIEW_POSITION_ROWS")
        Q._check_dates({"observed_date": observation.get("last")}, A._time(request["evaluation_at"]))
        Q._check_dates(observation.get("native_v75_predicates", {}), A._time(request["evaluation_at"]))
    return docs


def sections(source, request, result, producer, docs, sources):
    q = _ReviewQuotes(result, request, producer)
    q.data["supplement"] = docs
    tw = result.get("tw_local_bond_analysis")
    q.add("bond", "本輪債券資料範圍與資格", [("本人原04狀態", "/result/status"),
        ("原分析帳戶", "/request/owner/account"), ("帳戶幣別", "/request/owner/currency"),
        ("原04輪號", "/request/run_id"), ("原04查核時間", "/request/evaluation_at"),
        ("原帳戶涵蓋範圍", "/result/analysis_result/scope"),
        ("原V75狀態", "/result/native_bond_source/status"),
        ("V75原執行狀態", "/result/native_bond_source/native_runtime_attempt/status")],
        note="私人來源審閱；原帳戶結果與較早的跨帳戶參考分列。Work3結構可讀，不表示完整部署或買進許可。")
    bond = result.get("native_bond_source") or {}
    state = bond.get("structural_state", {})
    for index, gap in enumerate(state.get("gap_calculations", [])):
        base = f"/result/native_bond_source/structural_state/gap_calculations/{index}"
        q.add("bond", str(gap.get("asset_id")) + "｜本人原帳戶Work3", [
            ("目標金額", base + "/target_amount"), ("可計入既有金額", base + "/eligible_existing_amount"),
            ("原目標缺口", base + "/remaining_target_gap_amount"),
            ("原結構資格", base + "/eligibility_state"), ("原裁定理由", base + "/reason_codes")],
            note="原帳戶結構目標缺口；不是本輪核定買額或股數，不以缺口代替部署決策。")
    for index, row in enumerate(result["analysis_result"]["positions"]):
        if row["symbol"] not in bond.get("targets", {}) and row["instrument_id"] not in bond.get("requested_instruments", []):
            continue
        base = f"/result/analysis_result/positions/{index}"
        q.add("bond", row["symbol"] + "｜本人原04實持與行情", [
            ("原帳戶持股", base + "/holding/quantity"), ("持股來源日期", base + "/holding/observed_at"),
            ("原持股來源", base + "/holding/source_reference/source_reference"),
            ("原持股來源帳戶", base + "/holding/source_reference/account_key"),
            ("來源快照每股估值", base + "/holding/source_reference/broker_position/market_price"),
            ("來源快照持倉估值", base + "/holding/source_reference/broker_position/market_value"),
            ("來源快照幣別", base + "/holding/source_reference/broker_position/currency"),
            ("原行情日期", base + "/market/observed_date"), ("原行情數值", base + "/market/observed_close")],
            note="此為指定帳戶原04結果，與較早補充原件的估值及技術數值分開。")
        rec = result["recommendation_report"]["rows"][index]
        base = f"/result/recommendation_report/rows/{index}"
        q.add("actions", row["symbol"] + "｜原部署與新增額資格", [
            ("原模式", base + "/current_round_deployment_target/mode"),
            ("原階段", base + "/current_round_deployment_target/stage"),
            ("原階段金額", base + "/current_round_deployment_target/amount"),
            ("原階段金額幣別", base + "/current_round_deployment_target/currency"),
            ("原持股缺口", base + "/holding_gap_amount"),
            ("原既有資產調度金額", base + "/proposed_existing_asset_redeployment_amount"),
            ("原現金試算買額", base + "/native_cash_trial_buy_amount"),
            ("原新增外部資金買額", base + "/proposed_new_external_buy_amount"),
            ("新增外部資金幣別", base + "/new_external_currency")],
            note="未知保留UNKNOWN；原外部新增資金為0只表示該來源範圍，不將未知的既有資產買額或股數補0。")
    if docs:
        q.add("bond", "借用原件的時間與範圍", [("補充觀測輪號", "/supplement/raw/run_id"),
            ("補充觀測時間", "/supplement/raw/evaluation_at"),
            ("補充結構查核時間", "/supplement/structural/actual_evaluation_at"),
            ("補充結構資格", "/supplement/structural/status"),
            ("原來源包SHA256", "/supplement/raw/source_pack_sha256")],
            note="較早原件的參考引用；不冒充本輪原04的臺灣帳戶Work3/4/5或全戶金融結論。")
        for symbol, asset in docs["structural"]["assets"].items():
            if tw is not None and symbol in tw["registered_positions"]:
                continue  # The same-run native TW result is quoted below.
            base = "/supplement/structural/assets/" + symbol
            raw = "/supplement/raw/bond_positions/" + symbol
            ref = sources["structural"]["source_id"] + ":" + sources["structural"]["sha256"]
            q.add("bond", symbol + "｜補充實持／未持有目標與技術", [
                ("各券商實持原列", base + "/positions"), ("來源數量", base + "/total_quantity"),
                ("原報價日期", raw + "/last"), ("報價幣別", base + "/valuation_currency"),
                ("來源收盤價", base + "/provider_close"), ("參考估值原值", base + "/current_marked_value"),
                ("原結構資格", base + "/work3_structural_eligibility"),
                ("可新增長期目標", base + "/new_long_term_target_allowed"),
                ("原技術分類", base + "/v75_pred009/state"), ("完整金融資格", base + "/full_v75_financial_permission"),
                ("待核新增金額", base + "/normal_increment_amount"), ("待核新增股數", base + "/normal_increment_quantity")],
                reference=ref, note="補充原件參考；數量0是明示未持有，待核新增量仍UNKNOWN。兩券商各自保留，SGOV實體不重複計入角色桶。")
            q.add("bond", symbol + "｜補充技術原值與來源", [("日棒數", raw + "/rows"),
                ("原RSI／均線等數值", raw + "/native_numeric"), ("原TD數值", raw + "/native_td9"),
                ("原價來源檔", raw + "/source_file"), ("原價來源SHA256", raw + "/source_file_sha256"),
                ("原技術分類", raw + "/native_v75_predicates/PRED-009/original_result/aggregate_state"),
                ("原技術分類資格", raw + "/native_v75_predicates/PRED-009/original_result/assessment_status"),
                ("原技術分類時點", raw + "/native_v75_predicates/PRED-009/original_result/as_of")],
                reference=sources["raw"]["source_id"] + ":" + sources["raw"]["sha256"],
                note="來源數值逐欄引用，沒有重跑金融公式；原預設freshness不是來源完整性核准。")
    q.add("bond", "SGOV實體、債券桶與乾粉桶", [
        ("原債券桶金額", "/result/native_bond_source/structural_state/sgov_reconciliation/sgov_bond_bucket_amount"),
        ("原乾粉桶金額", "/result/native_bond_source/structural_state/sgov_reconciliation/sgov_dry_powder_bucket_amount"),
        ("原角色合計金額", "/result/native_bond_source/structural_state/sgov_reconciliation/observed_role_total_amount"),
        ("原角色分帳", "/result/native_bond_source/structural_state/sgov_reconciliation/roles_kept_separate")],
        note="依本人原角色分帳；實體持股只計一次，債券桶0不等於沒有SGOV，乾粉不是另加一筆實體或可動用現金。")
    q.add("risks", "本輪來源缺口與發布資格", [("原V70新鮮度", "/result/native_source_freshness/v70/state"),
        ("原V70來源日期", "/result/native_source_freshness/v70/feed_as_of"),
        ("原V70資格理由", "/result/native_source_freshness/v70/reason"),
        ("原完整部署狀態", "/result/deployment_status/full_native_canonical_complete"),
        ("V75原缺項", "/result/native_bond_source/native_runtime_attempt/issues"),
        ("交易授權", "/result/trade_authorization"), ("交易動作", "/result/trade_action")],
        note="正式完整金融報告仍需原C/Work9完整合格來源；私人來源審閱可保存已核事實，不能藉版型或附件齊全升格金融資格。")
    q.add("market", "本人原來源時點", [("原04查核時間", "/request/evaluation_at"),
        ("原市場來源資格", "/result/native_source_freshness/market/state"),
        ("來源時點不代表金融資格", "/result/native_source_freshness/market/source_recency_is_not_canonical_market_attestation")],
        note="非新的金融或總經計算。")
    TW.quote_sections(q, tw)
    for i, line in enumerate(request.get("confirmed_target", {}).get("payload", {}).get("draft", {}).get("target_lines", [])):
        if line.get("ticker") not in (docs.get("structural", {}).get("assets", {}) or bond.get("targets", {})):
            continue
        base = f"/request/confirmed_target/payload/draft/target_lines/{i}"
        q.add("bond", str(line.get("ticker")) + "｜原核准配置角色", [
            ("原標的／角色", base + "/instrument_id"), ("原核准比例", base + "/weight"),
            ("原核准金額", base + "/target_amount/amount"), ("核准幣別", base + "/target_amount/currency")],
            note="歷史核准長期配置；不代替本輪新增金額、股數或角色餘額。")
    envelopes = {name: {"client_id": source["client_id"], "run_id": request["run_id"], "section": name,
        "value_state": "PARTIAL", "scope": "ACCOUNT_HOLDINGS_REVIEW__SUPPLEMENT_DATES_SEPARATE",
        "source_id": producer["source_id"] + ":DISPLAY:" + name,
        "rules_sha": sha256(Path(__file__).read_bytes()).hexdigest(), "upstream_rules_sha": producer["rules_sha"],
        "as_of": request["evaluation_at"], "payload": rows, "payload_sha256": A.digest(rows)}
        for name, rows in q.rows.items() if rows}
    return envelopes, q.field_map


def make_inputs(source, request, result, *, source_id, rules_sha, review_sources=None):
    producer = {"source_id": source_id, "rules_sha": rules_sha, "result_sha256": A.digest(result)}
    validate(source, request, result, producer)
    supplement_documents(review_sources, source, request)
    binding = A.make_report_sources(source, request, result)
    binding.update(holdings_producer=producer, holdings_review_sources=deepcopy(review_sources))
    binding["digest"] = A.digest({k: v for k, v in binding.items() if k != "digest"})
    common = {"client_id": source["client_id"], "source_db_sha256": source["source_db_sha256"],
              "run_id": request["run_id"], "data_provenance": "SOURCE_BACKED"}
    return {"market": {**common, "verified": False, "valuation_state": "UNKNOWN",
        "market_as_of": request["evaluation_at"], "market_as_of_basis": "SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION"},
        "engine": {**common, "status": "ANALYSIS_PARTIAL", "evaluation_at": request["evaluation_at"],
                   "trade_authorization": "NONE", "report_sources": binding}}


def prepare_sources(source, market, engine, binding):
    A.require(binding["scope"] == "SOURCE_REVIEW" and binding.get("c7") is None
              and binding.get("target_context") is None and not binding.get("sections"),
              "W6_HOLDINGS_REVIEW_SCOPE_ONLY")
    request, result = binding["request"], binding["result"]
    A.require(request.get("run_id") == engine["run_id"] and request.get("evaluation_at") == engine["evaluation_at"],
              "W6_HOLDINGS_ENGINE_BINDING")
    producer = binding.get("holdings_producer")
    validate(source, request, result, producer)
    sources = binding.get("holdings_review_sources")
    docs = supplement_documents(sources, source, request)
    envelopes, fields = sections(source, request, result, producer, docs, sources)
    normalized, receipts = A._sections(envelopes, source, request["run_id"], A._time(request["evaluation_at"]))
    return {"scope": "SOURCE_REVIEW", "canonical": None, "radar": None, "sections": normalized,
        "current_position_display": TW.current_position_display(source, request, result, producer),
        "lineage": {"binding_sha256": binding["digest"], "sections": receipts,
            "holdings_analysis": deepcopy(result), "holdings_review_documents": deepcopy(docs),
            "request_sha256": A.digest(request), "result_sha256": A.digest(result),
            "holdings_producer": deepcopy(producer), "section_projection": {
                "schema_version": "Family.W8.HoldingsSectionDisplay.v1", "quoted_fields": fields,
                "source_result_sha256": A.digest(result), "financial_completeness_asserted": False,
                "private_source_review_eligible": True, "canonical_financial_report_eligible": False,
                "same_run_native_TW_present": result.get("tw_local_bond_analysis") is not None,
                "supplement_qualification": "EARLIER_REFERENCE_ONLY__NOT_SAME_RUN_ACCOUNT_FINANCIAL_OUTPUT",
                "document_receipts": {k: {x: v[x] for x in ("source_id", "sha256")} for k, v in (sources or {}).items()}}}}

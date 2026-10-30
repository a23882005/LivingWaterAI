"""Entirely synthetic upstream OUTPUT shapes; no customer data or strategy run.

Values intentionally cover a protected stock, current-only and target-only
instruments, positive/negative/zero drift and zero new deployment (WAIT).
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

W8 = Path(__file__).resolve().parents[3]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, W8 / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("report_html_fixture_adapter", "report_canonical_adapter.py")
S = load("report_html_fixture_source", "formal_report_source.py")
D = load("report_html_fixture_data", "w6_current_data.py")
R = load("report_html_fixture_render", "w6_member_render.py")
CLIENT = "fam_" + "c" * 32
ASOF = "2026-10-29T20:00:00Z"
AT = "2026-10-30T00:00:00Z"
LABEL = "合成全球長期資產配置與風險觀察專用中文長名稱"
AXES = [
    ("BULL_EARLY", "牛市初期"), ("BULL_MID", "牛市中期"), ("BULL_LATE", "牛市末期"),
    ("BEAR_NON_RECESSION_VALUATION", "非衰退熊市／估值壓縮"),
    ("BEAR_RECESSION", "景氣衰退熊市"), ("FINANCIAL_LIQUIDITY_CRISIS", "金融／流動性危機")]


def case():
    tables = {
        "portfolio_account": [{"client_id": CLIENT, "account_key": "SYNTH_ACCOUNT"}],
        "portfolio_instrument": [{"client_id": CLIENT, "instrument_key": x,
                                  "ticker": x, "instrument_label": LABEL + x}
                                 for x in ("KEEP", "SELL", "BOTH", "NEW")],
        "portfolio_position": [{"client_id": CLIENT, "account_key": "SYNTH_ACCOUNT",
                                "instrument_key": x, "quantity_decimal": "1", "as_of_utc": ASOF}
                               for x in ("KEEP", "SELL", "BOTH")],
        "cash_balance_snapshot": [], "portfolio_snapshot_item": [],
        "final_target_version": [], "final_target_allocation": []}
    snapshot = {"schema_version": "Family.W5.W1Snapshot.v1", "client_id": CLIENT,
                "source_sha256": "a" * 64, "identity": {"client_id": CLIENT, "family_alias": "Arthur"},
                "payload_digest": A.digest(tables), "tables": tables}
    source = S.build_report_source(snapshot, account="AR", expected_client_id=CLIENT)
    owner = {"client_id": CLIENT, "account": "SYNTH_ACCOUNT", "broker": "SYNTH_BROKER",
             "currency": "TWD", "funding_domain": "SYNTH_POOL"}
    native_owner = {"account": "SYNTH_ACCOUNT", "broker": "SYNTH_BROKER", "funding_domain": "SYNTH_POOL"}
    weights = {"KEEP": .4, "BOTH": .4, "NEW": .2}
    draft = {"identity": {"client_id": CLIENT, "run_id": "synthetic-historical-signing"},
             "allocation_id": "SYNTH_FINAL_7", "target_lines": [
                 {"instrument_id": x, "ticker": x, "weight": {"value_state": "KNOWN", "value": w}}
                 for x, w in weights.items()]}
    draft["draft_hash"] = A.digest(draft)
    evidence = {"action": "CONFIRM", "client_explicit_decision": "TRUE", "confirmed_by": CLIENT,
                "confirmed_at": "2026-09-01T00:00:00Z", "source_reference_ids": ["SYNTHETIC_APPROVAL"]}
    record = {"version": 7, "status": "CONFIRMED", "draft": draft, "target_hash": draft["draft_hash"],
              "proposed_at": "2026-08-31T00:00:00Z", "expires_at": "2026-09-02T00:00:00Z",
              "confirmation_evidence": evidence, "confirmation_evidence_hash": A.digest(evidence),
              "source_reference_ids": ["SYNTHETIC_APPROVAL"]}
    target = {"payload": record, "target_version": 7, "target_hash": draft["draft_hash"],
              "confirmation_run_id": "synthetic-historical-signing"}
    context = {"client_id": CLIENT, "source_db_sha256": source["source_db_sha256"],
               "snapshot_payload_sha256": snapshot["payload_digest"], "run_id": "synthetic-report-7",
               "evaluation_at": AT, "source_id": "SYNTHETIC_W2_RECORD",
               "target_key": "MAIN", "expected_target_version": 7, "expected_target_hash": target["target_hash"]}
    identity = {"client_id": CLIENT, "run_id": "synthetic-report-7"}
    denominator = {"value_state": "KNOWN", "amount": 1000, "currency": "TWD", "as_of": ASOF}
    def positions(ws):
        return [{"instrument_id": x, "ticker": x, "label": LABEL + x,
                 "weight": {"value_state": "KNOWN", "value": w}} for x, w in ws.items()]
    current = {"allocation_id": "SYNTH_CURRENT", "stage": "CURRENT", "as_of": ASOF,
               "denominator": deepcopy(denominator), "positions": positions({"KEEP": .4, "SELL": .3, "BOTH": .3})}
    final = {"allocation_id": "SYNTH_FINAL_7", "stage": "FINAL_TARGET", "as_of": ASOF,
             "confirmation_status": "CONFIRMED", "confirmed_at": evidence["confirmed_at"],
             "confirmed_by": CLIENT, "source_reference_ids": ["SYNTHETIC_APPROVAL"],
             "denominator": deepcopy(denominator), "positions": positions(weights)}
    axes = [{"axis_id": x, "label_zh": y, "order": i + 1} for i, (x, y) in enumerate(AXES)]
    radar = {"as_of": AT, "axes": axes, "views": [
        {"view_id": key, "axes": [{**axis, "score": {"value_state": "KNOWN", "value": i + 1,
                                                  "source_reference_ids": ["SYNTHETIC_RADAR"]}}
                                  for i, axis in enumerate(axes)], "source_reference_ids": ["SYNTHETIC_RADAR"]}
        for key in ("CURRENT_ATTACK", "TARGET_ATTACK", "CURRENT_DEFENSE", "TARGET_DEFENSE")],
        "display_requirements": {k: True for k in ("same_six_axes_for_all_four_views",
            "same_axis_order_for_all_four_views", "six_chinese_labels_directly_visible",
            "missing_overlapped_or_unreadable_label_is_formal_report_qa_fail")}}
    drifts = []
    for x, cw, tw, delta, action in (("KEEP", .4, .4, 0, "HOLD_PROTECTED"),
                                    ("SELL", .3, 0, -.3, "DECREASE_TARGET_WEIGHT"),
                                    ("BOTH", .3, .4, .1, "INCREASE_TARGET_WEIGHT"),
                                    ("NEW", 0, .2, .2, "INCREASE_TARGET_WEIGHT")):
        drifts.append({"instrument_id": x, "ticker": x, "current_weight": {"value_state": "KNOWN", "value": cw},
                       "final_target_weight": {"value_state": "KNOWN", "value": tw},
                       "drift": {"value_state": "KNOWN", "value": delta},
                       "protected": x == "KEEP", "client_facing_action": action})
    drift = {"value_state": "KNOWN", "as_of": AT, "denominator": deepcopy(denominator),
             "items": drifts, "renderer_must_not_recompute_final_target": True, "reason": None}
    w6 = {"identity": identity, "work6_snapshot_id": "SYNTH_WORK6", "loop_status": "FINAL_TARGET_CONFIRMED",
          "confirmation_status": "CONFIRMED", "final_target": {"value_state": "KNOWN", "snapshot": final},
          "drift_snapshot": drift, "radar_snapshot": radar}
    framework = {"identity": identity, "status": "READY_FOR_PM_GATE", "parent_work6_snapshot_id": "SYNTH_WORK6",
                 "drift_snapshot": deepcopy(drift), "radar_snapshot": deepcopy(radar),
                 "report_contract": {k: True for k in ("renderer_must_not_recompute_final_target",
                    "renderer_must_use_work6_drift_snapshot", "renderer_must_use_work6_radar_snapshot")}}
    original = {"schema_version": "Family.W5.C7Source.v1", "family_owner": owner,
                "producer": "SYNTHETIC_C_OUTPUT_FIXTURE", "version": "1", "source_reference": "SYNTHETIC_C_WORK6_7",
                "evaluated_at": AT, "canonical_input": {"identity": identity, "allocations": {
                    "current_allocation": {"value_state": "KNOWN", "snapshot": current}}}, "work6_result": w6}
    c7 = {"original_source": original, "result": framework}
    request = {"schema_version": "Family.W5.request.v1", "client_id": CLIENT,
               "run_id": identity["run_id"], "request_id": "SYNTH_REQUEST_7", "evaluation_at": AT,
               "trade_authorization": "NONE", "owner": owner, "expected_versions": {"target": "7"},
               "client_snapshot": {"payload": snapshot, "digest": A.digest(snapshot)}, "confirmed_target": target,
               "native_bundle": {"asset_framework": deepcopy(framework), "stock_request": {"work3_handoff": {"owner": native_owner}}}}
    core = {"items": [{"item_id": "SYNTH_WAIT_" + x, "asset_id": x, "account_owner": native_owner,
                       "data_lineage": ["SYNTHETIC"], "rule_lineage": ["SYNTHETIC"],
                       "canonical_action": "WAIT", "deployment_amount": {"status": "KNOWN", "value": {"amount": "0", "currency": "TWD"}}}
                      for x in ("KEEP", "SELL", "BOTH", "NEW")]}
    ret = {"run_id": identity["run_id"], "owner": native_owner, "currency": "TWD",
           "canonical_deployment_result_sha256": A.digest(core), "item_ids": [x["item_id"] for x in core["items"]]}
    unified = {"run_id": identity["run_id"], "owner": native_owner, "currency": "TWD", "source_bindings": {
        "final_target_allocation_id": final["allocation_id"]}, "canonical_deployment_result": core,
        "canonical_deployment_result_sha256": A.digest(core), "mentor_return": ret}
    mentor = {"client_id": CLIENT, "run_id": identity["run_id"], "owner": native_owner, "currency": "TWD",
              "canonical_deployment_result": deepcopy(core), "canonical_deployment_result_sha256": A.digest(core),
              "source_result_digest": A.digest(unified), "source_bindings": deepcopy(unified["source_bindings"]),
              "mentor_return": deepcopy(ret), "execution_advice_allowed": False}
    result = {"schema_version": "Family.W5.result.v1", "status": "OK", "client_id": CLIENT,
              "run_id": identity["run_id"], "request_id": request["request_id"], "evaluation_at": AT,
              "owner": owner, "production": "HOLD", "trade_action": "NO_TRADE", "data_provenance": "SOURCE_BACKED",
              "mentor": mentor, "native_result": {"unified_result": unified, "family_sources": {"c7": c7}}}
    sections = {name: {"client_id": CLIENT, "run_id": identity["run_id"], "section": name, "value_state": "KNOWN",
                       "source_id": "SYNTHETIC_NAMED_PRODUCER:" + name, "rules_sha": "f" * 64,
                       "as_of": "2026-10-01T00:00:00Z", "payload": [
                           {"heading": "合成章節來源 " + name,
                            "body": "SYNTHETIC::" + name + "::完整內文。" + LABEL * 3,
                            "source_reference": "SYNTHETIC_CITATION:" + name}]}
                for name in A.SECTION_NAMES}
    market = {"client_id": CLIENT, "source_db_sha256": snapshot["source_sha256"], "run_id": identity["run_id"],
              "verified": True, "data_provenance": "SOURCE_BACKED", "market_as_of": ASOF,
              "included_cash_accounts": [], "fx_to_twd": {}, "position_values_twd": [
                  {"account_key": "SYNTH_ACCOUNT", "instrument_key": x, "market_value_twd": str(v),
                   "source_reference": "SYNTHETIC_CURRENT_VALUE", "data_provenance": "SOURCE_BACKED"}
                  for x, v in (("KEEP", 400), ("SELL", 300), ("BOTH", 300))]}
    engine = {"client_id": CLIENT, "source_db_sha256": snapshot["source_sha256"], "run_id": identity["run_id"],
              "evaluation_at": AT, "data_provenance": "SOURCE_BACKED", "status": "OK", "trade_authorization": "NONE"}
    c = {"snapshot": snapshot, "source": source, "request": request, "result": result, "c7": c7,
         "sections": sections, "target_context": context, "market": market, "engine": engine}
    refresh(c)
    return c


def refresh(c, *, scope="CANONICAL_CALCULATION", result=True, c7=True):
    for envelope in c["sections"].values():
        envelope["payload_sha256"] = A.digest(envelope.get("payload"))
    c["c7"]["source_digest"] = A.digest(c["c7"]["original_source"])
    c["request"]["c7_source_digest"] = c["c7"]["source_digest"]
    c["request"]["native_bundle"]["asset_framework"] = deepcopy(c["c7"]["result"])
    c["result"]["input_digest"] = A._runtime("report_receiver", "W6/runtime").input_digest(c["request"])
    c["engine"]["report_sources"] = A.make_report_sources(c["source"], c["request"], c["result"] if result else None,
        c7=c["c7"] if c7 else None, sections=c["sections"], target_context=c["target_context"], scope=scope)


def current(c=None):
    c = c or case()
    return D.build_w6_current_data(c["source"], c["market"], c["engine"])


def db_review_case():
    """Fresh DB facts, no analysis result and no verified market valuation."""
    c=case();c['sections']={}
    c['market'].update(verified=False,valuation_state='UNKNOWN',
        market_as_of=AT,market_as_of_basis='SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION')
    c['engine']['status']='DATA_UNAVAILABLE'
    refresh(c,scope='SOURCE_REVIEW',result=False,c7=False)
    return c


def long_reference_case():
    """Long unbroken URL/path/hash and Chinese punctuation, all invented."""
    c=case()
    reference=("https://synthetic.invalid/"+"UnbrokenReference"*14+
               "/frozen/source/result.json#"+"a1"*32+"；路徑／資料來源（完整保留）。")
    for name,envelope in c["sections"].items():
        envelope["payload"][0]["source_reference"]=reference+name
        envelope["scope"]="SYNTHETIC_LONG_REFERENCE_SCOPE"
    # A narrower radar card exercises the same wrapping style without making
    # the approved, indivisible four-panel grid exceed its page-height limit.
    c["c7"]["original_source"]["source_reference"]="RADARREFERENCE"*2
    refresh(c)
    return c


def member_case():
    c=case();snapshot=deepcopy(c["snapshot"])
    snapshot["tables"]["final_target_version"]=[{"client_id":CLIENT,"target_key":"MAIN",
        "version_no":7,"lifecycle_state":"CONFIRMED","completeness_state":"COMPLETE",
        "confirmed_at_utc":"2026-09-01T00:00:00Z","confirmation_source_ref":"SYNTHETIC_APPROVAL"}]
    snapshot["tables"]["final_target_allocation"]=[{"client_id":CLIENT,"target_key":"MAIN",
        "version_no":7,"instrument_key":x,"weight_units":w,"allocation_state":"ACCEPTED"}
        for x,w in (("KEEP",400000),("BOTH",400000),("NEW",200000))]
    snapshot["payload_digest"]=A.digest(snapshot["tables"])
    source=S.build_report_source(snapshot,account="AR",expected_client_id=CLIENT)
    owner={"client_id":CLIENT,"scope":"ALL_MEMBER_ACCOUNTS",
           "broker":None,"account":None,"currency":None,"funding_domain":None}
    request={"schema_version":"Family.W8.MemberV82Request.v1","client_id":CLIENT,
        "run_id":"synthetic-member-review","evaluation_at":AT,"owner":owner,
        "trade_authorization":"NONE","client_snapshot":{"payload":snapshot},
        "confirmed_target":{**deepcopy(c["request"]["confirmed_target"]),
                            "original_confirmation":{"target_key":"MAIN"}}}
    rows=[{"instrument_id":symbol,"symbol":symbol,"owner":deepcopy(owner),
        "proposed_amount":None,"full_native_pipeline_complete":False,"trade_action":"NO_TRADE",
        "trade_authorization":"NONE","execution_status":"NATIVE_COMPONENTS_COMPUTED",
        "formal_conclusion":{"status":"INCOMPLETE_REQUIRED_FACTS",
            "classification":{"primary_class":"合成研究類別"},"binding":{
                "client_id":CLIENT,"run_id":request["run_id"],"owner":deepcopy(owner),
                "source_db_sha256":source["source_db_sha256"]}}}
        for symbol in ("KEEP","BOTH","NEW")]
    result={"schema_version":"Family.W8.MemberV82Analysis.v1","status":"ANALYSIS_PARTIAL",
        "client_id":CLIENT,"run_id":request["run_id"],"evaluation_at":AT,
        "source_db_sha256":source["source_db_sha256"],"universe":{"client_id":CLIENT,
            "source_db_sha256":source["source_db_sha256"],"expected_count":len(rows),
            "assets":[{"symbol":r["symbol"]} for r in rows]},"positions":rows,
        "summary":{"tested":len(rows)},"canonical_result":None,"mentor":None,
        "full_native_pipeline_complete":False,"full_native_mentor_reached":False,
        "database_written":False,"trade_action":"NO_TRADE","trade_authorization":"NONE"}
    c={"source":source,"request":request,"result":result}
    member_refresh(c)
    return c


def member_refresh(c):
    r=c["result"];r["request_digest"]=A.digest(c["request"])
    for row in r["positions"]:
        if row.get("formal_conclusion") is not None:
            row["formal_conclusion"]["binding"]["request_digest"]=r["request_digest"]
        row["result_digest"]=A.digest({k:v for k,v in row.items() if k!="result_digest"})
    universe=r["universe"]
    universe["universe_digest"]=A.digest({k:v for k,v in universe.items() if k!="universe_digest"})
    r["report_digest"]=A.digest({k:v for k,v in r.items() if k not in ("report_digest","source_sha256")})

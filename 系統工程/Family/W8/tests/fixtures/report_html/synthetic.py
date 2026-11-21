"""Entirely synthetic upstream OUTPUT shapes; no customer data or strategy run.

Values intentionally cover a protected stock, current-only and target-only
instruments, positive/negative/zero drift and zero new deployment (WAIT).
"""
from copy import deepcopy
from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha1, sha256
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

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


PINNED_PRODUCER = "d250d3c506da3f7bec1dd7f3b5c89639a69765f7"
PINNED_SNAPSHOT_SHA256 = "5417dd4530889a904e7a8e0b9e3616b3b55f4760b64e413c52d5373c141ee833"


@contextmanager
def pinned_producer():
    """Load exact public PR59 sources in isolation, never replacing report W5.

    Three differing upstream files are embedded as immutable source snapshots;
    fifteen unchanged dependencies are checked against their upstream hashes.
    Only the temporary import of Mentor sees the pinned runtime_loader module.
    No sys.path edits, source rewriting, financial-module mocks or downloads.
    """
    raw = (W8 / "report_html_evidence/mentor_scope_compatibility/upstream_snapshot.json").read_bytes()
    if sha256(raw).hexdigest() != PINNED_SNAPSHOT_SHA256:
        raise ValueError("PINNED_UPSTREAM_SNAPSHOT_INTEGRITY")
    snapshot = json.loads(raw)
    if snapshot["producer_commit"] != PINNED_PRODUCER:
        raise ValueError("PINNED_UPSTREAM_COMMIT")
    with TemporaryDirectory(prefix="report-pinned-pr59-") as directory:
        root = Path(directory)
        for row in snapshot["files"]:
            rel = Path(row["path"])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("PINNED_UPSTREAM_PATH")
            data = (row["content_utf8"].encode() if "content_utf8" in row
                    else (W8.parents[2] / rel).read_bytes())
            blob = sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if (len(data) != row["bytes"] or sha256(data).hexdigest() != row["sha256"]
                    or blob != row["git_blob_sha"]):
                raise ValueError("PINNED_UPSTREAM_SOURCE_INTEGRITY:" + row["path"])
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        def module(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            out = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(out)
            return out
        w5 = root / "系統工程/Family/W5"
        loader = module("report_pinned_pr59_loader", w5 / "runtime_loader.py")
        with patch.dict(sys.modules, {"runtime_loader": loader}):
            mentor = module("report_pinned_pr59_mentor", w5 / "mentor_bridge.py")
        native = loader.load_c_module(root, 9)
        request = json.loads((w5 / "tests/fixtures/work9_mentor_request.json").read_text())
        yield root, native, mentor, request


def native_work9_case(c, native, mentor_module, root, raw_request):
    """Bind the synthetic report to original Work9/Mentor outputs unchanged."""
    raw_before = deepcopy(raw_request)
    unified = native.build_unified_deployment(raw_request)
    original_owner = unified["owner"]
    account, run = original_owner["account"], unified["run_id"]
    owner = {"client_id": CLIENT, **original_owner, "currency": unified["currency"]}
    snapshot = c["snapshot"]
    snapshot["tables"]["portfolio_account"][0]["account_key"] = account
    for row in snapshot["tables"]["portfolio_position"]:
        row["account_key"] = account
    snapshot["payload_digest"] = A.digest(snapshot["tables"])
    c["source"] = S.build_report_source(snapshot, account="AR", expected_client_id=CLIENT)
    c["request"].update(run_id=run, owner=deepcopy(owner))
    c["request"]["client_snapshot"] = {"payload": snapshot, "digest": A.digest(snapshot)}
    c["request"]["native_bundle"]["stock_request"]["work3_handoff"]["owner"] = deepcopy(original_owner)
    c["market"]["run_id"] = c["engine"]["run_id"] = run
    for row in c["market"]["position_values_twd"]:
        row["account_key"] = account
    c["target_context"].update(run_id=run, snapshot_payload_sha256=snapshot["payload_digest"])
    original = c["c7"]["original_source"]
    original["family_owner"] = deepcopy(owner)
    for identity in (original["canonical_input"]["identity"], original["work6_result"]["identity"],
                     c["c7"]["result"]["identity"]):
        identity["run_id"] = run
    allocation_id = unified["source_bindings"]["final_target_allocation_id"]
    original["work6_result"]["final_target"]["snapshot"]["allocation_id"] = allocation_id
    target = c["request"]["confirmed_target"]
    target["payload"]["draft"]["allocation_id"] = allocation_id
    target["payload"]["draft"]["draft_hash"] = A.digest(
        {k: v for k, v in target["payload"]["draft"].items() if k != "draft_hash"})
    target["target_hash"] = target["payload"]["target_hash"] = target["payload"]["draft"]["draft_hash"]
    c["target_context"]["expected_target_hash"] = target["target_hash"]
    for envelope in c["sections"].values():
        envelope["run_id"] = run
    context = {"client_id": CLIENT, "run_id": run, "owner": original_owner, "currency": unified["currency"],
               "analysis_permission": "ANALYZE_ONLY", "trade_authorization": "NONE",
               "runtime_mode": "REAL_DETERMINISTIC", "data_provenance": "SYNTHETIC",
               "expected_result_digest": native._digest(unified)}
    before = deepcopy((raw_request, unified, context))
    mentor = mentor_module.explain_native(root, raw_request, unified, trusted_context=context)
    c["result"].update(run_id=run, owner=deepcopy(owner), mentor=mentor, data_provenance="SYNTHETIC")
    c["result"]["native_result"]["unified_result"] = unified
    c["upstream_originals"] = {"request_before": raw_before, "request": raw_request,
                               "before": before, "after": (raw_request, unified, context)}
    refresh(c)
    return c


@lru_cache(maxsize=1)
def _pinned_native_case():
    with pinned_producer() as (root, native, mentor, request):
        c = native_work9_case(case(), native, mentor, root, request)
    # Engineering-only chapter producer: quotes original Mentor text verbatim.
    # This is not a qualified envelope or a report for any real household.
    c["sections"]["actions"].update(source_id="SYNTHETIC_PINNED_PR59_MENTOR_ACTION_TEXT",
        rules_sha="308c254d60f8ffd42c7ea559cbf948ece1b0fe77ee0f753bd64d0fcdd6dd3907",
        payload=[{"heading": "合成原生建議 " + row["item_id"],
                  "body": row["recommendation_explanation"],
                  "source_reference": "SYNTHETIC_PR59:" + PINNED_PRODUCER}
                 for row in c["result"]["mentor"]["items"]])
    refresh(c)
    return c


def pinned_native_case():
    return deepcopy(_pinned_native_case())


def db_review_case():
    """Fresh DB facts, no analysis result and no verified market valuation."""
    c=case();c['sections']={}
    c['market'].update(verified=False,valuation_state='UNKNOWN',
        market_as_of=AT,market_as_of_basis='SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION')
    c['engine']['status']='DATA_UNAVAILABLE'
    refresh(c,scope='SOURCE_REVIEW',result=False,c7=False)
    return c


def owner_decision_case(db_path, *, row_changes=None):
    """Synthetic read-only profile seam; no real owner, ticker or quantity."""
    import sqlite3
    from hashlib import sha256
    base=member_case();snapshot=deepcopy(base['request']['client_snapshot']['payload'])
    snapshot['tables']['portfolio_account'][0]['account_label']='合成券商／合成帳戶'
    row={'client_id':CLIENT,'field_key':'funding_goal','value_state':'KNOWN',
         'value_text':'SYNTHETIC owner selection; approval projection is separately pinned.',
         'value_integer':None,'value_real':None,'value_boolean':None,'value_date':None,
         'source_kind':'OWNER_VERIFIED','source_reference':'SYNTHETIC_OWNER_DECISION',
         'recorded_at_utc':'2026-10-01T00:00:00Z','updated_at_utc':'2026-10-15T00:00:00Z'}
    row.update(row_changes or {})
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE personal_profile_attribute ('+','.join(k+' TEXT' for k in row)+')')
        conn.execute('INSERT INTO personal_profile_attribute VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
    snapshot['source_sha256']=sha256(Path(db_path).read_bytes()).hexdigest()
    snapshot['payload_digest']=A.digest(snapshot['tables'])
    evidence={'schema':'Family.PM.OwnerDecisionEvidence.v1','client_id':CLIENT,
        'source_db_sha256':snapshot['source_sha256'],'original_table':'personal_profile_attribute',
        'original_row':row,'PM_projection':{'excluded':['NEW'],'included_weight_pending':['SYN_A','SYN_B'],
            'weights_not_authorized':['SYN_A=7%','SYN_B=7%'],
            'salary_contributions_amount_and_time':'NOT_PROVIDED','existing_other_weights':'UNCHANGED',
            'old_complete_target_version':'SYNTHETIC MAIN v7 historical'},'trade_authorization':'NONE'}
    legacy=S.build_report_source(snapshot,account='AR',expected_client_id=CLIENT)
    source=S.build_report_source(snapshot,account='AR',expected_client_id=CLIENT,
        owner_decision=evidence,expected_owner_decision_digest=A.digest(evidence),
        profile_db_path=db_path,evaluation_at=AT)
    request={'schema_version':'Family.W5.request.v1','client_id':CLIENT,'run_id':'synthetic-owner-selection',
        'evaluation_at':AT,'trade_authorization':'NONE','owner':{'client_id':CLIENT,'account':'SYNTH_ACCOUNT'},
        'client_snapshot':{'payload':snapshot,'digest':A.digest(snapshot)}}
    c={'source':source,'snapshot':snapshot,'request':request,'sections':{},'target_context':None,
       'result':None,'c7':None,'legacy_source':legacy,'owner_evidence':evidence,'profile_path':str(db_path)}
    common={'client_id':CLIENT,'source_db_sha256':snapshot['source_sha256'],
            'run_id':request['run_id'],'data_provenance':'SOURCE_BACKED'}
    c['market']={**common,'verified':False,'valuation_state':'UNKNOWN','market_as_of':AT,
        'market_as_of_basis':'SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION'}
    c['engine']={**common,'status':'DATA_UNAVAILABLE','evaluation_at':AT,'trade_authorization':'NONE'}
    owner_decision_refresh(c)
    return c


def owner_decision_refresh(c):
    c['source']['digest']=A.digest({k:v for k,v in c['source'].items() if k!='digest'})
    c['engine']['report_sources']=A.make_report_sources(c['source'],c['request'],None,
        sections=c['sections'],scope='SOURCE_REVIEW')


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


def member_financial_case():
    """Invented partial full-asset output; no household values or identities."""
    c = member_case()
    snapshot = c["request"]["client_snapshot"]["payload"]
    snapshot["tables"]["portfolio_account"].append({"client_id": CLIENT, "account_key": "SYNTH_CASH"})
    snapshot["payload_digest"] = A.digest(snapshot["tables"])
    c["source"] = S.build_report_source(snapshot, account="AR", expected_client_id=CLIENT)
    result = c["result"]
    extra = deepcopy(result["positions"][0]);extra.update(symbol="SELL",instrument_id="SELL")
    result["positions"].append(extra)
    result["universe"].update(expected_count=4, assets=[{"symbol": r["symbol"]} for r in result["positions"]])
    result["summary"]["tested"] = 4
    macro = {"observed": {key: {"value": value, "unit": "SYN_UNIT", "as_of": "2026-10-29",
        "direction": "UNKNOWN", "speed": "UNKNOWN", "freshness": "UNKNOWN"}
        for key, value in (("hy_oas", "321.123"), ("vix", "18.456"), ("move", "87.654"))},
        "credit": {"C1": "TRUE", "C2": "FALSE", "C3": "UNKNOWN", "risk_level": "UNKNOWN"},
        "full_safety_contract_complete": False, "remaining_inputs": ["SYNTHETIC_CREDIT_DIRECTION_HISTORY"]}
    for index, row in enumerate(result["positions"]):
        row.update(coverage_basis="HOLDING_ONLY" if row["symbol"] == "SELL" else "HOLDING_AND_TARGET",
            data_complete=False, market={"observed_date": "2026-10-29", "observed_close": "12.345678901",
            "formal_deployment_eligible": False, "provider_verified_at": ASOF,
            "source_reference": "https://synthetic.invalid/market/" + row["symbol"],
            "numeric": {"ma20": "11.234", "ma50": "10.123", "kd_k_9_3": "20.456",
                        "kd_d_9_3_3": "22.345", "rsi14": "43.210"}},
            macro_observations=deepcopy(macro), daily_slice={"maturity": {"state": "IMMATURE"},
                "status": "UNKNOWN_AMOUNTS_RETAINED"},
            core_observation={"result": {"permission": {"hard_gate": "UNKNOWN"},
                "technical": {"runaway_down": "UNKNOWN"}, "structural_risk": {"risk_grade": "NONE"}}},
            valuation_observations=[{"metric_name": "FORWARD_PE", "current": "17.890123",
                "unit": "multiple", "source_row": {"dataDate": "2026-10-29"},
                "valuation_level": "UNKNOWN", "classification_scope": "SOURCE_OBSERVATION_ONLY",
                "source_reference": "https://synthetic.invalid/issuer/" + row["symbol"]}])
        row["formal_conclusion"].update(market_predicates={"right": "TRUE", "runaway_up": "UNKNOWN", "left": "UNKNOWN"},
            selected_mode="UNKNOWN", formal_stage="UNKNOWN", canonical_target_rate=None,
            stage_required_unknown_fields=["SYNTHETIC_APPROVED_CASH_SCOPE"],
            approved_v10_analysis={"qP": {"value": None, "status": "UNKNOWN", "depth": None},
                "qV": {"value": None, "status": "UNKNOWN"}, "left_stage_profile": {"eligible": {"2": "TRUE"}}},
            buy_permission={"value": False, "reason_codes": ["SYNTHETIC_MISSING_CASH"]},
            deployment_gap={"status": "NOT_RUN_REQUIRED_INPUTS_UNRESOLVED", "missing_fields": ["SYNTHETIC_VERIFIED_CASH"]},
            event_coverage={"status": "NOT_VERIFIED"}, order_source={"status": "UNKNOWN"})
    c["request"]["macro_snapshot"] = {"payload": {"indicators": {"SYN_RATE": {"value": "3.210987",
        "unit": "%", "dataDate": "2026-10-29", "status": "OK", "detail": "SYNTHETIC_ONLY",
        "source": "https://synthetic.invalid/macro"}}}}
    bonds = []
    for symbol, basis in (("SYN_BOND", "TARGET_ONLY"), ("SYN_SGOV", "HOLDING_ONLY")):
        bond = {"symbol": symbol, "route": "V75", "coverage_basis": basis, "full_financial_complete": False,
            "trade_action": "NO_TRADE", "market": {"observed_date": "2026-10-29", "observed_close": "101.234567",
                "source_reference": "https://synthetic.invalid/bond/" + symbol},
            "original_pred009": {"aggregate_state": "TECHNICAL_NEUTRAL", "assessment_status": "VALID",
                "as_of": ASOF, "input_freshness_state": "FRESH"},
            "missing_inputs": [{"field": "original_v75_financial_handoff", "reason": "SYNTHETIC_BUDGET_REQUIRED",
                                "affects": ["canonical amount", "Work9"]}]}
        if symbol == "SYN_SGOV":
            bond["sgov_roles"] = {"sgov_role_proposal": [], "sgov_role_confirmation": []}
        bond["result_digest"] = A.digest(bond);bonds.append(bond)
    expected = sorted([r["symbol"] for r in result["positions"]] + [b["symbol"] for b in bonds])
    coverage = {"schema_version": "Family.W8.AllAssetCoverage.v1", "client_id": CLIENT,
        "source_db_sha256": c["source"]["source_db_sha256"], "evaluation_at": AT,
        "expected": expected, "observed": expected, "missing": [], "excluded": [],
        "denominators": {"securities": 6, "equity": 4, "bonds": 2, "cash_accounts": 2,
                         "orders_and_commitments": "COMPLETENESS_UNKNOWN__NOT_ASSUMED_EMPTY"},
        "equity_symbols": [r["symbol"] for r in result["positions"]], "bonds": bonds,
        "cash_accounts": [{"account_key": key, "owner_candidate": {"client_id": CLIENT, "currency": "TWD"},
            "available_cash": None, "missing_binding_fields": ["funding_domain"],
            "missing_inputs": ["verified_settlement"], "cash_observations": []}
            for key in ("SYNTH_ACCOUNT", "SYNTH_CASH")],
        "coverage_complete": True, "financial_completeness_asserted": False,
        "database_written": False, "trade_action": "NO_TRADE"}
    coverage["coverage_digest"] = A.digest(coverage)
    result["all_asset_coverage"] = coverage
    member_refresh(c)
    return c

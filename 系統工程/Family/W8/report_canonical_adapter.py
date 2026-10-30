"""Read-only report bindings. C/W2/W5 own decisions, confirmation and scope.

The trusted current-input producer may attach ``engine.report_sources`` without
changing the public {market, engine} API. See Report_HTML_Contract_20261030.md.
No strategy, funding, confirmation, or transport-cycle computation lives here.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
from threading import RLock

FAMILY = Path(__file__).resolve().parents[1]
_IMPORT_LOCK = RLock()
SECTION_NAMES = ("bond", "market", "radar", "valuation", "actions", "risks", "education", "institutions")
WEIGHT_TOLERANCE = Decimal("0.0000005")  # original C Work6 contract
DISPLAY_TRANSFORM = "C_TARGET_MINUS_CURRENT_TO_W6_CURRENT_MINUS_TARGET_V1"


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(ok, code):
    if not ok:
        raise ValueError(code)


def _runtime(name, folder):
    """Reuse the original receivers/validator, refusing a different import."""
    path = FAMILY / folder
    with _IMPORT_LOCK:
        prior = sys.modules.get(name)
        if prior is not None:
            require(Path(prior.__file__).resolve() == path / (name + ".py"),
                    "W6_RUNTIME_MODULE_ORIGIN_CONFLICT")
            return prior
        sys.path.insert(0, str(path))
        try:
            return importlib.import_module(name)
        finally:
            sys.path.remove(str(path))


def _time(value):
    require(isinstance(value, str), "W6_REPORT_ASOF_REQUIRED")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("W6_REPORT_ASOF_INVALID") from None
    require(result.tzinfo is not None, "W6_REPORT_ASOF_UNZONED")
    return result


def _number(value, *, signed=False):
    require(value is not None and not isinstance(value, bool), "W6_CANONICAL_NUMBER_INVALID")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("W6_CANONICAL_NUMBER_INVALID") from None
    require(number.is_finite() and (signed or number >= 0), "W6_CANONICAL_NUMBER_INVALID")
    return number


def _metric(slot, *, signed=False):
    require(isinstance(slot, dict) and slot.get("value_state") == "KNOWN",
            "W6_CANONICAL_METRIC_UNKNOWN")
    require(slot.get("unit", "FRACTION") == "FRACTION", "W6_CANONICAL_WEIGHT_UNIT")
    value = _number(slot.get("value"), signed=signed)
    require(signed or value <= 1, "W6_CANONICAL_WEIGHT_UNIT")
    return value


def _same_target(a, b):
    def content(x):
        return (x["version_no"], sorted((r["ticker"], r["weight_units"]) for r in x["allocations"]))
    return content(a) == content(b)


def resolve_targets(source, approved_target=None, target_context=None):
    """Optional original W2 record -> W6 detail, through W5/W6 validation.

    A historical signing time/run remains historical. The separate trusted
    context pins the latest version/hash and this report's DB/run, not a new
    approval. DB/external conflicts are errors, including newer incomplete DB
    confirmations recorded by formal_report_source.
    """
    targets = deepcopy(source.get("current_confirmed_target_details", []))
    if approved_target is None:
        require(target_context is None, "W6_TARGET_CONTEXT_WITHOUT_SOURCE")
        return targets, None
    ctx = target_context
    require(isinstance(ctx, dict), "W6_EXTERNAL_TARGET_CONTEXT_REQUIRED")
    for key, expected in (("client_id", source["client_id"]),
                          ("source_db_sha256", source["source_db_sha256"]),
                          ("snapshot_payload_sha256", source.get("snapshot_payload_sha256"))):
        require(expected is not None and ctx.get(key) == expected, "W6_EXTERNAL_TARGET_SOURCE_BINDING")
    require(type(ctx.get("expected_target_version")) is int
            and ctx.get("expected_target_version") == approved_target.get("target_version")
            and ctx.get("expected_target_hash") == approved_target.get("target_hash"),
            "W6_EXTERNAL_TARGET_VERSION_CONFLICT")
    require(isinstance(ctx.get("target_key"), str) and bool(ctx["target_key"].strip()),
            "W6_TARGET_KEY_INVALID")
    boundary = _runtime("family_boundary", "W5")
    receipt = _runtime("target_receipt", "W6/runtime").receive_target(
        approved_target, client_id=source["client_id"], report_run_id=ctx.get("run_id"),
        evaluation_at=_time(ctx.get("evaluation_at")), source_id=ctx.get("source_id"),
        rules_sha=sha256((FAMILY / "W5/family_boundary.py").read_bytes()).hexdigest(),
        validator=boundary.validate_target)
    record = approved_target["payload"]
    lines = record["draft"].get("target_lines")
    require(isinstance(lines, list) and bool(lines), "W6_EXTERNAL_TARGET_LINES_REQUIRED")
    catalog = {x["instrument_key"]: x for x in source.get("source_instruments", [])}
    mapping = ctx.get("instrument_map", {})
    rows = []
    seen = set()
    for row in lines:
        iid = row.get("instrument_id")
        require(isinstance(iid, str) and iid and iid not in seen, "W6_EXTERNAL_TARGET_IDENTITY")
        seen.add(iid)
        identity = mapping.get(iid, catalog.get(iid))
        require(isinstance(identity, dict) and identity.get("ticker"), "W6_EXTERNAL_TARGET_ID_MAPPING")
        instrument = identity.get("instrument_key", iid)
        if instrument in catalog:
            require(identity["ticker"] == catalog[instrument]["ticker"], "W6_EXTERNAL_TARGET_ID_MAPPING")
        require(row.get("ticker", identity["ticker"]) == identity["ticker"], "W6_EXTERNAL_TARGET_ID_MAPPING")
        weight = _metric(row.get("weight"))
        units = weight * 1000000
        require(units > 0 and units == units.to_integral_value(), "W6_EXTERNAL_TARGET_WEIGHT_UNITS")
        rows.append({"instrument_key": instrument, "ticker": identity["ticker"],
                     "label": identity.get("label") or identity.get("instrument_label") or identity["ticker"],
                     "weight_units": int(units), "weight_fraction": str(weight)})
    require(sum(x["weight_units"] for x in rows) == 1000000
            and len({x["ticker"] for x in rows}) == len(rows), "W6_EXTERNAL_TARGET_NOT_COMPLETE")
    detail = {"target_key": ctx["target_key"], "version_no": approved_target["target_version"],
              "confirmed_at_utc": record["confirmation_evidence"]["confirmed_at"],
              "confirmation_source_reference": deepcopy(record["confirmation_evidence"]["source_reference_ids"]),
              "allocations": rows, "external_target_receipt": receipt}
    db_versions = [x for x in source.get("confirmed_target_versions", []) if x["target_key"] == ctx["target_key"]]
    if db_versions:
        require(max(x["version_no"] for x in db_versions) == detail["version_no"], "W6_DB_EXTERNAL_TARGET_CONFLICT")
    existing = [x for x in targets if x["target_key"] == detail["target_key"]]
    require(not existing or (len(existing) == 1 and _same_target(existing[0], detail)),
            "W6_DB_EXTERNAL_TARGET_CONFLICT")
    require(not db_versions or bool(existing), "W6_DB_EXTERNAL_TARGET_CONFLICT")
    if existing:
        existing[0]["external_target_receipt"] = receipt
    else:
        targets.append(detail)
    return targets, receipt


def make_report_sources(source, request, result=None, *, c7=None, sections=None,
                        target_context=None, scope="SOURCE_REVIEW"):
    """Trusted producer helper; it copies actual upstream objects, not names.

    FamilyRunner result.native_result.family_sources.c7 supplies C7. A partial
    analysis may inject the original c7_engine receipt without claiming Work9.
    Eight prose envelopes come from separately vetted, named report producers.
    """
    out = {"schema_version": "Family.W8.ReportSources.v1", "scope": scope,
           "client_id": source["client_id"], "source_db_sha256": source["source_db_sha256"],
           "source_digest": source["digest"], "snapshot_payload_sha256": source.get("snapshot_payload_sha256"),
           "run_id": request["run_id"], "request": deepcopy(request), "result": deepcopy(result),
           "c7": deepcopy(c7), "sections": deepcopy(sections or {}),
           "target_context": deepcopy(target_context)}
    out["digest"] = digest(out)
    return out


def _sections(envelopes, source, run_id, evaluated):
    require(isinstance(envelopes, dict) and not set(envelopes) - set(SECTION_NAMES), "W6_SECTION_NAMES")
    canonical_section = _runtime("source_views", "W6/runtime").canonical_section
    normalized, receipts = {}, {}
    for name in SECTION_NAMES:
        raw = canonical_section(envelopes.get(name), client_id=source["client_id"], run_id=run_id, section=name)
        receipts[name] = raw
        if raw.get("as_of"):
            require(_time(raw["as_of"]) <= evaluated, "W6_FUTURE_SECTION")
        payload = raw.get("payload")
        if payload is not None:
            require(isinstance(payload, list) and all(isinstance(x, dict) and x.get("heading")
                    and x.get("body") and x.get("source_reference") for x in payload), "W6_SECTION_PAYLOAD")
        normalized[name] = deepcopy(payload or [])
        if raw["value_state"] != "KNOWN" or not payload:
            normalized[name].append({"heading": "資料狀態：" + raw["value_state"],
                                     "body": "資料尚待提供或核對；缺值保留 UNKNOWN，不代表零或安全。",
                                     "source_reference": raw.get("source_id") or "SOURCE_NOT_PROVIDED"})
    return normalized, receipts


def _radar(snapshot, reference):
    # Use the C-owned display validator, without running any investment engine.
    base = FAMILY.parent / "C-配置決策引擎＋Mentor整合/正式Runtime"
    with _IMPORT_LOCK:
        sys.path.insert(0, str(base))
        try:
            module = importlib.import_module("work6.adjustment_loop")
        finally:
            sys.path.remove(str(base))
    require(Path(module.__file__).resolve() == base / "work6/adjustment_loop.py", "W6_C_MODULE_ORIGIN_CONFLICT")
    require(not module.validate_radar_display_contract(snapshot), "W6_C_RADAR_CONTRACT")
    views, order = {}, []
    for view in snapshot["views"]:
        key = view["view_id"].lower()
        order.append(key)
        levels = []
        for axis in view["axes"]:
            score = axis["score"]
            if score["value_state"] == "KNOWN":
                number = _number(score.get("value"))
                require(1 <= number <= 6 and number == number.to_integral_value(), "W6_RADAR_SCORES_INVALID")
                require(bool(score.get("source_reference_ids")), "W6_RADAR_SCORE_LINEAGE")
                levels.append(int(number))
            else:
                require(score["value_state"] == "UNKNOWN" and score.get("value") is None, "W6_RADAR_UNKNOWN_VALUE")
                levels.append(None)
        views[key] = {"levels": levels, "canonical_view": deepcopy(view)}
    return {"source_reference": reference, "data_provenance": "SOURCE_BACKED",
            "axes": deepcopy(snapshot["axes"]), "view_order": order, "views": views,
            "canonical_snapshot": deepcopy(snapshot), "allow_unknown": True}


def prepare_report_sources(source, market, engine):
    binding = engine.get("report_sources")
    if binding is None:
        return None
    require(isinstance(binding, dict) and binding.get("schema_version") == "Family.W8.ReportSources.v1",
            "W6_REPORT_BINDING_REQUIRED")
    require(binding.get("digest") == digest({k: v for k, v in binding.items() if k != "digest"}),
            "W6_REPORT_BINDING_DIGEST")
    for key, expected in (("client_id", source["client_id"]), ("source_db_sha256", source["source_db_sha256"]),
                          ("source_digest", source["digest"]), ("run_id", engine["run_id"]),
                          ("snapshot_payload_sha256", source.get("snapshot_payload_sha256"))):
        require(expected is not None and binding.get(key) == expected, "W6_REPORT_SOURCE_BINDING")
    require(binding.get("scope") in ("SOURCE_REVIEW", "CANONICAL_CALCULATION"), "W6_REPORT_SCOPE")
    request = binding.get("request")
    require(isinstance(request, dict) and request.get("schema_version") == "Family.W5.request.v1"
            and request.get("client_id") == source["client_id"] and request.get("run_id") == engine["run_id"]
            and request.get("evaluation_at") == engine["evaluation_at"]
            and request.get("trade_authorization") == "NONE", "W6_REPORT_REQUEST_BINDING")
    snap = request.get("client_snapshot", {}).get("payload", {})
    require(snap.get("client_id") == source["client_id"] and snap.get("source_sha256") == source["source_db_sha256"]
            and snap.get("payload_digest") == source["snapshot_payload_sha256"], "W6_REPORT_SNAPSHOT_BINDING")
    require(request["client_snapshot"].get("digest") == digest(snap), "W6_REPORT_SNAPSHOT_DIGEST")
    require(isinstance(snap.get("tables"), dict) and digest(snap["tables"]) == source["snapshot_payload_sha256"],
            "W6_REPORT_SNAPSHOT_TABLE_DIGEST")
    owner = request.get("owner", {})
    require(owner.get("client_id") == source["client_id"] and owner.get("account") in source.get("source_account_keys", []),
            "W6_REPORT_OWNER_ACCOUNT")
    evaluated = _time(engine["evaluation_at"])
    result = binding.get("result")
    action = None
    if result is not None:
        action = _runtime("report_receiver", "W6/runtime").receive_action(result, request)
        require(result.get("evaluation_at", engine["evaluation_at"]) == engine["evaluation_at"], "W6_RESULT_EVALUATION")
        if result.get("status") == "OK":
            require(result.get("owner") == owner, "W6_RESULT_OWNER")
            mentor = result["mentor"]
            native = result.get("native_result", {})
            unified = native.get("unified_result", {})
            # Work9._owner_obj uses these exact keys (not account_id/domain_id).
            native_owner = {"broker": owner.get("broker"), "account": owner.get("account"),
                            "funding_domain": owner.get("funding_domain")}
            require(unified.get("owner") == native_owner and unified.get("run_id") == engine["run_id"]
                    and unified.get("currency") == mentor.get("currency") == owner.get("currency"),
                    "W6_NATIVE_OWNER_ACCOUNT_CURRENCY")
            require(mentor.get("source_result_digest") == digest(unified)
                    and unified.get("canonical_deployment_result") == mentor["canonical_deployment_result"]
                    and unified.get("canonical_deployment_result_sha256") == action["canonical_digest"]
                    and unified.get("source_bindings") == mentor.get("source_bindings")
                    and unified.get("mentor_return") == mentor.get("mentor_return"), "W6_WORK9_MENTOR_CONFLICT")
            ret = unified.get("mentor_return", {})
            require(ret.get("run_id") == engine["run_id"] and ret.get("owner") == unified.get("owner") == mentor.get("owner")
                    and ret.get("canonical_deployment_result_sha256") == action["canonical_digest"]
                    and ret.get("item_ids") == [x["item_id"] for x in action["items"]], "W6_WORK9_SUMMARY_CONFLICT")
    if binding["scope"] == "CANONICAL_CALCULATION":
        require(action is not None and action["status"] == "OK", "W6_CANONICAL_WORK9_REQUIRED")
    c7 = binding.get("c7")
    native_c7 = (result or {}).get("native_result", {}).get("family_sources", {}).get("c7")
    require(c7 is None or native_c7 is None or c7 == native_c7, "W6_C7_SOURCE_CONFLICT")
    c7 = c7 or native_c7
    sections, receipts = _sections(binding.get("sections", {}), source, engine["run_id"], evaluated)
    out = {"scope": binding["scope"], "sections": sections, "radar": None, "canonical": None,
           "lineage": {"binding_sha256": binding["digest"], "sections": receipts, "action": action,
                       "request_sha256": digest(request), "result_sha256": digest(result)}}
    target_ctx = binding.get("target_context")
    if target_ctx is not None:
        require(target_ctx.get("run_id") == engine["run_id"] and target_ctx.get("evaluation_at") == engine["evaluation_at"],
                "W6_EXTERNAL_TARGET_REPORT_RUN")
        out["targets"], out["lineage"]["approved_target"] = resolve_targets(source, request.get("confirmed_target"), target_ctx)
    if c7 is None:
        require(binding["scope"] == "SOURCE_REVIEW", "W6_CANONICAL_C_SOURCE_REQUIRED")
        return out
    original = c7.get("original_source", {})
    w6 = original.get("work6_result", {})
    framework = c7.get("result", {})
    require(c7.get("source_digest") == digest(original) == request.get("c7_source_digest"), "W6_C_SOURCE_DIGEST")
    require(original.get("schema_version") == "Family.W5.C7Source.v1"
            and original.get("family_owner") == owner and original.get("source_reference")
            and original.get("producer") and original.get("version"), "W6_C_SOURCE_OWNER")
    for identity in (original.get("canonical_input", {}).get("identity", {}), w6.get("identity", {}), framework.get("identity", {})):
        require(identity.get("client_id") == source["client_id"] and identity.get("run_id") == engine["run_id"], "W6_C_IDENTITY_RUN")
    require(original.get("evaluated_at") == engine["evaluation_at"]
            and framework.get("parent_work6_snapshot_id") == w6.get("work6_snapshot_id")
            and bool(w6.get("work6_snapshot_id")), "W6_C_SNAPSHOT_LINEAGE")
    require(framework.get("drift_snapshot") == w6.get("drift_snapshot")
            and framework.get("radar_snapshot") == w6.get("radar_snapshot"), "W6_C_SNAPSHOT_CONFLICT")
    contract = framework.get("report_contract", {})
    require(all(contract.get(k) is True for k in ("renderer_must_not_recompute_final_target",
            "renderer_must_use_work6_drift_snapshot", "renderer_must_use_work6_radar_snapshot")), "W6_C_REPORT_CONTRACT")
    if binding["scope"] == "CANONICAL_CALCULATION":
        require(framework.get("status") == "READY_FOR_PM_GATE", "W6_C_NOT_QUALIFIED")
    if action is not None and action["status"] == "OK":
        require(request.get("native_bundle", {}).get("asset_framework") == framework, "W6_C_FRAMEWORK_BINDING")
    out["lineage"]["c7"] = deepcopy(c7)
    out["radar"] = _radar(w6["radar_snapshot"], original["source_reference"])
    require(_time(w6["radar_snapshot"]["as_of"]) <= evaluated, "W6_FUTURE_C_RADAR")
    slot = w6.get("final_target", {})
    if slot.get("value_state") != "KNOWN":
        require(binding["scope"] == "SOURCE_REVIEW", "W6_CANONICAL_FINAL_TARGET_REQUIRED")
        return out
    final = slot.get("snapshot", {})
    require(w6.get("confirmation_status") == final.get("confirmation_status") == "CONFIRMED"
            and final.get("stage") == "FINAL_TARGET" and final.get("confirmed_by")
            and final.get("source_reference_ids") and _time(final.get("confirmed_at")) <= evaluated,
            "W6_C_FINAL_TARGET_CONFIRMATION")
    validator = _runtime("family_boundary", "W5").validate_target
    approved = validator(request.get("confirmed_target"), source["client_id"], evaluated)
    require(str(approved["target_version"]) == request.get("expected_versions", {}).get("target")
            and approved["payload"]["draft"].get("allocation_id") == final.get("allocation_id"),
            "W6_C_APPROVED_TARGET_BINDING")
    reference = framework.get("work6_final_target_reference")
    if reference is not None:
        require(reference.get("allocation_id") == final.get("allocation_id")
                and reference.get("confirmed_at") == final.get("confirmed_at")
                and reference.get("confirmed_by") == final.get("confirmed_by"), "W6_C_FINAL_REFERENCE_CONFLICT")
    if action is not None and action["status"] == "OK":
        require(unified.get("source_bindings", {}).get("final_target_allocation_id") == final.get("allocation_id"),
                "W6_WORK9_FINAL_TARGET_CONFLICT")
    out["canonical"] = {"final": deepcopy(final), "current": deepcopy(original["canonical_input"]["allocations"]["current_allocation"]),
                        "drift": deepcopy(w6["drift_snapshot"]), "reference": original["source_reference"]}
    out["lineage"]["approved_target_original"] = deepcopy(approved)
    return out


def canonical_display(prepared, actual, total, market):
    """Unit/sign conversion only. Preserve every source slot in the sidecar."""
    canonical = prepared["canonical"]
    if canonical is None:
        return None
    final, drift = canonical["final"], canonical["drift"]
    current_slot = canonical["current"]
    require(current_slot.get("value_state") == "KNOWN", "W6_C_CURRENT_UNKNOWN")
    current = current_slot["snapshot"]
    denominator = final.get("denominator", {})
    require(drift.get("value_state") == "KNOWN" and drift.get("renderer_must_not_recompute_final_target") is True
            and drift.get("denominator") == denominator, "W6_C_DRIFT_DENOMINATOR")
    require(denominator.get("value_state") == "KNOWN", "W6_C_DENOMINATOR_UNKNOWN")
    amount = _number(denominator.get("amount"))
    currency = denominator.get("currency")
    require(amount > 0 and isinstance(currency, str), "W6_C_DENOMINATOR_UNIT")
    cd = current.get("denominator", {})
    require(cd.get("value_state") == "KNOWN" and cd.get("currency") == currency
            and _number(cd.get("amount")) == amount, "W6_C_CURRENT_DENOMINATOR")
    rate = Decimal(1)
    if currency != "TWD":
        fx = market.get("fx_to_twd", {}).get(currency, {})
        require(fx.get("verified") is True and fx.get("source_reference")
                and _time(fx.get("as_of")) <= _time(market["market_as_of"]), "W6_CANONICAL_FX_REQUIRED")
        rate = _number(fx.get("rate"))
        require(rate > 0, "W6_CANONICAL_FX_REQUIRED")
    denominator_twd = amount * rate
    require(_time(drift.get("as_of")) <= _time(prepared["lineage"]["c7"]["original_source"]["evaluated_at"]),
            "W6_FUTURE_C_DRIFT")
    require(abs(denominator_twd - total) <= Decimal("0.01"), "W6_C_MARKET_DENOMINATOR_CONFLICT")
    def index(rows):
        require(isinstance(rows, list), "W6_C_POSITIONS_REQUIRED")
        result = {x["instrument_id"]: x for x in rows}
        require(len(result) == len(rows), "W6_C_DUPLICATE_INSTRUMENT")
        return result
    cur, tar = index(current.get("positions")), index(final.get("positions"))
    rows = drift.get("items", [])
    require(set(index(rows)) == set(cur) | set(tar), "W6_C_DRIFT_UNIVERSE")
    for allocation in (cur, tar):
        require(abs(sum((_metric(x.get("weight")) for x in allocation.values()), Decimal(0)) - 1) <= WEIGHT_TOLERANCE,
                "W6_C_ALLOCATION_NOT_COMPLETE")
    actual_map = {x["代碼"]: _number(x["市值TWD"]) for x in actual}
    mapped, targets, drifts, currents = set(), [], [], []
    for row in rows:
        iid, code = row["instrument_id"], row.get("ticker")
        require(isinstance(code, str) and code and code not in mapped, "W6_C_SYMBOL_MAPPING")
        mapped.add(code)
        for position in (cur.get(iid), tar.get(iid)):
            require(position is None or position.get("ticker") == code, "W6_C_SYMBOL_MAPPING")
        cw, tw, d = (_metric(row.get("current_weight")), _metric(row.get("final_target_weight")),
                     _metric(row.get("drift"), signed=True))
        require(abs(cw - (_metric(cur[iid]["weight"]) if iid in cur else 0)) <= WEIGHT_TOLERANCE
                and abs(tw - (_metric(tar[iid]["weight"]) if iid in tar else 0)) <= WEIGHT_TOLERANCE
                and abs(d - (tw - cw)) <= WEIGHT_TOLERANCE, "W6_C_DRIFT_VALUES_CONFLICT")
        require(type(row.get("protected")) is bool and bool(row.get("client_facing_action")), "W6_C_ACTION_REQUIRED")
        if row["protected"]:
            require(iid in cur and cw == tw and d == 0 and row["client_facing_action"] == "HOLD_PROTECTED",
                    "W6_C_PROTECTED_INVARIANT")
        cv, tv = cw * denominator_twd, tw * denominator_twd
        require(abs(actual_map.get(code, Decimal(0)) - cv) <= max(Decimal("0.01"), total * WEIGHT_TOLERANCE),
                "W6_C_MARKET_CURRENT_CONFLICT")
        label = (cur.get(iid) or tar[iid]).get("label") or code
        if iid in cur:
            currents.append({"代碼": code, "顯示名稱": label, "市值TWD": str(cv), "權重": str(cw)})
        if iid in tar:
            targets.append({"代碼": code, "顯示名稱": label, "市值TWD": str(tv), "權重": str(tw)})
        drifts.append({"標的": code, "實際金額TWD": str(cv), "目標金額TWD": str(tv),
                       "差異TWD": str(-d * denominator_twd), "實際權重": str(cw), "目標權重": str(tw),
                       "差異百分點": str(-d * 100), "protected": row["protected"],
                       "client_facing_action": row["client_facing_action"], "canonical_item": deepcopy(row),
                       "display_transform": DISPLAY_TRANSFORM})
    require(not set(actual_map) - mapped, "W6_C_MARKET_CURRENT_COVERAGE")
    return {"actual": currents, "target": targets, "drift": drifts,
            "canonical_lineage": {"source": deepcopy(canonical), "display_transform": DISPLAY_TRANSFORM,
                                  "denominator_twd": str(denominator_twd), "fx_to_twd": str(rate),
                                  "money_unit": "TWD", "weight_unit": "FRACTION"}}

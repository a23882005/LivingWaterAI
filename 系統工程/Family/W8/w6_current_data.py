"""W8 -> accepted W6 v16: canonical, member-scoped current/target/drift data.

This is a DATA adapter, not a replacement for W6 v16's accepted 14-chapter
HTML/PDF/XLSX renderer. It requires current source-backed valuations and a
verified W5/Mentor same-run output. It never reads old Joseph report_data.
"""
from decimal import Decimal, InvalidOperation
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import importlib.util
from pathlib import Path


def _adapter():
    spec=importlib.util.spec_from_file_location("family_w8_canonical_report",
                                               Path(__file__).with_name("report_canonical_adapter.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def _number(value, code):
    if value is None or isinstance(value,bool):
        raise ValueError(code)
    try:
        number=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError):
        raise ValueError(code) from None
    if not number.is_finite() or number<0:
        raise ValueError(code)
    return number

def _utc(value):
    if not isinstance(value,str):
        raise ValueError("W6_ASOF_REQUIRED")
    try: moment=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: raise ValueError("W6_ASOF_INVALID") from None
    if moment.tzinfo is None:
        raise ValueError("W6_ASOF_UNZONED")
    return moment.astimezone(timezone.utc)

def _sha(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
                             separators=(",",":"),allow_nan=False).encode()).hexdigest()

def build_w6_current_data(source, market, engine):
    """Input from official_family_entry.checked_renderer's authorized source.

    market: operator-verified quotes/FX for the very same DB and analysis run.
    engine: original W5 FamilyRunner successful result, not an LLM estimate.
    Missing facts raise explicit errors instead of filling old report figures.
    """
    if (not isinstance(source,dict)
            or source.get("schema_version")!="Family.W8.FormalReportSource.v1"
            or not isinstance(source.get("digest"),str)
            or source["digest"]!=_sha({k:v for k,v in source.items() if k!="digest"})
            or not isinstance(source.get("source_db_sha256"),str)):
        raise ValueError("W6_VERIFIED_REPORT_SOURCE_REQUIRED")
    if not isinstance(market,dict) or not isinstance(engine,dict):
        raise ValueError("W6_VERIFIED_MARKET_AND_ENGINE_REQUIRED")
    adapter=_adapter()
    prepared=adapter.prepare_report_sources(source,market,engine)
    # A verified DB-only source review need not invent a native analysis to
    # report dated holdings and approved targets with an unknown NAV.
    source_review=(prepared is not None and prepared["scope"]=="SOURCE_REVIEW"
                   and prepared["canonical"] is None)
    unknown_nav=(source_review and market.get("valuation_state")=="UNKNOWN"
                 and market.get("verified") is False
                 and market.get("market_as_of_basis")=="SOURCE_REVIEW_TIME_NOT_MARKET_VALUATION")
    client=source["client_id"]
    same=(market.get("client_id")==engine.get("client_id")==client
          and market.get("source_db_sha256")==engine.get("source_db_sha256")==source["source_db_sha256"]
          and market.get("run_id")==engine.get("run_id")
          and (engine.get("status")=="OK" or (prepared is not None
               and prepared["scope"]=="SOURCE_REVIEW"
               and engine.get("status") in ("DATA_UNAVAILABLE","REJECTED","BLOCKED","INVALID_INPUT","ERROR","ANALYSIS_PARTIAL")))
          and engine.get("data_provenance")=="SOURCE_BACKED"
          and market.get("data_provenance")=="SOURCE_BACKED"
          and (market.get("verified") is True or unknown_nav)
          and engine.get("trade_authorization","NONE")=="NONE")
    if not same:
        raise PermissionError("W6_SAME_CLIENT_DB_AND_ENGINE_REQUIRED")
    evaluated=_utc(engine.get("evaluation_at"))
    observed=_utc(market.get("market_as_of"))
    if observed>evaluated:
        raise ValueError("W6_FUTURE_MARKET")
    # Formal targets are keyed by the member's approved W1 target_key.
    # Lilian, for example, uses LONG_TERM, not the provisional MAIN name.
    # Never silently take the first or an older confirmed target when there
    # are multiple distinct confirmed target purposes.
    targets=(prepared or {}).get("targets",source.get("current_confirmed_target_details",[]))
    if not isinstance(targets,list):
        raise ValueError("W6_FINAL_TARGET_NOT_CONFIRMED")
    key=market.get("confirmed_target_key")
    if key is not None and (not isinstance(key,str) or not key.strip()):
        raise ValueError("W6_TARGET_KEY_INVALID")
    target=[x for x in targets if isinstance(x,dict)
            and (key is None or x.get("target_key")==key)]
    partial=prepared is not None and prepared["scope"]=="SOURCE_REVIEW"
    if not target and not partial:
        raise ValueError("W6_FINAL_TARGET_NOT_CONFIRMED")
    if len(target)>1:
        raise ValueError("W6_MULTIPLE_CONFIRMED_TARGETS_REQUIRE_KEY")
    allocations=target[0].get("allocations",[]) if target else []
    if target and (not allocations or sum(int(x["weight_units"]) for x in allocations)!=1000000):
        raise ValueError("W6_FINAL_TARGET_NOT_COMPLETE")
    if unknown_nav:
        # No inferred NAV, zero holdings, FX, target amounts, or drift. The
        # original partial result remains separate from the dated DB facts.
        rows=[]
        for row in allocations:
            units=row.get("weight_units")
            if type(units) is not int or units<=0 or not row.get("ticker"):
                raise ValueError("W6_TARGET_WEIGHT_INVALID")
            rows.append({"代碼":row["ticker"],"顯示名稱":row.get("label") or row["ticker"],
                         "權重":str(Decimal(units)/Decimal(1000000)),"市值TWD":None})
        if len({x["代碼"] for x in rows})!=len(rows):
            raise ValueError("W6_DUPLICATE_TARGET_SYMBOL")
        out={"schema_version":"Family.W8.W6CurrentData.v1",
             "client_id":client,"member_alias":source["member_alias"],
             "source_db_sha256":source["source_db_sha256"],"source_digest":source["digest"],
             "run_id":engine["run_id"],"market_as_of":market["market_as_of"],
             "market_as_of_label":"來源查核時點（市值尚未核實）",
             "evaluation_at":engine["evaluation_at"],"current_total_twd":None,
             "current_value_state":"UNKNOWN","actual":[],"target":rows,"drift":[],
             "source_position_records":deepcopy(source.get("actual_position_records",[])),
             "engine_result_sha256":_sha(engine),"approved_radar":prepared["radar"],
             "verified_sections":prepared["sections"],"report_source_lineage":prepared["lineage"],
             "target_key":target[0]["target_key"] if target else None,
             "target_version":target[0]["version_no"] if target else None,
             "report_scope":"SOURCE_REVIEW","data_provenance":"SOURCE_BACKED",
             "report_content_state":"SOURCE_REVIEW_READY__VALUATION_AND_FINANCIAL_PIPELINE_UNKNOWN",
             "trade_authorization":"NONE"}
        out["digest"]=_sha(out)
        return out
    positions=source.get("actual_position_records",[])
    valuations=market.get("position_values_twd")
    if not isinstance(valuations,list):
        raise ValueError("W6_POSITION_VALUATIONS_REQUIRED")
    lookup={}
    for row in valuations:
        if (not isinstance(row,dict)
                or row.get("source_reference") in (None,"")
                or row.get("data_provenance")!="SOURCE_BACKED"):
            raise ValueError("W6_UNVERIFIED_PRICE")
        key=(row.get("account_key"),row.get("instrument_key"))
        if key in lookup:
            raise ValueError("W6_DUPLICATE_PRICE")
        lookup[key]=_number(row.get("market_value_twd"),"W6_INVALID_VALUE")
    keys={(p["account_key"],p["instrument_key"]) for p in positions}
    if len(keys)!=len(positions) or keys!=set(lookup):
        raise ValueError("W6_POSITION_VALUATION_COVERAGE")
    current={}
    for row in positions:
        key=(row["account_key"],row["instrument_key"])
        code=row.get("ticker")
        if not isinstance(code,str) or not code:
            raise ValueError("W6_INSTRUMENT_IDENTITY_REQUIRED")
        label=row.get("label") or code
        if code not in current:
            current[code]={"代碼":code,"顯示名稱":label,"市值TWD":Decimal(0)}
        elif current[code]["顯示名稱"]!=label:
            raise ValueError("W6_AMBIGUOUS_SYMBOL_LABEL")
        current[code]["市值TWD"]+=lookup[key]

    # Cash inside the explicitly included investment pool is valued, but its
    # reported amount does not establish deployable/settled funds.
    cash=source.get("current_cash_by_account_currency",[])
    scoped=market.get("included_cash_accounts")
    fx=market.get("fx_to_twd")
    if not isinstance(scoped,list) or not isinstance(fx,dict):
        raise ValueError("W6_INVESTMENT_POOL_OR_FX_REQUIRED")
    scopes={(row.get("account_key"),row.get("currency")) for row in scoped
            if isinstance(row,dict) and row.get("included") is True}
    if len(scopes)!=sum(bool(x.get("included") is True) for x in scoped if isinstance(x,dict)):
        raise ValueError("W6_DUPLICATE_CASH_SCOPE")
    source_cash={(row["account_key"],row["currency"]):row for row in cash}
    if not scopes.issubset(source_cash):
        raise ValueError("W6_CASH_SCOPE_MISSING")
    for account,currency in sorted(scopes):
        row=source_cash[(account,currency)]
        if row.get("data_state")!="VERIFIED":
            raise ValueError("W6_LATEST_CASH_NOT_VERIFIED")
        amount=_number(row.get("reported_cash_minor"),"W6_CASH_UNKNOWN")/Decimal(100)
        if currency=="TWD":
            rate=Decimal(1)
        else:
            evidence=fx.get(currency)
            if (not isinstance(evidence,dict) or not evidence.get("source_reference")
                    or evidence.get("verified") is not True):
                raise ValueError("W6_FX_UNVERIFIED")
            rate=_number(evidence.get("rate"),"W6_FX_INVALID")
            if _utc(evidence.get("as_of"))>evaluated:
                raise ValueError("W6_FUTURE_FX")
        code=currency+"_CASH"
        if code not in current:
            current[code]={"代碼":code,"顯示名稱":currency+"現金","市值TWD":Decimal(0)}
        current[code]["市值TWD"]+=amount*rate

    total=sum((row["市值TWD"] for row in current.values()),Decimal(0))
    if total<=0:
        raise ValueError("W6_INVESTMENT_POOL_EMPTY")
    actual=[{"代碼":code,"顯示名稱":row["顯示名稱"],
             "市值TWD":str(row["市值TWD"]),
             "權重":str(row["市值TWD"]/total)}
            for code,row in sorted(current.items(),
                                   key=lambda kv:(-kv[1]["市值TWD"],kv[0]))]
    target_rows=[]
    canonical=(prepared or {}).get("canonical")
    for row in ([] if canonical else allocations):
        units=row["weight_units"]
        if type(units) is not int or units<=0:
            raise ValueError("W6_TARGET_WEIGHT_INVALID")
        code=row.get("ticker")
        if not isinstance(code,str) or not code:
            raise ValueError("W6_TARGET_IDENTITY_MISSING")
        target_rows.append({"代碼":code,"顯示名稱":row.get("label") or code,
                            "權重":str(Decimal(units)/Decimal(1000000)),
                            "市值TWD":str(total*Decimal(units)/Decimal(1000000))})
    if len({x["代碼"] for x in target_rows})!=len(target_rows):
        raise ValueError("W6_DUPLICATE_TARGET_SYMBOL")
    target_map={x["代碼"]:x for x in target_rows}
    drift=[]
    for code in ([] if canonical or not target_rows else sorted(set(current)|set(target_map))):
        cv=current.get(code,{}).get("市值TWD",Decimal(0))
        tv=Decimal(target_map[code]["市值TWD"]) if code in target_map else Decimal(0)
        drift.append({"標的":code,"實際金額TWD":str(cv),"目標金額TWD":str(tv),
                      "差異TWD":str(cv-tv),
                      "實際權重":str(cv/total),
                      "目標權重":str(tv/total),
                      "差異百分點":str((cv-tv)*Decimal(100)/total)})
    out={
        "schema_version":"Family.W8.W6CurrentData.v1",
        "client_id":client,"member_alias":source["member_alias"],
        "source_db_sha256":source["source_db_sha256"],
        "source_digest":source["digest"],
        "run_id":engine["run_id"],"market_as_of":market["market_as_of"],
        "evaluation_at":engine["evaluation_at"],
        "current_total_twd":str(total),"actual":actual,
        "target":target_rows,"drift":drift,
        "engine_result_sha256":_sha(engine),
        # Four-panel six-stage radar belongs to approved C/Mentor output only.
        "approved_radar":engine.get("approved_report_radar"),
        "verified_sections":engine.get("approved_w6_section_content"),
        "target_key":target[0]["target_key"] if target else None,
        "target_version":target[0]["version_no"] if target else None,
        "report_scope":"DB_TARGET_SOURCE_REVIEW",
        "data_provenance":"SOURCE_BACKED",
        "report_content_state":"SOURCE_REVIEW_READY__W6_RENDER_AND_QA_REQUIRED",
        "trade_authorization":"NONE"}
    if prepared is not None:
        out["report_scope"]=prepared["scope"]
        out["approved_radar"]=prepared["radar"]
        out["verified_sections"]=prepared["sections"]
        out["report_source_lineage"]=prepared["lineage"]
        display=adapter.canonical_display(prepared,actual,total,market)
        if display is not None:
            out.update(display)
            out["canonical_final_target_id"]=canonical["final"]["allocation_id"]
        if prepared["scope"]=="CANONICAL_CALCULATION":
            out["report_content_state"]="CALCULATION_READY__W6_RENDER_AND_QA_REQUIRED"
    out["digest"]=_sha(out)
    return out

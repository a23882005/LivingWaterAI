"""Four-member W6 current-report intake from authenticated official W5 snapshots.

Keeps confirmed holdings, reported evidence and hypothetical scenarios separate.
Never converts historical prices or provisional values into live NAV or executable
funding. This is an input to approved W6 rendering, not a new 30-page renderer.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
                    separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def _known(row):
    return row.get("value_state")=="KNOWN"


def _qty(value):
    if value is None:
        return None
    try:
        d=Decimal(str(value))
    except (InvalidOperation,TypeError,ValueError):
        return None
    if not d.is_finite() or d<0:
        return None
    return format(d,"f")


def _latest_current_positions(tables):
    instruments={x["instrument_key"]:x for x in tables.get("portfolio_instrument",[])}
    accounts={x["account_key"]:x for x in tables.get("portfolio_account",[])}
    best={}
    for row in tables.get("portfolio_position",[]):
        key=row["account_key"],row["instrument_key"]
        if key not in best or row["as_of_utc"]>best[key]["as_of_utc"]:
            best[key]=row
    result=[]
    for (account,instrument),row in sorted(best.items()):
        if account not in accounts or instrument not in instruments:
            raise ValueError("W6_POSITION_IDENTITY_INCONSISTENT")
        amount=_qty(row.get("quantity_decimal"))
        if amount is None:
            raise ValueError("W6_POSITION_QUANTITY_INVALID")
        result.append({
            "account_key":account,
            "instrument_key":instrument,
            "ticker":instruments[instrument].get("ticker"),
            "label":instruments[instrument].get("instrument_label"),
            "quantity":amount,
            "as_of_utc":row["as_of_utc"],
            "source_reference":row.get("position_source_reference"),
            "cost_basis_state":row.get("cost_state","UNKNOWN"),
            "market_value_state":"UNKNOWN",
            "market_value_twd":None})
    return result


def _actual_user_evidence(tables):
    """Explicitly group true statements and hypothetical rows into two ledgers."""
    allrows=tables.get("portfolio_snapshot_item",[])
    source_labels={
        "OWNER_SCREENSHOT_SOURCE":"SCREENSHOT_AS_DISPLAYED",
        "W6_ACCEPTED_SOURCE":"ACCEPTED_HISTORICAL_W6",
        "USER_CONFIRMED_REAL_HOLDING_VALUE":"OWNER_CONFIRMED_REAL",
        "HOLDING":"REPORTED_HOLDING",
        "HYPOTHETICAL_ALLOCATION":"HYPOTHETICAL_ONLY",
    }
    result=defaultdict(dict)
    latest_at={}
    for row in allrows:
        source=source_labels.get(row.get("domain_code"))
        if source is None or not _known(row):
            continue
        ent=row.get("entity_key")
        field=row.get("field_key")
        if not ent or not field:
            continue
        key=(source,ent,field)
        asof=row.get("source_observed_at_utc") or row.get("recorded_at_utc") or ""
        if key in latest_at and asof<latest_at[key]:
            continue
        latest_at[key]=asof
        result[(source,ent)][field]={
            "value":row.get("value_text") if row.get("value_text") is not None
                    else row.get("value_integer_minor"),
            "unit":row.get("unit"),
            "currency":row.get("currency_code"),
            "as_of_utc":asof,
            "source_reference":row.get("source_reference")}
    actual=[]
    hypothetical=[]
    for (source,ent),values in sorted(result.items()):
        r={"evidence_tier":source,"entity":ent,"fields":values}
        if source=="HYPOTHETICAL_ONLY":
            hypothetical.append(r)
        else:
            actual.append(r)
    return actual,hypothetical


def _latest_cash_by_account(tables):
    """Select one latest dated cash observation per account/currency; never sum history."""
    latest={}
    for row in tables.get("cash_balance_snapshot", []):
        key=(row["account_key"], row["currency_code"])
        order=(str(row.get("as_of_utc","")), int(row.get("version") or 0),
               str(row.get("cash_snapshot_id","")))
        if key not in latest or order>latest[key][0]:
            latest[key]=(order,row)
    result=[]
    for (account, currency), (_, row) in sorted(latest.items()):
        result.append({
            "account_key":account, "currency":currency,
            "as_of_utc":row.get("as_of_utc"),
            "reported_cash_minor":row.get("reported_cash_minor"),
            "reported_cash_basis":row.get("reported_cash_basis"),
            "normalized_settled_minor":row.get("normalized_settled_minor"),
            "pending_payable_minor":row.get("pending_payable_minor"),
            "reserved_minor":row.get("reserved_minor"),
            "data_state":row.get("data_state","UNKNOWN"),
            "source_reference":row.get("source_reference")})
    return result


def _confirmed_target_details(tables):
    """Only active, fully accepted million-unit confirmed targets enter W6."""
    allocations=tables.get("final_target_allocation", [])
    instruments={row["instrument_key"]:row for row in tables.get("portfolio_instrument", [])}
    latest={}
    for version in tables.get("final_target_version", []):
        if (version.get("lifecycle_state")!="CONFIRMED"
                or version.get("completeness_state")!="COMPLETE"):
            continue
        key=(version["target_key"],version["version_no"])
        rows=[row for row in allocations if (row.get("target_key"),row.get("version_no"))==key]
        if (not rows or any(row.get("allocation_state")!="ACCEPTED"
                            or type(row.get("weight_units")) is not int
                            or row["weight_units"]<=0 for row in rows)
                or sum(row["weight_units"] for row in rows)!=1000000):
            continue
        identities=[row["instrument_key"] for row in rows]
        if len(identities)!=len(set(identities)) or any(k not in instruments for k in identities):
            raise ValueError("W6_TARGET_INSTRUMENT_INCONSISTENT")
        candidate={"target_key":key[0],"version_no":key[1],
                   "confirmed_at_utc":version.get("confirmed_at_utc"),
                   "confirmation_source_reference":version.get("confirmation_source_ref"),
                   "allocations":[{
                       "instrument_key":row["instrument_key"],
                       "ticker":instruments[row["instrument_key"]].get("ticker"),
                       "label":instruments[row["instrument_key"]].get("instrument_label"),
                       "weight_units":row["weight_units"],
                       "weight_fraction":str(Decimal(row["weight_units"])/Decimal(1000000))
                   } for row in sorted(rows,key=lambda r:r["instrument_key"])]}
        prior=latest.get(key[0])
        if prior is None or candidate["version_no"]>prior["version_no"]:
            latest[key[0]]=candidate
    return [latest[key] for key in sorted(latest)]


def build_report_source(snapshot, *, account, expected_client_id):
    if not isinstance(snapshot,dict) or snapshot.get("schema_version")!="Family.W5.W1Snapshot.v1":
        raise ValueError("VERIFIED_W5_SNAPSHOT_REQUIRED")
    if snapshot.get("client_id")!=expected_client_id or not isinstance(expected_client_id,str):
        raise PermissionError("REPORT_CLIENT_MISMATCH")
    family={"MOU":"mou","JO":"Joseph","AR":"Arthur","LI":"Lilian"}
    if account not in family:
        raise PermissionError("REPORT_ACCOUNT_UNKNOWN")
    identity=snapshot.get("identity",{})
    if (identity.get("client_id")!=expected_client_id
        or identity.get("family_alias")!=family[account]):
        raise PermissionError("REPORT_IDENTITY_MISMATCH")
    tables=snapshot.get("tables")
    if not isinstance(tables,dict):
        raise ValueError("REPORT_TABLES_MISSING")
    for name,rows in tables.items():
        if not isinstance(rows,list) or any(
            x.get("client_id",expected_client_id)!=expected_client_id
            for x in rows if isinstance(x,dict)):
            raise PermissionError("REPORT_CROSS_CLIENT_RECORD")
    actual,hypothetical=_actual_user_evidence(tables)
    positions=_latest_current_positions(tables)
    versions=[x for x in tables.get("final_target_version",[])
              if x.get("lifecycle_state")=="CONFIRMED"]
    versions.sort(key=lambda x:(str(x.get("target_key","")),int(x.get("version_no",0))))
    confirmations={}
    for row in versions:
        key=(row["target_key"],row["version_no"])
        weights=[r for r in tables.get("final_target_allocation",[])
                 if r.get("target_key")==key[0] and r.get("version_no")==key[1]]
        if weights and sum(int(x["weight_units"]) for x in weights)==1000000:
            confirmations[key]={"target_key":key[0],"version_no":key[1],
                                "confirmed_at_utc":row.get("confirmed_at_utc"),
                                "allocation_count":len(weights)}
    target_details=_confirmed_target_details(tables)
    available=bool(target_details)
    latest_cash=_latest_cash_by_account(tables)
    snapshot_cash=tables.get("cash_balance_snapshot",[])
    # Report cash amount as reported. Never equate it to settled, free-to-buy cash.
    cash=[{"account_key":x["account_key"],"currency":x["currency_code"],
           "as_of_utc":x["as_of_utc"],"reported_cash_minor":x.get("reported_cash_minor"),
           "normalized_settled_minor":x.get("normalized_settled_minor"),
           "reserved_minor":x.get("reserved_minor"),"source_reference":x.get("source_reference")}
          for x in snapshot_cash]
    source={"schema_version":"Family.W8.FormalReportSource.v1",
            "client_id":expected_client_id,"member_alias":family[account],
            "source_db_sha256":snapshot.get("source_sha256"),
            "snapshot_payload_sha256":snapshot.get("payload_digest"),
            "report_scope":"AUTHENTICATED_HISTORICAL_OR_REPORTED_INPUT",
            "actual_position_records":positions,
            "actual_user_evidence":actual,
            "hypothetical_evidence_separate":hypothetical,
            "cash_reports":cash,
            "formal_confirmed_targets":list(confirmations.values()),
            "current_confirmed_target_details":target_details,
            "current_cash_by_account_currency":latest_cash,
            "reporting_flags":{
                "current_live_market_valuation_verified":False,
                "confirmed_target_available":available,
                "deployable_cash_certified":False,
                "w6_v16_renderer_data_complete":False},
            "trade_authorization":"NONE"}
    source["digest"]=_digest(source)
    return source

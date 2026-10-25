"""W8 authenticated, real four-member SQLite mutations.

Called only through B06 Coordinator.update(), which takes a verified session,
backs up the original Drive file, locks the resource, writes same ID and
reads back exact bytes. No raw SQL, file IDs or client IDs from caller.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

TIME = "%Y-%m-%dT%H:%M:%SZ"


def now():
    return datetime.now(timezone.utc).strftime(TIME)


def require_text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("INVALID_" + name)
    return value.strip()


def timestamp(value):
    value = require_text(value, "TIMESTAMP", 20)
    if len(value) != 20 or datetime.strptime(value, TIME).strftime(TIME) != value:
        raise ValueError("INVALID_TIMESTAMP")
    return value


def positive(value, name, *, allow_zero=False):
    try:
        x = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("INVALID_" + name) from None
    if not x.is_finite() or (x < 0 if allow_zero else x <= 0):
        raise ValueError("INVALID_" + name)
    return x


def minor_units(value):
    v = positive(value, "AMOUNT", allow_zero=True) * 100
    if v != v.to_integral_value() or v > 9_000_000_000_000_000_000:
        raise ValueError("AMOUNT_MINOR_PRECISION")
    return int(v)


def identity(db, client_id):
    row = db.execute("SELECT client_id FROM family_member_identity").fetchall()
    if len(row) != 1 or row[0][0] != client_id:
        raise PermissionError("FAMILY_IDENTITY_MISMATCH")


def existing(db, table, client, field, key):
    return db.execute("SELECT 1 FROM " + table + " WHERE client_id=? AND " + field + "=?", (client, key)).fetchone() is not None


def target(db, client, data):
    if data.get("confirmed") is not True:
        raise ValueError("TARGET_OWNER_CONFIRMATION_REQUIRED")
    ref = require_text(data.get("source_reference"), "SOURCE_REFERENCE", 240)
    rows = data.get("allocations")
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        raise ValueError("INVALID_ALLOCATION_ROWS")
    parsed = []
    used = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ALLOCATION_ROW")
        key = require_text(row.get("instrument_key"), "INSTRUMENT_KEY", 100)
        if key in used or not existing(db, "portfolio_instrument", client, "instrument_key", key):
            raise ValueError("INVALID_ALLOCATION_INSTRUMENT")
        used.add(key)
        weight = positive(row.get("weight"), "WEIGHT", allow_zero=True) * 1000000
        if weight != weight.to_integral_value():
            raise ValueError("WEIGHT_PRECISION")
        if weight > 0:
            parsed.append((key, int(weight)))
    if sum(w for _, w in parsed) != 1000000:
        raise ValueError("TARGET_TOTAL_MUST_EQUAL_ONE")
    target_key = require_text(data.get("target_key", "MAIN"), "TARGET_KEY", 80)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", target_key):
        raise ValueError("INVALID_TARGET_KEY")
    version = db.execute("SELECT MAX(version_no) FROM final_target_version WHERE client_id=? AND target_key=?",
                         (client, target_key)).fetchone()[0]
    version = (version or 0) + 1
    stamp = now()
    db.execute("""INSERT INTO final_target_version
        (client_id,target_key,version_no,previous_version_no,lifecycle_state,completeness_state,
        origin_kind,origin_source_kind,origin_source_ref,created_at_utc,
        confirmed_by,confirmation_source_kind,confirmation_source_ref,confirmed_at_utc)
        VALUES(?,?,?,?,'CONFIRMED','COMPLETE','CLIENT_INPUT','OWNER_VERIFIED',?,?,
               'AUTHORIZED_REPRESENTATIVE','OWNER_VERIFIED',?,?)""",
        (client,target_key,version,version-1 if version>1 else None,ref,stamp,ref,stamp))
    for key,weight in parsed:
        db.execute("""INSERT INTO final_target_allocation
          (client_id,target_key,version_no,instrument_key,weight_units,allocation_state,
           allocation_source_kind,allocation_source_ref,created_at_utc)
          VALUES(?,?,?,?,?,'ACCEPTED','OWNER_VERIFIED',?,?)""",
          (client,target_key,version,key,weight,ref,stamp))
    return {"status":"STORED","operation":"adjust_target","version":version,
            "allocations":len(parsed),"weight_units":1000000,"client_id":client,
            "trade_authorization":"NONE"}


def funding(db,client,data):
    source_id=require_text(data.get("source_id"),"SOURCE_ID",120)
    ref=require_text(data.get("source_reference"),"SOURCE_REFERENCE",240)
    account=require_text(data.get("account_key"),"ACCOUNT_KEY",80)
    currency=require_text(data.get("currency"),"CURRENCY",3)
    if not re.fullmatch("[A-Z]{3}", currency):
        raise ValueError("INVALID_CURRENCY")
    if not existing(db,"cash_account_scope",client,"account_key",account):
        raise ValueError("CASH_ACCOUNT_SCOPE_NOT_CONFIRMED")
    if db.execute("SELECT 1 FROM cash_account_scope WHERE client_id=? AND account_key=? AND currency_code=?",
                  (client,account,currency)).fetchone() is None:
        raise ValueError("CASH_CURRENCY_SCOPE_NOT_CONFIRMED")
    amount=minor_units(data.get("amount"))
    db.execute("""INSERT INTO funding_source
      (client_id,source_id,source_kind,source_state,account_key,currency_code,amount_minor,
       source_reference,as_of_utc,evidence_state,created_at_utc)
      VALUES(?,?,'PLANNED_CONTRIBUTION','PLANNED',?,?,?,?,?,'VERIFIED',?)""",
      (client,source_id,account,currency,amount,ref,timestamp(data.get("as_of_utc")),now()))
    return {"status":"STORED","operation":"new_funding","source_id":source_id,
            "amount_minor":amount,"currency":currency,"trade_authorization":"NONE"}


def profile(db,client,data):
    key=require_text(data.get("field_key"),"PROFILE_FIELD",120)
    ref=require_text(data.get("source_reference"),"SOURCE_REFERENCE",240)
    value=require_text(data.get("value"),"PROFILE_VALUE",1000)
    meta=db.execute("SELECT value_type,allowed_values FROM personal_profile_field_catalog WHERE field_key=?",
                   (key,)).fetchone()
    if meta is None:
        raise ValueError("UNKNOWN_PROFILE_FIELD")
    kind,values=meta
    if kind=="ENUM" and value not in json.loads(values):
        raise ValueError("PROFILE_ENUM_INVALID")
    col={"TEXT":"value_text","ENUM":"value_text","INTEGER":"value_integer",
         "DECIMAL":"value_real","BOOLEAN":"value_boolean","DATE":"value_date"}[kind]
    if kind=="INTEGER": value=int(value)
    if kind=="DECIMAL": value=float(positive(value,"PROFILE_DECIMAL",allow_zero=True))
    if kind=="BOOLEAN" and value not in ("0","1"):
        raise ValueError("PROFILE_BOOLEAN_INVALID")
    if kind=="BOOLEAN": value=int(value)
    if kind=="DATE" and len(value)!=10:raise ValueError("PROFILE_DATE_INVALID")
    cols={"value_text":None,"value_integer":None,"value_real":None,"value_boolean":None,"value_date":None}
    cols[col]=value
    old=db.execute("SELECT recorded_at_utc FROM personal_profile_attribute WHERE client_id=? AND field_key=?",
                   (client,key)).fetchone()
    stamp=now()
    db.execute("""INSERT INTO personal_profile_attribute
       (client_id,field_key,value_state,value_text,value_integer,value_real,value_boolean,value_date,
        source_kind,source_reference,recorded_at_utc,updated_at_utc)
       VALUES(?,?,'KNOWN',?,?,?,?,?,'OWNER_VERIFIED',?, ?,?)
       ON CONFLICT(client_id,field_key) DO UPDATE SET
         value_state=excluded.value_state,value_text=excluded.value_text,
         value_integer=excluded.value_integer,value_real=excluded.value_real,
         value_boolean=excluded.value_boolean,value_date=excluded.value_date,
         source_kind=excluded.source_kind,source_reference=excluded.source_reference,
         updated_at_utc=excluded.updated_at_utc""",
        (client,key,cols["value_text"],cols["value_integer"],cols["value_real"],
         cols["value_boolean"],cols["value_date"],ref,old[0] if old else stamp,stamp))
    return {"status":"STORED","operation":"update_profile","field_key":key,
            "trade_authorization":"NONE"}


def record_event(db,client,data):
    event_id=require_text(data.get("event_id"),"EVENT_ID",120)
    event_kind=require_text(data.get("event_kind"),"EVENT_KIND",70)
    source_ref=require_text(data.get("source_reference"),"SOURCE_REFERENCE",240)
    when=timestamp(data.get("event_occurred_at_utc"))
    changes=data.get("changes")
    if not isinstance(changes,list) or not 1<=len(changes)<=50:
        raise ValueError("EVENT_CHANGES_REQUIRED")
    account=data.get("account_key")
    instrument=data.get("instrument_key")
    if account is not None and not existing(db,"portfolio_account",client,"account_key",account):
        raise ValueError("EVENT_ACCOUNT_UNKNOWN")
    if instrument is not None and not existing(db,"portfolio_instrument",client,"instrument_key",instrument):
        raise ValueError("EVENT_INSTRUMENT_UNKNOWN")
    canonical=json.dumps({"kind":event_kind,"at":when,"changes":changes},sort_keys=True,
                         ensure_ascii=False,allow_nan=False)
    stamp=now()
    db.execute("""INSERT INTO portfolio_event
      (client_id,event_id,event_kind,event_occurred_at_utc,received_at_utc,
       source_kind,source_namespace,source_reference,evidence_state,event_state,
       payload_hash,account_key,instrument_key,created_at_utc)
      VALUES(?,?,?,?,?,'OWNER_VERIFIED','FAMILY','?','NEEDS_REVIEW','DRAFT',?,?,?,?)""".replace("'?'","?"),
      (client,event_id,event_kind,when,stamp,source_ref,sha256(canonical.encode()).hexdigest(),
       account,instrument,stamp))
    kinds={"POSITION","CASH","ACCOUNT","INSTRUMENT","FUNDING","TARGET","SGOV_ROLE","OTHER"}
    for i,row in enumerate(changes,1):
        if not isinstance(row,dict) or row.get("entity_kind") not in kinds:
            raise ValueError("EVENT_CHANGE_INVALID")
        field=require_text(row.get("field_name"),"CHANGE_FIELD",120)
        val=require_text(row.get("after_value"),"AFTER_VALUE",240)
        ccy=row.get("currency_code")
        typ=row.get("value_type","TEXT")
        if typ not in ("TEXT","DECIMAL_TEXT","INTEGER_MINOR","BOOLEAN"):
            raise ValueError("CHANGE_TYPE_INVALID")
        db.execute("""INSERT INTO portfolio_event_change
            (client_id,event_id,change_no,entity_kind,entity_key,field_name,
             before_state,before_value,after_state,after_value,value_type,currency_code,
             source_reference,recorded_at_utc)
            VALUES(?,?,?,?,?,?,'UNKNOWN',NULL,'KNOWN',?,?,?,?,?)""",
            (client,event_id,i,row["entity_kind"],row.get("entity_key"),field,val,typ,ccy,source_ref,stamp))
    # This records the actual, evidenced transaction/correction for review.
    # It does not invent settled cash, filled shares or change positions.
    return {"status":"STORED","operation":"record_event","event_id":event_id,
            "changes":len(changes),"position_updated":False,"trade_authorization":"NONE"}


WRITERS={"adjust_target":target,"new_funding":funding,"update_profile":profile,
         "record_event":record_event}


def make_writer(operation, client_id):
    if operation not in WRITERS:
        raise ValueError("UNKNOWN_OFFICIAL_MUTATION")
    def write(db,payload):
        if not isinstance(payload,dict) or payload.get("client_id") != client_id:
            raise PermissionError("CLIENT_MISMATCH")
        identity(db,client_id)
        return WRITERS[operation](db,client_id,payload.get("record",{}))
    return write

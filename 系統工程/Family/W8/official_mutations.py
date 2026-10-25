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


def first_allocation(db, client, record):
    """Real-source initial positions/cash with a durable history snapshot.

    User-confirmed market value never turns into a fabricated share quantity.
    Account currency is inferred only from explicitly confirmed owner input.
    """
    if record.get("interview_confirmed") is not True:
        raise ValueError("CONFIRMED_INTERVIEW_REQUIRED")
    ref=require_text(record.get("confirmation_reference"),"CONFIRMATION_REFERENCE",240)
    as_of=timestamp(record.get("as_of_utc"))
    answers=record.get("mentor_answers")
    if not isinstance(answers,dict) or not answers:
        raise ValueError("MENTOR_ANSWERS_REQUIRED")
    holdings,cash=record.get("holdings"),record.get("cash")
    if not isinstance(holdings,list) or not isinstance(cash,list) or not (holdings or cash):
        raise ValueError("ASSETS_REQUIRED")
    account=require_text(record.get("account_key","INITIAL"),"ACCOUNT_KEY",80)
    if not re.fullmatch(r"[A-Za-z0-9_-]+",account):
        raise ValueError("INVALID_ACCOUNT_KEY")
    currency=(cash[0].get("currency") if cash else holdings[0].get("currency"))
    currency=require_text(currency,"CURRENCY",3).upper()
    if not re.fullmatch(r"[A-Z]{3}",currency):
        raise ValueError("INVALID_CURRENCY")
    if db.execute("SELECT 1 FROM currency_registry WHERE currency_code=?",(currency,)).fetchone() is None:
        raise ValueError("CURRENCY_NOT_REGISTERED")
    if not existing(db,"portfolio_account",client,"account_key",account):
        db.execute("""INSERT INTO portfolio_account
            (client_id,account_key,account_label,account_currency,account_state,source_kind,
             source_reference,as_of_utc,created_at_utc)
            VALUES(?,?,?,?,'KNOWN','OWNER_VERIFIED',?, ?, ?)""",
            (client,account,require_text(record.get("account_label","本人投資帳戶"),"ACCOUNT_LABEL",120),
             currency,ref,as_of,now()))
    run_id="FIRST01-"+sha256((client+":"+require_text(record.get("request_id"),"REQUEST_ID",120)).encode()).hexdigest()[:32]
    db.execute("""INSERT INTO portfolio_snapshot_run
      (client_id,run_id,as_of_utc,version_no,run_state,data_state,source_kind,source_reference,created_at_utc)
      VALUES(?,?,?,1,'DRAFT','PARTIAL','OWNER_VERIFIED',?,?)""",
       (client,run_id,as_of,ref,now()))
    items=[("PROFILE","MENTOR","interview_answers_json",json.dumps(answers,ensure_ascii=False,sort_keys=True),"TEXT",None)]
    seen=set()
    saved=0
    for h in holdings:
        if not isinstance(h,dict):raise ValueError("INVALID_HOLDING")
        ticker=require_text(h.get("ticker"),"TICKER",40).upper()
        hcur=require_text(h.get("currency"),"CURRENCY",3).upper()
        exchange=require_text(h.get("exchange","UNKNOWN"),"EXCHANGE",30).upper()
        label=require_text(h.get("display_name"),"DISPLAY_NAME",160)
        if not re.fullmatch("[A-Z0-9.^_-]+",ticker) or not re.fullmatch("[A-Z]{3}",hcur):
            raise ValueError("INVALID_HOLDING_IDENTITY")
        key=(ticker,exchange,hcur)
        if key in seen:raise ValueError("DUPLICATE_HOLDING")
        seen.add(key)
        existing_keys=db.execute("""SELECT instrument_key FROM portfolio_instrument
             WHERE client_id=? AND ticker=? AND exchange_code=? AND quote_currency=?""",
             (client,ticker,exchange,hcur)).fetchall()
        if len(existing_keys)>1: raise ValueError("AMBIGUOUS_INSTRUMENT")
        instrument=existing_keys[0][0] if existing_keys else "USER01-"+sha256(
            (client+":"+ticker+":"+exchange+":"+hcur).encode()).hexdigest()[:24]
        if not existing_keys:
            db.execute("""INSERT INTO portfolio_instrument
               (client_id,instrument_key,instrument_type,ticker,exchange_code,instrument_label,
                quote_currency,identity_state,source_kind,source_reference,as_of_utc,created_at_utc)
               VALUES(?,?,'STOCK',?,?,?,?,'KNOWN','OWNER_VERIFIED',?,?,?)""",
              (client,instrument,ticker,exchange,label,hcur,ref,as_of,now()))
        quantity=h.get("confirmed_quantity")
        if quantity is not None:
            qty=positive(quantity,"QUANTITY")
            qty=format(qty,'f')
            db.execute("""INSERT INTO portfolio_position
               (client_id,account_key,instrument_key,as_of_utc,quantity_decimal,cost_state,
                cost_source_kind,position_source_kind,position_source_reference,recorded_at_utc)
               VALUES(?,?,?,?,?,'UNKNOWN','NOT_PROVIDED','OWNER_VERIFIED',?,?)""",
              (client,account,instrument,as_of,qty,ref,now()))
            saved+=1
        if h.get("reported_market_value") is not None:
            mv=str(positive(h["reported_market_value"],"MARKET_VALUE",allow_zero=True))
            items.append(("HOLDING",instrument,"reported_market_value",mv,"DECIMAL_TEXT",hcur))
    for entry in cash:
        if not isinstance(entry,dict):raise ValueError("INVALID_CASH")
        cur=require_text(entry.get("currency"),"CURRENCY",3).upper()
        if not re.fullmatch("[A-Z]{3}",cur):raise ValueError("INVALID_CURRENCY")
        if not db.execute("SELECT 1 FROM currency_registry WHERE currency_code=?",(cur,)).fetchone():
            raise ValueError("CURRENCY_NOT_REGISTERED")
        if not db.execute("""SELECT 1 FROM cash_account_scope
          WHERE client_id=? AND account_key=? AND currency_code=?""",(client,account,cur)).fetchone():
            db.execute("""INSERT INTO cash_account_scope
              (client_id,account_key,currency_code,account_currency_state,source_kind,
               source_reference,created_at_utc) VALUES(?,?,?,?,'OWNER_VERIFIED',?,?)""",
              (client,account,cur,"MATCHED" if cur==currency else "ADDITIONAL_CURRENCY_VERIFIED",ref,now()))
        amount=minor_units(entry.get("reported_amount"))
        db.execute("""INSERT INTO cash_balance_snapshot
          (cash_snapshot_id,client_id,account_key,currency_code,as_of_utc,version,source_snapshot_id,
           reported_cash_minor,reported_cash_basis,data_state,source_kind,source_reference)
          VALUES(?,?,?,?,?,1,?,?,'UNKNOWN','NEEDS_REVIEW','OWNER_VERIFIED',?)""",
          (run_id+"-CASH-"+cur,client,account,cur,as_of,run_id,amount,ref))
        items.append(("CASH",account,"reported_amount_minor",str(amount),"INTEGER_MINOR",cur))
    for i,(domain,entity,field,value,kind,cur) in enumerate(items,1):
        db.execute("""INSERT INTO portfolio_snapshot_item
          (client_id,run_id,item_no,domain_code,entity_key,field_key,value_state,value_type,
           value_text,value_integer_minor,currency_code,source_kind,source_reference,recorded_at_utc)
          VALUES(?,?,?,?,?,?,'KNOWN',?,?,?,?, 'OWNER_VERIFIED',?,?)""",
          (client,run_id,i,domain,entity,field,kind,
           int(value) if kind=="INTEGER_MINOR" else value,
           None if kind=="INTEGER_MINOR" else None,cur,ref,now()))
    return {"status":"STORED","operation":"first_allocation","account_key":account,
            "run_id":run_id,"position_rows_added":saved,"cash_currencies":len(cash),
            "unconfirmed_quantities_retained_in_history":len(holdings)-saved,"trade_authorization":"NONE"}

WRITERS["first_allocation"]=first_allocation

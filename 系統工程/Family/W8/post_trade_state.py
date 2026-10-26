"""Owner-confirmed trade settlement projection over existing immutable Family W1 tables.
Used only inside B06 authenticated Coordinator.update, never from a public caller.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime

DOMAIN = "W8_POST_TRADE_POSITION"

def _utc(value):
    try:
        if not isinstance(value, str) or len(value) != 20 or datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError()
    except ValueError:
        raise ValueError("POST_TRADE_UTC_REQUIRED") from None
    return value

def _number(value, zero=True):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0 or (d==0 and not zero) or d.as_tuple().exponent < -18:
            raise ValueError()
        return d
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("POST_TRADE_NUMBER_INVALID") from None

def _text(value, length=200):
    if not isinstance(value,str) or not value.strip() or len(value)>length:
        raise ValueError("POST_TRADE_EVIDENCE_REQUIRED")
    return value.strip()

def _exists(db, table, client, field, key):
    return db.execute("SELECT 1 FROM "+table+" WHERE client_id=? AND "+field+"=?", (client,key)).fetchone() is not None

def append_post_trade(db, client, event_id, payload, stamp):
    """The transaction caller owns B06 lock, backup, rollback and remote readback."""
    if payload is None:
        return None
    if not isinstance(payload,dict) or payload.get("owner_confirmed") is not True:
        raise ValueError("POST_TRADE_CONFIRMATION_REQUIRED")
    ref=_text(payload.get("evidence_reference"),240)
    asof=_utc(payload.get("as_of_utc"))
    pos=payload.get("positions",[])
    cash=payload.get("cash",[])
    if not isinstance(pos,list) or not isinstance(cash,list) or not (pos or cash):
        raise ValueError("POST_TRADE_EMPTY")
    if len(pos)>200 or len(cash)>30:
        raise ValueError("POST_TRADE_TOO_LARGE")
    identities=db.execute("SELECT client_id FROM family_member_identity").fetchall()
    if len(identities)!=1 or identities[0][0]!=client:
        raise PermissionError("POST_TRADE_CLIENT_MISMATCH")
    if not db.execute("SELECT 1 FROM portfolio_event WHERE client_id=? AND event_id=?",
                      (client,event_id)).fetchone():
        raise ValueError("POST_TRADE_EVENT_NOT_RECORDED")
    pk=set()
    position_rows=[]
    for p in pos:
        if not isinstance(p,dict): raise ValueError("POST_TRADE_POSITION_INVALID")
        acct=_text(p.get("account_key"),80); inst=_text(p.get("instrument_key"),100)
        key=(acct,inst)
        if key in pk:raise ValueError("POST_TRADE_DUPLICATE_POSITION")
        pk.add(key)
        if not (_exists(db,"portfolio_account",client,"account_key",acct) and
                _exists(db,"portfolio_instrument",client,"instrument_key",inst)):
            raise PermissionError("POST_TRADE_FOREIGN_POSITION")
        qty=_number(p.get("quantity"))
        if len(format(qty,"f").split(".")[0])>38: raise ValueError("POST_TRADE_QUANTITY_TOO_LARGE")
        last=db.execute("SELECT MAX(as_of_utc) FROM portfolio_position WHERE client_id=? AND account_key=? AND instrument_key=?",(client,acct,inst)).fetchone()[0]
        last_overlay=db.execute("""SELECT MAX(s.source_observed_at_utc) FROM portfolio_snapshot_item s
          JOIN portfolio_snapshot_run r ON r.client_id=s.client_id AND r.run_id=s.run_id
          WHERE s.client_id=? AND s.domain_code=? AND s.entity_key=? AND r.run_state='SEALED'""",
          (client,DOMAIN,acct+"|"+inst)).fetchone()[0]
        if any(x and asof<=x for x in (last,last_overlay)):
            raise ValueError("POST_TRADE_STALE_POSITION")
        position_rows.append((acct,inst,format(qty,"f")))
    ckeys=set()
    cash_rows=[]
    for p in cash:
        if not isinstance(p,dict):raise ValueError("POST_TRADE_CASH_INVALID")
        acct=_text(p.get("account_key"),80)
        ccy=_text(p.get("currency"),3).upper()
        if len(ccy)!=3 or not ccy.isalpha() or ccy!=ccy.upper():
            raise ValueError("POST_TRADE_CURRENCY_INVALID")
        if (acct,ccy) in ckeys:raise ValueError("POST_TRADE_DUPLICATE_CASH")
        ckeys.add((acct,ccy))
        if not db.execute("SELECT 1 FROM cash_account_scope WHERE client_id=? AND account_key=? AND currency_code=?",(client,acct,ccy)).fetchone():
            raise PermissionError("POST_TRADE_CASH_ACCOUNT_MISMATCH")
        prior=db.execute("SELECT MAX(as_of_utc) FROM cash_balance_snapshot WHERE client_id=? AND account_key=? AND currency_code=?",(client,acct,ccy)).fetchone()[0]
        if prior and asof<=prior:raise ValueError("POST_TRADE_STALE_CASH")
        basis=p.get("reported_cash_basis","UNKNOWN")
        if basis not in ("UNKNOWN","GROSS_BEFORE_PAYABLE","NET_OF_PENDING_PAYABLE"):
            raise ValueError("POST_TRADE_CASH_BASIS")
        def minor(value):
            v=Decimal(str(value))*100
            if not v.is_finite() or v!=v.to_integral_value() or abs(v)>9_000_000_000_000_000_000:
                raise ValueError("POST_TRADE_CASH_PRECISION")
            return int(v)
        reported=minor(p["reported_cash"])
        full=all(p.get(k) is not None for k in ("pending_receivable","pending_payable","reserved","nonoverlap_evidence"))
        rec,pay,res=(minor(p[k]) for k in ("pending_receivable","pending_payable","reserved")) if full else (None,None,None)
        if full and min(rec,pay,res)<0:raise ValueError("POST_TRADE_NEGATIVE_OBLIGATION")
        if full and basis=="NET_OF_PENDING_PAYABLE" and not p.get("payable_netting_evidence"):
            raise ValueError("POST_TRADE_NETTING_EVIDENCE_REQUIRED")
        verified=bool(full and basis!="UNKNOWN")
        normalized=(reported if basis=="GROSS_BEFORE_PAYABLE" else reported+pay if verified else None)
        if basis=="NET_OF_PENDING_PAYABLE" and not verified:
            raise ValueError("POST_TRADE_NET_CASH_INCOMPLETE")
        cash_rows.append((acct,ccy,reported,basis,normalized,rec,pay,res,
                          str(p["nonoverlap_evidence"]) if verified else None,
                          p.get("payable_netting_evidence") if verified else None,
                          "VERIFIED" if verified else "NEEDS_REVIEW"))
    digest=hashlib.sha256((client+":"+event_id).encode()).hexdigest()[:32]
    run="W8-POST11-"+digest
    if position_rows:
        ver=(db.execute("SELECT MAX(version_no) FROM portfolio_snapshot_run WHERE client_id=? AND as_of_utc=?",(client,asof)).fetchone()[0] or 0)+1
        db.execute("""INSERT INTO portfolio_snapshot_run(client_id,run_id,as_of_utc,version_no,run_state,data_state,source_kind,source_reference,created_at_utc)
                     VALUES(?,?,?,?,'DRAFT','VERIFIED','OWNER_VERIFIED',?,?)""",(client,run,asof,ver,ref,stamp))
        for i,(acct,inst,qty) in enumerate(position_rows,1):
            db.execute("""INSERT INTO portfolio_snapshot_item(client_id,run_id,item_no,domain_code,entity_key,field_key,value_state,value_type,value_text,unit,source_observed_at_utc,source_kind,source_reference,recorded_at_utc)
                         VALUES(?,?,?,?,?,'quantity_decimal','KNOWN','DECIMAL_TEXT',?,'shares',?,'OWNER_VERIFIED',?,?)""",
                         (client,run,i,DOMAIN,acct+"|"+inst,qty,asof,ref,stamp))
            db.execute("""INSERT INTO portfolio_snapshot_lineage
                (client_id,run_id,item_no,origin_domain,origin_record_key,
                 origin_effective_at_utc,origin_received_at_utc,
                 origin_source_reference,origin_evidence_state)
                VALUES(?,?,?,'PORTFOLIO_EVENT',?,?,?,?, 'VERIFIED')""",
                (client,run,i,event_id,asof,stamp,ref))
            if Decimal(qty)>0:
                db.execute("""INSERT INTO portfolio_position(client_id,account_key,instrument_key,as_of_utc,quantity_decimal,cost_state,cost_source_kind,position_source_kind,position_source_reference,recorded_at_utc)
                             VALUES(?,?,?,?,?,'UNKNOWN','NOT_PROVIDED','OWNER_VERIFIED',?,?)""",
                             (client,acct,inst,asof,qty,ref,stamp))
        h=hashlib.sha256(json.dumps({"event":event_id,"positions":position_rows,"as_of":asof},sort_keys=True).encode()).hexdigest()
        db.execute("UPDATE portfolio_snapshot_run SET run_state='SEALED',sealed_at_utc=?,content_hash=? WHERE client_id=? AND run_id=?",(stamp,h,client,run))
    for acct,ccy,reported,basis,normalized,rec,pay,res,nonoverlap,netproof,state in cash_rows:
        key=hashlib.sha256((event_id+":"+acct+":"+ccy).encode()).hexdigest()[:26]
        cash_id="W8POST-"+key
        db.execute("""INSERT INTO cash_balance_snapshot(cash_snapshot_id,client_id,account_key,currency_code,as_of_utc,version,source_snapshot_id,reported_cash_minor,reported_cash_basis,normalized_settled_minor,pending_receivable_minor,pending_payable_minor,reserved_minor,payable_netting_evidence,nonoverlap_evidence,data_state,source_kind,source_reference,reconciled_at_utc)
                     VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,'OWNER_VERIFIED',?,?)""",
                   (cash_id,client,acct,ccy,asof,event_id,reported,basis,normalized,rec,pay,res,netproof,nonoverlap,state,ref,stamp if state=="VERIFIED" else None))
        availability=db.execute("SELECT available_state,available_minor FROM cash_available_view WHERE cash_snapshot_id=?",(cash_id,)).fetchone()
        state="VERIFIED" if availability and availability[0]=="VERIFIED" and availability[1] is not None and availability[1]>=0 else "NEEDS_REVIEW"
        db.execute("INSERT INTO funding_evaluation(client_id,evaluation_id,account_key,currency_code,cash_snapshot_id,cash_as_of_utc,evaluation_state,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                   (client,"POST11-"+key,acct,ccy,cash_id,asof,state,stamp))
    return {"status":"POST_TRADE_SYNC_SAVED","positions":len(position_rows),
            "closed_positions":sum(Decimal(x[2])==0 for x in position_rows),
            "cash_accounts":len(cash_rows),"trade_authorization":"NONE"}

def effective_positions(tables):
    """Zero-inclusive sealed owner snapshots overlay immutable position history."""
    current={}
    for row in tables.get("portfolio_position",[]):
        key=(row["account_key"],row["instrument_key"])
        prev=current.get(key)
        if prev is None or row["as_of_utc"]>prev[0]:
            current[key]=(row["as_of_utc"],0,row["quantity_decimal"],dict(row))
    sealed={x["run_id"] for x in tables.get("portfolio_snapshot_run",[]) if x.get("run_state")=="SEALED"}
    for x in tables.get("portfolio_snapshot_item",[]):
        if x.get("domain_code")!=DOMAIN or x.get("field_key")!="quantity_decimal" or x.get("value_state")!="KNOWN" or x.get("run_id") not in sealed:
            continue
        key=x["entity_key"].split("|",1)
        if len(key)!=2:raise ValueError("POST_TRADE_POSITION_KEY_INVALID")
        key=tuple(key)
        when=x["source_observed_at_utc"];prior=current.get(key)
        if prior is None or (when,1)>=(prior[0],prior[1]):
            current[key]=(when,1,x["value_text"],dict(x))
    result=[]
    for (acct,inst),(when,priority,qty,row) in sorted(current.items()):
        if Decimal(qty)==0:continue
        data=dict(row)
        data.update(account_key=acct,instrument_key=inst,as_of_utc=when,quantity_decimal=qty)
        data.setdefault("cost_state","UNKNOWN")
        data.setdefault("cost_source_kind","NOT_PROVIDED")
        data.setdefault("position_source_kind","OWNER_VERIFIED")
        data.setdefault("position_source_reference",row.get("source_reference"))
        result.append(data)
    return result

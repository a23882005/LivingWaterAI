"""Translate confirmed sleeve percentages and register target-only catalogue instruments."""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import re


def whole_account_weights(equity_units, sleeve_percent, retained_units):
    """Units are millionths of the account. Retain every confirmed non-equity line."""
    if (type(equity_units) is not int or not 0 < equity_units <= 1_000_000
            or any(type(v) is not int or v <= 0 for v in retained_units.values())
            or sum(retained_units.values()) + equity_units != 1_000_000):
        raise ValueError("請核對原股票比例與要保留的非股票配置")
    if (not sleeve_percent or any(type(v) is not int or v <= 0 for v in sleeve_percent.values())
            or sum(sleeve_percent.values()) != 100 or set(sleeve_percent) & set(retained_units)):
        raise ValueError("請核對本人指定方案內的標的及比例")
    allocation = dict(retained_units)
    for ticker, percent in sleeve_percent.items():
        units, remainder = divmod(equity_units * percent, 100)
        if remainder:
            raise ValueError("此精確比例超過帳本精度，需確認可保存的比例")
        allocation[ticker] = units
    return allocation


ROLE_SOURCE = "Family03 role: "


def approved_framework(source, client, approved_reader):
    """Replay the member's registered document and immutable role mapping."""
    raw = Path(source["mapping_path"]).read_bytes()
    if sha256(raw).hexdigest() != source["mapping_sha256"]:
        raise ValueError("已登錄的配置對照檔有更新，請核對版本")
    config = json.loads(raw)
    doc = config["document_target"]
    if config["client_id"] != client or doc["client_id"] != client:
        raise ValueError("核准文件的戶別與登入戶別不一致")
    args = {k: doc[k] for k in ("client_id", "allocation_version", "mappings", "rows",
                                "source_available_at", "source_reference", "target_version")}
    pack = approved_reader(source_path=source["document_path"], **args)
    proof = pack["trusted_approved_target_source"]
    if proof["source_sha256"] != doc["sha256"]:
        raise ValueError("核准配置原件有新版本，請重新核對")
    return pack


def document_preview(final, stock_weights, revision, snapshot, pack):
    target = pack["target"]
    draft = target["payload"]["draft"]
    proof = pack["trusted_approved_target_source"]
    equity = 0
    roles = {}
    retained = {}
    for line in draft["target_lines"]:
        units = Decimal(str(line["weight"]["value"])) * 1_000_000
        if units != units.to_integral_value() or units < 0:
            raise ValueError("核准權重超出帳本精度")
        if not units:
            continue
        if line["asset_type"] in ("股票ETF", "股票", "STOCK", "EQUITY"):
            equity += int(units)
            continue
        kind = {"債券ETF":"BOND", "債券":"BOND", "BOND":"BOND", "現金":"CASH", "cash":"CASH", "CASH":"CASH"}.get(line["asset_type"])
        role = line.get("instrument_id")
        if not kind or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,90}", role):
            raise ValueError("請核對保留部位的角色與資產類別")
        retained[role] = int(units)
        roles[role] = {"id":role, "ticker":line["ticker"], "kind":kind,
                       "reference":proof["source_reference"] + " " + proof["source_sha256"]}
    units = whole_account_weights(equity, stock_weights, retained)
    rows = []
    for key, value in units.items():
        row = {"approved_role":roles[key]} if key in roles else {"candidate_ticker":key}
        rows.append({**row, "weight":format(Decimal(value)/1_000_000, "f")})
    version = sha256((revision + target["target_hash"]).encode()).hexdigest()
    return {"status":"FAMILY03_ACCOUNT_PREVIEW", "唯讀":True, "股票方案":final["方案"],
            "原全帳戶目標":"LONG_TERM", "原全帳戶版本":target["target_version"],
            "原股票占比單位":equity, "每百萬單位":units, "保留部位":retained,
            "角色對照":{k:engine_role(k,r["ticker"],r["kind"]) for k,r in roles.items()},
            "核准來源":proof["source_reference"], "配置版本":draft["original_allocation_version"],
            "allocations":rows, "revision":version, "帳本摘要":snapshot["source_sha256"]}


def engine_role(role, ticker, kind):
    """The C engine uses a native cash identifier and no tradable ticker."""
    native = re.fullmatch(r"([A-Z]{3})_CASH", role)
    if native and kind == "CASH" and ticker == role:
        return {"instrument_id":"CASH_" + native[1], "ticker":None, "currency":native[1]}
    return {"instrument_id":role, "ticker":ticker}


def register_role(db, client, role, stamp):
    # Keep the approved role as the target identity and the listing as its ticker.
    binding = engine_role(role["id"], role["ticker"], role["kind"])
    key = binding["instrument_id"]
    label = role["id"] + " / " + role["ticker"]
    expected = (role["kind"], binding["ticker"], label, ROLE_SOURCE + role["reference"])
    existing = db.execute("""SELECT instrument_type,ticker,instrument_label,source_reference
        FROM portfolio_instrument WHERE client_id=? AND instrument_key=?""", (client, key)).fetchone()
    if existing is None:
        db.execute("""INSERT INTO portfolio_instrument
            (client_id,instrument_key,instrument_type,ticker,instrument_label,source_reference,quote_currency,
             identity_state,source_kind,as_of_utc,created_at_utc)
            VALUES (?,?,?,?,?,?,?,'KNOWN','DOCUMENT',?,?)""",
            (client,key,*expected,binding.get("currency"),stamp,stamp))
    elif tuple(existing) != expected:
        raise ValueError("既有角色與本次核准文件不同")
    return key


def resolve_target_rows(db, client, record, folder, calc, planner, market, stamp):
    """Resolve only rows requesting catalogue lookup, inside the original target transaction."""
    catalogue = planner.pool_rows(Path(folder) / planner.POOL_NAME)
    equities = set().union(*(group.keys() for group in catalogue.values()))
    meta, _ = calc.workbook(Path(folder) / "標的績效基準資料.xlsx")
    resolved = []
    for row in record["allocations"]:
        if "approved_role" in row:
            key = register_role(db, client, row["approved_role"], stamp)
            resolved.append({"instrument_key":key, "weight":row["weight"]})
            continue
        if "candidate_ticker" not in row:
            resolved.append(row)
            continue
        if set(row) != {"candidate_ticker", "weight"}:
            raise ValueError("請使用單一候選標的識別")
        symbol = row["candidate_ticker"]
        if symbol not in equities or symbol not in market.LISTINGS or symbol not in meta:
            raise ValueError("請先核實候選標的的正式身分")
        details = meta[symbol]
        listing, currency = market.LISTINGS[symbol]
        exchange = details.get("主要掛牌/市場")
        name = details.get("正式名稱")
        if (not exchange or exchange in ("UNKNOWN", "待查") or not name
                or currency != details.get("基礎幣別")):
            raise ValueError("候選標的缺少核實的掛牌或交易幣別")
        found = db.execute("""SELECT instrument_key,exchange_code,quote_currency
            FROM portfolio_instrument WHERE client_id=? AND ticker=?""", (client,symbol)).fetchall()
        matches = [key for key, exch, cur in found if exch == exchange and cur == currency]
        if len(matches) == 1:
            key = matches[0]
        elif any(exch is not None or cur not in (None, currency) for _, exch, cur in found):
            raise ValueError("既有代碼須核對掛牌，請使用已核實的本人商品識別")
        else:
            key = "TARGET03-" + sha256(f"{client}:{listing}:{exchange}:{currency}".encode()).hexdigest()[:24]
            kind = "ETF" if "ETF" in str(details.get("資產類型")) else "UNKNOWN"
            db.execute("""INSERT INTO portfolio_instrument
                (client_id,instrument_key,instrument_type,ticker,exchange_code,instrument_label,
                 quote_currency,identity_state,source_kind,source_reference,as_of_utc,created_at_utc)
                VALUES (?,?,?,?,?,?,?,'KNOWN','DOCUMENT',?,?,?)""",
                (client,key,kind,symbol,exchange,name,currency,calc.BOOK_ID,stamp,stamp))
        resolved.append({"instrument_key":key,"weight":row["weight"]})
    return {**record, "allocations":resolved}


def bond_tickers(pool_path):
    from openpyxl import load_workbook

    book = load_workbook(pool_path, read_only=True, data_only=True)
    try:
        rows = iter(book["債券參照"].values)
        if not any(row and row[0] == "代碼" for row in rows):
            raise ValueError("請核對候選表的債券參照")
        return {r[0] for r in rows if len(r) >= 3 and r[0] and r[2]}
    finally:
        book.close()


def account_preview(snapshot, final, stock_weights, catalog, pool_path, revision, document_source=None):
    """Use the member’s established account target for both preview and confirmation."""
    if not final:
        raise ValueError("請先指定本人的股票方案")
    tables = snapshot["tables"]
    versions = tables["final_target_version"]
    account_keys = {row["target_key"] for row in versions} & {"MAIN", "LONG_TERM"}
    if not account_keys:
        if document_source is not None and not versions:
            return document_preview(final, stock_weights, revision, snapshot, document_source())
        raise ValueError("尚缺已確認的全帳戶配置，請先由原流程建立資產框架")
    if len(account_keys) != 1:
        raise ValueError("有兩組全帳戶目標，請先核對本戶目前使用的配置")
    target_key = account_keys.pop()
    latest = max((r for r in versions if r["target_key"] == target_key), key=lambda r: r["version_no"])
    if latest["lifecycle_state"] != "CONFIRMED" or latest["completeness_state"] != "COMPLETE":
        raise ValueError("最新全帳戶配置仍待確認或補齊")
    version = latest["version_no"]
    instruments = {r["instrument_key"]: r for r in tables["portfolio_instrument"]}
    equities = set().union(*(group.keys() for group in catalog.values()))
    bonds = bond_tickers(pool_path)
    equity_units, retained, existing = 0, {}, {}
    roles = {}
    for line in tables["final_target_allocation"]:
        if line["target_key"] != target_key or line["version_no"] != version:
            continue
        key = line["instrument_key"]
        item = instruments[key]
        symbol = item["ticker"] or key
        if (item.get("source_reference") or "").startswith(ROLE_SOURCE):
            role, sep, ticker = item["instrument_label"].partition(" / ")
            binding = engine_role(role, ticker, item["instrument_type"])
            if not sep or not ticker or binding["instrument_id"] != key or binding["ticker"] != item["ticker"]:
                raise ValueError("請核對已保存的保留角色")
            roles[role] = binding
            symbol = role
        if symbol in existing:
            raise ValueError("原配置有相同代碼的不同商品，請核對掛牌")
        existing[symbol] = key
        if item["instrument_type"] in ("BOND", "CASH") or symbol in bonds:
            retained[symbol] = line["weight_units"]
        elif symbol in equities or item["instrument_type"] == "STOCK":
            equity_units += line["weight_units"]
        else:
            raise ValueError("請核對原配置的資產類別：" + symbol)
    units = whole_account_weights(equity_units, stock_weights, retained)
    rows = []
    for symbol, value in units.items():
        key = {"instrument_key":existing[symbol]} if symbol in existing else {"candidate_ticker":symbol}
        rows.append({**key, "weight":format(Decimal(value) / 1_000_000, "f")})
    return {"status":"FAMILY03_ACCOUNT_PREVIEW", "唯讀":True, "股票方案":final["方案"],
            "原全帳戶目標":target_key, "原全帳戶版本":version, "原股票占比單位":equity_units, "每百萬單位":units,
            "保留部位":retained, "角色對照":roles, "allocations":rows, "revision":revision,
            "帳本摘要":snapshot["source_sha256"]}


def confirmed_request(preview, payload, client):
    """Accept the trusted executor's C result for the exact preview the member confirmed."""
    if (set(payload) != {"action", "owner_confirmed", "revision", "source_sha256", "mentor_result"}
            or payload["owner_confirmed"] is not True):
        raise ValueError("需要本人確認看過的全帳戶配置")
    if (payload["revision"], payload["source_sha256"]) != (preview["revision"], preview["帳本摘要"]):
        raise ValueError("方案或帳本已有更新，請重新讀取全帳戶目標")
    result = payload["mentor_result"]
    engine_gate = (result.get("final_target_engine_result") or {}).get("formal_output_eligibility", {})
    if engine_gate.get("eligible") is not True or engine_gate.get("scope") == "NONE":
        raise ValueError("本次 C 引擎結果尚未具備正式輸出資格")
    if (result.get("loop_status") != "FINAL_TARGET_CONFIRMED"
            or result.get("identity", {}).get("client_id") != client
            or result.get("route", {}).get("decision") != "C_ONLY"
            or result.get("final_target", {}).get("value_state") != "KNOWN"):
        raise ValueError("請核對本人 C／Mentor 正式確認結果")
    snapshot = result["final_target"]["snapshot"]
    verified = {}
    roles = {v["instrument_id"]:(k,v) for k,v in preview.get("角色對照", {}).items()}
    for line in snapshot["positions"]:
        role = line.get("instrument_id")
        symbol = line["ticker"] or role
        if role in roles:
            symbol, binding = roles[role]
            if (line["ticker"] != binding["ticker"]
                    or ("currency" in binding and line.get("base_currency") != binding["currency"])):
                raise ValueError("確認結果與已核准角色的商品身分不同")
        elif symbol in preview.get("角色對照", {}):
            raise ValueError("缺少已核准的角色識別")
        weight = line["weight"]
        if symbol in verified or weight["value_state"] != "KNOWN":
            raise ValueError("全帳戶確認有重複標的或未知比例")
        units = Decimal(str(weight["value"])) * 1_000_000
        # C uses float math; allow only a sub-nanounit numerical residue.
        if abs(units - units.to_integral_value()) > Decimal("0.000000001"):
            raise ValueError("確認結果超過帳本精度")
        if units < 0:
            raise ValueError("全帳戶比例須為非負數")
        if units:
            verified[symbol] = int(units.to_integral_value())
    if verified != preview["每百萬單位"] or snapshot["confirmation_status"] != "CONFIRMED":
        raise ValueError("正式確認結果與本人看過的全帳戶配置不同")
    token = result["work6_snapshot_id"]
    return {"request_id":token, "owner_confirmed":True,
            "record":{"confirmed":True, "target_key":preview["原全帳戶目標"], "allocations":preview["allocations"],
                      "source_reference":f"Family03 {token} / Excel {preview['revision']}"}}

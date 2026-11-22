"""Translate confirmed sleeve percentages and register target-only catalogue instruments."""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path


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


def resolve_target_rows(db, client, record, folder, calc, planner, market, stamp):
    """Resolve only rows requesting catalogue lookup, inside the original target transaction."""
    catalogue = planner.pool_rows(Path(folder) / planner.POOL_NAME)
    equities = set().union(*(group.keys() for group in catalogue.values()))
    meta, _ = calc.workbook(Path(folder) / "標的績效基準資料.xlsx")
    resolved = []
    for row in record["allocations"]:
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
        elif found:
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


def account_preview(snapshot, final, stock_weights, catalog, pool_path, revision):
    """Use the member’s established account target for both preview and confirmation."""
    from openpyxl import load_workbook

    if not final:
        raise ValueError("請先指定本人的股票方案")
    tables = snapshot["tables"]
    versions = tables["final_target_version"]
    account_keys = {row["target_key"] for row in versions} & {"MAIN", "LONG_TERM"}
    if not account_keys:
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
    book = load_workbook(pool_path, read_only=True, data_only=True)
    try:
        rows = iter(book["債券參照"].values)
        if not any(row and row[0] == "代碼" for row in rows):
            raise ValueError("請核對候選表的債券參照")
        bonds = {r[0] for r in rows if len(r) >= 3 and r[0] and r[2]}
    finally:
        book.close()
    equity_units, retained, existing = 0, {}, {}
    for line in tables["final_target_allocation"]:
        if line["target_key"] != target_key or line["version_no"] != version:
            continue
        key = line["instrument_key"]
        item = instruments[key]
        symbol = item["ticker"] or key
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
            "保留部位":retained, "allocations":rows, "revision":revision,
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
    for line in snapshot["positions"]:
        symbol = line["ticker"] or line["instrument_id"]
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

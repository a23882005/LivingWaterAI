"""Menu 03 family-only historical preview. All weights are inside the equity sleeve."""
from collections import defaultdict
import csv
from datetime import date
import hashlib
from importlib import import_module
import json
from math import isfinite, sqrt
from pathlib import Path
from statistics import mean, stdev
import sys

ENGINE = Path(__file__).resolve().parents[2] / "C-配置決策引擎＋Mentor整合" / "正式Runtime"
HISTORY = Path(__file__).resolve().parents[3] / "data/market_history"
BOOK_ID = "1vbaPznrzrDwZ17AeLXSLJErMrXwxPl1-"
# These are listing identities, not inferred aliases for other exchanges.
USD_SERIES = {"VT":"VT", "VOO":"VOO", "QQQ":"QQQ", "VWRA":"VWRA.L",
              "GOOG":"GOOG", "DRAM":"DRAM","IBKR":"IBKR","ZTS":"ZTS","PPH":"PPH", "SMH":"SMH", "SOXX":"SOXX","NVDA":"NVDA","MSFT":"MSFT"}


def reader_module():
    sys.path.insert(0, str(ENGINE))
    try:
        reader = import_module("work2.benchmark_reader")
    finally:
        sys.path.pop(0)
    return reader


def workbook(path):
    reader = reader_module()
    if hashlib.sha256(path.read_bytes()).hexdigest() != reader.CURRENT_CLOSEOUT_SHA256:
        raise ValueError("請核對更新後的 B 基準檔版本")
    sheets = reader.read_xlsx(path).sheets
    return ({r["Ticker"]: r for r in sheets["Sheet1_標的績效基準資料"].rows},
            sheets["Sheet4_標的曝險基準資料"].rows)


def exposure(weights, rows):
    by_id = defaultdict(dict)
    for row in rows:
        symbol, item = row["Ticker"], row["Exposure_ID"]
        if (symbol not in weights or row["Data_Status"] != "KNOWN"
                or not item.startswith(("HOLDING.", "SECTOR."))
                or item.endswith((".OTHER", ".UNKNOWN"))
                or row["Proxy_Status"] not in ("NOT_USED", "SELF")
                or not isinstance(row["Exposure_Weight"], (int, float))):
            continue
        by_id[item, row["Weight_Unit"]][symbol] = {
            "股票桶占比百分點": round(weights[symbol] * row["Exposure_Weight"], 4),
            "資料日期": str(row["As_of_Date"])[:10]}
    items = [{"項目": item, "基準": unit, "來自": parts,
              "已知合計百分點": round(sum(v["股票桶占比百分點"] for v in parts.values()), 4)}
             for (item, unit), parts in by_id.items() if len(parts) >= 2]
    return {"共同曝險": sorted(items, key=lambda r: -r["已知合計百分點"]),
            "範圍": "只列有資料且口徑相同的共同成分或產業。各基金資料日可能不同，未列項目仍可能重疊。"}


def series(symbol, meta):
    if symbol == "0050":
        group, name, currency = "taiwan", "0050.TW", "TWD"
    elif symbol in ("2454","2330","00956"):
        group, name, currency = "taiwan", symbol+".TW", "TWD"
    elif symbol in USD_SERIES:
        group, name, currency = "global", USD_SERIES[symbol], "USD"
    else:
        return None
    folder = HISTORY / group
    entry = json.loads((folder/"manifest.json").read_text())["items"].get(name, {})
    if entry.get("status") != "OK":
        return None
    inception = str(meta.get("成立日", ""))[:10]
    values = {}
    with (folder/(name+".csv")).open() as stream:
        for row in csv.DictReader(stream):
            when = row["Date"]
            if when < inception or when > entry["latest_observation"]:
                continue
            try:
                value = float(row["Adj Close"])
            except (ValueError, TypeError):
                continue
            if value <= 0 or not isfinite(value) or when in values:
                return None
            values[when] = value
    return (currency, values) if values else None


def simulate(weights, series_by_asset):
    missing = [s for s in weights if not series_by_asset.get(s)]
    if missing:
        return {"狀態":"待補同一掛牌的還原行情", "標的":missing}
    if len({series_by_asset[s][0] for s in weights}) != 1:
        return {"狀態":"待換算相同幣別", "標的":list(weights)}
    prices = {s:series_by_asset[s][1] for s in weights}
    dates = sorted(set.intersection(*(set(v) for v in prices.values())))
    if len(dates) < 2:
        return {"狀態":"共同日期不足"}
    days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    if len(dates) < days / 365.25 * 200 or any(
            (date.fromisoformat(b)-date.fromisoformat(a)).days > 14 for a,b in zip(dates,dates[1:])):
        return {"狀態":"共同日資料不足以估算年化績效", "起日":dates[0], "迄日":dates[-1]}
    wealth = [sum(weights[s]/100 * prices[s][d]/prices[s][dates[0]] for s in weights) for d in dates]
    ret = [b/a-1 for a,b in zip(wealth,wealth[1:])]
    peak = peak_at = bottom = 0
    dd = 0.0
    for i,val in enumerate(wealth):
        if val >= wealth[peak]:
            peak = i
        loss = 1-val/wealth[peak]
        if loss > dd:
            dd, peak_at, bottom = loss, peak, i
    recovery = next((dates[i] for i in range(bottom, len(dates)) if wealth[i]>=wealth[peak_at]), None)
    if days<365:
        return {"狀態":"共同紀錄未滿一年","起日":dates[0],"迄日":dates[-1],"共同觀察筆數":len(dates),
                "期間報酬率":wealth[-1]/wealth[0]-1,"最大回撤幅度":dd,"幣別":series_by_asset[next(iter(weights))][0]}
    cagr = (wealth[-1]/wealth[0])**(365.25/days)-1
    vol = stdev(ret)
    downside = sqrt(mean(min(0, v)**2 for v in ret))
    return {"狀態":"歷史粗估", "起日":dates[0], "迄日":dates[-1], "共同觀察筆數":len(dates),
            "幣別":series_by_asset[next(iter(weights))][0],"年化波動率":vol*sqrt(252), "年化報酬率":cagr,
            "最大回撤幅度":dd, "Sharpe":mean(ret)*sqrt(252)/vol if vol else None,
            "Sortino":mean(ret)*sqrt(252)/downside if downside else None,
            "Calmar":cagr/dd if dd else None, "回撤前高點":dates[peak_at] if dd else None,
            "回撤最低點":dates[bottom] if dd else None, "回到前高日期":recovery if dd else None,
            "回復天數":(date.fromisoformat(recovery)-date.fromisoformat(dates[peak_at])).days if dd and recovery else None,
            "口徑":"Yahoo 還原收盤價、期初配置後持有、未扣個人稅費。用共同交易日；Sharpe 無風險利率及 Sortino 門檻暫設零，年化按 252 日。"}


def common_currency(prices, reader):
    currencies={v[0] for v in prices.values() if v}
    if not reader or currencies!={"USD","TWD"}:
        return prices
    fx=reader(("USDTWD",)).get("USDTWD")
    if not fx or fx[0]!="TWD_PER_USD":
        return prices
    rates=fx[1]
    normalized={}
    for symbol,series_data in prices.items():
        if series_data and series_data[0]=="TWD":
            normalized[symbol]=("USD",{d:v/rates[d] for d,v in series_data[1].items()
                                       if d in rates and isfinite(rates[d]) and rates[d]>0})
        else:
            normalized[symbol]=series_data
    return normalized


def direct_exposures(symbols, individual, rows):
    rows=list(rows)
    if "PAWZ" in symbols:
        rows.append({"Ticker":"PAWZ","Exposure_ID":"HOLDING.ZTS","Data_Status":"KNOWN",
                     "Proxy_Status":"NOT_USED","Exposure_Weight":.0999,"Weight_Unit":"% of fund",
                     "As_of_Date":"2026-11-18","Source_URL":"https://www.proshares.com/our-etfs/strategic/pawz"})
    aliases={"2330":"TSMC","2454":"MEDIATEK","GOOG":"GOOGL"}
    for symbol in symbols & individual:
        possible={"HOLDING."+symbol,"HOLDING."+aliases.get(symbol,symbol)}
        for item,unit in {(r["Exposure_ID"],r["Weight_Unit"]) for r in rows
                          if r["Ticker"] in symbols and r["Exposure_ID"] in possible}:
            rows.append({"Ticker":symbol,"Exposure_ID":item,"Data_Status":"KNOWN","Proxy_Status":"SELF",
                         "Exposure_Weight":1.0,"Weight_Unit":unit,"As_of_Date":"直接持股"})
    return rows

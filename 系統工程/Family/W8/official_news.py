"""Real on-demand public news headlines for the four Family members.

News feeds are external information, not investment engine signals.
No background monitoring, broker connection, trading, or DB mutation.
"""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


def feed(query, *, max_items=10, timeout=8):
    if not isinstance(query,str) or not 1<=len(query)<=220:
        raise ValueError("INVALID_NEWS_QUERY")
    url="https://news.google.com/rss/search?"+urlencode({
        "q":query+" when:3d", "hl":"zh-TW", "gl":"TW", "ceid":"TW:zh-Hant"})
    request=Request(url,headers={
        "User-Agent":"LivingWaterAI-Family-ReadOnly/1.0",
        "Accept":"application/rss+xml,application/xml,text/xml"})
    with urlopen(request,timeout=timeout) as response:
        if response.status!=200:
            raise ValueError("NEWS_SOURCE_UNAVAILABLE")
        xml=response.read(900001)
        if len(xml)>900000:
            raise ValueError("NEWS_TOO_LARGE")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("UNSAFE_NEWS_XML")
    root=ET.fromstring(xml)
    now=datetime.now(timezone.utc)
    entries=[]
    for node in root.findall("./channel/item"):
        title=(node.findtext("title") or "").strip()
        link=(node.findtext("link") or "").strip()
        pub=node.findtext("pubDate")
        try:
            date=parsedate_to_datetime(pub).astimezone(timezone.utc)
        except (ValueError,TypeError,AttributeError):
            continue
        # Do not present old feed items as current market headlines.
        if not title or not link.startswith("https://") or not now-timedelta(days=3)<=date<=now+timedelta(hours=1):
            continue
        source=node.find("source")
        entries.append({"title":title[:260],"url":link,"published_at_utc":date.isoformat(),
                        "source":((source.text or "").strip() if source is not None else "")[:100]})
        if len(entries)>=max_items:
            break
    return entries


def holdings_tickers(snapshot):
    """Latest per-account positions; do not resurrect historical closed holdings."""
    tables=snapshot.get("tables",{})
    instruments={x.get("instrument_key"):x for x in tables.get("portfolio_instrument",[])}
    latest={}
    for row in tables.get("portfolio_position",[]):
        key=(row.get("account_key"),row.get("instrument_key"))
        asof=row.get("as_of_utc","")
        if not key[1] or (key in latest and asof<=latest[key].get("as_of_utc","")):
            continue
        latest[key]=row
    tickers=[]
    for row in latest.values():
        qty=row.get("quantity_decimal")
        try:
            if qty is None or Decimal(str(qty))<=0:
                continue
        except (InvalidOperation,ValueError,TypeError):
            continue
        instrument=instruments.get(row.get("instrument_key")) or {}
        ticker=instrument.get("ticker")
        if ticker and isinstance(ticker,str) and ticker not in tickers:
            tickers.append(ticker)
    return tickers[:8]


def market_news():
    headlines=feed("台灣 美國 股市 聯準會 經濟 半導體 財經",max_items=10)
    return {"status":"OK" if headlines else "DATA_UNAVAILABLE",
            "as_of_utc":datetime.now(timezone.utc).isoformat(),
            "source":"GOOGLE_NEWS_RSS_PUBLIC",
            "headlines":headlines,"trade_authorization":"NONE"}


def holding_news(snapshot, *, ticker=None):
    owned=holdings_tickers(snapshot)
    if ticker:
        if not isinstance(ticker,str) or ticker.upper() not in owned:
            raise ValueError("TICKER_NOT_IN_CURRENT_HOLDINGS")
        names=[ticker.upper()]
    else:
        names=owned[:3]
    if not names:
        return {"status":"DATA_UNAVAILABLE","code":"CONFIRMED_CURRENT_HOLDINGS_UNAVAILABLE",
                "headlines":[],"trade_authorization":"NONE"}
    headlines=[]
    for name in names:
        for item in feed(name+" stock 股票",max_items=3,timeout=7):
            headlines.append(dict(item,ticker=name))
    return {"status":"OK" if headlines else "DATA_UNAVAILABLE",
            "as_of_utc":datetime.now(timezone.utc).isoformat(),
            "source":"GOOGLE_NEWS_RSS_PUBLIC","tickers_checked":names,
            "headlines":headlines,"trade_authorization":"NONE"}

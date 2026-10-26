"""W8 ChatGPT-on-demand Family menu 05/08/09 with verified public evidence.

The ChatGPT executor uses its web search to supply a trusted fetch callback.
No Python network, background server, or hardcoded headlines are required.
These research/news handlers do not alter official DBs or authorize trades.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import importlib.util
import re

_STOCK=Path(__file__).with_name("official_news.py")
_SYMBOL=re.compile(r"[A-Z][A-Z0-9.^_-]{0,14}\Z")
_ALLOWED=frozenset(("theme","tickers"))

def _load_owned_tickers(snapshot):
    spec=importlib.util.spec_from_file_location("w8_family_news_identity",_STOCK)
    if spec is None or spec.loader is None:
        raise RuntimeError("FAMILY_HOLDINGS_NEWS_HELPER_MISSING")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj.holdings_tickers(snapshot)

def _validate_articles(articles, max_items):
    if not isinstance(articles,list) or len(articles)>max_items:
        raise ValueError("TRUSTED_PUBLIC_ARTICLES_REQUIRED")
    now=datetime.now(timezone.utc)
    seen=set()
    clean=[]
    for article in articles:
        if not isinstance(article,dict):
            raise ValueError("UNVERIFIED_NEWS_ITEM")
        title,url,date,source=(article.get("title"),article.get("url"),
                               article.get("published_at_utc"),article.get("source"))
        if (not isinstance(title,str) or not title.strip() or len(title)>260
            or not isinstance(url,str) or not url.startswith("https://")
            or len(url)>2048 or not isinstance(date,str)
            or not isinstance(source,str) or not source.strip()):
            raise ValueError("UNVERIFIED_NEWS_ITEM")
        try:
            published=datetime.fromisoformat(date.replace("Z","+00:00"))
        except ValueError:
            raise ValueError("INVALID_NEWS_TIMESTAMP") from None
        if (published.tzinfo is None or
            not now-timedelta(days=3)<=published.astimezone(timezone.utc)<=now+timedelta(hours=1)):
            raise ValueError("STALE_OR_FUTURE_NEWS_ITEM")
        if url not in seen:
            clean.append({"title":title.strip(),"url":url,
                          "published_at_utc":published.astimezone(timezone.utc).isoformat(),
                          "source":source.strip()[:100]})
            seen.add(url)
    return clean

def _fetch_or_handoff(fetcher,operation,query,max_items):
    if fetcher is None:
        return {"status":"TOOL_FETCH_REQUIRED","operation":operation,
                "source_query":query,"max_items":max_items,
                "required_evidence":["title","url","published_at_utc","source"],
                "trade_authorization":"NONE"}
    if not callable(fetcher):
        raise TypeError("TRUSTED_PUBLIC_FETCHER_REQUIRED")
    items=_validate_articles(fetcher(operation,query,max_items),max_items)
    return {"status":"OK" if items else "DATA_UNAVAILABLE",
            "as_of_utc":datetime.now(timezone.utc).isoformat(),
            "source":"TRUSTED_CHATGPT_ON_DEMAND_PUBLIC_SEARCH",
            "headlines":items,"trade_authorization":"NONE"}

def public_handlers(official_entry,auth,*,trusted_public_fetcher=None,
                    trusted_account_change=None):
    if not hasattr(official_entry,"current_snapshot") or not hasattr(auth,"require_login"):
        raise ValueError("FAMILY_VERIFIED_ENTRY_REQUIRED")

    def market_news(payload):
        if not isinstance(payload,dict) or payload:
            raise ValueError("INVALID_MARKET_NEWS_PAYLOAD")
        return _fetch_or_handoff(trusted_public_fetcher,"market_news",
                                 "台灣 美國 股市 聯準會 經濟 半導體 財經",10)

    def holding_news(payload):
        if not isinstance(payload,dict) or set(payload)-{"ticker"}:
            raise ValueError("INVALID_HOLDING_NEWS_PAYLOAD")
        auth.require_login()
        snapshot=official_entry.current_snapshot()
        owned=_load_owned_tickers(snapshot)
        ticker=payload.get("ticker")
        if ticker is not None:
            if not isinstance(ticker,str) or ticker.upper() not in owned:
                raise ValueError("TICKER_NOT_IN_CURRENT_HOLDINGS")
            selected=[ticker.upper()]
        else:
            selected=owned[:3]
        if not selected:
            return {"status":"DATA_UNAVAILABLE",
                    "code":"CONFIRMED_CURRENT_HOLDINGS_UNAVAILABLE",
                    "headlines":[],"trade_authorization":"NONE"}
        results=[]
        for ticker in selected:
            data=_fetch_or_handoff(trusted_public_fetcher,"holding_news",
                                   ticker+" stock 股票",3)
            if data["status"]=="TOOL_FETCH_REQUIRED":
                results.append({"ticker":ticker,"query":data["source_query"]})
            else:
                results.extend(dict(article,ticker=ticker)
                               for article in data["headlines"])
        if trusted_public_fetcher is None:
            return {"status":"TOOL_FETCH_REQUIRED","operation":"holding_news",
                    "ticker_queries":results,
                    "trade_authorization":"NONE"}
        return {"status":"OK" if results else "DATA_UNAVAILABLE",
                "tickers_checked":selected,"headlines":results,
                "source":"TRUSTED_CHATGPT_ON_DEMAND_PUBLIC_SEARCH",
                "trade_authorization":"NONE"}

    def research_candidates(payload):
        if not isinstance(payload,dict) or set(payload)-_ALLOWED:
            raise ValueError("INVALID_RESEARCH_PAYLOAD")
        theme=payload.get("theme") or ""
        tickers=payload.get("tickers") or []
        if not isinstance(theme,str) or len(theme)>160 or not isinstance(tickers,list) or len(tickers)>8:
            raise ValueError("INVALID_RESEARCH_CRITERIA")
        if any(not isinstance(x,str) or not _SYMBOL.fullmatch(x) for x in tickers) or len(set(tickers))!=len(tickers):
            raise ValueError("INVALID_CANDIDATE_TICKERS")
        if not theme.strip() and not tickers:
            return {"status":"NEEDS_CRITERIA",
                    "message":"請提供想研究的產業或ETF／股票代碼。",
                    "trade_authorization":"NONE"}
        auth.require_login()
        current=set(_load_owned_tickers(official_entry.current_snapshot()))
        searches=[]
        if theme.strip():
            searches.append(("theme",theme.strip()+" ETF 股票 投資",5))
        searches.extend((x,x+" stock ETF 股票",3) for x in tickers)
        evidence={}
        for item,query,n in searches:
            evidence[item]=_fetch_or_handoff(trusted_public_fetcher,"research_candidates",query,n)
        if trusted_public_fetcher is None:
            return {"status":"TOOL_FETCH_REQUIRED","operation":"research_candidates",
                    "source_queries":[{"name":item,"query":query,"max_items":n}
                                      for item,query,n in searches],
                    "trade_authorization":"NONE"}
        return {"status":"RESEARCH_EVIDENCE",
                "theme":theme.strip(),
                "candidate_instruments":[
                    {"ticker":ticker,"held_in_current_portfolio":ticker in current,
                     "recent_news":evidence[ticker]["headlines"],
                     "instrument_identity":"USER_REQUESTED_NOT_VERIFIED",
                     "market_price":"DATA_UNAVAILABLE","v82_decision":"NOT_EVALUATED"}
                    for ticker in tickers],
                "theme_news":evidence.get("theme",{}).get("headlines",[]),
                "allocation_change":False,"buy_recommendation":"NOT_EVALUATED",
                "source":"TRUSTED_CHATGPT_ON_DEMAND_PUBLIC_SEARCH",
                "trade_authorization":"NONE"}

    def account(payload):
        if not isinstance(payload,dict) or set(payload)-{"action","current_password","new_password"}:
            raise ValueError("INVALID_ACCOUNT_PAYLOAD")
        auth.require_login()
        action=payload.get("action")
        if action is None:
            return {"status":"ACCOUNT_OPTIONS",
                    "actions":["logout","change_password"],
                    "trade_authorization":"NONE"}
        if action!="change_password":
            raise ValueError("UNKNOWN_ACCOUNT_ACTION")
        old,new=payload.get("current_password"),payload.get("new_password")
        if not isinstance(old,str) or not isinstance(new,str) or not 1<=len(old)<=256 or not 1<=len(new)<=256:
            raise ValueError("ACCOUNT_PASSWORD_INPUT_REQUIRED")
        if trusted_account_change is None:
            return {"status":"ACCOUNT_CHANGE_WRITEBACK_REQUIRED",
                    "code":"TRUSTED_ACCOUNT_DB_WRITER_NOT_CONNECTED",
                    "trade_authorization":"NONE"}
        if not callable(trusted_account_change):
            raise TypeError("TRUSTED_ACCOUNT_CHANGE_REQUIRED")
        result=trusted_account_change(old,new)
        if not isinstance(result,dict) or result.get("trade_authorization")!="NONE":
            raise ValueError("ACCOUNT_CHANGE_RESULT_INVALID")
        return result

    return {"research_candidates":research_candidates,
            "market_news":market_news,"holding_news":holding_news,
            "account":account}

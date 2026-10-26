"""On-demand member-specific Family menu 05: verifiable candidate research.

Evidence is a recent public news feed and authenticated family holdings; the
candidate instruments are explicitly user-submitted ticker symbols. An
unvalidated media mention is never promoted into an approved allocation,
confirmed V82 signal, forecast, price, or automatically bought position.
"""
import re
from datetime import datetime, timezone
from official_news import feed, holdings_tickers

_SYMBOL = re.compile(r"\A[A-Z][A-Z0-9.^_-]{0,14}\Z")
_QUERY = re.compile(r"\A.{2,160}\Z", re.S)


def research_candidates(snapshot, *, theme=None, tickers=None):
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get("tables"),dict):
        raise ValueError("VERIFIED_FAMILY_SNAPSHOT_REQUIRED")
    if theme is not None and (not isinstance(theme,str) or not _QUERY.fullmatch(theme.strip())):
        raise ValueError("INVALID_RESEARCH_THEME")
    theme=(theme or "").strip()
    if tickers is None:
        tickers=[]
    if not isinstance(tickers,list) or len(tickers)>8:
        raise ValueError("INVALID_CANDIDATE_TICKERS")
    clean=[]
    for ticker in tickers:
        if not isinstance(ticker,str) or not _SYMBOL.fullmatch(ticker) or ticker in clean:
            raise ValueError("INVALID_CANDIDATE_TICKER")
        clean.append(ticker)
    if not theme and not clean:
        return {"status":"NEEDS_CRITERIA",
                "message":"請告訴我想研究的產業或ETF代碼，我會結合本人正式持倉及最新公開來源比較。",
                "source":"OFFICIAL_FAMILY_DB", "trade_authorization":"NONE"}
    current=set(holdings_tickers(snapshot))
    evidence=[]
    for ticker in clean:
        items=feed(ticker+" stock ETF 股票",max_items=3)
        evidence.append({"ticker":ticker,"held_in_current_portfolio":ticker in current,
                         "recent_news":items,"news_evidence_count":len(items),
                         "instrument_identity":"USER_REQUESTED_NOT_VERIFIED",
                         "market_price":"DATA_UNAVAILABLE",
                         "v82_decision":"NOT_EVALUATED"})
    topic_news=feed(theme+" ETF 股票 投資",max_items=5) if theme else []
    return {"status":"RESEARCH_EVIDENCE" if topic_news or any(x["recent_news"] for x in evidence)
            else "DATA_UNAVAILABLE",
            "produced_at_utc":datetime.now(timezone.utc).isoformat(),
            "source":"OFFICIAL_FAMILY_DB_PLUS_CURRENT_PUBLIC_RSS",
            "theme":theme,
            "current_holdings_count":len(current),
            "candidate_instruments":evidence, "theme_news":topic_news,
            "allocation_change":False,"buy_recommendation":"NOT_EVALUATED",
            "next_step":"如需加入目標配置，請於03確認；實際買進判斷需04原生V82及正式資金來源。",
            "trade_authorization":"NONE"}

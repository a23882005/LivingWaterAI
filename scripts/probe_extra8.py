#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe official sources for the eight not-yet-automated macro readings.
Never substitute proxies, stale webpage templates, ETF EPS, or invented observations.
This is a diagnostic artifact, not verified_overrides.json.
"""
import datetime as dt
import json
import pathlib
import re
import requests
from bs4 import BeautifulSoup

TARGETS = {
    "m06": ("CME FedWatch", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"),
    "m03_qqq": ("Invesco QQQ", "https://www.invesco.com/qqq-etf/en/about.html"),
    "m03_spy": ("SPDR SPY", "https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy"),
    "m03_vt": ("Vanguard VT", "https://investor.vanguard.com/investment-products/etfs/profile/vt"),
    "m04": ("ISM Manufacturing", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "m15": ("ISM Services", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "m16": ("Conference Board LEI", "https://www.conference-board.org/topics/us-leading-indicators"),
    "s05": ("TradingView MMFI", "https://www.tradingview.com/symbols/INDEX-MMFI/"),
}
def main():
    s = requests.Session()
    s.headers["User-Agent"] = "LivingWaterAI-Macro-Audit/1.0 (source verification only)"
    records = {}
    # Inspect structured JSON availability without promoting values to verified OK.
    for ticker in ("QQQ", "SPY", "VT"):
        try:
            url = "https://query1.finance.yahoo.com/v7/finance/quote"
            response = s.get(url, params={"symbols": ticker}, timeout=(5, 20))
            print("ETF_JSON_PROBE", ticker, "HTTP", response.status_code, "JSON", "json" in response.headers.get("content-type", "").lower(), flush=True)
        except requests.RequestException as exc:
            print("ETF_JSON_PROBE", ticker, type(exc).__name__, flush=True)
    for key, (label, url) in TARGETS.items():
        item = {"label": label, "source": url, "status": "UNVERIFIED", "candidate": None}
        try:
            r = s.get(url, timeout=(5, 9), allow_redirects=True)
            item["http_status"] = r.status_code
            item["resolved_url"] = r.url
            item["bytes"] = len(r.content)
            r.raise_for_status()
            text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
            item["visible_text_chars"] = len(text)
            # A working webpage does NOT establish correct value, as-of date or data definition.
            item["status"] = "PAGE_REACHABLE_UNVERIFIED"
        except requests.RequestException as exc:
            item["status"] = "UNREACHABLE"
            item["error"] = f"{type(exc).__name__}: {exc}"[:280]
        records[key] = item
        print(key, item["status"], item.get("http_status", ""), flush=True)
    result = {"schema": "LivingWaterAI/probe-extra8-v1",
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "note": "Source connectivity only; no source has yet passed indicator value/date/unit QA.",
              "indicators": records}
    out = pathlib.Path("build/macro24/extra8_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if __name__ == "__main__":
    main()

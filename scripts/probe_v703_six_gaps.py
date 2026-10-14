#!/usr/bin/env python3
"""V70.3 six missing indicators: independent source diagnostics, NEVER promote to OK."""
import datetime as dt
import json
import os
from pathlib import Path
import requests

OUT = Path("build/macro24/six_gap_probe.json")
TARGETS = {
    "m06": ("CME FedWatch", "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"),
    "m03_qqq": ("Invesco QQQ", "https://www.invesco.com/qqq-etf/en/about.html"),
    "m03_spy": ("State Street SPY", "https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy"),
    "m03_vt": ("Vanguard VT", "https://investor.vanguard.com/investment-products/etfs/profile/vt"),
    "m16": ("Conference Board LEI", "https://www.conference-board.org/topics/us-leading-indicators"),
    "s05": ("NYSE MMFI", "https://stockcharts.com/h-sc/ui?s=%24MMFI"),
}

def probe(key, name, url, session):
    item = {"status": "UNVERIFIED", "source": url, "source_name": name}
    try:
        response = session.get(url, timeout=(6, 20), allow_redirects=True)
        item["http_status"] = response.status_code
        item["final_url"] = response.url
        item["page_bytes"] = len(response.content)
        item["page_accessible"] = bool(response.ok and len(response.content) >= 500)
        # HTTP 200 proves connectivity, NOT valuation or observation availability.
        item["reason"] = "Source reachable; numeric value, published date and methodology still require verification" if item["page_accessible"] else "Source not accessible or empty"
    except requests.RequestException as exc:
        item["page_accessible"] = False
        item["reason"] = type(exc).__name__
    return item

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LivingWaterAI V70.3 source audit)"})
    result = {"schema": "V70.3/six-gap-source-probe-v1",
              "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "note": "Transport diagnostics only. Never used to fabricate indicator values.",
              "items": {}}
    for key, (name, url) in TARGETS.items():
        result["items"][key] = probe(key, name, url, session)
        print("GAP_PROBE", key, result["items"][key].get("http_status", "ERR"),
              result["items"][key]["reason"])
    result["items"]["m06"]["api_token_configured"] = bool(os.environ.get("CME_FEDWATCH_BEARER"))
    result["items"]["s05"]["definition"] = "NYSE $MMFI, not S&P 500 percentage above MA50"
    result["items"]["m16"]["definition"] = "Conference Board LEI YoY, same release vintage"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(result["items"]) == 6
    print("Six-gap diagnostics saved:", OUT, "NO STATUS PROMOTIONS")

if __name__ == "__main__":
    main()

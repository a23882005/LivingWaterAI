"""Check the protected page and the below-cap regression in a mobile viewport."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def check(site):
    feed = json.loads((site / "V70_macro_latest.json").read_text())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 390, "height": 844})

        def serve(route):
            url = urlsplit(route.request.url)
            if url.netloc == "snapshot.invalid" and url.path in ("/index.html", "/V70_macro_latest.json"):
                route.fulfill(path=site / url.path[1:])
            else:
                route.abort()

        page.route("**/*", serve)
        page.goto("https://snapshot.invalid/index.html")
        page.wait_for_function("window.v703FeedDocument && window.v703ReloadFeed")
        page.evaluate("() => window.v703ReloadFeed()")
        page.wait_for_function("window.v703MacroSnapshot?.capNote")
        snapshot = page.evaluate("window.v703MacroSnapshot")
        note = snapshot["capNote"]
        assert note in page.locator("#macro-cap-text").inner_text()
        cap = feed["engineeringCap"]["cap"]
        if cap < 100:
            assert f"CAP {cap} 已生效" in note
        elif not feed["engineeringCap"]["missing"]:
            assert note == "未封頂"
        print("正式批次", feed["asOf"], note)
        scenarios = page.evaluate("""() => {
            const describe = window.v70Cap.describeCap;
            const caps = {cap:60, layers:{恐慌:60,危機:100,衰退:100},
                          reasons:{恐慌:['VIX'],危機:[],衰退:[]}, missing:[]};
            return [
                ...[53.1,60,74].map(raw => describe(caps,raw,Math.min(raw,60))),
                describe({...caps, cap:100},53.1,53.1),
                describe({...caps, cap:100, missing:['m01']},53.1,NaN),
                describe({...caps, missing:['m18']},53.1,NaN),
                describe({...caps, cap:55, layers:{恐慌:60,危機:55,衰退:55}},74,55)
            ];
        }""")
        expected = ["恐慌層 CAP 60 已生效。原始分數在上限內，最終仍為 53.1 分",
                    "CAP 60 已生效。原始分數在上限內，最終仍為 60.0 分",
                    "CAP 60 已生效。原始 74.0 分超過上限，最終採 60.0 分",
                    "未封頂", "封頂狀態待確認", "CAP 60 已生效。本期最終分數待確認",
                    "危機層、衰退層 CAP 55 已生效"]
        for actual, required in zip(scenarios, expected, strict=True):
            assert required in actual, actual
        print("封頂說明 7 個案例通過")
        browser.close()


if __name__ == "__main__":
    check(Path(sys.argv[1]))

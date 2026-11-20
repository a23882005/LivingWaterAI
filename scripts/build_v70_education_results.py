"""Render the fifteen-day chart, public indicators and scenario outputs in private CI."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

KEYS = "m01 m08 m05 m13 m17 m14 m18 m19 m20 m06_rate m06_inf m06_rstar m06_output_gap".split()


def build(site, template, output):
    feed = json.loads((site / "V70_macro_latest.json").read_text())
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        model = browser.new_page()
        model.route("https://**/*", lambda route: route.abort())
        model.goto((site / "index.html").resolve().as_uri())
        model.wait_for_function("window.v703FeedDocument && window.v703ReloadFeed")
        model.evaluate("() => window.v703ReloadFeed()")
        if model.evaluate("window.v703FeedDocument.asOf") != feed["asOf"]:
            raise ValueError("Model and education data dates differ")
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content(template.read_text())
        rows = page.locator("#edu-indicators tbody tr")
        if rows.count() != len(KEYS):
            raise ValueError("Education indicator template mismatch")
        indicators = []
        for index, key in enumerate(KEYS):
            item = feed["indicators"][key]
            unit = {"pp": " 個百分點", "USD bn": " 十億美元"}.get(item["unit"], item["unit"])
            if key == "m01":
                unit = " 個百分點"
            value = item.get("value")
            indicators.append({
                "key": key, "value": value, "unit": unit,
                "date": item["dataDate"], "carried": bool(item.get("carryForward")),
            })
            cells = rows.nth(index).locator("td")
            for cell, text in zip([cells.nth(0), cells.nth(1)], [
                "待更新" if value is None else f"{value:.6f}".rstrip("0").rstrip(".") + unit,
                item["dataDate"] + ("（沿用）" if item.get("carryForward") else "")
            ]):
                cell.evaluate("(e,t)=>e.textContent=t", text)
        scenarios = {}
        for life in model.locator("#family-life option").evaluate_all("xs=>xs.map(x=>x.value)"):
            model.select_option("#family-life", life)
            for style in model.locator("#family-style option").evaluate_all("xs=>xs.map(x=>x.value)"):
                model.select_option("#family-style", style)
                scenarios[life + "/" + style] = model.evaluate("""() => {
                    window.v703Recompute();
                    const v = window.v703Latest;
                    if (!window.v703CanPublishFormalAllocation() || !v || v.syntheticInputs)
                        return null;
                    if (v.lifeStage !== document.querySelector('#family-life').value ||
                        v.preference !== document.querySelector('#family-style').value)
                        throw Error('Scenario mismatch');
                    return {stock:v.totals.stock,bond:v.totals.bond,cash:v.totals.dryPowder};
                }""")
        if len(scenarios) != 40:
            raise ValueError("Expected forty education scenarios")
        output.mkdir(parents=True, exist_ok=True)
        # This intermediate is consumed by the public layout renderer. It contains only outputs.
        (output / "education-results.json").write_text(json.dumps({
            "asOf":feed["asOf"], "scenarios":scenarios,
            "indicators":rows.all_inner_texts(), "indicatorData":indicators
        },ensure_ascii=False),encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("site","template","output"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    build(args.site,args.template,args.output)

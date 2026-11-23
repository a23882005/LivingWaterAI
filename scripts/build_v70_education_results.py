"""Render the fifteen-day chart, public indicators and scenario outputs in private CI."""
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

from v70_cap.rules import evaluate, snapshot_inputs

KEYS = "m01 m08 m05 m13 m17 m14 m18 m19 m20 m06_rate m06_inf m06_rstar m06_output_gap".split()


ALERT_MESSAGES = {
    "normal": ("", "本期無特別警示。"),
    "yellow": ("黃牌", "市場波動值得留意。"),
    "orange": ("橘牌", "市場風險偏高。"),
    "red": ("紅牌", "市場風險警示已達最高級別。"),
    "unknown": ("", "本期資料待更新。"),
}


def render_market_alert(page, feed):
    level = evaluate(snapshot_inputs(feed))["level"]
    if feed.get("publication", {}).get("scoringAllowed") is not True:
        level = "unknown"
    label, message = ALERT_MESSAGES[level]
    page.locator("#education-alert").evaluate("""(section, [level, label, message]) => {
        section.dataset.level = level;
        const line = section.querySelector("p");
        line.textContent = message;
        if (label) {
            line.className = "alert-card";
            const badge = document.createElement("strong");
            badge.textContent = label;
            line.prepend(badge, " ");
        }
    }""", [level, label, message])
    return level


def build(site, template, output):
    feed = json.loads((site / "V70_macro_latest.json").read_text())
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        model = browser.new_page()
        def serve_snapshot(route):
            from urllib.parse import urlsplit
            url = urlsplit(route.request.url)
            if url.netloc == "snapshot.invalid" and url.path in ("/index.html", "/V70_macro_latest.json"):
                route.fulfill(path=site / url.path[1:])
            else:
                route.abort()
        model.route("**/*", serve_snapshot)
        model.goto("https://snapshot.invalid/index.html")
        model.wait_for_function("window.v703FeedDocument && window.v703ReloadFeed")
        model.evaluate("() => window.v703ReloadFeed()")
        if model.evaluate("window.v703FeedDocument.asOf") != feed["asOf"]:
            raise ValueError("Model and education data dates differ")
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        import re
        layout = re.sub(r"<script>(?:(?!</script>).)*</script>", "", template.read_text(), flags=re.S)
        page.set_content(layout)
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
        bars = page.locator("#macro-inputs > div")
        for i, key in enumerate(("m01","m08","m05")):
            score = model.locator("#sc_" + key).text_content()
            row = bars.nth(i)
            row.evaluate("""(node,args)=>{
                const [value,score]=args;
                node.querySelector('b').nextSibling.textContent='　'+value;
                node.lastChild.textContent=score;
                const marker=node.querySelector('i');
                const n=Number.parseFloat(score);
                marker.hidden=!Number.isFinite(n);
                if (!marker.hidden) marker.style.left=Math.max(0,Math.min(100,n*10))+'%';
            }""",[rows.nth(i).locator("td").first.text_content(),score])
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
                    return true;
                }""")
        if len(scenarios) != 40:
            raise ValueError("Expected forty education scenarios")
        alert_level = render_market_alert(page, feed)
        output.mkdir(parents=True, exist_ok=True)
        # This intermediate is consumed by the public layout renderer. It contains only outputs.
        (output / "education-results.json").write_text(json.dumps({
            "asOf":feed["asOf"], "scenarios":scenarios,
            "marketAlert": alert_level,
            "indicators":rows.all_inner_texts(), "indicatorData":indicators
        },ensure_ascii=False),encoding="utf-8")
        # Serialize the approved public layout after replacing its fixture script.
        page.locator("script:not([src])").evaluate_all("nodes=>nodes.forEach(n=>n.remove())")
        for ident in ("v703-rolling15", "v703-research-charts", "v703-wallstreet-observation"):
            source = model.locator("#" + ident)
            fragment = source.evaluate("""node => {
                const copy = node.cloneNode(true);
                copy.querySelectorAll('script,iframe,object,embed').forEach(n=>n.remove());
                for (const el of [copy,...copy.querySelectorAll('*')])
                    for (const attr of [...el.attributes])
                        if (attr.name.startsWith('on') || attr.name.startsWith('data-'))
                            el.removeAttribute(attr.name);
                return copy.innerHTML;
            }""")
            target = page.locator("#" + ident)
            # The education template owns the public headings and learning notes.
            copy_selectors = {
                "v703-rolling15": ["h3 + p", "p.r15-notice:not([id])"],
                "v703-wallstreet-observation": ["h3", "h3 + p"],
                "v703-research-charts": ["h2", "h2 + p"],
            }[ident]
            notes = [(selector, target.locator(selector).inner_text()) for selector in copy_selectors]
            page.locator("#" + ident).evaluate("(node,html)=>node.innerHTML=html", fragment)
            for selector, note in notes:
                target.locator(selector).evaluate("(e,t)=>e.textContent=t", note)
        research = page.locator("#v703-research-charts")
        research.locator("figcaption, th").evaluate_all("""nodes => nodes.forEach(n => {
            n.textContent = n.textContent.replaceAll('季度微分','較上季變化').replaceAll('微分','變化')
                .replaceAll('_pct','（%）').replaceAll('SP500','標普 500').replaceAll('_','｜');
        })""")
        points = model.locator("#r15-chart circle[data-r15-index]")
        details = points.evaluate_all("""nodes => nodes.map(node => {
            node.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            return document.getElementById('r15-point').textContent
                .replace('較前一交易日 NA｜NA｜缺前一交易日合格分數','缺少前一交易日分數，無法比較');
        })""")
        # Ship the engineering chart's drawing functions with public observations only.
        source = model.locator("script").evaluate_all(
            "nodes=>nodes.map(node=>node.textContent).find(code=>code.includes('function smoothSegments(coordinates)'))")
        draw = []
        for pattern in (r"^ const esc=.*;$", r"^ const numberFormat=.*;$", r"^ const fmt=.*;$",
                        r"^ function smoothSegments\(coordinates\)\{[\s\S]*?^ \}$",
                        r"^ function chart\(points\)\{[\s\S]*?^ \}$"):
            match = re.search(pattern, source, re.M)
            if not match:
                raise ValueError("Engineering trend chart drawing function missing")
            draw.append(match.group())
        observations = model.evaluate("""() => window.v703Rolling15.state.points.map(
            ({date, score, snapshotDateTaipei, kind}) => ({date, score, snapshotDateTaipei, kind}))""")
        if len(observations) != len(details):
            raise ValueError("Rolling chart observations and details differ")
        chart_data = json.dumps([observations, details], ensure_ascii=False).replace("<", "\\u003c")
        chart_script = "\n".join(draw) + "\nconst [observations,details]=" + chart_data + ";\n" + """
const svg=document.getElementById('r15-chart');
let lastWidth=0;
function redraw(){
 const width=svg.parentElement.clientWidth;
 if(!width || width===lastWidth)return;
 lastWidth=width;
 chart(observations);
 svg.querySelectorAll('circle[data-r15-index]').forEach(node=>{
    node.setAttribute('aria-label',details[Number(node.dataset.r15Index)]);
 });
}
redraw();
new ResizeObserver(redraw).observe(svg.parentElement);
"""
        stamp = datetime.fromisoformat(feed["asOf"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Missing time zone for education snapshot")
        local_time = stamp.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d %H:%M:%S")
        page.locator("#v703-update-banner").evaluate(
            "(node,stamp)=>node.textContent='資料更新（台灣時間）　'+stamp", local_time)
        for ident in ("bond-raw","bond-slider"):
            value = model.locator("#" + ident).input_value()
            page.locator("#" + ident).evaluate("(node,value)=>node.setAttribute('value',value)", value)
        width = model.locator("#macro-bar").evaluate("node=>node.style.width")
        page.locator("#macro-bar").evaluate("(node,width)=>node.style.width=width", width)
        for ident in ("bond-data-status","bond-nominal-yield", "bond-cpi-yoy", "bond-real-yield",
                      "bond-score-display", "macro-safety-val"):
            value = model.locator("#" + ident).text_content()
            page.locator("#" + ident).evaluate("(node,value)=>node.textContent=value", value)
        page.locator("#edu-indicators caption").evaluate(
            "(node,stamp)=>node.textContent='資料更新（台灣時間）　'+stamp", local_time)
        counter = model.locator("script").evaluate_all(
            "nodes=>nodes.map(n=>n.textContent).find(s=>s.includes('async function showViewCounts'))")
        if not counter:
            raise ValueError("Missing approved view counter")
        page.locator("#v70-view-counts").evaluate("(e)=>e.textContent='瀏覽統計載入中'")
        page.evaluate("""([scenarios,counter]) => {
            const data=document.createElement('script');
            data.type='application/json';
            data.id='education-scenarios';
            data.textContent=JSON.stringify(scenarios);
            document.body.append(data);
            const counts=document.createElement('script');
            counts.textContent=counter;
            document.body.append(counts);
        }""", [scenarios, counter])
        display = """const choices=JSON.parse(document.getElementById('education-scenarios').textContent);
const el=id=>document.getElementById(id);
const chart=el('r15-chart');
function showPoint(event){
 let point=event.target.closest('circle[aria-label]');
 if(!point && event.type==='click'){
  const matrix=chart.getScreenCTM();
  if(!matrix)return;
  const x=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()).x;
  const distance=node=>Math.abs(node.cx.baseVal.value-x);
  for(const node of chart.querySelectorAll('circle[aria-label]'))
   if(!point||distance(node)<distance(point))point=node;
 }
 if(point)el('r15-point').textContent=point.getAttribute('aria-label');
}
chart.addEventListener('click',showPoint);
chart.addEventListener('focusin',showPoint);
const lesson = el('learning-context');
function showAvailability(){
 if(!choices[el('family-life').value+'/'+el('family-style').value])
  lesson.textContent+=' 本期市場資料待更新。';
}
for(const id of ['family-life','family-style'])el(id).addEventListener('change',showAvailability);
showAvailability();"""
        lesson_source = re.search(r'<script id="public-lesson-script">(.*?)</script>', template.read_text(), re.S).group(1)
        page.evaluate("(code)=>{const s=document.createElement('script');s.textContent=code;document.body.append(s)}",
                      "(() => {" + lesson_source + "})();")
        observations = []
        for key, label in (("m08", "美國十年期實質殖利率"), ("m05", "核心物價年增率")):
            item = next(row for row in indicators if row["key"] == key)
            value = item["value"]
            reading = "待更新" if value is None else f"{value:.6f}".rstrip("0").rstrip(".") + item["unit"]
            observations.append(f"{label} {reading}（{item['date']}{'，沿用' if item['carried'] else ''}）")
        page.locator("#public-market-reading").evaluate("(e,t)=>e.textContent=t", "本期資料｜" + "；".join(observations))
        page.evaluate("(code)=>{const s=document.createElement('script');s.textContent=code;document.body.append(s)}", display)
        page.evaluate("(code)=>{const s=document.createElement('script');s.textContent=code;document.body.append(s)}",
                      "(() => {" + chart_script + "})();")
        if page.locator("#education-sources li").count() != 13:
            raise ValueError("Expected thirteen attributions")
        if page.locator("#edu-indicators tbody tr").count() != 13:
            raise ValueError("Public homepage must display thirteen indicator rows")
        html = page.content()
        check = browser.new_page()
        check.route("**/*", lambda route: route.abort())
        check.set_content(html)
        for width in (390, 844, 360):
            check.set_viewport_size({"width": width, "height": 844})
            check.wait_for_function("""() => {
                const svg=document.getElementById('r15-chart'), box=svg.viewBox.baseVal;
                const width=svg.parentElement.clientWidth, compact=width<520;
                return box.width===width && box.height===(compact?230:285) &&
                    [...svg.querySelectorAll('.r15-date')].every(node=>
                        (node.getAttribute('transform') || '').includes('rotate(-58)')===compact);
            }""")
        for point, detail in zip(check.locator("#r15-chart circle[aria-label]").all(), details):
            point.dispatch_event("click")
            if check.locator("#r15-point").text_content() != detail or "體質分" not in detail:
                raise ValueError("Published education chart point did not show its observation")
        for pair, result in scenarios.items():
            life, style = pair.split("/")
            check.select_option("#family-life", life)
            check.select_option("#family-style", style)
            lesson = check.locator("#learning-context").inner_text()
            if not lesson.startswith("情境練習｜") or ("本期市場資料待更新" in lesson) != (result is None):
                raise ValueError(f"Education scenario mismatch: {pair}")
        label, message = ALERT_MESSAGES[alert_level]
        assert check.locator("#education-alert-message").inner_text().split() == (label + " " + message).split()
        assert check.locator("#v703-result article").count() == 9
        assert check.locator("#total-stock,#allocation-list,#strategic-stock").count() == 0
        for ident in ("bond-nominal-yield", "bond-cpi-yoy", "bond-real-yield", "bond-score-display"):
            if check.locator("#" + ident).text_content() != model.locator("#" + ident).text_content():
                raise ValueError("Published education bond field differs from engineering: " + ident)
        if model.evaluate("typeof window.v703BondInputsQualified") != "boolean":
            raise ValueError("Education rendering requires the engineering bond calculation")
        if any(text in check.locator("body").inner_text() for text in ("Rule Owner=V70", "22項計分輸入")):
            raise ValueError("Engineering header in education homepage")
        (output / "index.html").write_text(html, encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("site","template","output"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    build(args.site,args.template,args.output)

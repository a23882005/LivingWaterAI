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
                    return {
                        stock:v.totals.stock, bond:v.totals.bond, cash:v.totals.dryPowder,
                        strategic:{stock:v.strategic.stock,bond:v.strategic.bond},
                        classes:Object.fromEntries(
                            ['S1','S2','S3','B1','B2','B3','B4','C0'].map(key => {
                                const value = v.percentages[key];
                                if (!Number.isFinite(value)) throw Error('Missing allocation: '+key);
                                return [key,value];
                            })
                        )
                    };
                }""")
        if len(scenarios) != 40:
            raise ValueError("Expected forty education scenarios")
        output.mkdir(parents=True, exist_ok=True)
        # This intermediate is consumed by the public layout renderer. It contains only outputs.
        (output / "education-results.json").write_text(json.dumps({
            "asOf":feed["asOf"], "scenarios":scenarios,
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
            page.locator("#" + ident).evaluate("(node,html)=>node.innerHTML=html", fragment)
        for ident in ("family-data-status","family-news","v703-update-banner","v703-data-state"):
            page.locator("#" + ident).evaluate("(node)=>node.textContent=''")
        page.locator("#v703-update-banner").evaluate(
            "(node,stamp)=>node.textContent='資料時間　'+stamp", feed["asOf"])
        for ident in ("bond-raw","bond-slider"):
            value = model.locator("#" + ident).input_value()
            page.locator("#" + ident).evaluate("(node,value)=>node.setAttribute('value',value)", value)
        width = model.locator("#macro-bar").evaluate("node=>node.style.width")
        page.locator("#macro-bar").evaluate("(node,width)=>node.style.width=width", width)
        for ident in ("bond-data-status","bond-nominal-yield", "bond-cpi-yoy", "bond-real-yield",
                      "bond-score-display", "macro-safety-val", "macro-zone-text"):
            value = model.locator("#" + ident).text_content()
            page.locator("#" + ident).evaluate("(node,value)=>node.textContent=value", value)
        page.locator("#edu-indicators caption").evaluate(
            "(node,stamp)=>node.textContent='資料時間　'+stamp", feed["asOf"])
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
const labels={S1:'分散核心股票',S2:'成長集中股票',S3:'高風險股票',B1:'超短公債',
 B2:'中短天期投資級公司債',B3:'長天期美國公債',B4:'信用敏感公司債',C0:'待投入資金'};
function display(){
 const v=choices[el('family-life').value+'/'+el('family-style').value];
 for(const key of ['stock','bond','cash']) el('total-'+key).textContent=v?v[key]+'%':'—';
 for(const key of ['stock','bond']) el('strategic-'+key).value=v?v.strategic[key]:'';
 for(const id of ['allocation-list','v703-result']){
  const target=el(id);target.replaceChildren();
  if(!v){target.textContent='本期暫停正式配置';continue;}
  for(const [key,label] of Object.entries(labels)){
   const row=document.createElement('div');row.textContent=label+'　'+v.classes[key]+'%';target.append(row);
  }
 }
}
for(const id of ['family-life','family-style'])el(id).addEventListener('change',display);
display();"""
        page.evaluate("(code)=>{const s=document.createElement('script');s.textContent=code;document.body.append(s)}", display)
        if page.locator("#education-sources li").count() != 13:
            raise ValueError("Expected thirteen attributions")
        (output / "index.html").write_text(page.content(), encoding="utf-8")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("site","template","output"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    build(args.site,args.template,args.output)

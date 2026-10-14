"""Build a fail-closed daily V70.3 web package from 09h observations and 10h s05."""
import argparse,datetime as dt,json,shutil
from pathlib import Path
def build(macro,mmfi,html,dest):
    m=json.loads(Path(macro).read_text(encoding="utf-8"))
    items=dict(m.get("items",{}))
    if "s03" not in items and "m07" in items: items["s03"]=dict(items["m07"],id="s03")
    if Path(mmfi).exists():
        supplement=json.loads(Path(mmfi).read_text(encoding="utf-8"))
        record=supplement.get("s05",supplement.get("items",{}).get("s05",supplement))
        if isinstance(record,dict): items["s05"]=record
    now=dt.datetime.now(dt.timezone.utc)
    problems=[]
    if len(items)!=24: problems.append(f"expected 24 transport fields, got {len(items)}")
    if "s03" in items and "m07" in items and items["s03"].get("value")!=items["m07"].get("value"):problems.append("s03/m07 mismatch")
    for key,item in items.items():
        if item.get("status")!="OK" or item.get("value") is None:problems.append(f"{key}: {item.get('status')} / missing")
        raw=item.get("observation_date")
        if not raw:problems.append(f"{key}: no observation_date")
        else:
            try:
                obs=dt.date.fromisoformat(raw[:10])
                if obs>now.date():problems.append(f"{key}: future observation")
            except ValueError:problems.append(f"{key}: invalid date")
    if "s05" in items:
        s=items["s05"]
        if s.get("value") is not None and not 0<=float(s["value"])<=100:problems.append("s05 must be percentage 0..100")
    site=Path(dest);site.mkdir(parents=True,exist_ok=True)
    output={"schema":"V70.3/daily-verified-feed-v1","generated_utc":now.isoformat(),"ready":not problems,"problems":problems,"items":items}
    (site/"V70_macro_latest.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    shutil.copyfile(html,site/"index.html")
    (site/"QA.json").write_text(json.dumps({"ready":not problems,"problems":problems},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"ready":not problems,"problems":problems},ensure_ascii=False))
    return not problems
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--macro",default="data/22_macro_verification.json")
    p.add_argument("--mmfi",default="data/s05_mmfi_verified.json")
    p.add_argument("--html",default="系統工程/總經V70/V70-3-10.html")
    p.add_argument("--out",default="build/site")
    a=p.parse_args()
    if not build(a.macro,a.mmfi,a.html,a.out):raise SystemExit("QUALITY_GATE_BLOCKED: preserve current published site")
